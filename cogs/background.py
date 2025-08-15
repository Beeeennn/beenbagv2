# cogs/backgrounds.py
from __future__ import annotations

import os
import math
import discord
from typing import Optional, Callable, List, Dict, Any
from discord.ext import commands

from services.monetization import fetch_user_entitlement, consume_entitlement

EXPBG_DIR = "assets/others/expbg"


def _bg_path(filename: str) -> str:
    return os.path.join(EXPBG_DIR, filename)


async def _get_sku_info(conn, sku_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        "SELECT filename FROM background_skus WHERE sku_id = $1",
        sku_id,
    )
    return (row and row["filename"]) or None


# ----------------------- Store Browser View -----------------------

class BackgroundStoreView(discord.ui.View):
    """
    Paginated store with purchase buttons (premium buttons when supported).
    `purchase_button_factory` must be a callable that returns a discord.ui.Item given a SKU id.
    """

    def __init__(
        self,
        items: List[Dict[str, Any]],
        author_id: int,
        purchase_button_factory: Callable[[str], discord.ui.Item],
        page_size: int = 8,
    ):
        super().__init__(timeout=120)
        self.items = items  # [{sku_id, filename, display_name}]
        self.author_id = author_id
        self.page_size = page_size
        self.page = 0
        self._purchase_button_factory = purchase_button_factory
        self._rebuild()

    def _slice(self) -> List[Dict[str, Any]]:
        start = self.page * self.page_size
        end = start + self.page_size
        return self.items[start:end]

    def _rebuild(self) -> None:
        # Clear existing components
        for child in list(self.children):
            self.remove_item(child)

        # Purchase buttons (no labels for premium; labels for link fallback)
        page_items = self._slice()
        for it in page_items:
            self.add_item(self._purchase_button_factory(it["sku_id"]))

        # Navigation
        total_pages = max(1, math.ceil(len(self.items) / self.page_size))
        prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)

        async def _prev(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.defer()
            if self.page > 0:
                self.page -= 1
                self._rebuild()
                await interaction.response.edit_message(embed=self._embed(), view=self)
            else:
                await interaction.response.defer()

        async def _next(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.defer()
            total_pages_local = max(1, math.ceil(len(self.items) / self.page_size))
            if self.page < total_pages_local - 1:
                self.page += 1
                self._rebuild()
                await interaction.response.edit_message(embed=self._embed(), view=self)
            else:
                await interaction.response.defer()

        prev_btn.callback = _prev
        next_btn.callback = _next
        self.add_item(prev_btn)
        self.add_item(next_btn)

    def _embed(self) -> discord.Embed:
        total = len(self.items)
        total_pages = max(1, math.ceil(total / self.page_size))
        page_items = self._slice()

        desc_lines = []
        for it in page_items:
            name = it["display_name"]
            fname = it["filename"]
            desc_lines.append(f"• **{name}**  (`{fname}`)")
        if not desc_lines:
            desc_lines.append("_No backgrounds available._")

        em = discord.Embed(
            title="🖼 Background Store",
            description="\n".join(desc_lines),
            color=discord.Color.blurple(),
        )
        em.set_footer(text=f"Page {self.page + 1}/{total_pages} • {total} total")
        return em


# ----------------------------- Cog -----------------------------

class Backgrounds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="bg", invoke_without_command=True)
    async def bg_group(self, ctx: commands.Context):
        """Background commands. Try: !bg buy / !bg claim <sku> / !bg set <filename>"""
        await ctx.send("Use `!bg buy`, `!bg claim <sku>`, or `!bg set <filename>`")

    @bg_group.command(name="buy")
    async def bg_buy(self, ctx: commands.Context):
        """Open the background store with purchase buttons for each SKU (paginated)."""
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT sku_id,
                       filename,
                       COALESCE(display_name,
                                INITCAP(REPLACE(REGEXP_REPLACE(filename, '\\.png$', ''), '_', ' '))
                               ) AS display_name
                  FROM background_skus
                 ORDER BY display_name
                """
            )

        if not rows:
            return await ctx.send("❌ No backgrounds are configured in the store yet.")

        items = [
            {"sku_id": r["sku_id"], "filename": r["filename"], "display_name": r["display_name"]}
            for r in rows
        ]

        # Build a factory that creates a premium button when possible, else a link button.
        app_dir_url = os.getenv("APP_DIRECTORY_URL") or f"https://discord.com/application-directory/{ctx.bot.user.id}"

        def purchase_button_factory(sku_id: str) -> discord.ui.Item:
            try:
                # Premium purchase button: DO NOT pass label when using sku_id
                style = getattr(discord.ButtonStyle, "premium")
                return discord.ui.Button(style=style, sku_id=sku_id)  # type: ignore[arg-type]
            except Exception:
                # Fallback link (older libs/clients)
                return discord.ui.Button(label="Open Store", url=app_dir_url)

        view = BackgroundStoreView(
            items=items,
            author_id=ctx.author.id,
            purchase_button_factory=purchase_button_factory,
            page_size=8,
        )
        await ctx.send(embed=view._embed(), view=view)

    @bg_group.command(name="claim")
    async def claim_background(self, ctx: commands.Context, sku_id: Optional[str] = None):
        """Claim a purchased background.
        - With sku_id: claim just that one.
        - Without args: scan all SKUs and claim what you own.
        """
        user_id = ctx.author.id
        guild_id = ctx.guild.id

        async with self.bot.db_pool.acquire() as conn:
            if sku_id:
                rows = await conn.fetch(
                    "SELECT sku_id, filename, consumable FROM background_skus WHERE sku_id = $1",
                    sku_id,
                )
                if not rows:
                    return await ctx.send("❌ That SKU isn’t in the store.")
            else:
                rows = await conn.fetch(
                    "SELECT sku_id, filename, consumable FROM background_skus ORDER BY display_name NULLS LAST, filename"
                )
                if not rows:
                    return await ctx.send("❌ No backgrounds are configured yet.")

        claimed, missing = [], []

        # DEV bypass: unlock without talking to Discord
        dev_mode = os.getenv("DEV_MODE") == "1" or os.getenv("ENV") == "dev"
        if dev_mode:
            async with self.bot.db_pool.acquire() as conn:
                for r in rows:
                    await conn.execute(
                        """
                        INSERT INTO user_backgrounds (user_id, guild_id, background_name)
                        VALUES ($1, $2, $3)
                        ON CONFLICT DO NOTHING
                        """,
                        user_id, guild_id, r["filename"]
                    )
                    claimed.append(f"{r['filename']} [DEV]")
            msg = "✅ Claimed:\n" + "\n".join(f"• {c}" for c in claimed)
            return await ctx.send(msg)

        # Real entitlement flow
        for r in rows:
            sku = r["sku_id"]
            filename = r["filename"]
            consumable = bool(r["consumable"])

            # Check entitlement
            try:
                ent = await fetch_user_entitlement(user_id, sku)
            except Exception as e:
                missing.append(f"{filename} (API error: {e})")
                continue

            if not ent:
                missing.append(filename)
                continue

            # Optionally consume consumables
            if consumable and not ent.get("consumed"):
                try:
                    await consume_entitlement(ent["id"])
                except Exception as e:
                    missing.append(f"{filename} (consume failed: {e})")
                    continue

            # Grant ownership
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_backgrounds (user_id, guild_id, background_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    user_id, guild_id, filename
                )
            claimed.append(filename)

        # Respond
        if sku_id:
            if claimed:
                return await ctx.send(f"✅ Claimed: **{claimed[0]}**")
            return await ctx.send(f"❌ No entitlement found for `{sku_id}`.")

        parts = []
        if claimed:
            parts.append("✅ Claimed:\n" + "\n".join(f"• {c}" for c in claimed))
        if missing:
            parts.append("⚠️ Not owned / failed:\n" + "\n".join(f"• {m}" for m in missing))
        await ctx.send("\n\n".join(parts) if parts else "Nothing to claim.")

    @bg_group.command(name="set")
    async def bg_set(self, ctx: commands.Context, name: str):
        """Equip a background you own. Use the exact filename (e.g., neon_wave.png or neon_wave)."""
        filename = name if name.lower().endswith(".png") else f"{name}.png"
        if not os.path.exists(_bg_path(filename)):
            return await ctx.send("❌ That background file doesn’t exist on the server.")

        async with self.bot.db_pool.acquire() as conn:
            owned = await conn.fetchval(
                """
                SELECT 1 FROM user_backgrounds
                 WHERE user_id=$1 AND guild_id=$2 AND background_name=$3
                """,
                ctx.author.id, ctx.guild.id, filename
            )
            if not owned:
                return await ctx.send("❌ You don't own this background. Buy & claim it first.")

            await conn.execute(
                """
                INSERT INTO user_settings (user_id, guild_id, selected_background)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET selected_background = EXCLUDED.selected_background
                """,
                ctx.author.id, ctx.guild.id, filename
            )

        await ctx.send(f"✅ Equipped **{filename}** for your rank card.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Backgrounds(bot))
