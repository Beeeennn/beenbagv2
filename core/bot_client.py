# core/bot_client.py
import logging, asyncpg, discord
from discord.ext import commands
from db.pool import init_pool
from utils import prefixes
from cogs.link_comments_api import setup_comment_link_listener_api
from config import settings
from core.outbox import MessageOutbox
log = logging.getLogger("beenbag.bot")

class BeenBag(commands.Bot):
    def __init__(self, db_pool=None, **kwargs):
        intents = kwargs.get("intents", discord.Intents.default())
        intents.members = True
        intents.message_content = True

        kwargs["intents"] = intents

        # ✅ strip_after_prefix lets "! help" work
        kwargs.setdefault("command_prefix", lambda b, m: commands.when_mentioned_or("!")(b, m))
        kwargs.setdefault("strip_after_prefix", True)

        # ✅ make commands case-insensitive
        kwargs.setdefault("case_insensitive", True)

        super().__init__(**kwargs)

        self.db_pool = db_pool
        self.state = {}
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
        # start DM outbox BEFORE starting background jobs
        self.outbox = MessageOutbox(self, per_second=3.0)
        await self.outbox.start()
        # ✅ start the global YouTube comment poller here
        setup_comment_link_listener_api(
            self,              # the bot instance
            self.db_pool,      # your asyncpg pool
            settings.YT_API_KEY,
            settings.YT_VERIFY_VIDEO_ID,
        )

        for ext in ("cogs.base","cogs.jokes","cogs.mcprofile","cogs.entitlements",
                    "cogs.help","cogs.admin","cogs.events","cogs.general",
                    "cogs.game","cogs.leaderboard","cogs.background","cogs.stream_watch"):
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
        
