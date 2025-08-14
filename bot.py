# bot.py
import os
import sys
import asyncio
import logging
import random

from discord.errors import HTTPException

from core.bot_client import BeenBag
from db.pool import init_pool, close_pool
from http_server.server import start_http_server, stop_http_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("beenbag.startup")

# Tunables
BACKOFF_START = 5          # seconds
BACKOFF_MAX   = 600        # 10 minutes cap
NON429_DELAY  = 30         # delay for non-429 HTTPException or generic errors


def _get_env() -> tuple[int, str, str]:
    """Fetch required environment values with minimal validation."""
    port = int(os.environ.get("PORT", "8080"))
    db_url = os.environ["DATABASE_URL"]
    token  = os.environ["DISCORD_BOT_TOKEN"]
    return port, db_url, token


def _new_bot(db_pool) -> BeenBag:
    """Factory to ensure a fresh Bot per login attempt."""
    return BeenBag(db_pool=db_pool)


async def login_with_backoff(token: str, db_pool):
    """
    Keep trying to log in with exponential backoff + jitter on 429s.
    IMPORTANT: We create a NEW bot each iteration and wrap it with
    'async with bot:' so the underlying aiohttp session always closes.
    """
    backoff = BACKOFF_START

    while True:
        bot = _new_bot(db_pool)

        try:
            async with bot:  # guarantees client session closes on exit
                await bot.start(token)
            # If we reach here, it was a clean shutdown (no retry).
            return

        except HTTPException as e:
            status = getattr(e, "status", None)
            if status == 429:
                # Cloudflare 1015/429 during /users/@me. Back off with jitter.
                jitter = random.uniform(0, backoff)
                wait = min(backoff + jitter, BACKOFF_MAX)
                log.warning("Discord login rate-limited (429). Retrying in %.1fs", wait)
                await asyncio.sleep(wait)
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue

            log.exception("Discord login HTTPException (status=%s). Retrying in %ss", status, NON429_DELAY)
            await asyncio.sleep(NON429_DELAY)
            continue

        except Exception:
            log.exception("Unhandled error during bot.start; retrying in %ss", NON429_DELAY)
            await asyncio.sleep(NON429_DELAY)
            continue


async def run():
    print("=== BOT.PY ENTRYPOINT REACHED ===", flush=True)

    port, db_url, token = _get_env()

    # Init DB and HTTP first so health checks pass even if Discord is blocked.
    pool = await init_pool(db_url)
    runner = await start_http_server(port=port, db_pool=pool)
    log.info("HTTP server listening on 0.0.0.0:%s (health: / or /healthz)", port)

    try:
        await login_with_backoff(token, pool)
    finally:
        # Clean shutdown of HTTP and DB resources.
        try:
            await stop_http_server(runner)
        except Exception:
            log.exception("Error while stopping HTTP server")
        try:
            await close_pool()
        except Exception:
            log.exception("Error while closing DB pool")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
