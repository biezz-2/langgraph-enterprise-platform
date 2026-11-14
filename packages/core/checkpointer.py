"""
LGP v2.0 Checkpoint Persistence Layer
Menggunakan psycopg 3 dan AsyncPostgresSaver dengan isolasi skema 'langgraph' (ADR-011).
Mendukung multi-loop asyncio dan fallback ke MemorySaver.
"""

import os
import logging
import asyncio
from typing import Optional
from urllib.parse import urlparse
from dotenv import load_dotenv

import psycopg
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver

load_dotenv()

logger = logging.getLogger("packages.core.checkpointer")

SUPABASE_SCHEMA = os.environ.get("SUPABASE_SCHEMA", "langgraph")
USE_SUPABASE = os.environ.get("USE_SUPABASE", "false").lower() == "true"

_pool: Optional[AsyncConnectionPool] = None
_pool_loop: Optional[asyncio.AbstractEventLoop] = None
_saver_instance: Optional[AsyncPostgresSaver] = None
_saver_loop: Optional[asyncio.AbstractEventLoop] = None
_setup_completed: bool = False


def get_postgres_conninfo() -> Optional[str]:
    """Menyusun connection URI PostgreSQL dari konfigurasi environment."""
    supabase_url = os.environ.get("SUPABASE_URL")
    db_host = os.environ.get("SUPABASE_DB_HOST")
    db_port = int(os.environ.get("SUPABASE_DB_PORT", 5432))
    db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    db_user = os.environ.get("SUPABASE_DB_USER", "postgres")
    db_password = os.environ.get("SUPABASE_DB_PASSWORD", "")

    if not db_host and supabase_url:
        parsed = urlparse(supabase_url)
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432

    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not db_password and service_role_key:
        db_password = service_role_key.split("_")[-1]

    if not db_host or not db_password:
        return None

    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


async def get_checkpointer_pool(schema: Optional[str] = None) -> Optional[AsyncConnectionPool]:
    """Mengembalikan connection pool psycopg 3 dengan max 5 koneksi (ADR-011) dan isolasi skema."""
    global _pool, _pool_loop
    target_schema = schema or SUPABASE_SCHEMA
    conninfo = get_postgres_conninfo()
    if not conninfo:
        logger.warning("PostgreSQL credentials tidak lengkap untuk checkpointer.")
        return None

    curr_loop = asyncio.get_running_loop()
    if _pool is not None and not _pool.closed and _pool_loop is curr_loop and not curr_loop.is_closed():
        return _pool

    if _pool is not None:
        try:
            if not _pool.closed:
                await _pool.close()
        except Exception:
            pass
        _pool = None
        _pool_loop = None

    # Pastikan skema dibuat terlebih dahulu jika belum ada
    try:
        async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as init_conn:
            async with init_conn.cursor() as cur:
                await cur.execute(f"CREATE SCHEMA IF NOT EXISTS {target_schema};")
    except Exception as e:
        logger.error("Gagal memastikan skema %s: %s", target_schema, e)
        return None

    # ADR-011: Max 5 client connections untuk psycopg pool
    new_pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=1,
        max_size=5,
        timeout=10.0,
        kwargs={
            "options": f"-c search_path={target_schema},public",
            "autocommit": True
        },
        open=False
    )
    await new_pool.open(wait=True, timeout=10.0)
    _pool = new_pool
    _pool_loop = curr_loop
    logger.info("Psycopg 3 AsyncConnectionPool checkpointer aktif (schema=%s, max_size=5)", target_schema)
    return _pool


async def close_checkpointer_pool() -> None:
    """Menutup connection pool checkpointer secara bersih."""
    global _pool, _pool_loop, _saver_instance, _saver_loop
    if _pool is not None and not _pool.closed:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None
        _pool_loop = None
    _saver_instance = None
    _saver_loop = None


async def get_async_postgres_saver(schema: Optional[str] = None) -> Optional[AsyncPostgresSaver]:
    """Mengembalikan instance AsyncPostgresSaver dengan setup tabel skema terisolasi."""
    global _saver_instance, _saver_loop, _setup_completed
    target_schema = schema or SUPABASE_SCHEMA
    curr_loop = asyncio.get_running_loop()

    pool = await get_checkpointer_pool(target_schema)
    if pool is None:
        return None

    if _saver_instance is not None and _saver_loop is curr_loop and not curr_loop.is_closed():
        return _saver_instance

    saver = AsyncPostgresSaver(pool)
    if not _setup_completed:
        await saver.setup()
        _setup_completed = True
        logger.info("AsyncPostgresSaver setup selesai pada skema '%s'", target_schema)

    _saver_instance = saver
    _saver_loop = curr_loop
    return _saver_instance


async def get_checkpointer(schema: Optional[str] = None, fallback_to_memory: bool = True) -> BaseCheckpointSaver:
    """Factory pembuat checkpointer: AsyncPostgresSaver jika DB tersedia, MemorySaver sebagai fallback."""
    target_schema = schema or SUPABASE_SCHEMA
    conninfo = get_postgres_conninfo()
    if USE_SUPABASE and conninfo:
        try:
            saver = await get_async_postgres_saver(target_schema)
            if saver is not None:
                return saver
        except Exception as e:
            logger.warning("Gagal menginisialisasi AsyncPostgresSaver: %s. Fallback ke MemorySaver.", e)

    if not fallback_to_memory:
        raise RuntimeError(f"PostgreSQL Checkpointer tidak dapat diinisialisasi pada skema {target_schema}")

    logger.info("Menggunakan MemorySaver (in-memory checkpointer)")
    return MemorySaver()
