# services/achievements.py
from typing import Dict, Any, Iterable, Optional, List
import asyncpg
from discord import Embed, Color, ui, ButtonStyle, Interaction
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
        "category":"Starter",
    },
    "craft_pick": {
        "name": "Craft A Pickaxe",
        "description": "It costs 4 wood - `craft pickaxe wood`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "first_mine": {
        "name": "Yearned for the Mines - `mine`",
        "description": "Go mining",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "first_fish": {
        "name": "Plenty of fish in the sea",
        "description": "Catch your first fish - `fish`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "first_farm": {
        "name": "It aint much, but it's honest work",
        "description": "Go Farming for the time - `farm`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "first_breed": {
        "name": "Matchmaker",
        "description": "Breed a mob for the first time - `breed <mob>`",
        "exp": 3,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "mob_catch": {
        "name": "Gotcha",
        "description": "Catch a mob by saying its name",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "upbarn": {
        "name": "Upgrades, people!",
        "description": "Upgrade your barn - `upbarn`",
        "exp": 2,
        "hidden": False,
        "repeatable": False,
        "category":"Starter",
    },
    "gift_leg":{
        "name": "Too Kind",
        "description": "Give another player a legendary mob `give <player> <mob>`",
        "exp": 20,
        "hidden": False,
        "repeatable": False,
        "category":"Challenging",
    },
    "20_wood": {
        "name": "Lumberjack",
        "description": "Use chop at least 20 times",
        "exp": 5,
        "hidden": False,
        "repeatable": False,  
        "category":"Early",     
    },
    "full_aquarium": {
        "name": "Too Many Fish in the Sea",
        "description": "Have a full aquarium",
        "exp": 5,
        "hidden": False,
        "repeatable": False, 
        "category":"Challenging",      
    },
    "full_food": {
        "name": "No More Food",
        "description": "Obtain fish food at the maximum rate (38 / half hour)",
        "exp": 5,
        "hidden": False,
        "repeatable": False,  
        "category":"Challenging",     
    },
    "overkill": {
        "name": "Overkill",
        "description": "Sacrifice a chicken with a diamond sword",
        "exp": 5,
        "hidden": False,
        "repeatable": False,  
        "category":"Random",     
    },
    "sac": {
        "name": "Don't hate the player",
        "description": "Sacrifice any innocent, passive mob",
        "exp": 5,
        "hidden": False,
        "repeatable": False,  
        "category":"Starter",     
    },
    "epic_mob": {
        "name": "EPIC!",
        "description": "catch an epic mob",
        "exp": 5,
        "hidden": False,
        "repeatable": False,     
        "category":"Early",  
    },
    "chicken_jockey": {
        "name": "CHICKEN JOCKEY",
        "description": "catch a zombie while you have a chicken in your barn", 
        "exp": 5,
        "hidden": True,
        "repeatable": False,    
        "category":"Hidden",   
    },
    "1000_ems":{
        "name": "Slightly Rich",
        "description": "Have 1000 emeralds", 
        "exp": 20,
        "hidden": False,
        "repeatable": False,      
        "category":"Challenging", 
    },
    "10000_ems":{
        "name": "Very Rich",
        "description": "Have 10000 emeralds", 
        "exp": 20,
        "hidden": False,
        "repeatable": False,  
        "category":"Extreme",     
    },
    "dia_with_wood": {
        "name": "RNG Carried",
        "description": "Mine a diamond with a wood pickaxe",
        "exp": 10,
        "hidden": False,
        "repeatable": False,  
        "category":"Random",     
    },
    "dia_hoe": {
        "name": "Don't waste your diamonds on a hoe",
        "description": "...unless you want this achievement (craft a diamond hoe)",
        "exp": 5,
        "hidden": False,
        "repeatable": False,      
        "category":"Early", 
    },
    "full_bestiary": {
        "name": "Master Assassin",
        "description": "Sacrifice at least one of every mob", ######
        "exp": 20,
        "hidden": False,
        "repeatable": False,     
        "category":"Extreme",  
    },
    "full_barn": {
        "name": "Noah's Ark",
        "description": "Have at least one of every breedable mob in your barn", ########
        "exp": 20,
        "hidden": False,
        "repeatable": False,  
        "category":"Extreme",     
    },
    "baby_been": {
    "name": "Why....",
    "description": "Have a baby with beenbag",
    "exp": 2,
    "hidden": True,
    "repeatable": False,  
    "category":"Hidden",     
    },
    "fast_quiz": {
    "name": "Fast AF",
    "description": "Answer a trivia question in less than half a second",
    "exp": 3,
    "hidden": False,
    "repeatable": False,  
    "category":"Random",     
    },
    "full_marks": {
    "name": "Brainbox",
    "description": "Get first place in all 5 rounds of trivia",
    "exp": 3,
    "hidden": False,
    "repeatable": False,  
    "category":"Random",     
    },
}

# ---- 2b) Schema + migration helpers (per-guild unlocks) ----
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS achievement (
  id SERIAL PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  exp INT NOT NULL DEFAULT 0,
  hidden BOOLEAN NOT NULL DEFAULT FALSE,
  repeatable BOOLEAN NOT NULL DEFAULT FALSE,
  category TEXT NOT NULL DEFAULT 'General'
);

-- Per-guild ownership (note the guild_id here)
CREATE TABLE IF NOT EXISTS user_achievement (
  user_id BIGINT NOT NULL,
  guild_id BIGINT NOT NULL,
  achievement_id INT NOT NULL REFERENCES achievement(id) ON DELETE CASCADE,
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  times_awarded INT NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, guild_id, achievement_id)
);
"""

UPSERT_SQL = """
INSERT INTO achievement (key, name, description, exp, hidden, repeatable, category)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (key) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  exp = EXCLUDED.exp,
  hidden = EXCLUDED.hidden,
  repeatable = EXCLUDED.repeatable,
  category = EXCLUDED.category;
"""

CATEGORY_ORDER = ["Starter", "Early", "Challenging", "Random", "Extreme","Hidden"]

def _ordered_categories(cats: List[str]) -> List[str]:
    order_index = {name: i for i, name in enumerate(CATEGORY_ORDER)}
    BIG = 10**9
    return sorted(cats, key=lambda c: (order_index.get(c, BIG), c.lower()))

# --- create / migrate to per-guild user_achievement ---
async def ensure_schema(pool: asyncpg.Pool):
    async with pool.acquire() as con:
        # Create tables / new columns
        await con.execute("""
        CREATE TABLE IF NOT EXISTS achievement (
          id SERIAL PRIMARY KEY,
          key TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          exp INT NOT NULL DEFAULT 0,
          hidden BOOLEAN NOT NULL DEFAULT FALSE,
          repeatable BOOLEAN NOT NULL DEFAULT FALSE,
          category TEXT NOT NULL DEFAULT 'General'
        );

        CREATE TABLE IF NOT EXISTS user_achievement (
          user_id BIGINT NOT NULL,
          guild_id BIGINT NOT NULL,
          achievement_id INT NOT NULL REFERENCES achievement(id) ON DELETE CASCADE,
          unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          times_awarded INT NOT NULL DEFAULT 1,
          PRIMARY KEY (user_id, guild_id, achievement_id)
        );
        """)

        # Migrate from older schema (no guild_id / different PK)
        await con.execute("ALTER TABLE user_achievement ADD COLUMN IF NOT EXISTS guild_id BIGINT;")
        await con.execute("UPDATE user_achievement SET guild_id = 0 WHERE guild_id IS NULL;")
        await con.execute("ALTER TABLE user_achievement ALTER COLUMN guild_id SET NOT NULL;")

        # Read the CURRENT primary key column list in order
        current_pk_cols = await con.fetch("""
            SELECT a.attname
            FROM pg_index i
            JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
            JOIN pg_attribute a
              ON a.attrelid = i.indrelid
             AND a.attnum   = k.attnum
            WHERE i.indrelid = 'user_achievement'::regclass
              AND i.indisprimary
            ORDER BY k.ord;
        """)
        current_pk_cols = [r["attname"] for r in current_pk_cols]

        desired = ["user_id", "guild_id", "achievement_id"]

        if not current_pk_cols:
            # No PK set — add the correct one.
            await con.execute("""
                ALTER TABLE user_achievement
                ADD CONSTRAINT user_achievement_pkey
                PRIMARY KEY (user_id, guild_id, achievement_id);
            """)
        elif current_pk_cols != desired:
            # Drop whatever PK exists, then add the desired one.
            pk_name = await con.fetchval("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'user_achievement'::regclass
                  AND contype  = 'p'
                LIMIT 1;
            """)
            if pk_name:
                await con.execute(f'ALTER TABLE user_achievement DROP CONSTRAINT {pk_name};')
            await con.execute("""
                ALTER TABLE user_achievement
                ADD CONSTRAINT user_achievement_pkey
                PRIMARY KEY (user_id, guild_id, achievement_id);
            """)

# keep master in sync (also ensures schema)
async def sync_master(pool: asyncpg.Pool):
    await ensure_schema(pool)
    async with pool.acquire() as con:
        async with con.transaction():
            for k, v in ACHIEVEMENTS.items():
                await con.execute(
                    UPSERT_SQL,
                    k, v["name"], v["description"], v["exp"],
                    v.get("hidden", False), v.get("repeatable", False),
                    v.get("category", "General"),
                )

# --- tiny embed helpers & send utils ---
def _safe_avatar(user):
    try:
        return getattr(user.display_avatar, "url", None) or getattr(user.avatar, "url", None)
    except Exception:
        return None

async def _ctx_send(ctx_or_msg, **kwargs):
    send = getattr(ctx_or_msg, "send", None)
    if callable(send):
        return await send(**kwargs)
    ch = getattr(ctx_or_msg, "channel", None)
    if ch and hasattr(ch, "send"):
        return await ch.send(**kwargs)
    raise RuntimeError("No way to send message from the given context/message.")

def _resolve_bot(ctx_or_msg) -> Optional[discord.Client]:
    return getattr(ctx_or_msg, "bot", None) or getattr(ctx_or_msg, "client", None)

async def _send_unlock_embed(ctx_or_msg, *, name: str, description: str,
                             exp: int, repeatable: bool, times_awarded: int):
    e = Embed(title="🏆 Achievement Unlocked!", description=f"**{name}**\n{description}", color=Color.gold())
    e.add_field(name="EXP", value=f"+{exp}", inline=True)
    if repeatable and times_awarded > 1:
        e.add_field(name="Times Awarded", value=f"×{times_awarded}", inline=True)
    author = getattr(ctx_or_msg, "author", None)
    if author:
        e.set_author(name=getattr(author, "display_name", "You"), icon_url=_safe_avatar(author))
    e.set_footer(text="Use `achievement` to see more")
    try:
        await _ctx_send(ctx_or_msg, embed=e)
    except Exception:
        try:
            await _ctx_send(ctx_or_msg, content=f"🏆 **Achievement Unlocked:** {name} (+{exp} EXP)")
        except Exception:
            pass

# ---- EXP hand-off (works with Context OR Message) -------------------------
async def _grant_exp(conn: asyncpg.Connection, ctx_or_msg, user_id: int, amount: int):
    gid = game_helpers.gid_from_ctx(ctx_or_msg)
    bot = _resolve_bot(ctx_or_msg)
    await game_helpers.gain_exp(conn, bot, user_id, amount, ctx_or_msg, gid)

# ---- core lookups (per-guild) ---------------------------------------------
async def _get_achievement_row(con: asyncpg.Connection, key: str):
    return await con.fetchrow("SELECT * FROM achievement WHERE key = $1", key)

async def _get_user_ach(con: asyncpg.Connection, user_id: int, ach_id: int, guild_id: int):
    return await con.fetchrow(
        """
        SELECT * FROM user_achievement
        WHERE user_id = $1 AND guild_id = $2 AND achievement_id = $3
        """,
        user_id, guild_id, ach_id
    )

# ---- grant API (per-guild) ------------------------------------------------
async def grant(pool: asyncpg.Pool, ctx, user_id: int, key: str, notify: bool = True) -> Optional[int]:
    meta = ACHIEVEMENTS.get(key)
    if not meta:
        return None

    guild_id = game_helpers.gid_from_ctx(ctx)
    if guild_id is None:
        # Only award achievements in servers
        return 0

    async with pool.acquire() as con, con.transaction():
        ach = await _get_achievement_row(con, key)
        if not ach:
            await con.execute(
                UPSERT_SQL, key, meta["name"], meta["description"], meta["exp"],
                meta.get("hidden", False), meta.get("repeatable", False),
                meta.get("category", "General"),
            )
            ach = await _get_achievement_row(con, key)

        ach_id = ach["id"]
        exp    = ach["exp"]
        is_repeat = ach["repeatable"]

        if is_repeat:
            row = await con.fetchrow(
                """
                INSERT INTO user_achievement (user_id, guild_id, achievement_id, times_awarded)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (user_id, guild_id, achievement_id)
                DO UPDATE SET times_awarded = user_achievement.times_awarded + 1,
                              unlocked_at   = NOW()
                RETURNING times_awarded
                """,
                user_id, guild_id, ach_id
            )
            await _grant_exp(con, ctx, user_id, exp)
            if notify:
                await _send_unlock_embed(
                    ctx, name=meta["name"], description=meta["description"],
                    exp=exp, repeatable=True, times_awarded=row["times_awarded"]
                )
            return exp
        else:
            inserted = await con.fetchrow(
                """
                INSERT INTO user_achievement (user_id, guild_id, achievement_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, guild_id, achievement_id) DO NOTHING
                RETURNING 1
                """,
                user_id, guild_id, ach_id
            )
            if inserted:
                await _grant_exp(con, ctx, user_id, exp)
                if notify:
                    await _send_unlock_embed(
                        ctx, name=meta["name"], description=meta["description"],
                        exp=exp, repeatable=False, times_awarded=1
                    )
                return exp
            return 0
async def grant_with_conn(conn, ctx, user_id: int, key: str, notify: bool = True) -> Optional[int]:
    meta = ACHIEVEMENTS.get(key)
    if not meta:
        return None

    guild_id = game_helpers.gid_from_ctx(ctx)
    if guild_id is None:
        # Only award achievements in servers
        return 0

    ach = await _get_achievement_row(conn, key)
    if not ach:
        await conn.execute(
            UPSERT_SQL, key, meta["name"], meta["description"], meta["exp"],
            meta.get("hidden", False), meta.get("repeatable", False),
            meta.get("category", "General"),
        )
        ach = await _get_achievement_row(conn, key)

    ach_id = ach["id"]
    exp    = ach["exp"]
    is_repeat = ach["repeatable"]

    if is_repeat:
        row = await conn.fetchrow(
            """
            INSERT INTO user_achievement (user_id, guild_id, achievement_id, times_awarded)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (user_id, guild_id, achievement_id)
            DO UPDATE SET times_awarded = user_achievement.times_awarded + 1,
                            unlocked_at   = NOW()
            RETURNING times_awarded
            """,
            user_id, guild_id, ach_id
        )
        await _grant_exp(conn, ctx, user_id, exp)
        if notify:
            await _send_unlock_embed(
                ctx, name=meta["name"], description=meta["description"],
                exp=exp, repeatable=True, times_awarded=row["times_awarded"]
            )
        return exp
    else:
        inserted = await conn.fetchrow(
            """
            INSERT INTO user_achievement (user_id, guild_id, achievement_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, guild_id, achievement_id) DO NOTHING
            RETURNING 1
            """,
            user_id, guild_id, ach_id
        )
        if inserted:
            await _grant_exp(conn, ctx, user_id, exp)
            if notify:
                await _send_unlock_embed(
                    ctx, name=meta["name"], description=meta["description"],
                    exp=exp, repeatable=False, times_awarded=1
                )
            return exp
        return 0
async def try_grant(pool: asyncpg.Pool, ctx, user_id: int, key: str, *, notify: bool = True) -> Optional[int]:
    if ACHIEVEMENTS.get(key) is None:
        print(f"Error getting achievement {key}")
        return None
    return await grant(pool, ctx, user_id, key, notify=notify)

async def try_grant_conn(conn, ctx, user_id: int, key: str, *, notify: bool = True) -> Optional[int]:
    if ACHIEVEMENTS.get(key) is None:
        print(f"Error getting achievement {key}")
        return None
    return await grant_with_conn(conn, ctx, user_id, key, notify=notify)

async def try_grant_many(pool: asyncpg.Pool, ctx, user_id: int, keys: Iterable[str]) -> int:
    total = 0
    for k in keys:
        gained = await try_grant(pool, ctx, user_id, k) or 0
        total += gained
    return total

# ---- listing & UI (per-guild) ---------------------------------------------
async def _fetch_categories(conn) -> List[str]:
    rows = await conn.fetch("SELECT DISTINCT category FROM achievement ORDER BY 1")
    return [r["category"] for r in rows] or ["General"]

async def _fetch_category_rows(con: asyncpg.Connection, category: str, user_id: int, guild_id: int):
    return await con.fetch(
        """
        SELECT a.key, a.name, a.description, a.exp, a.hidden, a.repeatable, a.category,
               ua.times_awarded, ua.unlocked_at
          FROM achievement a
          LEFT JOIN user_achievement ua
            ON ua.achievement_id = a.id
           AND ua.user_id = $2
           AND ua.guild_id = $3
         WHERE a.category = $1
         ORDER BY a.name
        """,
        category, user_id, guild_id
    )

def _row_to_line(r) -> str:
    unlocked = r["times_awarded"] is not None
    if unlocked:
        rpt = ""
        if r["repeatable"] and r["times_awarded"] and r["times_awarded"] > 1:
            rpt = f" ×{r['times_awarded']}"
        return f"• **{r['name']}**{rpt} — {r['description']} *(+{r['exp']} EXP)*"
    else:
        return f"• **{r['name']}** — {r['description']} *(+{r['exp']} EXP)*"

def _build_achievements_embed(ctx_or_msg, *, category: str, mode_locked: bool,
                              rows: List[asyncpg.Record], start: int) -> Embed:
    if mode_locked:
        filt = [r for r in rows if r["times_awarded"] is None and not r["hidden"]]
        title = f"🏆 Achievements — {category} — Locked"
        color = Color.dark_grey()
    else:
        filt = [r for r in rows if r["times_awarded"] is not None]
        title = f"🏆 Achievements — {category} — Unlocked"
        color = Color.gold()

    total = len(filt)
    start = max(0, min(start, max(0, total - 1)))
    page = filt[start:start + 10]

    e = Embed(title=title, color=color)
    if page:
        lines = [_row_to_line(r) for r in page]
        e.description = "\n".join(lines)
        a = start + 1
        b = min(start + 10, total)
        e.set_footer(text=f"Showing {a}-{b} of {total} • Use the dropdown to change category • Only you can use the controls.")
    else:
        e.description = "Nothing to show here."
    author = getattr(ctx_or_msg, "author", None)
    if author:
        try:
            e.set_author(name=author.display_name, icon_url=getattr(author.display_avatar, "url", None))
        except Exception:
            pass
    return e

class AchievementsView(discord.ui.View):
    def __init__(self, ctx, pool, user_id: int, guild_id: int, initial_category: str, categories: List[str]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pool = pool
        self.user_id = user_id
        self.guild_id = guild_id
        self.category = initial_category
        self.categories = categories[:]  # keep our own copy
        self.mode_locked = False
        self.start = 0
        self.cache: Dict[str, List[asyncpg.Record]] = {}
        self._refresh_select_options()

    def _refresh_select_options(self):
        self.category_select.options = [
            discord.SelectOption(label=c, value=c, default=(c == self.category))
            for c in self.categories
        ]

    async def _load(self):
        async with self.pool.acquire() as con:
            if self.category not in self.cache:
                self.cache[self.category] = await _fetch_category_rows(
                    con, self.category, self.user_id, self.guild_id
                )

    async def _render(self, interaction: Interaction | None = None):
        await self._load()
        self._refresh_select_options()
        rows = self.cache.get(self.category, [])

        if self.mode_locked:
            total = len([r for r in rows if r["times_awarded"] is None and not r["hidden"]])
        else:
            total = len([r for r in rows if r["times_awarded"] is not None])

        self.start = max(0, min(self.start, max(0, total - 1)))
        self.prev_button.disabled = (self.start <= 0)
        self.next_button.disabled = (self.start + 10 >= total)
        self.toggle_button.label = "Show Locked" if not self.mode_locked else "Show Unlocked"
        self.toggle_button.style = ButtonStyle.primary if self.mode_locked else ButtonStyle.secondary

        embed = _build_achievements_embed(
            self.ctx, category=self.category, mode_locked=self.mode_locked,
            rows=rows, start=self.start
        )
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await self.ctx.send(embed=embed, view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.ctx.author.id

    @discord.ui.select(placeholder="Select a category…", min_values=1, max_values=1, row=0)
    async def category_select(self, interaction: Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        self.start = 0
        await self._render(interaction)

    @discord.ui.button(label="Show Locked", style=ButtonStyle.secondary, row=1)
    async def toggle_button(self, interaction: Interaction, button: discord.ui.Button):
        self.mode_locked = not self.mode_locked
        self.start = 0
        await self._render(interaction)

    @discord.ui.button(emoji="◀️", style=ButtonStyle.secondary, row=1)
    async def prev_button(self, interaction: Interaction, button: discord.ui.Button):
        self.start = max(0, self.start - 10)
        await self._render(interaction)

    @discord.ui.button(emoji="▶️", style=ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: Interaction, button: discord.ui.Button):
        self.start = self.start + 10
        await self._render(interaction)

# Public opener (per-guild)
async def open_achievements_menu(pool: asyncpg.Pool, ctx, user_id: int):
    await ensure_schema(pool)
    async with pool.acquire() as con:
        cats = await _fetch_categories(con)
    cats = _ordered_categories(cats)
    initial = cats[0] if cats else "General"

    guild_id = game_helpers.gid_from_ctx(ctx)
    if guild_id is None:
        return await ctx.send("Achievements are only available in servers.")

    view = AchievementsView(ctx, pool, user_id, guild_id, initial, cats)
    await view._render()