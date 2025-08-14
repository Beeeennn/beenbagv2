# db/pool.py
import ssl
import asyncpg
from urllib.parse import urlparse


# db/pool.py
import os, ssl
import asyncpg
from urllib.parse import urlparse, parse_qs

_pool: asyncpg.Pool | None = None

def _is_local_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower()
    return host in ("localhost", "127.0.0.1") or host.endswith(".local")

def _needs_encrypted_no_verify(dsn: str) -> bool:
    """Treat ?sslmode=require like 'encrypt but don't verify' (libpq behavior)."""
    q = parse_qs(urlparse(dsn).query or "")
    sm = (q.get("sslmode", [""])[0] or "").lower()
    # default to True for remote hosts even if sslmode not present
    return sm in ("require", "prefer") or sm == ""  # prefer/empty -> allow

def _make_require_ctx() -> ssl.SSLContext:
    # Encrypt the connection but skip certificate/hostname verification
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

async def init_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    host = urlparse(dsn).hostname
    ssl_param = None
    if not _is_local_host(host) and _needs_encrypted_no_verify(dsn):
        ssl_param = _make_require_ctx()  # like sslmode=require
    _pool = await asyncpg.create_pool(dsn, ssl=ssl_param, command_timeout=60)
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
