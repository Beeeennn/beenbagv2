# services/monetization.py
from __future__ import annotations
import os
import aiohttp
from typing import Optional
import asyncpg
import logging
from datetime import datetime, timezone
PREMIUM_SKU_ID = 1405934572436193462  # "premium"
IS_DEV = os.getenv("ENV", "").lower() == "dev"



DISCORD_API = "https://discord.com/api/v10"

import time
from typing import Dict, Tuple

CACHE_TTL_SECONDS = 60  # short TTL so negatives don't stick

# user_id -> (has_premium, expires_at_epoch)
_premium_cache: Dict[int, Tuple[bool, float]] = {}

def _cache_put(user_id: int, has: bool, ttl: int = CACHE_TTL_SECONDS) -> None:
    _premium_cache[user_id] = (has, time.time() + ttl)

def _cache_get(user_id: int) -> Tuple[bool, bool]:
    """
    Returns (has_premium, fresh).
    fresh=False means caller should not trust this and should refresh (async).
    """
    item = _premium_cache.get(user_id)
    if not item:
        return (False, False)
    has, exp = item
    if exp <= time.time():
        return (False, False)
    return (has, True)

def peek_premium(user_id: int) -> bool:
    """
    Sync, non-blocking check used by cooldown decorators.
    Returns cached value only; may be slightly stale. If no fresh entry, returns False.
    """
    if IS_DEV:
        return True
    has, fresh = _cache_get(user_id)
    return has if fresh else False

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


# services/monetization.py
import os
import time
from typing import Iterable, Optional

import asyncpg
import aiohttp

APP_ID = int(os.environ["APPLICATION_ID"])         # your bot application id
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]            # your bot token
IS_DEV = os.getenv("ENV", "").lower() == "dev"
PREMIUM_SKU_STR = str(PREMIUM_SKU_ID)
async def has_premium(pool, user_id: int) -> bool:
    if IS_DEV:
        return True

    # Try cache first; if fresh, return immediately
    has, fresh = _cache_get(user_id)
    if fresh:
        return has

    # Otherwise, hit DB and refresh cache
    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT 1
            FROM premium_users
            WHERE user_id=$1
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            user_id,
        )
        has = row is not None
    _cache_put(user_id, has)
    return has
async def grant_premium(con, user_id: int, sku_id: int | str, expires_at: str | None):
    await con.execute(
        """
        INSERT INTO premium_users (user_id, sku_id, expires_at, granted_at)
        VALUES ($1, $2::bigint, $3::timestamptz, NOW())
        ON CONFLICT (user_id) DO UPDATE
          SET sku_id    = EXCLUDED.sku_id,
              expires_at= EXCLUDED.expires_at,
              granted_at= NOW()
        """,
        user_id, int(sku_id), expires_at,
    )
    _cache_put(user_id, True)

async def revoke_premium(con: "asyncpg.Connection", user_id: int):
    await con.execute("DELETE FROM premium_users WHERE user_id=$1", user_id)
    _cache_put(user_id, False)

# -------- Periodic full sync from REST (Option A) --------

API = "https://discord.com/api/v10"

async def _fetch_entitlements_page(session, before: str | None = None):
    params = {
        "application_id": str(APP_ID),
        "limit": "100",
        "sku_ids": PREMIUM_SKU_STR,  # only your premium SKU
        "exclude_deleted": "true",
        "exclude_ended": "true",     # trims most expired subs
    }
    if before:
        params["before"] = before
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    async with session.get(
        f"{API}/applications/{APP_ID}/entitlements",
        headers=headers, params=params, timeout=15
    ) as resp:
        resp.raise_for_status()
        return await resp.json()
    
def is_active_entitlement(e: dict, now: datetime) -> bool:
    if e.get("deleted"):
        return False
    # for consumables, you may want to exclude consumed entitlements
    if e.get("consumed"):
        return False
    starts = e.get("starts_at")
    ends   = e.get("ends_at") or e.get("expires_at")  # some payloads use ends_at
    if starts and datetime.fromisoformat(starts.replace("Z","+00:00")) > now:
        return False
    if ends:
        if datetime.fromisoformat(ends.replace("Z","+00:00")) <= now:
            return False
    return True

async def fetch_all_entitlements(session):
    out, before = [], None
    while True:
        page = await _fetch_entitlements_page(session, before)
        if not page:
            break
        out.extend(page)
        before = page[-1]["id"]
        if len(page) < 100:
            break
    return out

async def sync_entitlements(pool):
    logging.info("Syncing entitlements")
    async with aiohttp.ClientSession() as session:
        ents = await fetch_all_entitlements(session)

    now = datetime.now(timezone.utc)
    current = []
    for e in ents:
        if str(e.get("sku_id")) != PREMIUM_SKU_STR:
            continue
        if not is_active_entitlement(e, now):
            continue
        user_id = int(e["user_id"])
        # active subs often have no ends_at; store NULL for “indefinite (for now)”
        expires_at = e.get("ends_at") or e.get("expires_at")
        current.append((user_id, expires_at))

    async with pool.acquire() as con:
        async with con.transaction():
            existing = {r["user_id"] for r in await con.fetch("SELECT user_id FROM premium_users")}
            for uid, exp in current:
                await grant_premium(con, uid, PREMIUM_SKU_ID, exp)
            current_ids = {uid for uid, _ in current}
            to_revoke = existing - current_ids
            if to_revoke:
                await con.executemany("DELETE FROM premium_users WHERE user_id=$1", [(u,) for u in to_revoke])
            await con.execute("""
                DELETE FROM premium_users
                WHERE expires_at IS NOT NULL AND expires_at <= NOW()
            """)

    # Warm caches (optional but nice)
    for uid, _ in current:
        _cache_put(uid, True)
    for uid in (existing - {u for u, _ in current}):
        _cache_put(uid, False)
    logging.info(f"{len(current)} members have premium")