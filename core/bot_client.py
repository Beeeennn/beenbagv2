# core/bot_client.py
import logging, asyncpg, discord
from discord.ext import commands
from db.pool import init_pool
from utils import prefixes
from config import settings

log = logging.getLogger("beenbag.bot")

class BeenBag(commands.Bot):
    def __init__(self, db_pool=None, **kwargs):
        # sensible defaults if not provided by the caller
        intents = kwargs.get("intents", discord.Intents.default())
        # ✅ enable the privileged members intent for on_member_join
        intents.members = True
        # (optional) you already use prefix commands; keep message_content on
        intents.message_content = True

        kwargs["intents"] = intents
        kwargs.setdefault("command_prefix", lambda b, m: commands.when_mentioned_or("!")(b, m))
        kwargs.setdefault("strip_after_prefix", True)

        super().__init__(**kwargs)
        self.db_pool = db_pool
        self.state = {}              # for tasks/spawns.py
        self._bg_tasks = set()

        log.info("Intents set: members=%s, message_content=%s",
                 self.intents.members, self.intents.message_content)

    async def _ensure_open_pool(self):
        if self.db_pool is None:
            self.db_pool = await init_pool(settings.DATABASE_URL); return
        try:
            async with self.db_pool.acquire() as con:
                await con.execute("SELECT 1")
        except asyncpg.exceptions.InterfaceError as e:
            if "pool is closed" in str(e):
                log.warning("DB pool was closed; reinitializing.")
                self.db_pool = await init_pool(settings.DATABASE_URL)
            else:
                raise

    async def setup_hook(self):
        await self._ensure_open_pool()
        try:
            await prefixes.warm_prefix_cache(self.db_pool)
        except asyncpg.exceptions.InterfaceError as e:
            if "pool is closed" in str(e):
                self.db_pool = await init_pool(settings.DATABASE_URL)
                await prefixes.warm_prefix_cache(self.db_pool)
            else:
                raise

        for ext in ("cogs.base","cogs.jokes","cogs.mcprofile","cogs.entitlements",
                    "cogs.help","cogs.admin","cogs.events","cogs.general",
                    "cogs.game","cogs.leaderboard","cogs.background"):
            try:
                await self.load_extension(ext)
            except Exception:
                log.exception("Failed to load extension %s", ext)

    async def close(self):
        # cancel any spawn/background tasks stored by your spawner
        try:
            for t in list(self.state.get("spawn_tasks", {}).values()):
                t.cancel()
        except Exception:
            pass
        await super().close()
