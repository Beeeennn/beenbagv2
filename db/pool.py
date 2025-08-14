# db/pool.py
import ssl, asyncpg
from urllib.parse import urlparse, parse_qs

_pool: asyncpg.Pool | None = None

def _is_local_host(host: str | None) -> bool:
    return bool(host) and (host.lower() in ("localhost", "127.0.0.1") or host.lower().endswith(".local"))

def _make_require_ctx() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

async def init_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    host = urlparse(dsn).hostname
    ssl_ctx = None if _is_local_host(host) else _make_require_ctx()
    _pool = await asyncpg.create_pool(dsn, ssl=ssl_ctx, command_timeout=60)
    return _pool

def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized yet")
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None