# db/pool.py
import asyncpg
_pool: asyncpg.Pool | None = None

async def init_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(dsn, command_timeout=60)
    return _pool

def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialised"
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
