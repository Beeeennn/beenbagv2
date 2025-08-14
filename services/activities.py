from utils.game_helpers import gid_from_ctx,ensure_player,give_items,get_items,lb_inc
import discord
from constants import TIER_ORDER, DROP_TABLES, WHEAT_DROP, AXEWOOD
from services import achievements
import asyncio
import random
async def farm(pool, ctx):
    """Farm for wheat, better hoe means more wheat."""
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    async with pool.acquire() as conn:
        await ensure_player(conn,ctx.author.id,guild_id)

        # 1) Fetch all usable pickaxes
        pickaxes = await conn.fetch(
            """
            SELECT tier, uses_left
              FROM tools
             WHERE user_id = $1
               AND guild_id = $2
               AND tool_name = 'hoe'
               AND uses_left > 0
            """,
            user_id, guild_id
        )
        # 2) Determine your highest tier hoe
        owned_tiers = {r["tier"] for r in pickaxes}
        best_tier = None
        for tier in reversed(TIER_ORDER):
            if tier in owned_tiers:
                best_tier = tier
                break

        # 3) Consume 1 use on that hoe
        if best_tier:
            await conn.execute(
                """
                UPDATE tools
                SET uses_left = uses_left - 1
                WHERE user_id = $1
                AND guild_id = $2
                AND tool_name = 'hoe'
                AND tier = $3
                AND uses_left > 0
                """,
                user_id, guild_id, best_tier
            )

        # 4) Pick a drop according to your tier’s table
        avg = WHEAT_DROP[best_tier]
        drop = random.randint(avg-1,avg+1)

        await give_items(user_id,"wheat",drop,"resource",False,conn,guild_id)
        # fetch new total
        total = await get_items(conn,user_id,"wheat",guild_id)

    # Prepare the final result text
    if best_tier:
        result = (
            f"{ctx.author.mention} farmed with a **{best_tier.title()} Hoe** and found "
            f"🌾 **{drop} Wheat**! You now have **{total} Wheat**."
        )
    else:
        result = (
            f"{ctx.author.mention} farmed by **hand** and found "
            f"🌾 **{drop} Wheat**! You now have **{total} Wheat**."
        )

    # --- 2) Play the animation ---
    frames = [
        "⛏️ farming... [⛏️🌾🌾🌾🌾]",
        "⛏️ farming... [🌿⛏️🌾🌾🌾]",
        "⛏️ farming... [🌿🌿⛏️🌾🌾]",
        "⛏️ farming... [🌿🌿🌿⛏️🌾]",
        "⛏️ farming... [🌿🌿🌿🌿⛏️]",
        "⛏️ farming... [🌿🌿🌿🌿🌿]",
    ]
    msg = await ctx.send(f"{ctx.author.mention} {frames[0]}")
    for frame in frames[1:]:
        await asyncio.sleep(0.5)
        await msg.edit(content=f"{ctx.author.mention} {frame}")
    await achievements.try_grant(pool,ctx,user_id,"first_farm")
    # --- 3) Show the result ---
    await asyncio.sleep(0.5)
    await msg.edit(content=result)


async def chop(pool, ctx):
    """Gain 1 wood every 60s."""
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    async with pool.acquire() as conn:
        await ensure_player(conn,ctx.author.id,guild_id)
        # 1) Fetch all usable pickaxes
        axes = await conn.fetch(
            """
            SELECT tier, uses_left
              FROM tools
             WHERE user_id = $1
             AND guild_id = $2
               AND tool_name = 'axe'
               AND uses_left > 0
            """,
            user_id, guild_id
        )
        owned_tiers = {r["tier"] for r in axes}
        best_tier = None
        for tier in reversed(TIER_ORDER):
            if tier in owned_tiers:
                best_tier = tier
                break
        
        num = AXEWOOD[best_tier]
        # grant 1 wood
        await give_items(user_id,"wood",num,"resource",False,conn,guild_id)
        await conn.execute(
            """
            UPDATE tools
               SET uses_left = uses_left - 1
             WHERE user_id = $1
             AND guild_id = $2
               AND tool_name = 'axe'
               AND tier = $3
               AND uses_left > 0
            """,
            user_id, guild_id, best_tier
        )
        # fetch the updated wood count
        wood = await get_items(conn,user_id,"wood",guild_id)
        await lb_inc(conn,"wood_collected",user_id,guild_id,num)
        await achievements.try_grant(pool,ctx,user_id,"first_chop")
        if wood >= 20:
            await achievements.try_grant(pool,ctx,user_id,"20_wood")
    await ctx.send(
        f"{ctx.author.mention} swung their axe and chopped 🌳 **{num} wood**! "
        f"You now have **{wood}** wood."
    )

async def mine(pool, ctx):
    """Mine for cobblestone or ores; better pickaxes yield rarer drops."""
    import asyncio, random
    from pathlib import Path
    import discord

    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)

    async with pool.acquire() as conn:
        await ensure_player(conn, ctx.author.id, guild_id)

        # 1) Fetch all usable pickaxes
        pickaxes = await conn.fetch(
            """
            SELECT tier, uses_left
              FROM tools
             WHERE user_id = $1
               AND guild_id = $2
               AND tool_name = 'pickaxe'
               AND uses_left > 0
            """,
            user_id, guild_id
        )

        if not pickaxes:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"❌ You need a pickaxe with at least 1 use to mine! Craft one with `{ctx.clean_prefix}craft pickaxe wood`."
            )

        # 2) Determine your highest tier pickaxe
        owned_tiers = {r["tier"] for r in pickaxes}
        best_tier = None
        for tier in reversed(TIER_ORDER):
            if tier in owned_tiers:
                best_tier = tier
                break

        if best_tier is None:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("❌ You have no usable pickaxe.")

        # Uses before (to handle rare cases where RETURNING isn't available)
        uses_before = next((r["uses_left"] for r in pickaxes if r["tier"] == best_tier), 0)

        # 3) Consume 1 use on that pickaxe and get remaining uses
        uses_after = await conn.fetchval(
            """
            UPDATE tools
               SET uses_left = uses_left - 1
             WHERE user_id = $1
               AND guild_id = $2
               AND tool_name = 'pickaxe'
               AND tier = $3
               AND uses_left > 0
         RETURNING uses_left
            """,
            user_id, guild_id, best_tier
        )

        # Did it break on this swing?
        broke = (uses_after == 0) if uses_after is not None else (uses_before == 1)

        # 4) Pick a drop according to your tier’s table
        table = DROP_TABLES[best_tier]
        ores = list(table.keys())
        weights = [table[ore]["chance"] for ore in ores]

        chosen_ore = random.choices(ores, weights=weights, k=1)[0]
        drop_info = table[chosen_ore]
        amount = random.randint(drop_info["min"], drop_info["max"])

        # 5) Grant the drop
        await give_items(user_id, chosen_ore, amount, "resource", False, conn, guild_id)

        # fetch new total
        total = await get_items(conn, user_id, chosen_ore, guild_id)

    # Emojis + color helpers
    emojis = {"cobblestone": "🪨", "iron": "🔩", "gold": "🪙", "diamond": "💎"}
    emoji = emojis.get(chosen_ore, "⛏️")
    tier_colors = {
        "wood": 0x8B5A2B,
        "stone": 0x808080,
        "iron": 0xC0C0C0,
        "gold": 0xFFD700,
        "diamond": 0x00FFFF
    }
    color = tier_colors.get(best_tier, 0x5865F2)  # fallback to blurple

    # Grant achievements
    if best_tier == "wood" and chosen_ore == "diamond":
        await achievements.try_grant(pool, ctx, user_id, "dia_with_wood")
    await achievements.try_grant(pool, ctx, user_id, "first_mine")

    # Build the final result embed
    def build_result_embed() -> discord.Embed:
        e = discord.Embed(
            title="⛏️ Mining Result",
            description=f"{ctx.author.mention} mined with a **{best_tier.title()} Pickaxe**!",
            color=color
        )
        e.add_field(name="Drop", value=f"{emoji} **{chosen_ore}**", inline=True)
        e.add_field(name="Amount", value=f"**{amount}**", inline=True)
        e.add_field(name="Total Owned", value=f"**{total} {chosen_ore}**", inline=True)
        if broke:
            e.set_footer(text="Your pickaxe broke!")
        return e

    # --- Play the GIF animation from assets/mining/<best_pick>/<drop>.gif ---
    def gif_path_for(bt: str, dr: str) -> Path:
        base = Path("assets/gifs/mining")
        bt = (bt or "default").lower()
        dr = (dr or "default").lower()
        return base / bt / f"{dr}.gif"

    path = gif_path_for(best_tier, chosen_ore)
    if not path.exists():
        path = gif_path_for(best_tier, "default")
        if not path.exists():
            path = Path("assets/gifs/mining/default/default.gif")

    msg = None
    try:
        if path.exists():
            file = discord.File(path, filename="mine.gif")

            # Initial "swing" embed with GIF
            broke_text = " and it broke" if broke else ""
            pre = discord.Embed(
                description=f"{ctx.author.mention} swings their **{best_tier.title()} Pickaxe**...{broke_text}",
                color=color
            )
            pre.set_image(url="attachment://mine.gif")

            msg = await ctx.send(embed=pre, file=file)
            await asyncio.sleep(2.0)

            # Edit to the final RESULT EMBED (keeps the attachment)
            await msg.edit(embed=build_result_embed())
        else:
            # No GIF: just send the result embed
            await ctx.send(embed=build_result_embed())

    except Exception:
        # Fallback: still send the result embed
        try:
            if msg:
                await msg.edit(embed=build_result_embed())
            else:
                await ctx.send(embed=build_result_embed())
        except Exception:
            # Absolute last resort
            await ctx.send(
                f"{ctx.author.mention} mined with a **{best_tier.title()} Pickaxe** and found "
                f"{emoji} **{amount} {chosen_ore}**! You now have **{total} {chosen_ore}**."
            )
