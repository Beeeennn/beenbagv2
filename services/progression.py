
from utils.game_helpers import gid_from_ctx,resolve_member,get_level_from_exp
import discord
from constants import LEVEL_EXP


async def exp_cmd(pool, ctx, who: str = None):
    """Show your current level and progress toward the next level."""
    # Resolve who → Member (or fallback to author)
    guild_id = gid_from_ctx(ctx)
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")  # or "Member not found."

    # Now you’ve got a real Member with .id, .display_name, etc.
    user_id = member.id

    # 1) Fetch their total exp from accountinfo
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT experience FROM accountinfo WHERE discord_id = $1 AND guild_id = $2",
            user_id,guild_id
        )
    total_exp = row["experience"] if row else 0

    # 2) Compute current & next levels
    current_level = get_level_from_exp(total_exp)
    max_level     = max(LEVEL_EXP.keys())

    if current_level < max_level:
        next_level = current_level + 1
        req_current = LEVEL_EXP.get(current_level, 0)
        req_next    = LEVEL_EXP[next_level]
        exp_into    = total_exp - req_current
        exp_needed  = req_next - total_exp
        # progress percentage
        pct = int(exp_into / (req_next - req_current) * 100)
    else:
        next_level = None

    # 3) Build an embed
    embed = discord.Embed(
        title=f"{member.display_name}'s Progress",
        color=discord.Color.gold()
    )
    embed.add_field(name="🎖️ Level", value=str(current_level), inline=True)
    embed.add_field(name="💯 Total EXP", value=str(total_exp), inline=True)

    if next_level:
        embed.add_field(
            name=f"➡️ EXP to Level {next_level}",
            value=f"{exp_needed} EXP ({pct}% there)",
            inline=False
        )
    else:
        embed.add_field(
            name="🏆 Max Level",
            value="You have reached the highest level!",
            inline=False
        )

    await ctx.send(embed=embed)

async def leaderboard(pool, ctx,bot):
    """Show the top 10 users by overall EXP, plus your own rank."""
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)

    async with pool.acquire() as conn:
        # 1) Top 10 overall EXP
        top_rows = await conn.fetch(
            """
            SELECT discord_id, overallexp
              FROM accountinfo
              WHERE guild_id = $1
             ORDER BY overallexp DESC
             LIMIT 10
            """, guild_id
        )
        # 2) Get invoking user’s total EXP
        user_row = await conn.fetchrow(
            "SELECT overallexp FROM accountinfo WHERE discord_id = $1 AND guild_id = $2",
            user_id,guild_id
        )
        user_exp = user_row["overallexp"] if user_row else 0

        # 3) Compute their rank (1-based)
        higher_count = await conn.fetchval(
            "SELECT COUNT(*) FROM accountinfo WHERE overallexp > $1 AND guild_id = $2",
            user_exp,guild_id
        )
        user_rank = higher_count + 1

    # 4) Build the embed
    embed = discord.Embed(
        title="🌟 Overall EXP Leaderboard",
        color=discord.Color.gold()
    )

    lines = []
    pos = 1
    for record in top_rows:
        uid  = record["discord_id"]
        exp  = record["overallexp"]
        # Try to get a guild Member for nickname, else fetch a User
        member = ctx.guild.get_member(uid)
        if member:
            name = member.display_name
        else:
            try:
                user = await bot.fetch_user(uid)
                name = f"{user.name}#{user.discriminator}"
            except:
                name = f"<Unknown {uid}>"
        lines.append(f"**#{pos}** {name} — {exp} EXP")
        pos += 1

    embed.description = "\n".join(lines)
    # 5) Add your own position
    embed.add_field(
        name="Your Position",
        value=f"#{user_rank} — {user_exp} EXP",
        inline=False
    )

    await ctx.send(embed=embed)
