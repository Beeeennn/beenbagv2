from datetime import datetime, timedelta
from constants import CRAFT_RECIPES, TIER_ORDER
from utils.game_helpers import ensure_player, get_items, take_items, give_items, gid_from_ctx

async def craft(ctx, pool, tool: str, tier: str | None):
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)

    # Normalize
    t = tool.replace(" ", "_").lower()
    if t in ("fishing_rod", "fishingrod", "fishing", "rod"):
        t = "fishing_rod"

    if t == "totem":
        cost = 2
        async with pool.acquire() as conn:
            await ensure_player(conn, user_id, guild_id)
            if await get_items(conn, user_id, "diamond", guild_id) < cost:
                await ctx.send(f"❌ You need {cost} diamonds to craft that.")
                return
            await give_items(user_id, "totem", 1, "items", False, conn, guild_id)
            await take_items(user_id, "diamond", cost, conn, guild_id)
        await ctx.send("🔨 You crafted a **totem**. One extra life in a stronghold!")
        return

    if tier is None:
        await ctx.send("❌ You must specify a tier for that tool.")
        return

    key = (t, tier.lower())
    if key not in CRAFT_RECIPES:
        await ctx.send(f"❌ Invalid recipe. Try `{ctx.clean_prefix}craft pickaxe iron`.")
        return

    wood_cost, ore_cost, ore_col, uses = CRAFT_RECIPES[key]

    async with pool.acquire() as conn:
        await ensure_player(conn, user_id, guild_id)
        row = await conn.fetchrow(
            """SELECT
                 MAX(CASE WHEN item_name = 'wood' THEN quantity ELSE 0 END) AS wood,
                 MAX(CASE WHEN item_name = $2 THEN quantity ELSE 0 END) AS ore
               FROM player_items
               WHERE player_id=$1 AND guild_id=$3 AND item_name IN ('wood',$2)""",
            user_id, ore_col, guild_id
        )
        wood_have, ore_have = row["wood"], row["ore"]
        if wood_have < wood_cost or (ore_col and ore_have < ore_cost):
            need = [f"**{wood_cost} wood**"]
            if ore_col: need.append(f"**{ore_cost} {ore_col}**")
            await ctx.send(f"❌ You need {' and '.join(need)} to craft that.")
            return

        await take_items(user_id, "wood", wood_cost, conn, guild_id)
        if ore_col:
            await take_items(user_id, ore_col, ore_cost, conn, guild_id)

        await conn.execute(
            """INSERT INTO tools (user_id, guild_id, tool_name, tier, uses_left)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (user_id,guild_id,tool_name,tier)
               DO UPDATE SET uses_left = tools.uses_left + EXCLUDED.uses_left""",
            user_id, guild_id, t, tier, uses
        )

    await ctx.send(f"🔨 You crafted a **{tier.title()} {t.replace('_',' ').title()}** with {uses} uses!")

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