# core/bot_client.py
import logging
import asyncpg
import discord
from discord.ext import commands

from db.pool import init_pool
from utils import prefixes       # you already have warm_prefix_cache here
from config import settings      # where DATABASE_URL lives

log = logging.getLogger("beenbag.bot")

def _prefix_callable(bot, message):
    # use your warmed cache; default "!"
    gid = message.guild.id if message and message.guild else None
    base = prefixes.get_cached_prefix(gid)  # implement if you don't have it (see note below)
    return commands.when_mentioned_or(base)(bot, message)

class BeenBag(commands.Bot):
    def __init__(self, db_pool=None, **kwargs):
        # fallback prefix & intents if not provided by caller
        if "command_prefix" not in kwargs:
            kwargs["command_prefix"] = _prefix_callable
        if "intents" not in kwargs:
            intents = discord.Intents.default()
            # enable this if you use classic prefix commands that read message content
            intents.message_content = True
            kwargs["intents"] = intents

        super().__init__(**kwargs)
        self.db_pool = db_pool
        self._bg_tasks = set()

    async def _ensure_open_pool(self):
        if self.db_pool is None:
            self.db_pool = await init_pool(settings.DATABASE_URL)
            return
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
        # warm the prefix cache (resilient once-retry)
        try:
            await prefixes.warm_prefix_cache(self.db_pool)
        except asyncpg.exceptions.InterfaceError as e:
            if "pool is closed" in str(e):
                log.warning("Pool closed during warm_prefix_cache; rebuilding once.")
                self.db_pool = await init_pool(settings.DATABASE_URL)
                await prefixes.warm_prefix_cache(self.db_pool)
            else:
                raise

        for ext in ("cogs.admin", "cogs.events", "cogs.general", "cogs.game", "cogs.leaderboard"):
            try:
                await self.load_extension(ext)
            except Exception:
                log.exception("Failed to load extension %s", ext)

    async def close(self):
        # don't close the shared DB pool here; outer runner owns it
        for t in list(self._bg_tasks):
            t.cancel()
        await super().close()
