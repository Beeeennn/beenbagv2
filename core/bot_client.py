# core/bot_client.py
import logging
import discord
from discord.ext import commands
from utils.prefixes import dynamic_prefix, warm_prefix_cache
from db.pool import init_pool
from config import settings


class BeenBag(commands.Bot):
    def __init__(self, **kwargs):
        intents = kwargs.pop("intents", discord.Intents.default())
        intents.message_content = True
        super().__init__(
            command_prefix=dynamic_prefix,
            case_insensitive=True,
            intents=intents,
            help_command=None,
            **kwargs
        )
        self.db_pool = None

        # Import here to avoid potential circulars
        from core.checks import only_in_game_channels
        self.add_check(only_in_game_channels())

    async def setup_hook(self):
        # create db pool and cache prefixes before cogs start using them
        self.db_pool = await init_pool(settings.DATABASE_URL)
        await warm_prefix_cache(self.db_pool)

        # load cogs
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
                logging.exception("Failed to load extension %s", ext)

    async def close(self):
        try:
            if self.db_pool:
                await self.db_pool.close()
        finally:
            await super().close()
    async def shutdown_background_tasks(self):
        # Stop any background loops or tasks here if needed
        pass
