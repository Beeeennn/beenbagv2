from typing import List, Optional, Dict, Tuple
import os
import discord
from discord import ui
from discord.ext import commands
from services import progression,exp_display
from constants import VALID_METRICS  # e.g. {"mobs_caught":"Mobs Caught", ...}

PAGE_SIZE = 10


EMERALD_ITEM_NAME = "emeralds"  # change to "emeralds" if that’s your row name

PAGE_SIZE = 10

async def fetch_lb(conn, *, metric: str, scope: str, guild_id: Optional[int], offset: int, limit: int) -> Tuple[List[dict], int]:
    """
    scope: 'guild' or 'global'
    returns (rows, total)
    rows: list of dicts with keys: user_id, value
    """

    # --- Special metric: Emeralds (from player_items) ---
    if metric == "emeralds":
        if scope == "guild" and guild_id is not None:
            rows = await conn.fetch(
                """
                SELECT player_id AS user_id, SUM(quantity)::bigint AS value
                FROM player_items
                WHERE guild_id = $1
                  AND LOWER(item_name) = LOWER($2)
                GROUP BY player_id
                ORDER BY value DESC, player_id
                OFFSET $3 LIMIT $4
                """,
                guild_id, EMERALD_ITEM_NAME, offset, limit
            )
            total = await conn.fetchval(
                """
                SELECT COUNT(*) FROM (
                  SELECT player_id
                  FROM player_items
                  WHERE guild_id = $1
                    AND LOWER(item_name) = LOWER($2)
                  GROUP BY player_id
                ) t
                """,
                guild_id, EMERALD_ITEM_NAME
            )
        else:
            # Global: sum across all guilds by player_id
            rows = await conn.fetch(
                """
                SELECT player_id AS user_id, SUM(quantity)::bigint AS value
                FROM player_items
                WHERE LOWER(item_name) = LOWER($1)
                GROUP BY player_id
                ORDER BY value DESC, player_id
                OFFSET $2 LIMIT $3
                """,
                EMERALD_ITEM_NAME, offset, limit
            )
            total = await conn.fetchval(
                """
                SELECT COUNT(*) FROM (
                  SELECT player_id
                  FROM player_items
                  WHERE LOWER(item_name) = LOWER($1)
                  GROUP BY player_id
                ) t
                """,
                EMERALD_ITEM_NAME
            )
        return [dict(r) for r in rows], int(total or 0)

    # --- Special metric: Experience (from accountinfo.overallexp) ---
    if metric == "experience":
        if scope == "guild" and guild_id is not None:
            rows = await conn.fetch(
                """
                SELECT discord_id AS user_id, MAX(experience)::bigint AS value
                FROM accountinfo
                WHERE guild_id = $1
                GROUP BY discord_id
                ORDER BY value DESC, discord_id
                OFFSET $2 LIMIT $3
                """,
                guild_id, offset, limit
            )
            total = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT discord_id)
                FROM accountinfo
                WHERE guild_id = $1
                """,
                guild_id
            )
        else:
            # Global: sum overallexp across all guilds by user
            rows = await conn.fetch(
                """
                SELECT discord_id AS user_id, SUM(overallexp)::bigint AS value
                FROM accountinfo
                GROUP BY discord_id
                ORDER BY value DESC, discord_id
                OFFSET $1 LIMIT $2
                """,
                offset, limit
            )
            total = await conn.fetchval(
                "SELECT COUNT(DISTINCT discord_id) FROM accountinfo"
            )
        return [dict(r) for r in rows], int(total or 0)

    # --- Default: lb_counters (uses 0 as the sentinel for global) ---
    wanted_gid = guild_id if (scope == "guild" and guild_id is not None) else 0

    rows = await conn.fetch(
        """
        SELECT user_id, value
        FROM lb_counters
        WHERE metric = $1
          AND guild_id = $2::bigint
        ORDER BY value DESC, user_id
        OFFSET $3 LIMIT $4
        """,
        metric, wanted_gid, offset, limit
    )

    total = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM lb_counters
        WHERE metric = $1
          AND guild_id = $2::bigint
        """,
        metric, wanted_gid
    )
    return [dict(r) for r in rows], int(total or 0)



def metric_options(current: str) -> List[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=label,
            value=key,
            default=(key == current)
        )
        for key, label in VALID_METRICS.items()
    ]


class LBMetricSelect(ui.Select):
    def __init__(self, view: "LBView"):
        super().__init__(placeholder="Choose leaderboard…",
                         options=metric_options(view.metric), row=0)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        new_metric = self.values[0]
        self.view_ref.metric = new_metric
        self.view_ref.page = 0

        # reflect the new selection in the UI
        for opt in self.options:
            opt.default = (opt.value == new_metric)

        await self.view_ref.refresh(interaction)



class LBScopeSelect(ui.Select):
    def __init__(self, view: "LBView", has_guild: bool):
        opts = [discord.SelectOption(label="Global", value="global",
                                     default=(view.scope == "global"))]
        if has_guild:
            opts.insert(0, discord.SelectOption(label="This server", value="guild",
                                                default=(view.scope == "guild")))
        super().__init__(placeholder="Scope…", options=opts, row=1)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        new_scope = self.values[0]
        self.view_ref.scope = new_scope
        self.view_ref.page = 0

        # reflect the new selection in the UI
        for opt in self.options:
            opt.default = (opt.value == new_scope)

        await self.view_ref.refresh(interaction)


class LBView(ui.View):
    def __init__(self, ctx: commands.Context, *, metric: str = "mobs_caught", scope: str = "guild"):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.metric = metric if metric in VALID_METRICS else next(iter(VALID_METRICS.keys()))
        self.scope = scope if ctx.guild else "global"
        self.page = 0

        self.add_item(LBMetricSelect(self))
        self.add_item(LBScopeSelect(self, has_guild=ctx.guild is not None))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only the command invoker can use the controls
        return interaction.user and interaction.user.id == self.ctx.author.id

    async def build_embed(self) -> Tuple[discord.Embed, int]:
        offset = self.page * PAGE_SIZE
        gid = self.ctx.guild.id if (self.scope == "guild" and self.ctx.guild) else None

        async with self.ctx.bot.db_pool.acquire() as conn:
            rows, total = await fetch_lb(
                conn,
                metric=self.metric, scope=self.scope, guild_id=gid,
                offset=offset, limit=PAGE_SIZE
            )

        title = f"Leaderboard • {VALID_METRICS[self.metric]}"
        desc = "This server" if gid else "Global"

        e = discord.Embed(title=title, description=desc, color=discord.Color.blurple())

        if not rows:
            e.add_field(name="No entries", value="No data yet.", inline=False)
            e.set_footer(text="Page 1/1 • 0 entries")
            return e, total

        lines = []
        start_rank = offset + 1
        for i, r in enumerate(rows, start=start_rank):
            uid = r["user_id"]; val = r["value"]
            display = f"<@{uid}>"
            if self.ctx.guild:
                m = self.ctx.guild.get_member(uid)
                if m:
                    display = m.display_name
            lines.append(f"**{i}.** {display} — **{val}**")

        e.add_field(name="Top", value="\n".join(lines), inline=False)

        max_page = (total - 1) // PAGE_SIZE if total else 0
        e.set_footer(text=f"Page {self.page + 1}/{max_page + 1} • {total} entries")
        return e, total

    async def refresh(self, interaction: discord.Interaction, hard: bool = False):
        embed, total = await self.build_embed()
        max_page = (total - 1) // PAGE_SIZE if total else 0
        if self.page > max_page:
            self.page = max_page
            embed, total = await self.build_embed()

        # keep buttons in sync with page bounds
        for child in self.children:
            if isinstance(child, ui.Button):
                if child.label == "Prev":
                    child.disabled = (self.page <= 0)
                elif child.label == "Next":
                    child.disabled = (self.page >= max_page)

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

    # --- Buttons ---
    @ui.button(label="Prev", style=discord.ButtonStyle.secondary, row=2)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            self.page -= 1
        await self.refresh(interaction)

    @ui.button(label="Next", style=discord.ButtonStyle.secondary, row=2)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page += 1
        await self.refresh(interaction)

    @ui.button(label="Refresh", style=discord.ButtonStyle.primary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.refresh(interaction, hard=True)


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="lb", aliases=["leaderboard"])
    async def lb(self, ctx: commands.Context, metric: Optional[str] = None):
        """
        Open the leaderboard picker. Optionally seed with a metric, e.g. !lb mobs_caught
        """
        chosen = (metric or next(iter(VALID_METRICS.keys()))).lower()
        if chosen not in VALID_METRICS:
            chosen = next(iter(VALID_METRICS.keys()))

        view = LBView(ctx, metric=chosen, scope="guild")
        embed, _ = await view.build_embed()

        # disable Prev initially if needed
        for child in view.children:
            if isinstance(child, ui.Button) and child.label == "Prev":
                child.disabled = True

        await ctx.send(embed=embed, view=view)
    @commands.command(name="exp", aliases=["experience", "level", "lvl", "rank"])
    async def exp_cmd(self,ctx, *, who: str = None):
        await exp_display.rank_cmd(self.bot.db_pool, ctx, who)

    @commands.command()
    async def setbackground(self, ctx, name: str):
        filename = f"{name}.png"
        path = os.path.join("assets", "others", "expbg", filename)

        if not os.path.exists(path):
            return await ctx.send("❌ That background doesn't exist.")

        async with self.bot.db_pool.acquire() as conn:
            # Ensure owned
            owned = await conn.fetchval(
                "SELECT 1 FROM user_backgrounds WHERE user_id=$1 AND guild_id=$2 AND background_name=$3",
                ctx.author.id, ctx.guild.id, filename
            )
            if not owned:
                return await ctx.send("❌ You don't own this background.")

            await conn.execute(
                """
                INSERT INTO user_settings (user_id, guild_id, selected_background)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET selected_background = EXCLUDED.selected_background
                """,
                ctx.author.id, ctx.guild.id, filename
            )

        await ctx.send(f"✅ Your background is now set to **{name}**.")

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))