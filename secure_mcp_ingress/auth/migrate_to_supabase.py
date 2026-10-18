#!/usr/bin/env python3
"""
CLI & Service utility to migrate and bidirectional-sync ingress tokens
between tokens_store.json and Supabase PostgreSQL schema langgraph.ingress_tokens.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure root workspace is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "tokens_store.json"

INGRESS_TOKENS_DDL = """
CREATE TABLE IF NOT EXISTS langgraph.ingress_tokens (
    token_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    description TEXT DEFAULT '',
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    aud TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    grace_until TIMESTAMPTZ,
    rotated_to TEXT,
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ingress_tokens_client_id ON langgraph.ingress_tokens(client_id);
CREATE INDEX IF NOT EXISTS idx_ingress_tokens_status ON langgraph.ingress_tokens(status);
"""


async def ensure_supabase_table() -> bool:
    """Ensures that the langgraph.ingress_tokens table exists."""
    try:
        from packages.core.db import get_db_connection
        conn = await get_db_connection()
        async with conn.execute(INGRESS_TOKENS_DDL):
            pass
        await conn.close()
        return True
    except Exception as e:
        print(f"[Supabase Migration] Failed to ensure table: {e}")
        return False


async def migrate_file_to_supabase(store_path: Path = DEFAULT_STORE_PATH) -> int:
    """Pushes all tokens from JSON flat-file into Supabase langgraph.ingress_tokens."""
    if not store_path.exists():
        print(f"[Supabase Migration] Store path {store_path} not found.")
        return 0

    from packages.core.db import get_db_connection
    conn = await get_db_connection()

    async with conn.execute(INGRESS_TOKENS_DDL):
        pass

    with open(store_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tokens = data.get("tokens", {})
    upserted = 0

    upsert_sql = """
    INSERT INTO langgraph.ingress_tokens (
        token_hash, client_id, description, scopes, aud, status,
        created_at, expires_at, grace_until, rotated_to, revoked_at, revocation_reason, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
    ON CONFLICT (token_hash) DO UPDATE SET
        client_id = EXCLUDED.client_id,
        description = EXCLUDED.description,
        scopes = EXCLUDED.scopes,
        aud = EXCLUDED.aud,
        status = EXCLUDED.status,
        expires_at = EXCLUDED.expires_at,
        grace_until = EXCLUDED.grace_until,
        rotated_to = EXCLUDED.rotated_to,
        revoked_at = EXCLUDED.revoked_at,
        revocation_reason = EXCLUDED.revocation_reason,
        updated_at = NOW();
    """

    for th, rec in tokens.items():
        scopes_json = json.dumps(rec.get("scopes", []))
        created_at = datetime.fromisoformat(rec["created_at"]) if rec.get("created_at") else datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(rec["expires_at"]) if rec.get("expires_at") else datetime.now(timezone.utc)
        grace_until = datetime.fromisoformat(rec["grace_until"]) if rec.get("grace_until") else None
        revoked_at = datetime.fromisoformat(rec["revoked_at"]) if rec.get("revoked_at") else None

        async with conn.execute(
            upsert_sql,
            (
                rec["token_hash"],
                rec.get("client_id", ""),
                rec.get("description", ""),
                scopes_json,
                rec.get("aud", ""),
                rec.get("status", "ACTIVE"),
                created_at,
                expires_at,
                grace_until,
                rec.get("rotated_to"),
                revoked_at,
                rec.get("revocation_reason"),
            )
        ):
            pass
        upserted += 1

    await conn.close()
    print(f"[Supabase Migration] Successfully migrated {upserted} tokens to Supabase.")
    return upserted


async def pull_supabase_to_file(store_path: Path = DEFAULT_STORE_PATH) -> int:
    """Pulls all tokens from Supabase langgraph.ingress_tokens to update local tokens_store.json."""
    from packages.core.db import get_db_connection
    conn = await get_db_connection()

    query = """
    SELECT token_hash, client_id, description, scopes, aud, status,
           created_at, expires_at, grace_until, rotated_to, revoked_at, revocation_reason
    FROM langgraph.ingress_tokens
    """

    tokens_dict: dict[str, Any] = {}
    async with conn.execute(query) as cur:
        rows = await cur.fetchall()
        for r in rows:
            th = r[0]
            scopes_val = r[3]
            if isinstance(scopes_val, str):
                try:
                    scopes_val = json.loads(scopes_val)
                except Exception:
                    scopes_val = []
            tokens_dict[th] = {
                "token_hash": th,
                "client_id": r[1],
                "description": r[2] or "",
                "scopes": scopes_val or [],
                "aud": r[4],
                "status": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
                "expires_at": r[7].isoformat() if r[7] else None,
                "grace_until": r[8].isoformat() if r[8] else None,
                "rotated_to": r[9],
                "revoked_at": r[10].isoformat() if r[10] else None,
                "revocation_reason": r[11],
            }

    await conn.close()

    store_path.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "version": "1.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tokens": tokens_dict,
    }

    temp_path = store_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass

    temp_path.replace(store_path)
    try:
        os.chmod(store_path, 0o600)
    except OSError:
        pass

    print(f"[Supabase Migration] Synced {len(tokens_dict)} tokens from Supabase to {store_path}.")
    return len(tokens_dict)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingress Token Supabase Migration")
    parser.add_argument("--direction", choices=["push", "pull"], default="push", help="Push to Supabase or pull from Supabase")
    args = parser.parse_args()

    if args.direction == "push":
        asyncio.run(migrate_file_to_supabase())
    else:
        asyncio.run(pull_supabase_to_file())
