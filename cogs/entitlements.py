# cogs/entitlements.py
import logging
import random
from discord.ext import commands, tasks
from services.monetization import sync_entitlements, IS_DEV

BASE_INTERVAL = 10 * 60         # 10 minutes
MAX_INTERVAL  = 60 * 60         # cap at 60 minutes

class EntitlementSync(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._current_interval = BASE_INTERVAL
        # start loop once the bot is ready
        self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()

    @tasks.loop(seconds=BASE_INTERVAL, reconnect=True)
    async def sync_loop(self):
        if IS_DEV:
            return
        try:
            logging.info("[entitlements] sync run starting")
            await sync_entitlements(self.bot.db_pool)  # uses 429-aware fetcher you added
            logging.info("[entitlements] sync complete")

            # success: reset interval to base (+tiny jitter)
            self._current_interval = BASE_INTERVAL + random.randint(0, 5)
            self.sync_loop.change_interval(seconds=self._current_interval)
        except Exception:
            logging.exception("[entitlements] sync failed")

            # AIMD backoff: double the interval (cap at MAX_INTERVAL), add jitter
            self._current_interval = min(MAX_INTERVAL, max(BASE_INTERVAL, self._current_interval * 2))
            self._current_interval += random.randint(0, 5)
            self.sync_loop.change_interval(seconds=self._current_interval)
            logging.info(f"[entitlements] backoff → next run in ~{self._current_interval}s")

    @sync_loop.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

        # One-shot immediate sync on startup (doesn't rely on the loop interval)
        if not IS_DEV:
            try:
                logging.info("[entitlements] initial sync starting…")
                await sync_entitlements(self.bot.db_pool)
                logging.info("[entitlements] initial sync complete")
            except Exception:
                logging.exception("[entitlements] initial sync failed")
            # ensure first scheduled interval honours base (with jitter)
            self._current_interval = BASE_INTERVAL + random.randint(0, 5)
            self.sync_loop.change_interval(seconds=self._current_interval)

async def setup(bot: commands.Bot):
    await bot.add_cog(EntitlementSync(bot))
