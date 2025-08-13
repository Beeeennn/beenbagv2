# bot.py
import os, sys, asyncio, logging, random
from core.bot_client import BeenBag
from db.pool import init_pool, close_pool
from http_server.server import start_http_server, stop_http_server
from discord.errors import HTTPException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("beenbag.startup")

# Tunables
BACKOFF_START = 5         # seconds
BACKOFF_MAX   = 600       # 10 minutes cap
NON429_DELAY  = 30        # delay for non-429 HTTPException or generic errors

async def login_with_backoff(bot: BeenBag, token: str):
    """Keep trying to log in with exponential backoff + jitter on 429s."""
    backoff = BACKOFF_START
    while True:
        try:
            await bot.start(token)  # returns only on clean shutdown
            return
        except HTTPException as e:
            status = getattr(e, "status", None)
            if status == 429:
                # Cloudflare 1015 → 429 at /users/@me. Back off with jitter.
                jitter = random.uniform(0, backoff)
                wait = min(backoff + jitter, BACKOFF_MAX)
                log.warning("Discord login rate-limited (429). Retrying in %.1fs", wait)
                await asyncio.sleep(wait)
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue
            # Other HTTPException (network blip, 5xx, bad gateway, etc.)
            log.exception("Discord login HTTPException (status=%s). Retrying in %ss", status, NON429_DELAY)
            await asyncio.sleep(NON429_DELAY)
        except Exception:
            log.exception("Unhandled error during bot.start; retrying in %ss", NON429_DELAY)
            await asyncio.sleep(NON429_DELAY)

async def run():
    print("=== BOT.PY ENTRYPOINT REACHED ===", flush=True)

    # Render (web service) provides PORT. If not present, default for local dev.
    port = int(os.environ.get("PORT", "8080"))
    db_url = os.environ["DATABASE_URL"]
    token  = os.environ["DISCORD_BOT_TOKEN"]

    # Init DB and HTTP first so health checks pass even if Discord is blocked.
    pool = await init_pool(db_url)
    bot  = BeenBag(db_pool=pool)

    runner = await start_http_server(port=port, db_pool=pool)
    log.info("HTTP server listening on 0.0.0.0:%s (health: / or /healthz)", port)

    try:
        await login_with_backoff(bot, token)
    finally:
        # Clean shutdown: close bot session/connector, HTTP, and DB pool.
        try:
            await bot.close()
        except Exception:
            pass
        try:
            await stop_http_server(runner)
        except Exception:
            pass
        try:
            await close_pool()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
