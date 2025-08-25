# core/outbox.py
import asyncio, logging
from contextlib import suppress

class MessageOutbox:
    """Single-worker queue that paces DMs to avoid Discord rate limits."""
    def __init__(self, bot, per_second: float = 3.0):
        self.bot = bot
        self.queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        # ~3 DMs/sec is very gentle. Adjust if needed.
        self.min_delay = 1.0 / max(per_second, 0.1)

    async def start(self):
        if self._task:  # already running
            return
        self._task = asyncio.create_task(self._run(), name="dm_outbox")

    async def stop(self):
        if not self._task:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def dm(self, user_id: int, content: str):
        """Queue a DM to a user ID."""
        await self.queue.put((user_id, content))

    async def _run(self):
        from services.discord_limits import call_with_gate
        while True:
            user_id, content = await self.queue.get()
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                dm = user.dm_channel or await user.create_dm()
                # Use your retry/backoff wrapper
                await call_with_gate(lambda: dm.send(content), op_name="dm_send")
            except Exception as e:
                logging.warning("DM failed to %s: %s", user_id, e)
            finally:
                # Pace to avoid bursts
                await asyncio.sleep(self.min_delay)
                self.queue.task_done()
