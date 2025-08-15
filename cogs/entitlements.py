# cogs/entitlements.py
import asyncio
import logging
from discord.ext import commands, tasks
from services.monetization import sync_entitlements, IS_DEV

SYNC_EVERY_SECONDS = 600  # 10 minutes; you can use 300 (5m) if you prefer

class EntitlementSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # start loop once the bot is ready
        self._task = self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()

    @tasks.loop(seconds=SYNC_EVERY_SECONDS)
    async def sync_loop(self):
        if IS_DEV:
            return
        try:
            await sync_entitlements(self.bot.db_pool)
            logging.info("[entitlements] sync complete")
        except Exception:
            logging.exception("[entitlements] sync failed")

    @sync_loop.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(EntitlementSync(bot))
