# somewhere central, e.g., services/discord_limits.py
import asyncio
import logging
from discord.errors import HTTPException

API_SEMAPHORE = asyncio.Semaphore(4)   # keep this small (2–5)

async def call_with_gate(coro, *, op_name:str="api", max_retries:int=5):
    """Run any discord.py REST coroutine behind a small global concurrency gate with backoff.
       Retries on Cloudflare HTML 429 (error 1015) and normal 429."""
    attempt = 0
    backoff = 5
    async with API_SEMAPHORE:
        while True:
            try:
                return await coro
            except HTTPException as e:
                txt = str(e)
                # Detect Cloudflare HTML 1015 or generic 429
                is_html_429 = "Access denied | discord.com used Cloudflare" in txt or "Error 1015" in txt
                is_json_429 = "429 Too Many Requests" in txt and not is_html_429
                if (is_html_429 or is_json_429) and attempt < max_retries:
                    attempt += 1
                    logging.warning(f"[{op_name}] 429/Cloudflare hit. attempt={attempt} backoff={backoff}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 300)  # cap at 5 minutes
                    continue
                raise
