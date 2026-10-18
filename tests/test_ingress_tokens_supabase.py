import pytest
import asyncio
from secure_mcp_ingress.auth.token_manager import TokenManager
from secure_mcp_ingress.auth.migrate_to_supabase import (
    ensure_supabase_table,
    migrate_file_to_supabase,
    pull_supabase_to_file,
)
from packages.core.db import get_db_connection


@pytest.mark.asyncio
async def test_supabase_ingress_table_exists():
    ok = await ensure_supabase_table()
    assert ok is True

    conn = await get_db_connection()
    async with conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'langgraph' AND table_name = 'ingress_tokens'"
    ) as cur:
        row = await cur.fetchone()
        assert row[0] == 1
    await conn.close()


@pytest.mark.asyncio
async def test_migrate_and_query_supabase_tokens(tmp_path):
    # Verify migration function works
    count = await migrate_file_to_supabase()
    assert count >= 5

    conn = await get_db_connection()
    async with conn.execute("SELECT count(*) FROM langgraph.ingress_tokens") as cur:
        row = await cur.fetchone()
        assert row[0] >= 5
    await conn.close()


@pytest.mark.asyncio
async def test_token_creation_and_supabase_sync(tmp_path):
    store_file = tmp_path / "test_store.json"
    tm = TokenManager(store_path=store_file)

    raw, rec = tm.create_token(
        client_id="pytest-supabase-client",
        scopes=["memory:read"],
        description="Automated Pytest Client for Supabase Sync",
    )
    assert raw.startswith("mcp_")
    token_hash = rec["token_hash"]

    # Explicitly ensure token is synced to Supabase
    await tm.async_sync_token_to_supabase(rec)

    # Verify token exists in Supabase
    conn = await get_db_connection()
    async with conn.execute(
        "SELECT client_id, status FROM langgraph.ingress_tokens WHERE token_hash = ?",
        (token_hash,)
    ) as cur:
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == "pytest-supabase-client"
        assert row[1] == "ACTIVE"
    await conn.close()

    # Revoke and verify status in Supabase
    tm.revoke_token(token_hash, reason="pytest_cleanup")
    rec_revoked = tm.get_token(token_hash)
    if rec_revoked:
        await tm.async_sync_token_to_supabase(rec_revoked)

    conn2 = await get_db_connection()
    async with conn2.execute(
        "SELECT status, revocation_reason FROM langgraph.ingress_tokens WHERE token_hash = ?",
        (token_hash,)
    ) as cur:
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == "REVOKED"
        assert row[1] == "pytest_cleanup"

    # Cleanup test token
    async with conn2.execute("DELETE FROM langgraph.ingress_tokens WHERE token_hash = ?", (token_hash,)):
        pass
    await conn2.close()
