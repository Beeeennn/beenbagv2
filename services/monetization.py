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

# services/monetization.py
import os
import time
from typing import Iterable, Optional

import asyncpg
import aiohttp

APP_ID = int(os.environ["APPLICATION_ID"])         # your bot application id
BOT_TOKEN = os.environ["DISCORD_TOKEN"]            # your bot token
PREMIUM_SKU_ID = 1405934572436193462               # your Premium SKU
IS_DEV = os.getenv("ENV", "").lower() == "dev"

# tiny in-process cache for has_premium (reduce DB hits in busy chats)
_premium_cache: dict[int, tuple[bool, float]] = {}  # user_id -> (has, expires_at_ts)

async def has_premium(pool: "asyncpg.Pool", user_id: int) -> bool:
    """Global premium: ENV=dev -> True; else check DB (with 60s cache)."""
    if IS_DEV:
        return True
    now = time.time()
    cached = _premium_cache.get(user_id)
    if cached and cached[1] > now:
        return cached[0]

    async with pool.acquire() as con:
        has = bool(await con.fetchval(
            "SELECT 1 FROM premium_users WHERE user_id=$1 AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1",
            user_id
        ))
    _premium_cache[user_id] = (has, now + 60)
    return has

async def grant_premium(con: "asyncpg.Connection", user_id: int, sku_id: int, expires_at: Optional[str]):
    await con.execute(
        """
        INSERT INTO premium_users (user_id, sku_id, expires_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
          SET sku_id=$2, expires_at=$3, granted_at=NOW()
        """,
        user_id, sku_id, expires_at
    )
    # bust cache
    _premium_cache.pop(user_id, None)

async def revoke_premium(con: "asyncpg.Connection", user_id: int):
    await con.execute("DELETE FROM premium_users WHERE user_id=$1", user_id)
    _premium_cache.pop(user_id, None)

# -------- Periodic full sync from REST (Option A) --------

API = "https://discord.com/api/v10"

async def _fetch_entitlements_page(session: aiohttp.ClientSession, before: Optional[str] = None):
    params = {
        "application_id": str(APP_ID),
        "limit": "100"
    }
    if before:
        params["before"] = before
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    async with session.get(f"{API}/applications/{APP_ID}/entitlements", headers=headers, params=params, timeout=15) as resp:
        resp.raise_for_status()
        return await resp.json()

async def fetch_all_entitlements(session: aiohttp.ClientSession) -> list[dict]:
    """Pull all entitlements for the application (paginated)."""
    out: list[dict] = []
    before = None
    while True:
        data = await _fetch_entitlements_page(session, before=before)
        if not data:
            break
        out.extend(data)
        # pagination: use the oldest id as 'before'
        before = data[-1]["id"]
        if len(data) < 100:
            break
    return out

async def sync_entitlements(pool: "asyncpg.Pool"):
    """
    Full reconciliation: fetch all app entitlements, filter to your premium SKU,
    upsert current rows, and remove rows that no longer exist (or are expired).
    """
    async with aiohttp.ClientSession() as session:
        entitlements = await fetch_all_entitlements(session)

    # Keep only your Premium SKU and valid entitlements
    current = []
    for e in entitlements:
        try:
            if int(e.get("sku_id", 0)) != PREMIUM_SKU_ID:
                continue
            # Discord returns user_id for user entitlements
            user_id = int(e["user_id"])
            # expires_at might be null; store as timestamptz or None
            expires_at = e.get("ends_at") or e.get("expires_at")
            current.append((user_id, expires_at))
        except Exception:
            continue

    # Reconcile DB
    async with pool.acquire() as con:
        async with con.transaction():
            # mark all existing premium users to diff later
            db_rows = await con.fetch("SELECT user_id FROM premium_users")
            existing = {r["user_id"] for r in db_rows}

            # upsert current
            for user_id, expires_at in current:
                await grant_premium(con, user_id, PREMIUM_SKU_ID, expires_at)

            # revoke users no longer present (and not in current list)
            current_ids = {u for (u, _) in current}
            to_revoke = existing - current_ids
            if to_revoke:
                await con.executemany("DELETE FROM premium_users WHERE user_id=$1", [(u,) for u in to_revoke])

            # also clean expired (belt-and-braces)
            await con.execute("DELETE FROM premium_users WHERE expires_at IS NOT NULL AND expires_at <= NOW()")

    # clear cache for any user we touched
    for user_id, _ in current:
        _premium_cache.pop(user_id, None)