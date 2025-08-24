import os
import asyncio
import logging
import random
import discord
from discord.ext import commands
import asyncpg
from aiohttp import web
from PIL import Image
import io
import dateparser
from services import achievements
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import string
import secrets
import re
from constants import *

async def init_util(dab_pool):
    pass
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")  # required
if not PUBLIC_BASE_URL:
    raise RuntimeError("PUBLIC_BASE_URL environment variable not set")


def media_url(media_id: str) -> str:
    # nice .png suffix for Discord preview; path still resolves by id only
    return f"{PUBLIC_BASE_URL}/i/{media_id}.png"

async def save_image_bytes(conn: asyncpg.Connection, data: bytes, mime: str = "image/png") -> str:
    rec = await conn.fetchrow(
        "INSERT INTO media (mime, bytes) VALUES ($1, $2) RETURNING id",
        mime, data
    )
    return str(rec["id"])


async def giverole(ctx:commands.Context, id: int, user):
    role = ctx.guild.get_role(id)
    if not role:
        return logging.info("⚠️ Role not found in this server.")

    if role in user.roles:
        return logging.info("user already has role.")
    try:
        await user.add_roles(role)
    except discord.Forbidden:
        logging.info("❌ I don't have permission to give that role.")
    except Exception as e:
        logging.info(f"❌ Something went wrong: `{e}`")

def gid_from_ctx(ctx) -> int:
    return ctx.guild.id if ctx and ctx.guild else None

async def sucsac(ctx:commands.Context, user, mob_name: str, is_gold: bool, note: str, conn):
    from services import achievements
    """
    gives the correct reward for a mob and all of its emeralds
    """
    guild_id = gid_from_ctx(ctx)
    user_id = user.id
    key = mob_name.title()

    rarity = MOBS[key]["rarity"]
    rar_info = RARITIES[rarity]
    reward  = rar_info["emeralds"]
    color   = COLOR_MAP[rar_info["colour"]]

    #check sword
    swords = await conn.fetch(
        """
        SELECT tier, uses_left
            FROM tools
            WHERE user_id = $1
            AND guild_id = $2
            AND tool_name = 'sword'
            AND uses_left > 0
        """,
        user_id,
        guild_id
    )
    owned_tiers = {r["tier"] for r in swords}
    best_tier = None
    for tier in reversed(TIER_ORDER):
        if tier in owned_tiers:
            best_tier = tier
            break
    if is_gold:
        reward*=2
    num = SWORDS[best_tier]
    if best_tier == "diamond" and mob_name.lower() == "chicken":
        await achievements.try_grant(ctx.bot.db_pool, ctx, user_id, "overkill")
    reward += num
    await conn.execute(
        """
        UPDATE tools
            SET uses_left = uses_left - 1
            WHERE user_id = $1
            AND guild_id = $2
            AND tool_name = 'sword'
            AND tier = $3
            AND uses_left > 0
        """,
        user_id, guild_id, best_tier
    )

    # grant emeralds
    await give_items(user_id,"emeralds",reward,"emeralds",False,conn,guild_id)
    ems = await get_items(conn,user_id,"emeralds",guild_id)
    if ems >= 1000:
        achievements.try_grant_conn(conn,ctx,user_id,"1000_ems")
    if ems >= 10000:
        achievements.try_grant_conn(conn,ctx,user_id,"10000_ems")
    # record in sacrifice_history
    await conn.execute(
        """
        INSERT INTO sacrifice_history
            (discord_id, guild_id, mob_name, is_golden, rarity)
        VALUES ($1,$2,$3,$4,$5)
        """,
        user_id, guild_id, key, is_gold, rarity
    )

    # send embed
    embed = discord.Embed(
        title=f"🗡️ {user.display_name} sacrificed a {'✨ Golden ' if is_gold else ''} {key} {note}",
        description=f"You gained 💠 **{reward} Emerald{'s' if reward!=1 else ''}**!",
        color=color
    )
    embed.add_field(name="Rarity", value=rar_info["name"].title(), inline=True)
    if is_gold:
        embed.set_footer(text="Golden mobs drop double emeralds!")
    await ctx.send(embed=embed)
    return reward

async def resolve_member(ctx: commands.Context, query: str) -> discord.Member | None:
    """
    Resolve a string to a Member by:
      1) MemberConverter (handles mentions, IDs, name#disc, nicknames)
      2) guild.fetch_member() for raw IDs
      3) case‐insensitive match on display_name or name
    """
    # 1) try the built-in converter
    try:
        return await commands.MemberConverter().convert(ctx, query)
    except commands.BadArgument:
        pass

    guild = ctx.guild
    if not guild:
        return None

    q = query.strip()

    # 2) raw mention or ID
    m = re.match(r"<@!?(?P<id>\d+)>$", q)
    if m:
        uid = int(m.group("id"))
    elif q.isdigit():
        uid = int(q)
    else:
        uid = None

    if uid is not None:
        # a) cached?
        member = guild.get_member(uid)
        if member:
            return member
        # b) fetch from API
        try:
            return await guild.fetch_member(uid)
        except discord.NotFound:
            return None

    # 3) name or display_name (case‐insensitive)
    ql = q.lower()
    for m in guild.members:
        if m.display_name.lower() == ql or m.name.lower() == ql:
            return m

    return None
def get_level_from_exp(exp: int) -> int:
    # find the highest level whose threshold is <= exp
    lvl = 0
    for level, req in LEVEL_EXP.items():
        if exp >= req and level > lvl:
            lvl = level
    return lvl

async def gain_exp(conn, bot, user_id: int, exp_gain: int, message=None, guild_id: int = None):
    """
    Grants XP, announces level-ups (to the guild's announce channel if set, else the message channel),
    and manages milestone roles. Safe if `bot` is None and only `message` is provided.
    """
    # --- derive guild_id if missing ---
    if guild_id is None:
        guild_id = (getattr(getattr(message, "guild", None), "id", None) if message else None)

    # If we still don't know the guild, we can't proceed safely.
    if guild_id is None:
        return

    # --- ensure account row exists ---
    await ensure_account(conn, user_id, guild_id)

    # --- compute new exp/level ---
    old_exp = await conn.fetchval(
        "SELECT experience FROM accountinfo WHERE guild_id = $1 AND discord_id = $2",
        guild_id, user_id
    ) or 0

    new_exp = old_exp + exp_gain
    await conn.execute(
        """
        UPDATE accountinfo
           SET experience = $1, overallexp = overallexp + $2
         WHERE guild_id = $3 AND discord_id = $4
        """,
        new_exp, exp_gain, guild_id, user_id
    )

    old_lvl = get_level_from_exp(old_exp)
    new_lvl = get_level_from_exp(new_exp)
    if new_lvl <= old_lvl:
        return  # no level-up; nothing else to do

    # leaderboard tally
    await lb_inc(conn, "overall_experience", user_id, guild_id, exp_gain)

    # --- recover bot if caller passed None ---
    if bot is None:
        bot = getattr(message, "bot", None) or getattr(message, "client", None)
        if bot is None and message is not None:
            # discord.Message has an internal state that can yield the client
            st = getattr(message, "_state", None)
            if st is not None and hasattr(st, "_get_client"):
                try:
                    bot = st._get_client()
                except Exception:
                    bot = None  # keep None; we'll just skip bot-dependent lookups

    # --- choose announce channel (guild setting -> cache) ---
    announce_ch = None
    try:
        announce_id = await conn.fetchval(
            "SELECT announce_channel_id FROM guild_settings WHERE guild_id = $1",
            guild_id
        )
    except Exception:
        announce_id = None

    if announce_id and bot is not None:
        announce_ch = bot.get_channel(int(announce_id))  # may still be None if not cached

    # Fallback: use the message's channel if available
    if announce_ch is None and message is not None:
        announce_ch = getattr(message, "channel", None)

    # --- role updates (don’t require message) ---
    guild = None
    member = None

    # Prefer guild/member from message if we have it
    if message is not None and getattr(message, "guild", None):
        guild = message.guild
        member = guild.get_member(user_id)

    # Otherwise try cache via bot
    if guild is None and bot is not None:
        guild = bot.get_guild(guild_id)
        if guild is not None and member is None:
            member = guild.get_member(user_id)

    # Remove previous milestone role & add new one (best-effort)
    if guild is not None and member is not None:
        try:
            prev_milestone = max([m for m in MILESTONE_ROLES if m < new_lvl], default=None)
            if prev_milestone is not None:
                prev_role_id = await conn.fetchval(
                    "SELECT role_id FROM guild_level_roles WHERE guild_id = $1 AND level = $2",
                    guild_id, prev_milestone
                )
                if prev_role_id:
                    old_role = guild.get_role(int(prev_role_id))
                    if old_role and old_role in member.roles:
                        await member.remove_roles(old_role, reason="Leveled up")

            if new_lvl in MILESTONE_ROLES:
                role_id = await conn.fetchval(
                    "SELECT role_id FROM guild_level_roles WHERE guild_id = $1 AND level = $2",
                    guild_id, new_lvl
                )
                if role_id:
                    new_role = guild.get_role(int(role_id))
                    if new_role:
                        await member.add_roles(new_role, reason="Leveled up")
        except Exception:
            # Don’t let role errors block XP/announcement
            import logging
            logging.exception("gain_exp: role update failed for user %s in guild %s", user_id, guild_id)

    # --- announcement toggle & send ---
    try:
        level_ann = await conn.fetchval(
            "SELECT COALESCE(level_announcements_enabled, TRUE) FROM guild_settings WHERE guild_id = $1",
            guild_id
        )
    except Exception:
        level_ann = True  # default to on if the setting can't be read

    if level_ann:
        text = f"🎉 <@{user_id}> leveled up to **Level {new_lvl}**!"
        try:
            if announce_ch is not None:
                await announce_ch.send(text)
            elif message is not None:
                await message.channel.send(text)
            # else: nowhere to announce; silently skip
        except Exception:
            import logging
            logging.exception("gain_exp: failed to send level-up announcement in guild %s", guild_id)

# utils/game_helpers.py
async def ensure_account(conn, user_id: int, guild_id: int):
    await conn.execute("""
        INSERT INTO accountinfo (guild_id, discord_id, experience, overallexp)
        VALUES ($1, $2, 0, 0)
        ON CONFLICT (guild_id, discord_id) DO NOTHING
    """, guild_id, user_id)

async def lb_inc(conn, leaderboard_name: str, user_id: int, guild_id: int | None, amount: int):
    """
    Increment a leaderboard counter.
    Updates both server scope (if guild_id is provided) and global scope (guild_id=NULL).
    """
    if leaderboard_name not in VALID_METRICS:
        raise ValueError(f"Unknown leaderboard '{leaderboard_name}'")

    if amount == 0:
        return

    # 1) Per-guild (if provided)
    if guild_id is not None:
        await conn.execute(
            """
            INSERT INTO lb_counters(metric, user_id, guild_id, value)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (metric, user_id, guild_id)
            DO UPDATE SET value = lb_counters.value + EXCLUDED.value
            """,
            leaderboard_name, user_id, guild_id, amount
        )

async def ensure_player(conn, user_id, guild_id: int):
        await conn.execute(
            "INSERT INTO new_players (guild_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING;",
            guild_id,user_id
        )

async def take_items(user_id: int, item: str, amount: int, conn, guild_id: int):
    """
    Atomically subtract items; error if not enough. Deletes the row when it hits 0.
    """
    if amount <= 0:
        return
    rec = await conn.fetchrow(
        """
        UPDATE player_items
           SET quantity = quantity - $3
         WHERE guild_id = $1 AND player_id = $2 AND item_name = $4 AND quantity >= $3
     RETURNING quantity
        """,
        guild_id, user_id, amount, item
    )
    if not rec:
        # Not enough; fetch current to report a good error
        have = await conn.fetchval(
            "SELECT quantity FROM player_items WHERE guild_id=$1 AND player_id=$2 AND item_name=$3",
            guild_id, user_id, item
        ) or 0
        raise ValueError(f"User {user_id} does not have enough of '{item}' (has {have})")

    # Clean up zero rows
    if rec["quantity"] == 0:
        await conn.execute(
            "DELETE FROM player_items WHERE guild_id=$1 AND player_id=$2 AND item_name=$3 AND quantity <= 0",
            guild_id, user_id, item
        )

async def give_items(user_id: int, item: str, amount: int, cat: str, useable: bool, conn, guild_id: int):
    """
    Atomically add items, creating the row if missing.
    """
    if amount == 0:
        return
    await conn.execute(
        """
        INSERT INTO player_items (guild_id, player_id, item_name, category, quantity, useable)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (guild_id, player_id, item_name)
        DO UPDATE SET quantity = player_items.quantity + EXCLUDED.quantity
        """,
        guild_id, user_id, item, cat, amount, useable
    )
    if item == "emeralds":
        await lb_inc(conn, "overall_emeralds", user_id, guild_id, amount)
async def get_items(conn,user_id, item,guild_id:int):

    row = await conn.fetchrow("""
        SELECT quantity FROM player_items
        WHERE guild_id = $1 AND player_id = $2 AND item_name = $3
    """, guild_id, user_id, item)
    if not row:
        return 0
    else:
        return row["quantity"]

async def give_mob(conn,user_id, mob,guild_id,is_golden = False):
    key = mob.title()
    await conn.execute(
        """
        INSERT INTO barn (user_id, guild_id, mob_name, is_golden, count)
        VALUES ($1, $2, $3, $4, 1)
        ON CONFLICT (guild_id, user_id, mob_name, is_golden)
        DO UPDATE SET count = barn.count + 1
        """,
        user_id, guild_id, mob, is_golden
    )
    # 7) Fetch new total
    new_count = await conn.fetchval(
        """
        SELECT count
            FROM barn
            WHERE user_id=$1 AND mob_name=$2 AND is_golden=false
        """,
        user_id, key
    )
    return new_count
