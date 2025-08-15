# services/monetization.py
from __future__ import annotations
import os
import aiohttp
from typing import Optional
import asyncpg


DISCORD_API = "https://discord.com/api/v10"

def _app_and_token() -> tuple[str, str]:
    app_id = os.getenv("DISCORD_APP_ID") or os.getenv("APPLICATION_ID")
    token  = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not app_id or not token:
        raise RuntimeError("Set DISCORD_APP_ID and DISCORD_BOT_TOKEN in env.")
    return app_id, token

async def fetch_user_entitlement(user_id: int, sku_id: str) -> Optional[dict]:
    """
    Return the newest entitlement dict for (user, sku) or None.
    Durable entitlements don't need consuming.
    """
    app_id, token = _app_and_token()
    url = f"{DISCORD_API}/applications/{app_id}/entitlements"
    params = {
        "user_id": str(user_id),
        "sku_ids": sku_id,
        "exclude_consumed": "false",  # include all; caller can decide
        "limit": "100"
    }
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Entitlements GET {resp.status}: {text}")
            items = await resp.json()
    if not items:
        return None
    # choose the most recent, just in case
    items.sort(key=lambda e: e.get("starts_at") or "", reverse=True)
    return items[0]

async def consume_entitlement(entitlement_id: str) -> None:
    """
    For CONSUMABLE SKUs only. Not needed for durable cosmetics.
    """
    app_id, token = _app_and_token()
    url = f"{DISCORD_API}/applications/{app_id}/entitlements/{entitlement_id}/consume"
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, headers=headers) as resp:
            if resp.status not in (200, 204):
                text = await resp.text()
                raise RuntimeError(f"Entitlement consume {resp.status}: {text}")
            
import os, time
from typing import Dict, Tuple

PREMIUM_SKU_ID = 1405934572436193462  # "premium"
IS_DEV = os.getenv("ENV", "").lower() == "dev"

# user_id -> (has_premium, expires_at_epoch)
_premium_cache: Dict[int, Tuple[bool, float]] = {}

def peek_premium(user_id: int) -> bool:
    """Sync, non-blocking check used by cooldown decorators.
    Returns cached value only; may be slightly stale."""
    if IS_DEV:
        return True
    now = time.time()
    cached = _premium_cache.get(user_id)
    if not cached:
        return False
    has, exp = cached
    # Only trust if still fresh
    return has if exp > now else False

async def has_premium(pool, user_id: int) -> bool:
    """Authoritative async check; refreshes the cache (60s TTL)."""
    if IS_DEV:
        return True
    now = time.time()
    cached = _premium_cache.get(user_id)
    if cached and cached[1] > now:
        return cached[0]

    async with pool.acquire() as con:
        has = bool(
            await con.fetchval(
                """
                SELECT 1
                FROM entitlements
                WHERE user_id=$1 AND sku_id=$2
                  AND (expires_at IS NULL OR expires_at > NOW())
                LIMIT 1
                """,
                user_id, PREMIUM_SKU_ID
            )
        )

    _premium_cache[user_id] = (has, now + 60.0)  # 60s TTL
    return has