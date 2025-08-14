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
        "category":"Challanging",
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
        "description": "catch a zombie while you have a chicken in your barn", #################
        "exp": 5,
        "hidden": True,
        "repeatable": False,    
        "category":"Starter",   
    },
    "1000_ems":{
        "name": "Slightly Rich",
        "description": "Have 1000 emeralds", ###############
        "exp": 20,
        "hidden": False,
        "repeatable": False,      
        "category":"Challenging", 
    },
    "10000_ems":{
        "name": "Very Rich",
        "description": "Have 10000 emeralds", ###################
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
# --- helpers to work with Context OR Message -------------------------------
from typing import List  # at top with your other typing imports

def _lines_to_embeds(title: str, lines: List[str], color: Color, author=None, icon_url=None) -> List[Embed]:
    """
    Split a long list of lines into multiple embeds safely (Discord ~6k hard cap;
    stay well under by limiting description to ~3800 chars).
    """
    chunks: List[List[str]] = []
    cur: List[str] = []
    cur_len = 0
    limit = 3800  # leave room for title/headers/footers

    for line in lines:
        ln = len(line) + 1
        if cur_len + ln > limit:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += ln
    if cur:
        chunks.append(cur)

    embeds: List[Embed] = []
    for i, chunk in enumerate(chunks, 1):
        e = Embed(title=title, description="\n".join(chunk), color=color)
        if author:
            e.set_author(name=author, icon_url=icon_url)
        if len(chunks) > 1:
            e.set_footer(text=f"Page {i}/{len(chunks)}")
        embeds.append(e)
    return embeds

def render_achievements_embeds(user, owned: List[dict], not_owned: List[dict]) -> List[Embed]:
    """
    Build one or more embeds listing unlocked and locked (non-hidden) achievements.
    Expects the shape returned by list_user_achievements().
    """
    # Unlocked
    owned_lines: List[str] = []
    for o in owned:
        name = o["name"]
        desc = o["description"]
        exp  = o["exp"]
        rpt  = f" ×{o['times_awarded']}" if o.get("repeatable") and o.get("times_awarded", 1) > 1 else ""
        owned_lines.append(f"• **{name}**{rpt} — {desc} *(+{exp} EXP)*")

    # Locked (non-hidden already filtered by list_user_achievements)
    locked_lines: List[str] = []
    for n in not_owned:
        name = n["name"]
        desc = n["description"]
        exp  = n["exp"]
        locked_lines.append(f"• **{name}** — {desc} *(+{exp} EXP)*")

    # Author icon (avoid depending on _safe_avatar)
    icon_url = (
        getattr(getattr(user, "display_avatar", None), "url", None)
        or getattr(getattr(user, "avatar", None), "url", None)
    )

    embeds: List[Embed] = []
    if owned_lines:
        embeds += _lines_to_embeds(
            title=f"🏆 {user.display_name} — Unlocked ({len(owned)})",
            lines=owned_lines,
            color=Color.gold(),
            author=user.display_name,
            icon_url=icon_url,
        )
    if locked_lines:
        embeds += _lines_to_embeds(
            title=f"🔒 {user.display_name} — Locked ({len(not_owned)})",
            lines=locked_lines,
            color=Color.dark_grey(),
            author=user.display_name,
            icon_url=icon_url,
        )
    if not embeds:
        embeds = [Embed(title="Achievements", description="No achievements defined yet.", color=Color.blurple())]
    return embeds
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

# Update sync_master to pass category (default "General")
async def sync_master(pool: asyncpg.Pool):
    async with pool.acquire() as con:
        async with con.transaction():
            for k, v in ACHIEVEMENTS.items():
                await con.execute(
                    UPSERT_SQL,
                    k,
                    v["name"],
                    v["description"],
                    v["exp"],
                    v.get("hidden", False),
                    v.get("repeatable", False),
                    v.get("category", "General"),
                )

# ------------------ fetch helpers for UI ------------------

async def _fetch_categories(conn) -> List[str]:
    rows = await conn.fetch("SELECT DISTINCT category FROM achievement ORDER BY 1")
    return [r["category"] for r in rows] or ["General"]

async def _fetch_category_rows(conn: asyncpg.Connection, category: str, user_id: int):
    """Return raw rows for a category with a LEFT JOIN on ownership."""
    rows = await conn.fetch(
        """
        SELECT a.key, a.name, a.description, a.exp, a.hidden, a.repeatable, a.category,
               ua.times_awarded, ua.unlocked_at
          FROM achievement a
          LEFT JOIN user_achievement ua
            ON ua.achievement_id = a.id AND ua.user_id = $2
         WHERE a.category = $1
         ORDER BY a.name
        """,
        category, user_id
    )
    return rows

def _row_to_line(r) -> str:
    """Format a single achievement row into a list line."""
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
    """
    mode_locked=False => show Unlocked
    mode_locked=True  => show Locked (non-hidden only)
    """
    # Filter rows according to mode
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

# ------------------ View (dropdown + arrows + locked/unlocked toggle) ------------------

class AchievementsView(discord.ui.View):
    def __init__(self, ctx, pool, user_id: int, initial_category: str, categories: List[str]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pool = pool
        self.user_id = user_id
        self.category = initial_category
        self.categories = categories
        self.mode_locked = False  # False = show unlocked; True = show locked
        self.start = 0
        self.cache: Dict[str, List[asyncpg.Record]] = {}  # raw rows per category

        # Populate the select options
        self.category_select.options = [
            discord.SelectOption(label=c, value=c, default=(c == self.category)) for c in categories
        ]

    async def _load(self):
        async with self.pool.acquire() as con:
            if self.category not in self.cache:
                self.cache[self.category] = await _fetch_category_rows(con, self.category, self.user_id)

    async def _render(self, interaction: Interaction | None = None):
        await self._load()
        rows = self.cache.get(self.category, [])
        # determine total after filter to set button states
        if self.mode_locked:
            total = len([r for r in rows if r["times_awarded"] is None and not r["hidden"]])
        else:
            total = len([r for r in rows if r["times_awarded"] is not None])

        # button states
        self.prev_button.disabled = (self.start <= 0)
        self.next_button.disabled = (self.start + 10 >= total)
        self.toggle_button.label = "Show Locked" if not self.mode_locked else "Show Unlocked"
        self.toggle_button.style = ButtonStyle.primary if self.mode_locked else ButtonStyle.secondary

        embed = _build_achievements_embed(self.ctx, category=self.category, mode_locked=self.mode_locked,
                                          rows=rows, start=self.start)
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await self.ctx.send(embed=embed, view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Only the invoker can use this view
        return interaction.user.id == self.ctx.author.id

    @discord.ui.select(placeholder="Select a category…", min_values=1, max_values=1, row=0)
    async def category_select(self, interaction: Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        # reset paging when switching category
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

# ------------------ Public opener ------------------

async def open_achievements_menu(pool: asyncpg.Pool, ctx, user_id: int):
    """Send the interactive Achievements menu for this user."""
    # Ensure the schema has category column
    await ensure_schema(pool)

    async with pool.acquire() as con:
        cats = await _fetch_categories(con)
    view = AchievementsView(ctx, pool, user_id, cats[0], cats)
    await view._render()