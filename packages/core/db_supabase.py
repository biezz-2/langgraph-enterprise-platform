import os
import json
import hashlib
import time
from typing import List, Dict, Any, Optional, Union
import asyncpg
try:
    from supabase import create_client, Client, ClientOptions
except ImportError:
    create_client = None
    Client = None
    ClientOptions = None

# Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_SCHEMA = os.environ.get("SUPABASE_SCHEMA", "langgraph")
USE_SUPABASE = os.environ.get("USE_SUPABASE", "false").lower() == "true"

SUPABASE_DB_HOST = os.environ.get("SUPABASE_DB_HOST", "localhost")
SUPABASE_DB_PORT = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
SUPABASE_DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.environ.get("SUPABASE_DB_USER", "postgres")
SUPABASE_DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD", "")

# Global instances
supabase_client: Optional[Any] = None
_supabase_pool: Optional[asyncpg.Pool] = None

def is_supabase_configured() -> bool:
    """Check if Supabase credentials are valid and not placeholder values."""
    if not USE_SUPABASE or not SUPABASE_URL:
        return False
    if not SUPABASE_SERVICE_ROLE_KEY or "YOUR_" in SUPABASE_SERVICE_ROLE_KEY:
        return False
    return True

def get_supabase_client(schema: Optional[str] = None) -> Optional[Any]:
    """Get Supabase client configured for the isolated schema."""
    global supabase_client
    if not is_supabase_configured() or create_client is None:
        return None

    target_schema = schema or SUPABASE_SCHEMA
    if supabase_client is None:
        try:
            if ClientOptions is not None:
                options = ClientOptions(schema=target_schema)
                supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, options=options)
            else:
                supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        except Exception as e:
            print(f"Failed to initialize Supabase client: {e}")
            supabase_client = None

    return supabase_client

def get_schema_client(schema: Optional[str] = None):
    """Return Supabase client scoped to the target schema (client.schema('langgraph'))."""
    target_schema = schema or SUPABASE_SCHEMA
    client = get_supabase_client(target_schema)
    if client is not None and hasattr(client, "schema"):
        return client.schema(target_schema)
    return client

async def get_supabase_connection(schema: Optional[str] = None) -> asyncpg.Connection:
    """Get a direct PostgreSQL connection to Supabase with search_path=langgraph,public."""
    target_schema = schema or SUPABASE_SCHEMA
    server_settings = {"search_path": f"{target_schema},public"}

    if "YOUR_" in SUPABASE_DB_PASSWORD or not SUPABASE_DB_PASSWORD:
        raise ValueError("SUPABASE_DB_PASSWORD is not configured or contains placeholder value")

    return await asyncpg.connect(
        host=SUPABASE_DB_HOST,
        port=SUPABASE_DB_PORT,
        user=SUPABASE_DB_USER,
        password=SUPABASE_DB_PASSWORD,
        database=SUPABASE_DB_NAME,
        server_settings=server_settings,
        timeout=10,
    )

async def get_supabase_pool(schema: Optional[str] = None, min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    """Get or create asyncpg Connection Pool with search_path=langgraph,public."""
    global _supabase_pool
    target_schema = schema or SUPABASE_SCHEMA
    server_settings = {"search_path": f"{target_schema},public"}

    if _supabase_pool is not None:
        try:
            if not _supabase_pool._loop.is_closed():
                return _supabase_pool
        except Exception:
            pass
        _supabase_pool = None

    if "YOUR_" in SUPABASE_DB_PASSWORD or not SUPABASE_DB_PASSWORD:
        raise ValueError("SUPABASE_DB_PASSWORD is not configured or contains placeholder value")

    _supabase_pool = await asyncpg.create_pool(
        host=SUPABASE_DB_HOST,
        port=SUPABASE_DB_PORT,
        user=SUPABASE_DB_USER,
        password=SUPABASE_DB_PASSWORD,
        database=SUPABASE_DB_NAME,
        server_settings=server_settings,
        min_size=min_size,
        max_size=max_size,
    )
    return _supabase_pool

async def init_supabase_db() -> bool:
    """Verify Supabase isolated schema and connection readiness."""
    if not is_supabase_configured():
        return False

    # Attempt via schema client first
    try:
        sc = get_schema_client()
        if sc is not None:
            res = sc.table("subagent_registry").select("id").limit(1).execute()
            return True
    except Exception as e:
        print(f"Supabase REST schema check failed: {e}")

    # Fallback check via direct PostgreSQL connection
    try:
        conn = await get_supabase_connection()
        try:
            cnt = await conn.fetchval(f"SELECT count(*) FROM {SUPABASE_SCHEMA}.subagent_registry;")
            return True
        finally:
            await conn.close()
    except Exception as e:
        print(f"Supabase direct SQL connection check failed: {e}")

    return False
