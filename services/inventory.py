from utils.game_helpers import gid_from_ctx,resolve_member
import discord

async def inv(pool, ctx, who: str = None):
    """Show your inventory."""
    # Resolve member
    guild_id = gid_from_ctx(ctx)
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")

    user_id = member.id

    # Fetch inventory
    async with pool.acquire() as conn:
        # 1. Items from new table
        items = await conn.fetch("""
            SELECT item_name, category, quantity
            FROM player_items
            WHERE player_id = $1 AND guild_id = $2 AND quantity > 0
        """, user_id, guild_id)

        # 2. Tools
        tools = await conn.fetch("""
            SELECT tool_name, tier, uses_left
            FROM tools
            WHERE user_id = $1 AND guild_id = $2 AND uses_left > 0
        """, user_id,guild_id)

    # Empty check
    if not items and not tools:
        return await ctx.send(f"{member.mention}, your inventory is empty.")

    # Build embed
    embed = discord.Embed(
        title=f"{member.display_name}'s Inventory",
        color=discord.Color.green()
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)

    # Organize items by category
    from collections import defaultdict
    grouped = defaultdict(list)
    for row in items:
        grouped[row["category"]].append((row["item_name"], row["quantity"]))

    # Display resources, crops, mobs, etc.
    emojis = {
        "wood": "🌳", "cobblestone": "🪨", "iron": "🔩", "gold": "🪙", "diamond": "💎",
        "wheat": "🌾",
        "emeralds": "💠"
    }

    for category, entries in grouped.items():
        lines = []
        for name, qty in entries:
            emoji = emojis.get(name.lower(), "📦")
            label = name.replace("_", " ").title()
            lines.append(f"{emoji} **{label}**: {qty}")
        embed.add_field(
            name=category.capitalize(),
            value="\n".join(lines),
            inline=False
        )

    # Tools section
    if tools:
        tool_lines = []
        for record in tools:
            name = record["tool_name"].replace("_", " ").title()
            tier = record["tier"].title()
            uses = record["uses_left"]
            emoji = {
                "Axe": "🪓",
                "Pickaxe": "⛏️",
                "Hoe": "🌱",
                "Fishing Rod": "🎣",
                "Sword": "⚔️"
            }.get(name, "🛠️")
            tool_lines.append(f"{emoji} **{tier} {name}** — {uses} use{'s' if uses != 1 else ''}")
        embed.add_field(
            name="Tools",
            value="\n".join(tool_lines),
            inline=False
        )
    embed.set_footer(text="Use !shop to spend your emeralds & resources")
    await ctx.send(embed=embed)


