# db/pool.py
import ssl
import asyncpg
from urllib.parse import urlparse


async def _init_conn(conn: asyncpg.Connection) -> None:
    # Optional: keep timestamps consistent and avoid per-session surprises
    await conn.execute("SET TIME ZONE 'UTC';")
    # If you use schemas, you can also do:
    # await conn.execute("SET search_path TO public;")

async def init_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """
    Creates a pool with TLS on non-local hosts, no TLS on localhost.
    Works with Render's External Database URL and your local Postgres.
    """
    global _pool
    u = urlparse(dsn)
    host = (u.hostname or "").lower()

    ssl_ctx = None
    if host not in {"localhost", "127.0.0.1"}:
        # Remote DB (e.g., Render) → enable TLS
        ssl_ctx = ssl.create_default_context()

    _pool = await asyncpg.create_pool(
        dsn,
        ssl=ssl_ctx,                 # TLS only when remote
        min_size=min_size,
        max_size=max_size,
        command_timeout=60,          # seconds; applies to all commands
        init=_init_conn,             # run once per new connection
    )
    return _pool

async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialised"
    return _pool