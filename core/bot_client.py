# core/bot_client.py
import logging
import asyncpg
from discord.ext import commands

from db.pool import init_pool  # your existing initializer
from utils import prefixes
from config import settings     # adjust import to wherever DATABASE_URL lives

log = logging.getLogger("beenbag.bot")

class BeenBag(commands.Bot):
    def __init__(self, db_pool=None, **kwargs):
        super().__init__(**kwargs)
        self.db_pool = db_pool
        self._bg_tasks = set()

    async def _ensure_open_pool(self):
        """Ensure self.db_pool exists and is usable; recreate if it's closed."""
        if self.db_pool is None:
            self.db_pool = await init_pool(settings.DATABASE_URL)
            return

        # Try a cheap query to verify usability; recreate on failure
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
        # 1) Make sure the pool is alive
        await self._ensure_open_pool()

        # 2) Warm caches; if the pool dies between here and acquire, rebuild once
        try:
            await prefixes.warm_prefix_cache(self.db_pool)
        except asyncpg.exceptions.InterfaceError as e:
            if "pool is closed" in str(e):
                log.warning("Pool closed during warm_prefix_cache; rebuilding once.")
                self.db_pool = await init_pool(settings.DATABASE_URL)
                await prefixes.warm_prefix_cache(self.db_pool)
            else:
                raise

        # 3) Load cogs
        for ext in (
            "cogs.admin",
            "cogs.events",
            "cogs.general",
            "cogs.game",
            "cogs.leaderboard",
        ):
            try:
                await self.load_extension(ext)
            except Exception:
                log.exception("Failed to load extension %s", ext)

    async def close(self):
        # Do NOT close the shared DB pool here; the outer runner owns it.
        for t in list(self._bg_tasks):
            t.cancel()
        await super().close()
