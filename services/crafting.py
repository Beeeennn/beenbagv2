from datetime import datetime, timedelta
from constants import CRAFT_RECIPES, TIER_ORDER
from utils.game_helpers import ensure_player, get_items, take_items, give_items, gid_from_ctx
from services import achievements,barn

# services/crafting.py

async def craft(ctx, pool, tool: str, tier: str | None):
    """
    Craft a tool. Costs come from CRAFT_RECIPES.
    Uses get_items() so missing rows -> 0, avoiding None comparisons.
    """
    from utils.game_helpers import gid_from_ctx, ensure_player, get_items, take_items, give_items
    from services import achievements

    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)

    # Normalize tool name
    t = tool.replace(" ", "_").lower()
    if t in ("fishing_rod", "fishingrod", "fishing", "rod"):
        t = "fishing_rod"

    # Special case: totem (no tier)
    if t == "totem":
        cost = 2
        async with pool.acquire() as conn:
            await ensure_player(conn, user_id, guild_id)
            await barn.ensure_player_and_barn(conn, user_id, guild_id)
            diamonds = await get_items(conn, user_id, "diamond", guild_id)
            if diamonds < cost:
                return await ctx.send(f"❌ You need {cost} diamonds to craft that.")
            await give_items(user_id, "totem", 1, "items", False, conn, guild_id)
            await take_items(user_id, "diamond", cost, conn, guild_id)
        return await ctx.send("🔨 You crafted a **totem**. One extra life in a stronghold!")

    if tier is None:
        return await ctx.send("❌ You must specify a tier for that tool.")

    key = (t, tier.lower())
    if key not in CRAFT_RECIPES:
        return await ctx.send(f"❌ Invalid recipe. Try `{ctx.clean_prefix}craft pickaxe iron`.")

    wood_cost, ore_cost, ore_col, uses = CRAFT_RECIPES[key]

    async with pool.acquire() as conn:
        await ensure_player(conn, user_id, guild_id)
        await barn.ensure_player_and_barn(conn, user_id, guild_id)

        # Robust counts (0 if user has none)
        wood_have = await get_items(conn, user_id, "wood", guild_id)
        ore_have  = await get_items(conn, user_id, ore_col, guild_id) if ore_col else 0

        # Check affordability
        need_bits = []
        if wood_have < wood_cost:
            need_bits.append(f"**{wood_cost} wood**")
        if ore_col and ore_have < ore_cost:
            need_bits.append(f"**{ore_cost} {ore_col}**")
        if need_bits:
            return await ctx.send(f"❌ You need {' and '.join(need_bits)} to craft that.")

        # Deduct materials
        await take_items(user_id, "wood", wood_cost, conn, guild_id)
        if ore_col:
            await take_items(user_id, ore_col, ore_cost, conn, guild_id)

        # Give/stack the tool
        await conn.execute(
            """
            INSERT INTO tools (user_id, guild_id, tool_name, tier, uses_left)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (guild_id, user_id, tool_name, tier)
            DO UPDATE SET uses_left = tools.uses_left + EXCLUDED.uses_left
            """,
            user_id, guild_id, t, tier.lower(), uses
        )

    # Achievements
    if t == "pickaxe":
        await achievements.try_grant(pool, ctx, user_id, "craft_pick")
    if t == "hoe" and tier.lower() == "diamond":
        await achievements.try_grant(pool, ctx, user_id, "dia_hoe")

    await ctx.send(f"🔨 You crafted a **{tier.title()} {t.replace('_', ' ').title()}** with {uses} uses!")


async def recipe(ctx, args):
    if not args:
        return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}recipe <tool> [tier]`")

    # Build tool name from all but last arg; tier is last arg if 2+ args
    if len(args) == 1:
        tool_raw = args[0]
        tier = None
    else:
        tool_raw = "_".join(args[:-1])
        tier = args[-1].lower()

    tool = tool_raw.replace(" ", "_").lower()

    # If it’s the fishing rod, force tier to “wood”
    if tool in ("fishing_rod", "fishingrod", "fishing","rod"):
        tool = "fishing_rod"

    if tier is None:
        return await ctx.send("❌ You must specify a tier for that tool.")

    key = (tool, tier)
    if key not in CRAFT_RECIPES:
        return await ctx.send(f"❌ Invalid recipe. Try `{ctx.clean_prefix}recipe pickaxe iron` or `{ctx.clean_prefix}recipe totem`.")

    wood_cost, ore_cost, ore_col, uses = CRAFT_RECIPES[key]
    need = [f"**{wood_cost} wood**"]
    if ore_col:
        need.append(f"**{ore_cost} {ore_col}**")
    return await ctx.send(f"You need { ' and '.join(need) } to craft a {tool}.")