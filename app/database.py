import asyncpg
from typing import Optional
from app.config import get_settings

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
            init=_init_connection,
        )
    return _pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register pgvector codec so vector columns round-trip correctly."""
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.set_type_codec(
        "vector",
        encoder=lambda v: v,
        decoder=lambda v: v,
        schema="public",
        format="text",
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def execute_query(sql: str, *args, timeout: int = 5) -> list[dict]:
    """
    Run a SELECT query and return rows as a list of plain dicts.
    Raises ValueError if the SQL is not a SELECT statement.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(sql, *args, timeout=timeout)
    return [dict(r) for r in rows]
