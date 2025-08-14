# services/achievements.py
from typing import Dict, Any, Iterable, Optional
import asyncpg
from discord import Embed, Color
from utils import game_helpers

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
# --- Embeds ---
def _safe_avatar(user):
    try:
        return getattr(user.display_avatar, "url", None) or getattr(user.avatar, "url", None)
    except Exception:
        return None

async def _send_unlock_embed(ctx, *, key: str, name: str, description: str, exp: int,
                             repeatable: bool, times_awarded: int):
    trophy = "🏆"
    title = f"{trophy} Achievement Unlocked!"
    desc = f"**{name}**\n{description}"

    e = Embed(title=title, description=desc, color=Color.gold())
    e.add_field(name="EXP", value=f"+{exp}", inline=True)
    if repeatable and times_awarded > 1:
        e.add_field(name="Times Awarded", value=f"×{times_awarded}", inline=True)

    e.set_author(name=ctx.author.display_name, icon_url=_safe_avatar(ctx.author))
    e.set_footer(text=key)

    try:
        await ctx.send(embed=e)
    except Exception:
        # never break gameplay if an embed fails
        try:
            await ctx.send(f"{trophy} **Achievement Unlocked:** {name} (+{exp} EXP)")
        except Exception:
            pass
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

# ---- 2c) EXP hand-off ----
async def _grant_exp(conn, ctx, amount: int):
    """
    Call your existing progression.gain_exp here.
    Adjust call signature as needed — most projects either do:
        await progression.gain_exp(pool, ctx.author.id, amount)
    or
        await progression.gain_exp(ctx, pool, amount)
    Below we try the common patterns to keep this drop-in.
    """
    gid = game_helpers.gid_from_ctx(ctx)
    await game_helpers.gain_exp(conn,ctx.bot, ctx.author.id, amount, None, gid) 

# ---- 2d) Public API ----
async def grant(pool: asyncpg.Pool, ctx, user_id: int, key: str, notify: bool = True) -> Optional[int]:
    """
    Grant (idempotent for non-repeatables). Returns EXP granted (int),
    0 if already owned (non-repeatable), or None if key unknown.
    """
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
            await _grant_exp(con, ctx, exp)
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
                await _grant_exp(con, ctx, exp)
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
def _lines_to_embeds(title: str, lines: list[str], color: Color, author=None, icon_url=None):
    # Split long lists into multiple embeds safely
    chunks = []
    cur = []
    cur_len = 0
    for line in lines:
        if cur_len + len(line) + 1 > 3800:  # leave room for title/headers
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line) + 1
    if cur:
        chunks.append(cur)

    embeds = []
    for i, chunk in enumerate(chunks, 1):
        e = Embed(title=title, description="\n".join(chunk), color=color)
        if author:
            e.set_author(name=author, icon_url=icon_url)
        if len(chunks) > 1:
            e.set_footer(text=f"Page {i}/{len(chunks)}")
        embeds.append(e)
    return embeds

def render_achievements_embeds(user, owned: list[dict], not_owned: list[dict]) -> list[Embed]:
    # Owned (unlocked)
    owned_lines = []
    for o in owned:
        rpt = f" ×{o['times_awarded']}" if o.get("repeatable") and o.get("times_awarded", 1) > 1 else ""
        owned_lines.append(f"• **{o['name']}**{rpt} — {o['description']} *(+{o['exp']} EXP)*")

    # Locked (non-hidden)
    locked_lines = [f"• **{n['name']}** — {n['description']} *(+{n['exp']} EXP)*" for n in not_owned]

    icon = _safe_avatar(user)
    embeds: list[Embed] = []

    if owned_lines:
        embeds += _lines_to_embeds(
            title=f"🏆 {user.display_name} — Unlocked ({len(owned)})",
            lines=owned_lines,
            color=Color.gold(),
            author=user.display_name,
            icon_url=icon
        )

    if locked_lines:
        embeds += _lines_to_embeds(
            title=f"🔒 {user.display_name} — Locked ({len(not_owned)})",
            lines=locked_lines,
            color=Color.dark_grey(),
            author=user.display_name,
            icon_url=icon
        )

    if not embeds:
        embeds = [Embed(title="Achievements", description="No achievements defined yet.", color=Color.blurple())]

    return embeds
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
