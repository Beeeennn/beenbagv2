# somewhere central, e.g., services/discord_limits.py
import asyncio
import logging
from discord.errors import HTTPException

API_SEMAPHORE = asyncio.Semaphore(4)   # keep this small (2–5)
# services/discord_limits.py
import asyncio, random, logging
from typing import Callable, Awaitable

async def call_with_gate(
    op_factory: Callable[[], Awaitable],
    *,
    op_name: str,
    max_attempts: int = 5,
    base_backoff: float = 5.0,
):
    attempt = 1
    while True:
        try:
            return await op_factory()  # create a *new* coroutine each attempt
        except Exception as e:
            # 429 / Cloudflare or transient network issues — backoff + retry
            if attempt >= max_attempts:
                raise
            delay = base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logging.warning(f"[{op_name}] transient error; attempt={attempt} backoff={delay:.1f}s: {e}")
            await asyncio.sleep(delay)
            attempt += 1