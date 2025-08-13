# bot.py
import asyncio
from core.bot_client import BeenBag
from config import settings
from db.pool import init_pool, close_pool, get_pool
from http_server.server import start_http_server, stop_http_server
print("=== BOT.PY ENTRYPOINT REACHED ===")
import logging
logging.basicConfig(level=logging.INFO)
logging.info("Bot starting… (this is before anything else runs)")

async def run():
    pool = await init_pool(settings.DATABASE_URL)
    bot = BeenBag(db_pool=pool)

    # start HTTP server
    runner = await start_http_server(port=settings.PORT, db_pool=pool)

    try:
        await bot.start(settings.DISCORD_BOT_TOKEN)
    finally:
        await stop_http_server(runner)
        await bot.shutdown_background_tasks()
        await close_pool()

if __name__ == "__main__":
    asyncio.run(run())
