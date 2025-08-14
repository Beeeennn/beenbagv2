# services/achievements.py
from typing import Dict, Any, Iterable, Optional
import asyncpg
from discord import Embed, Color
from utils import game_helpers
import discord

# ---- 2a) Define your achievements here (source of truth) ----
# key must be stable; you can safely change name/description/exp later.
ACHIEVEMENTS: Dict[str, Dict[str, Any]] = {
    "first_chop": {
        "name": "First Chop",
        "description": "Chop wood for the first time.",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "craft_pick": {
        "name": "Craft A Pickaxe",
        "description": "It costs 4 wood - `craft pickaxe wood`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "first_mine": {
        "name": "Yearned for the Mines - `mine`",
        "description": "Go mining",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "first_fish": {
        "name": "Plenty of fish in the sea",
        "description": "Catch your first fish - `fish`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "first_farm": {
        "name": "It aint much, but it's honest work",
        "description": "Go Farming for the time - `farm`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "first_breed": {
        "name": "Matchmaker",
        "description": "Breed a mob for the first time - `breed <mob>`",
        "exp": 3,
        "hidden": False,
        "repeatable": False,
    },
    "mob_catch": {
        "name": "Gotcha",
        "description": "Catch a mob by saying its name",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "upbarn": {
        "name": "Upgrades, people!",
        "description": "Upgrade your barn - `upbarn`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
    },
    "gift_leg":{
        "name": "Too Kind",
        "description": "Give another player a legendary mob `give <player> <mob>`",
        "exp": 20,
        "hidden": False,
        "repeatable": False,
    },
    "20_wood": {
        "name": "Lumberjack",
        "description": "Use chop at least 20 times",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "full_aquarium": {
        "name": "Too Many Fish in the Sea",
        "description": "Have a full aquarium",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "full_food": {
        "name": "No More Food",
        "description": "Obtain fish food at the maximum rate (38 / half hour)",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "overkill": {
        "name": "Overkill",
        "description": "Sacrifice a chicken with a diamond sword",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "sac": {
        "name": "Don't hate the player",
        "description": "Sacrifice any innocent, passive mob",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "epic_mob": {
        "name": "EPIC!",
        "description": "catch an epic mob",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "chicken_jockey": {
        "name": "CHICKEN JOCKEY",
        "description": "catch a zombie while you have a chicken in your barn", #################
        "exp": 5,
        "hidden": True,
        "repeatable": False,       
    },
    "1000_ems":{
        "name": "Slightly Rich",
        "description": "Have 1000 emeralds", ###############
        "exp": 20,
        "hidden": False,
        "repeatable": False,       
    },
    "10000_ems":{
        "name": "Very Rich",
        "description": "Have 10000 emeralds", ###################
        "exp": 20,
        "hidden": False,
        "repeatable": False,       
    },
    "dia_with_wood": {
        "name": "RNG Carried",
        "description": "Mine a diamond with a wood pickaxe",
        "exp": 10,
        "hidden": False,
        "repeatable": False,       
    },
    "dia_hoe": {
        "name": "Don't waste your diamonds on a hoe",
        "description": "...unless you want this achievement (craft a diamond hoe)",
        "exp": 5,
        "hidden": False,
        "repeatable": False,       
    },
    "full_bestiary": {
        "name": "Master Assassin",
        "description": "Sacrifice at least one of every mob", ######
        "exp": 20,
        "hidden": False,
        "repeatable": False,       
    },
    "full_barn": {
        "name": "Noah's Ark",
        "description": "Have at least one of every breedable mob in your barn", ########
        "exp": 20,
        "hidden": False,
        "repeatable": False,       
    },
}

# ---- 2b) Schema + sync helpers ----
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS achievement (
  id SERIAL PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  exp INT NOT NULL DEFAULT 0,
  hidden BOOLEAN NOT NULL DEFAULT FALSE,
  repeatable BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS user_achievement (
  user_id BIGINT NOT NULL,
  achievement_id INT NOT NULL REFERENCES achievement(id) ON DELETE CASCADE,
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  times_awarded INT NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, achievement_id)
);
"""

UPSERT_SQL = """
INSERT INTO achievement (key, name, description, exp, hidden, repeatable)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (key) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  exp = EXCLUDED.exp,
  hidden = EXCLUDED.hidden,
  repeatable = EXCLUDED.repeatable;
"""
# --- helpers to work with Context OR Message -------------------------------

def _safe_avatar(user):
    try:
        return getattr(user.display_avatar, "url", None) or getattr(user.avatar, "url", None)
    except Exception:
        return None

async def _ctx_send(ctx_or_msg, **kwargs):
    """Send using ctx.send(...) if available, else message.channel.send(...)."""
    send = getattr(ctx_or_msg, "send", None)
    if callable(send):
        return await send(**kwargs)
    ch = getattr(ctx_or_msg, "channel", None)
    if ch and hasattr(ch, "send"):
        return await ch.send(**kwargs)
    # last resort (shouldn't happen)
    raise RuntimeError("No way to send message from the given context/message.")

def _resolve_bot(ctx_or_msg) -> Optional[discord.Client]:
    """Get a bot/client from Context or Message."""
    bot = getattr(ctx_or_msg, "bot", None) or getattr(ctx_or_msg, "client", None)
    if bot:
        return bot
    # Try to pull from guild/channel state
    g = getattr(ctx_or_msg, "guild", None)
    if g is not None:
        st = getattr(g, "_state", None)
        if st:
            bot = getattr(st, "client", None)
            if bot:
                return bot
            getter = getattr(st, "_get_client", None)
            if callable(getter):
                try:
                    return getter()
                except Exception:
                    pass
    ch = getattr(ctx_or_msg, "channel", None)
    if ch is not None:
        st = getattr(ch, "_state", None)
        if st:
            bot = getattr(st, "client", None)
            if bot:
                return bot
    return None

async def _send_unlock_embed(ctx_or_msg, *, key: str, name: str, description: str,
                             exp: int, repeatable: bool, times_awarded: int):
    trophy = "🏆"
    title = f"{trophy} Achievement Unlocked!"
    desc = f"**{name}**\n{description}"

    author = getattr(ctx_or_msg, "author", None)
    e = Embed(title=title, description=desc, color=Color.gold())
    e.add_field(name="EXP", value=f"+{exp}", inline=True)
    if repeatable and times_awarded > 1:
        e.add_field(name="Times Awarded", value=f"×{times_awarded}", inline=True)
    if author:
        e.set_author(name=getattr(author, "display_name", "You"), icon_url=_safe_avatar(author))
    e.set_footer(text=key)

    try:
        await _ctx_send(ctx_or_msg, embed=e)
    except Exception:
        # never break gameplay if an embed fails
        try:
            await _ctx_send(ctx_or_msg, content=f"{trophy} **Achievement Unlocked:** {name} (+{exp} EXP)")
        except Exception:
            pass

# ---- EXP hand-off (works with Context OR Message) -------------------------

async def _grant_exp(conn: asyncpg.Connection, ctx_or_msg, user_id: int, amount: int):
    """Grant EXP using the same DB connection; resolves bot and guild from ctx/message."""
    gid = game_helpers.gid_from_ctx(ctx_or_msg)
    bot = _resolve_bot(ctx_or_msg)
    # Pass the original message/context in as 'message' so your gain_exp can still use guild/member
    await game_helpers.gain_exp(conn, bot, user_id, amount, ctx_or_msg, gid)
async def ensure_schema(pool: asyncpg.Pool):
    async with pool.acquire() as con:
        await con.execute(SCHEMA_SQL)

async def sync_master(pool: asyncpg.Pool):
    async with pool.acquire() as con:
        async with con.transaction():
            for k, v in ACHIEVEMENTS.items():
                await con.execute(
                    UPSERT_SQL,
                    k, v["name"], v["description"], v["exp"], v.get("hidden", False), v.get("repeatable", False)
                )

async def _get_achievement_row(con: asyncpg.Connection, key: str):
    return await con.fetchrow("SELECT * FROM achievement WHERE key = $1", key)

async def _get_user_ach(con: asyncpg.Connection, user_id: int, ach_id: int):
    return await con.fetchrow(
        "SELECT * FROM user_achievement WHERE user_id = $1 AND achievement_id = $2",
        user_id, ach_id
    )

async def grant(pool: asyncpg.Pool, ctx, user_id: int, key: str, notify: bool = True) -> Optional[int]:
    meta = ACHIEVEMENTS.get(key)
    if not meta:
        return None

    async with pool.acquire() as con, con.transaction():
        ach = await _get_achievement_row(con, key)
        if not ach:
            await con.execute(
                UPSERT_SQL, key, meta["name"], meta["description"], meta["exp"],
                meta.get("hidden", False), meta.get("repeatable", False)
            )
            ach = await _get_achievement_row(con, key)

        ach_id = ach["id"]
        exp    = ach["exp"]
        is_repeat = ach["repeatable"]

        if is_repeat:
            row = await con.fetchrow(
                """
                INSERT INTO user_achievement (user_id, achievement_id, times_awarded)
                VALUES ($1, $2, 1)
                ON CONFLICT (user_id, achievement_id)
                DO UPDATE SET times_awarded = user_achievement.times_awarded + 1,
                              unlocked_at   = NOW()
                RETURNING times_awarded
                """,
                user_id, ach_id
            )
            await _grant_exp(con, ctx, user_id, exp)
            if notify:
                await _send_unlock_embed(
                    ctx, key=key, name=meta["name"], description=meta["description"],
                    exp=exp, repeatable=True, times_awarded=row["times_awarded"]
                )
            return exp
        else:
            inserted = await con.fetchrow(
                """
                INSERT INTO user_achievement (user_id, achievement_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, achievement_id) DO NOTHING
                RETURNING 1
                """,
                user_id, ach_id
            )
            if inserted:
                await _grant_exp(con, ctx, user_id, exp)
                if notify:
                    await _send_unlock_embed(
                        ctx, key=key, name=meta["name"], description=meta["description"],
                        exp=exp, repeatable=False, times_awarded=1
                    )
                return exp
            return 0

async def try_grant(pool: asyncpg.Pool, ctx, user_id: int, key: str, *, notify: bool = True) -> Optional[int]:
    if ACHIEVEMENTS.get(key) is None:
        return None
    return await grant(pool, ctx, user_id, key, notify=notify)

async def try_grant_many(pool: asyncpg.Pool, ctx, user_id: int, keys: Iterable[str]) -> int:
    """
    Convenience: attempts several keys; returns total EXP granted.
    """
    total = 0
    for k in keys:
        gained = await try_grant(pool, ctx, user_id, k) or 0
        total += gained
    return total

async def list_user_achievements(pool: asyncpg.Pool, user_id: int):
    """
    Returns: (owned, not_owned) where:
      owned = list[ {key, name, description, exp, times_awarded, unlocked_at} ]
      not_owned = list[ {key, name, description, exp, hidden} ]  (filtered if hidden)
    """
    async with pool.acquire() as con:
        rows = await con.fetch("""
            SELECT a.key, a.name, a.description, a.exp, a.hidden, a.repeatable,
                   ua.times_awarded, ua.unlocked_at
            FROM achievement a
            LEFT JOIN user_achievement ua
              ON ua.achievement_id = a.id AND ua.user_id = $1
            ORDER BY a.name
        """, user_id)

    owned, not_owned = [], []
    for r in rows:
        if r["times_awarded"] is not None:
            owned.append({
                "key": r["key"], "name": r["name"], "description": r["description"],
                "exp": r["exp"], "times_awarded": r["times_awarded"], "unlocked_at": r["unlocked_at"],
                "repeatable": r["repeatable"]
            })
        else:
            # Hide hidden achievements the user doesn't have
            if not r["hidden"]:
                not_owned.append({
                    "key": r["key"], "name": r["name"], "description": r["description"],
                    "exp": r["exp"], "hidden": r["hidden"]
                })
    return owned, not_owned
