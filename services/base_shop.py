import discord, io, asyncio, asyncpg
from discord.ext import commands
from typing import List, Dict, Any, Tuple

# ===== Helpers to fetch data =====

async def _base_fetch_categories(conn) -> List[str]:
    rows = await conn.fetch("""
        SELECT DISTINCT category
          FROM base_shop_items
         WHERE NOT disabled
         ORDER BY category
    """)
    return [r["category"] for r in rows] or ["General"]

async def _base_fetch_items_for_category(conn, category: str) -> List[asyncpg.Record]:
    rows = await conn.fetch("""
        SELECT item_id, name, description, purchase_limit, sort_order
          FROM base_shop_items
         WHERE category = $1 AND NOT disabled
         ORDER BY sort_order, item_id
    """, category)
    return rows

async def _base_fetch_owned_counts(conn, guild_id: int, user_id: int, item_ids: List[int]) -> Dict[int, int]:
    if not item_ids:
        return {}
    rows = await conn.fetch("""
        SELECT item_id, COUNT(*)::int AS owned
          FROM base_inventory
         WHERE guild_id = $1 AND user_id = $2 AND item_id = ANY($3::bigint[])
         GROUP BY item_id
    """, guild_id, user_id, item_ids)
    return {r["item_id"]: r["owned"] for r in rows}

async def _base_fetch_costs_bulk(conn, item_ids: List[int]) -> Dict[int, List[Tuple[str,int]]]:
    if not item_ids:
        return {}
    rows = await conn.fetch("""
        SELECT item_id, currency_item, amount
          FROM base_shop_item_costs
         WHERE item_id = ANY($1::bigint[])
         ORDER BY item_id, currency_item
    """, item_ids)
    costs: Dict[int, List[Tuple[str,int]]] = {}
    for r in rows:
        costs.setdefault(r["item_id"], []).append((r["currency_item"], r["amount"]))
    return costs

def _format_cost_list(costs_for_item: List[Tuple[str,int]]) -> str:
    if not costs_for_item:
        return "free"
    return " + ".join(f"{amt} × {name}" for (name, amt) in costs_for_item)

# ===== Embed/view builder =====

def _build_category_embed(ctx: commands.Context, category: str,
                          items: List[asyncpg.Record],
                          owned_map: Dict[int,int],
                          costs_map: Dict[int, List[Tuple[str,int]]],
                          start: int) -> discord.Embed:
    e = discord.Embed(title=f"🏠 Base Shop — {category}", color=discord.Color.blurple())
    if not items:
        e.description = "No items in this category."
        return e

    chunk = items[start:start+10]  # show up to 10 per page
    for r in chunk:
        item_id = r["item_id"]
        name    = r["name"]
        desc    = (r["description"] or "").strip()
        limit   = r["purchase_limit"]
        owned   = owned_map.get(item_id, 0)
        limit_text = "unlimited" if limit is None else f"{limit} / 24h"
        price_text = _format_cost_list(costs_map.get(item_id, []))
        body = []
        if desc:
            body.append(desc)
        body.append(f"**Price:** {price_text}")
        body.append(f"**You own:** {owned}")
        body.append(f"**Limit:** {limit_text}")
        body.append(f"Buy: `{ctx.clean_prefix}base buy {item_id}`")
        e.add_field(name=f"#{item_id} — {name}", value="\n".join(body), inline=False)

    total = len(items)
    a = start + 1
    b = min(start + 10, total)
    e.set_footer(text=f"Showing {a}-{b} of {total} • Use the controls below • Only you can use them.")
    return e

class BaseShopView(discord.ui.View):
    def __init__(self, ctx, pool, guild_id, user_id, categories, initial_cat):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pool = pool
        self.guild_id = guild_id
        self.user_id = user_id
        self.categories = categories
        self.category = initial_cat
        self.start = 0
        self.items_cache = {}
        self.owned_cache = {}
        self.costs_cache = {}
        self.message: discord.Message | None = None
        self._lock = asyncio.Lock()

        self.category_select.options = [
            discord.SelectOption(label=c, value=c, default=(c == initial_cat))
            for c in categories
        ]

    async def on_timeout(self):
        # disable controls when view times out
        for child in self.children:
            child.disabled = True
        try:
            # edit the message if we still have it
            await self.message.edit(view=self)
        except Exception:
            pass


    async def _load(self):
        async with self.pool.acquire() as con:
            if self.category not in self.items_cache:
                rows = await _base_fetch_items_for_category(con, self.category)
                self.items_cache[self.category] = rows
                ids = [r["item_id"] for r in rows]
                owned = await _base_fetch_owned_counts(con, self.guild_id, self.user_id, ids)
                costs = await _base_fetch_costs_bulk(con, ids)
                self.owned_cache[self.category] = owned
                self.costs_cache[self.category] = costs

    async def _render_first(self):
        """Send the initial message and remember it so we can edit later."""
        await self._load()
        items = self.items_cache.get(self.category, [])
        embed = _build_category_embed(
            self.ctx, self.category,
            items,
            self.owned_cache.get(self.category, {}),
            self.costs_cache.get(self.category, {}),
            self.start
        )
        # send once, store the message
        self.message = await self.ctx.send(embed=embed, view=self)

    async def _render_update(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()  # use defer(), not defer_update()
            except Exception:
                # if we already acked or token expired, ignore
                pass

        await self._load()
        items = self.items_cache.get(self.category, [])
        self.start = max(0, min(self.start, max(0, len(items) - 1)))
        self.prev_btn.disabled = (self.start <= 0)
        self.next_btn.disabled = (self.start + 10 >= len(items))

        embed = _build_category_embed(
            self.ctx, self.category, items,
            self.owned_cache.get(self.category, {}),
            self.costs_cache.get(self.category, {}),
            self.start
        )

        if self.message:
            await self.message.edit(embed=embed, view=self)
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only the invoker can press controls (flip to True if you want public controls)
        return interaction.user.id == self.ctx.author.id

    @discord.ui.select(placeholder="Pick a category…", min_values=1, max_values=1, row=0)
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        async with self._lock:
            self.category = select.values[0]
            self.start = 0
            for o in self.category_select.options:
                o.default = (o.value == self.category)
            await self._render_update(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, _):
        async with self._lock:
            self.start = max(0, self.start - 10)
            await self._render_update(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        async with self._lock:
            self.start = self.start + 10
            await self._render_update(interaction)

# ===== Public entry point =====

async def base_shop_run(pool, ctx: commands.Context):
    guild_id = ctx.guild.id
    user_id = ctx.author.id
    async with pool.acquire() as con:
        categories = await _base_fetch_categories(con)
    view = BaseShopView(ctx, pool, guild_id, user_id, categories, categories[0])
    await view._render_first()
