import discord
import random
import asyncio
from constants import DISABLED_SHOP_ITEMS,MOBS
from utils.game_helpers import gid_from_ctx,give_mob,sucsac,gain_exp,give_items,giverole, get_items,take_items
from datetime import datetime,timedelta,timezone
import math
import discord
from discord.ext import commands
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import asyncpg
from utils.game_helpers import get_items, take_items, give_items, gid_from_ctx  # you already have these
from constants import DISABLED_SHOP_ITEMS

# ---------- DB helpers ----------
async def _fetch_pages(conn) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT page_name
          FROM shop_items
         WHERE NOT (LOWER(name) = ANY($1::text[]))
         ORDER BY 1
        """,
        list(DISABLED_SET)
    )
    return [r["page_name"] for r in rows] or ["General"]

async def _fetch_items_for_page(conn, page_name: str):
    rows = await conn.fetch(
        """
        SELECT i.item_id, i.name, i.description, i.purchase_limit
          FROM shop_items i
         WHERE i.page_name = $1
           AND NOT (LOWER(i.name) = ANY($2::text[]))
         ORDER BY i.item_id
        """,
        page_name, list(DISABLED_SET)
    )
    return rows

async def _fetch_costs(conn, item_id: int) -> List[asyncpg.Record]:
    # zero or more cost lines (currency_item, amount)
    rows = await conn.fetch(
        """
        SELECT currency_item, amount
          FROM shop_item_costs
         WHERE item_id = $1
         ORDER BY currency_item
        """,
        item_id
    )
    return rows

async def _fallback_emerald_cost(conn, item_id: int):
    val = await conn.fetchval("SELECT price_emeralds FROM shop_items WHERE item_id = $1", item_id)
    return val

def _format_costs(cost_rows: List[asyncpg.Record], fallback_emeralds: int | None) -> str:
    parts = []
    for r in cost_rows:
        parts.append(f"{r['amount']} × {r['currency_item']}")
    if not parts and fallback_emeralds and fallback_emeralds > 0:
        parts.append(f"{fallback_emeralds} × emeralds")
    return " + ".join(parts) if parts else "free"

# ---------- Embed builder ----------
def _build_shop_embed(ctx, page_name: str, items: List[asyncpg.Record], start: int, costs_map: Dict[int, str]) -> discord.Embed:
    color = discord.Color.gold()
    e = discord.Embed(title=f"🏪 Shop — {page_name}", color=color)
    if not items:
        e.description = "No items for sale on this page."
        return e

    slice_ = items[start:start+5]
    for r in slice_:
        item_id = r["item_id"]
        name = r["name"]
        desc = r["description"] or ""
        limit = r["purchase_limit"]
        limit_text = "unlimited" if limit is None else f"{limit} per 24 h"
        cost_text = costs_map.get(item_id, "free")
        e.add_field(
            name=f"#{item_id} — {name}",
            value=f"{desc}\n**Cost:** {cost_text}\n**Limit:** {limit_text}\nUse: `!buy {item_id} [qty]`",
            inline=False
        )

    total = len(items)
    a = start + 1
    b = min(start + 5, total)
    e.set_footer(text=f"Showing {a}-{b} of {total} • Use the dropdown to switch pages • Only you can use the controls.")
    return e

# ---------- View (dropdown + arrows) ----------
class ShopView(discord.ui.View):
    def __init__(self, ctx: commands.Context, pool, pages: List[str], initial_page: str):
        super().__init__(timeout=90)
        self.ctx = ctx
        self.pool = pool
        self.pages = pages
        self.page = initial_page
        self.start = 0  # index into items list
        self.items_cache: Dict[str, List[asyncpg.Record]] = {}
        self.costs_cache: Dict[int, str] = {}
        # build select options
        self.page_select.options = [
            discord.SelectOption(label=p, value=p, default=(p == initial_page)) for p in pages
        ]

    async def _load(self):
        async with self.pool.acquire() as con:
            if self.page not in self.items_cache:
                rows = await _fetch_items_for_page(con, self.page)
                self.items_cache[self.page] = rows
                # pre-compute costs for rows on this page
                for r in rows:
                    costs = await _fetch_costs(con, r["item_id"])
                    fallback = await _fallback_emerald_cost(con, r["item_id"])
                    self.costs_cache[r["item_id"]] = _format_costs(costs, fallback)

    async def _render(self, interaction=None):
        await self._load()
        items = self.items_cache.get(self.page, [])
        self.start = max(0, min(self.start, max(0, len(items) - 1)))
        # enable/disable buttons
        self.prev_button.disabled = (self.start <= 0)
        self.next_button.disabled = (self.start + 5 >= len(items))
        embed = _build_shop_embed(self.ctx, self.page, items, self.start, self.costs_cache)
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await self.ctx.send(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # only command invoker can use the controls
        return interaction.user.id == self.ctx.author.id

    @discord.ui.select(placeholder="Select a shop page…", min_values=1, max_values=1, row=0)
    async def page_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.page = select.values[0]
        self.start = 0
        await self._render(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.start = max(0, self.start - 5)
        await self._render(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.start = self.start + 5
        await self._render(interaction)

# ---------- Public entry ----------
async def shop(pool, ctx):
    async with pool.acquire() as con:
        pages = await _fetch_pages(con)

    view = ShopView(ctx, pool, pages, pages[0])
    await view._render()  # sends the first embed + view

async def _lookup_item(conn, raw: str):
    # Accept numeric ID or case-insensitive name
    if raw.isdigit():
        return await conn.fetchrow(
            "SELECT item_id, name, purchase_limit FROM shop_items WHERE item_id = $1",
            int(raw)
        )
    return await conn.fetchrow(
        "SELECT item_id, name, purchase_limit FROM shop_items WHERE LOWER(name) = $1",
        raw.lower()
    )

async def _get_all_costs(conn, item_id: int) -> Dict[str, int]:
    rows = await _fetch_costs(conn, item_id)
    if rows:
        return {r["currency_item"]: r["amount"] for r in rows}
    # fallback to emeralds if costs table empty
    emer = await _fallback_emerald_cost(conn, item_id)
    return {"emeralds": emer or 0}
DISABLED_SET = {s.lower() for s in DISABLED_SHOP_ITEMS}
async def buy(pool, ctx, args):
    """
    Purchase one or more of an item.
    Now supports: !buy <ID> [qty]  or  !buy <item name> [qty]
    Costs can be any combination of items defined in shop_item_costs.
    """
    if not args:
        return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}buy <item id|name> [quantity]`")

    # Parse quantity (last token) if int
    try:
        qty = int(args[-1])
        name_tokens = args[:-1]
    except ValueError:
        qty = 1
        name_tokens = args

    if qty < 1:
        return await ctx.send("❌ Quantity must be at least 1.")

    raw_key = " ".join(name_tokens).strip()
    if not raw_key:
        return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}buy <item id|name> [quantity]`")

    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        # Lookup (ID or name), skip disabled
        item = await _lookup_item(conn, raw_key)
        if not item:
            return await ctx.send(f"❌ No shop item matching **{raw_key}**.")
        name_lower = (await conn.fetchval("SELECT LOWER(name) FROM shop_items WHERE item_id=$1", item["item_id"])) or ""
        if name_lower in DISABLED_SET:
            return await ctx.send("❌ That item is not available right now.")

        item_id = item["item_id"]
        display_name = await conn.fetchval("SELECT name FROM shop_items WHERE item_id = $1", item_id)
        limit = item["purchase_limit"]  # None = unlimited

        # Enforce daily limit
        if limit is not None:
            since = now - timedelta(hours=24)
            bought = await conn.fetchval(
                """
                SELECT COUNT(*) FROM purchase_history
                 WHERE user_id = $1 AND guild_id=$2 AND item_id = $3 AND purchased_at > $4
                """,
                user_id, guild_id, item_id, since
            )
            if bought + qty > limit:
                return await ctx.send(f"❌ You can only buy {limit}/{limit} **{display_name}** per 24 h.")

        # Fetch costs (multi-currency)
        costs = await _get_all_costs(conn, item_id)  # dict: item_name -> unit_amount
        if not costs:
            costs = {"emeralds": 0}

        # Check balances
        deficits = []
        for currency_item, unit_amt in costs.items():
            need = unit_amt * qty
            if need <= 0:
                continue
            have = await get_items(conn, user_id, currency_item, guild_id)
            if have < need:
                deficits.append((currency_item, need, have))

        if deficits:
            msg_lines = ["❌ You don't have enough for that:"]
            for it, need, have in deficits:
                msg_lines.append(f"• {it}: need **{need}**, have **{have}**")
            return await ctx.send("\n".join(msg_lines))

        # Deduct costs (all or nothing) & log purchases
        async with conn.transaction():
            for currency_item, unit_amt in costs.items():
                need = unit_amt * qty
                if need > 0:
                    await take_items(user_id, currency_item, need, conn, guild_id)

            # history rows
            for _ in range(qty):
                await conn.execute(
                    "INSERT INTO purchase_history (user_id, item_id, guild_id) VALUES ($1,$2,$3)",
                    user_id, item_id, guild_id
                )
            # cumulative
            await conn.execute(
                """
                INSERT INTO shop_purchases (user_id,item_id,quantity,guild_id)
                VALUES ($1,$2,$3,$4)
                ON CONFLICT (user_id,item_id,guild_id)
                DO UPDATE SET quantity = shop_purchases.quantity + EXCLUDED.quantity
                """,
                user_id, item_id, qty, guild_id
            )

        # Deliver effect/content
        # You can keep your special-cases here. Example:
        if display_name.lower() == "exp bottle":
            await ctx.send(f"✅ Bought **{qty}× Exp Bottle**! Say `!use Exp Bottle` to use them (uses all at once).")
            async with pool.acquire() as con2:
                await give_items(user_id, "Exp Bottle", qty, "items", True, con2, guild_id)

        elif display_name.lower() == "boss mob ticket":
            await ctx.send(
                f"✅ You bought **{qty} Boss Mob Ticket{'s' if qty!=1 else ''}**! "
                f"Use `{ctx.clean_prefix}use Ticket <mob name>` before stream to redeem."
            )
            async with pool.acquire() as con2:
                await give_items(user_id, "Boss Mob Ticket", qty, "items", True, con2, guild_id)

        elif display_name.lower() == "mystery animal":
            await ctx.send(
                f"✅ You bought **{qty} Mystery Mob Pack{'s' if qty!=1 else ''}**! "
                f"Use `{ctx.clean_prefix}use Mob Pack` to redeem."
            )
            async with pool.acquire() as con2:
                await give_items(user_id, "Mystery Mob Pack", qty, "items", True, con2, guild_id)

        elif display_name.lower() == "rich role":
            await giverole(ctx, 1396839599921168585, ctx.author)
            await ctx.send(f"✅ You bought **RICH role**! Be careful not to buy it again.")

        else:
            # Generic “item” delivery into inventory
            async with pool.acquire() as con2:
                await give_items(user_id, display_name, qty, "items", True, con2, guild_id)
            await ctx.send(f"✅ You bought **{qty}× {display_name}**!")

async def buy(pool, ctx, args):
    """
    Purchase one or more of an item.
    Usage:
      !buy <item name> [quantity]
    Examples:
      !buy Exp Bottle 5
      !buy exp 100
    """
    if not args:
        return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}buy <item name> [quantity]`")

    # 1) Parse quantity if last arg is an integer
    try:
        qty = int(args[-1])
        name_parts = args[:-1]
    except ValueError:
        qty = 1
        name_parts = args

    if qty < 1:
        return await ctx.send("❌ Quantity must be at least 1.")

    raw_name = " ".join(name_parts).strip().lower()

    # allow "exp" shortcut for "Exp Bottle"
    if raw_name in ("exp", "experience"):
        lookup_name = "exp bottle"
    elif raw_name in ("pack", "mob pack", "mystery mob pack"):
        lookup_name = "mystery animal"
    else:
        lookup_name = raw_name

    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    async with pool.acquire() as conn:
        # 2) Look up the item
        item = await conn.fetchrow(
            """
            SELECT item_id, name, price_emeralds, purchase_limit
              FROM shop_items
             WHERE LOWER(name) = $1
            """,
            lookup_name
        )
        if not item:
            return await ctx.send(f"❌ No shop item named **{raw_name}**.")

        item_id      = item["item_id"]
        display_name = item["name"]
        cost_each    = item["price_emeralds"]
        limit        = item["purchase_limit"]  # None = unlimited

        total_cost = cost_each * qty

        # 3) Check emerald balance
        have = await get_items(conn,user_id,"emeralds",guild_id)

        if have < total_cost:
            return await ctx.send(
                f"❌ You need {total_cost} 💠 but only have {have}."
            )

        # 4) Enforce daily limit (for Exp Bottle only, or any limited item)
        if limit is not None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            bought = await conn.fetchval(
                """
                SELECT COUNT(*) FROM purchase_history
                 WHERE user_id = $1
                   AND guild_id = $4
                   AND item_id = $2
                   AND purchased_at > $3
                """,
                user_id, item_id, since, guild_id
            )
            if bought + qty > limit:
                return await ctx.send(
                    f"❌ You can only buy {limit}/{limit} **{display_name}** per 24 h."
                )

        # 5) Deduct emeralds
        await take_items(user_id,"emeralds",total_cost,conn,guild_id)

        # 6) Log each purchase for history
        for _ in range(qty):
            await conn.execute(
                "INSERT INTO purchase_history (user_id, item_id, guild_id) VALUES ($1,$2,$3)",
                user_id, item_id, guild_id
            )
        # 7) Update your cumulative purchases (e.g. boss tickets)
        await conn.execute("""
            INSERT INTO shop_purchases (user_id,item_id,quantity,guild_id)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id,item_id,guild_id) DO UPDATE
              SET quantity = shop_purchases.quantity + $3
        """, user_id, item_id, qty,guild_id)

    # 8) Grant the effect
    async with pool.acquire() as conn:
        if display_name == "Exp Bottle":
            await ctx.send(f"✅ Spent {total_cost} 💠 for an Exp Bottle with **{qty} EXP**! Say **!use Exp Bottle** to use them, you must use them all at once though")
            await give_items(user_id,"Exp Bottle",qty,"items",True,conn,guild_id)

        elif display_name == "Boss Mob Ticket":
            await ctx.send(
                f"✅ You bought **{qty} Boss Mob Ticket{'s' if qty!=1 else ''}**! "
                f"Use `{ctx.clean_prefix}use Ticket <mob name>` before stream to redeem, this allows you to say the name of the mob during the stream to spawn it, don't worry about typos, it will still be valid."
            )
            await give_items(user_id,"Boss Mob Ticket",qty,"items",True,conn,guild_id)

        elif display_name == "Mystery Animal":
            await ctx.send(
                f"✅ You bought **{qty} Mystery Mob Pack{'s' if qty!=1 else ''}**! "
                f"Use `{ctx.clean_prefix}use Mob Pack` to redeem"
            )
            await give_items(user_id,"Mystery Mob Pack",qty,"items",True,conn,guild_id)

        elif display_name == "RICH Role":
            await giverole(ctx,1396839599921168585,ctx.author)
            await ctx.send(f"✅ You bought **RICH role** for {total_cost} 💠!, you must be super rich. Be careful not to buy it again")
        else:
            await ctx.send(f"✅ You bought **{qty}× {display_name}** for {total_cost} 💠!")