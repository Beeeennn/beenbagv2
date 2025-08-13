from datetime import datetime, timedelta
from utils.game_helpers import gid_from_ctx,resolve_member
import discord
import string
import secrets
import asyncio

async def make_link_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

async def safe_dm(user: discord.User, content: str, *, retry: int = 3):
    """
    Send user a DM, reusing their DMChannel and retrying on the 40003 error.
    Returns True on success, False on permanent failure.
    """
    # 1) Get or create the DM channel
    dm = user.dm_channel
    if dm is None:
        dm = await user.create_dm()

    # 2) Attempt to send, with retries if rate-limited
    for attempt in range(retry):
        try:
            await dm.send(content)
            return True
        except discord.HTTPException as e:
            # 40003 = opening DMs too fast
            if e.code == 40003 and attempt < retry - 1:
                await asyncio.sleep(1 + attempt)  # back-off
                continue
            # any other error or no more retries
            break

    return False
async def linkyt(pool, ctx, channel_name: str):
    """
    Generate a one-time code to link your YouTube channel.
    Usage: !linkyt <your YouTube channel name>
    """
    user_id = ctx.author.id
    gid = gid_from_ctx(ctx)
    code = await make_link_code(8)
    expires = datetime.utcnow() + timedelta(hours=3)
    channel_name = channel_name.removeprefix("@")
    # store (or update) in pending_links
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pending_links
                (discord_id, guild_id, yt_channel_id, code, expires_at)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (discord_id) DO UPDATE
              SET yt_channel_id = EXCLUDED.yt_channel_id,
                  code            = EXCLUDED.code,
                  expires_at      = EXCLUDED.expires_at;
            """,
            user_id, gid, channel_name.lower(), code, expires
        )

    # DM them the code

    sent = await safe_dm(
    ctx.author,
    f"🔗 **YouTube Link Code** 🔗\n"
    f"Channel: **{channel_name}**\n"
    f"Your code is: `{code}`\n\n"
    f"Please type `{ctx.clean_prefix}link {code}` in one of my **livestreams** within 3 hours to complete linking."
        
    )
    if sent:
        await ctx.send(f"{ctx.author.mention}, check your DMs for the code!")
    else:
        await ctx.send(
            f"{ctx.author.mention}, I couldn’t DM you right now—please try again later. Make sure to enable DMs from server members and try again (Content and social -> Social Permissions -> Direct Messages) You can turn it back off after."
        )
async def get_link_channel_ids(pool, guild_id: int) -> list[int]:
    """Return configured link channels for this guild or []."""
    async with pool.acquire() as conn:
        ids = await conn.fetchval(
            "SELECT link_channel_ids FROM guild_settings WHERE guild_id = $1",
            guild_id
        )
    return ids or []
async def yt(pool, ctx, who = None):
    """
    Show the YouTube channel linked to a user.
    Usage:
      !yt             → your own channel
      !yt @Someone    → their channel
    """
    """Show your current level and progress toward the next level."""
    # Resolve who → Member (or fallback to author)
    gid = gid_from_ctx(ctx)
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")  # or "Member not found."
    user_id = member.id
    # 0) Restrict to link channels (if any configured)
    link_ids = await get_link_channel_ids(ctx.guild.id)
    if link_ids and ctx.channel.id not in link_ids:
        # build nice mentions for configured channels that still exist
        mentions = [f"<#{cid}>" for cid in link_ids if ctx.guild.get_channel(cid)]
        where = ", ".join(mentions) if mentions else "one of the configured link channels"
        return await ctx.send(f"❌ You can’t do that here. Please use {where}.")

    # 2) Fetch from accountinfo
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT yt_channel_name, yt_channel_id
              FROM accountinfo
             WHERE discord_id = $1
             AND guild_id = $2
            """,
            user_id,gid
        )

    # 3) No link yet?
    if not row or (not row["yt_channel_name"] and not row["yt_channel_id"]):
        if member == ctx.author:
            return await ctx.send(
                "You haven’t linked a YouTube channel! Use `{ctx.clean_prefix}linkyt <channel name>`."
            )
        else:
            return await ctx.send(f"{member.display_name} hasn’t linked YT yet.")

    # 4) Build URL
    name = row["yt_channel_name"]
    cid  = row["yt_channel_id"]
    if cid:
        url = f"https://www.youtube.com/channel/{cid}"
    else:
        url = f"https://www.youtube.com/c/{name.replace(' ', '')}"

    # 5) Send embed
    embed = discord.Embed(
        title=f"{member.display_name}'s YouTube",
        url=url, color=discord.Color.red()
    )
    embed.add_field(name="Channel Name", value=name or "–", inline=True)
    embed.add_field(name="Link", value=f"[Watch on YouTube]({url})", inline=True)
    await ctx.send(embed=embed)
