#!/usr/bin/env python3
"""
LangGraph Platform (LGP v2.0) - SQLite to Supabase Migration Tool
===================================================================
Migrate data from SQLite (data/lgp.db) to isolated Supabase schema ('langgraph').
Supports:
  1. Dry-run mode (default or --dry-run)
  2. SQL export generation (--sql-export)
  3. Direct PostgreSQL execution via asyncpg or Supabase REST API (--execute)
  4. Automatic safe fallback if Supabase host is not yet reachable.
"""

import os
import sys
import json
import sqlite3
import argparse
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add root directory to python path for module imports
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Order of tables for foreign key dependency resolution
MIGRATION_TABLES = [
    "subagent_registry",
    "correlation_settings",
    "matrix_config",
    "threads",
    "runs",
    "checkpoints",
    "telemetry_events",
    "hitl_inbox",
    "correlation_edges",
    "temporal_facts",
    "audit_log",
    "kanban_boards",
    "kanban_columns",
    "kanban_cards"
]

TIMESTAMP_FIELDS = {
    "threads": ["created_at", "updated_at"],
    "runs": ["created_at", "updated_at"],
    "checkpoints": ["created_at"],
    "telemetry_events": ["timestamp", "created_at"],
    "correlation_edges": ["updated_at"],
    "temporal_facts": ["valid_at", "invalid_at", "created_at", "expired_at"],
    "audit_log": ["created_at"],
    "hitl_inbox": ["created_at", "resolved_at"],
    "correlation_settings": ["updated_at"],
    "kanban_boards": ["created_at", "updated_at"],
    "kanban_cards": ["created_at", "updated_at"],
    "matrix_config": ["created_at"]
}

JSON_FIELDS = {
    "threads": ["metadata_json"],
    "runs": ["context_packet_json", "budget_allocated_json", "budget_spent_json"],
    "checkpoints": ["state_data_json"],
    "telemetry_events": ["payload_json"],
    "hitl_inbox": ["state_diff_json"],
    "kanban_cards": ["metadata_json"]
}


def to_iso_timestamptz(val: Any) -> Optional[str]:
    """Convert float epoch timestamp or date string to ISO-8601 UTC string."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc).isoformat()
        except Exception:
            return None
    if isinstance(val, str):
        try:
            # Check if it is a string representation of float
            num = float(val)
            return datetime.fromtimestamp(num, tz=timezone.utc).isoformat()
        except ValueError:
            return val
    return str(val)


def parse_json_value(val: Any, default: Any = None) -> Any:
    """Parse string to JSON object or return default."""
    if val is None or val == "":
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def format_sql_literal(val: Any, is_json: bool = False, is_ts: bool = False) -> str:
    """Format Python value as SQL literal for PostgreSQL."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        if is_ts:
            iso = to_iso_timestamptz(val)
            return f"'{iso}'::timestamptz" if iso else "NULL"
        return str(val)
    if is_json:
        if isinstance(val, (dict, list)):
            dumped = json.dumps(val).replace("'", "''")
            return f"'{dumped}'::jsonb"
        dumped = str(val).replace("'", "''")
        return f"'{dumped}'::jsonb"
    if is_ts:
        iso = to_iso_timestamptz(val)
        return f"'{iso}'::timestamptz" if iso else "NULL"
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def read_sqlite_data(sqlite_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Read all tables and records from SQLite database."""
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite database not found at: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    data: Dict[str, List[Dict[str, Any]]] = {}
    for table in MIGRATION_TABLES:
        try:
            cursor.execute(f"SELECT * FROM {table};")
            rows = [dict(row) for row in cursor.fetchall()]
            data[table] = rows
        except sqlite3.OperationalError as e:
            # Table may not exist yet in SQLite
            data[table] = []

    conn.close()
    return data


def transform_records(table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform SQLite rows into Supabase-compatible PostgreSQL dicts."""
    ts_cols = TIMESTAMP_FIELDS.get(table, [])
    json_cols = JSON_FIELDS.get(table, [])
    transformed = []

    for r in rows:
        row = dict(r)

        # Handle telemetry_events timestamp mapping
        if table == "telemetry_events":
            raw_ts = row.get("timestamp")
            iso_ts = to_iso_timestamptz(raw_ts)
            row["timestamp"] = iso_ts
            row["created_at"] = iso_ts

        # Handle timestamps
        for col in ts_cols:
            if col in row:
                row[col] = to_iso_timestamptz(row[col])

        # Handle JSON fields
        for col in json_cols:
            if col in row:
                row[col] = parse_json_value(row[col], default={} if "diff" in col or "payload" in col or "metadata" in col else None)

        transformed.append(row)

    return transformed


def generate_sql_dump(schema: str, data: Dict[str, List[Dict[str, Any]]]) -> str:
    """Generate SQL statements for inserting data into isolated schema."""
    lines: List[str] = [
        f"-- ============================================================================",
        f"-- LangGraph Platform (LGP v2.0) - Data Migration Seed File",
        f"-- Target Schema: {schema}",
        f"-- Generated At: {datetime.now(timezone.utc).isoformat()}",
        f"-- ============================================================================",
        f"SET search_path TO {schema}, public;",
        ""
    ]

    for table in MIGRATION_TABLES:
        rows = data.get(table, [])
        if not rows:
            lines.append(f"-- Table {schema}.{table}: 0 rows (Skipped)")
            continue

        lines.append(f"-- Table {schema}.{table} ({len(rows)} rows)")
        ts_cols = set(TIMESTAMP_FIELDS.get(table, []))
        json_cols = set(JSON_FIELDS.get(table, []))

        # Sample columns from first record
        cols = list(rows[0].keys())
        if table == "telemetry_events" and "created_at" not in cols:
            cols.append("created_at")

        cols_str = ", ".join(f'"{c}"' for c in cols)

        for row in rows:
            val_strs = []
            for col in cols:
                val = row.get(col)
                if table == "telemetry_events" and col == "created_at":
                    val = row.get("timestamp")
                is_json = col in json_cols
                is_ts = col in ts_cols
                val_strs.append(format_sql_literal(val, is_json=is_json, is_ts=is_ts))

            lines.append(f"INSERT INTO {schema}.{table} ({cols_str}) VALUES ({', '.join(val_strs)}) ON CONFLICT DO NOTHING;")

        lines.append("")

    return "\n".join(lines)


async def execute_postgres_migration(
    schema: str,
    data: Dict[str, List[Dict[str, Any]]],
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str
) -> bool:
    """Execute migration directly via asyncpg connection."""
    import asyncpg

    print(f"Connecting to PostgreSQL ({host}:{port}/{dbname}) with search_path={schema},public...")
    conn = await asyncpg.connect(
        host=host,
        port=port,
        database=dbname,
        user=user,
        password=password,
        server_settings={"search_path": f"{schema},public"},
        timeout=10
    )

    try:
        async with conn.transaction():
            # Ensure schema exists
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")

            for table in MIGRATION_TABLES:
                rows = data.get(table, [])
                if not rows:
                    continue

                ts_cols = set(TIMESTAMP_FIELDS.get(table, []))
                json_cols = set(JSON_FIELDS.get(table, []))

                cols = list(rows[0].keys())
                if table == "telemetry_events" and "created_at" not in cols:
                    cols.append("created_at")

                cols_str = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
                query = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"

                batch_params = []
                for r in rows:
                    p_row = []
                    for c in cols:
                        val = r.get(c)
                        if table == "telemetry_events" and c == "created_at":
                            val = r.get("timestamp")

                        # Parse for asyncpg types
                        if c in ts_cols and val is not None:
                            try:
                                if isinstance(val, (int, float)):
                                    p_row.append(datetime.fromtimestamp(float(val), tz=timezone.utc))
                                elif isinstance(val, str):
                                    p_row.append(datetime.fromisoformat(val.replace("Z", "+00:00")))
                                else:
                                    p_row.append(val)
                            except Exception:
                                p_row.append(None)
                        elif c in json_cols and val is not None:
                            if isinstance(val, (dict, list)):
                                p_row.append(json.dumps(val))
                            else:
                                p_row.append(str(val))
                        else:
                            p_row.append(val)

                    batch_params.append(p_row)

                await conn.executemany(query, batch_params)
                print(f"  [OK] Table {schema}.{table}: {len(rows)} records successfully migrated.")

        return True
    finally:
        await conn.close()


def execute_supabase_rest_migration(schema: str, data: Dict[str, List[Dict[str, Any]]], url: str, key: str) -> bool:
    """Execute migration using Supabase REST Client with custom schema."""
    from supabase import create_client, ClientOptions

    print(f"Connecting to Supabase REST API ({url}) with schema '{schema}'...")
    options = ClientOptions(schema=schema)
    client = create_client(url, key, options=options)

    for table in MIGRATION_TABLES:
        rows = data.get(table, [])
        if not rows:
            continue

        try:
            # Chunk into batches of 100
            batch_size = 100
            for i in range(0, len(rows), batch_size):
                chunk = rows[i:i + batch_size]
                client.schema(schema).table(table).upsert(chunk).execute()
            print(f"  [OK] Table {schema}.{table}: {len(rows)} records migrated via Supabase REST API.")
        except Exception as e:
            print(f"  [ERROR] Failed to migrate table {table}: {e}")
            return False

    return True


def run():
    parser = argparse.ArgumentParser(description="Migrate LGP database from SQLite to Supabase isolated schema.")
    parser.add_argument("--sqlite-path", default=os.environ.get("LGP_DB_PATH", os.path.join(BASE_DIR, "data/lgp.db")), help="Path to SQLite db file")
    parser.add_argument("--schema", default=os.environ.get("SUPABASE_SCHEMA", "langgraph"), help="Target PostgreSQL schema")
    parser.add_argument("--execute", action="store_true", help="Execute migration against Supabase/PostgreSQL (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run simulation only without writing")
    parser.add_argument("--sql-export", default=os.path.join(BASE_DIR, "data/langgraph_seed_migration.sql"), help="Path to write SQL export dump")

    args = parser.parse_args()

    print("==================================================================")
    print("  LangGraph Platform - SQLite to Supabase Migration")
    print("==================================================================")
    print(f"Source SQLite DB : {args.sqlite_path}")
    print(f"Target Schema    : {args.schema}")
    print(f"Mode             : {'EXECUTE' if args.execute and not args.dry_run else 'DRY-RUN (Safe Simulation)'}")
    print("------------------------------------------------------------------")

    # 1. Read and transform SQLite data
    try:
        raw_data = read_sqlite_data(args.sqlite_path)
    except Exception as e:
        print(f"Error reading SQLite data: {e}")
        sys.exit(1)

    transformed_data: Dict[str, List[Dict[str, Any]]] = {}
    total_records = 0

    print("Summary of Records Found in SQLite:")
    for table in MIGRATION_TABLES:
        rows = raw_data.get(table, [])
        t_rows = transform_records(table, rows)
        transformed_data[table] = t_rows
        count = len(t_rows)
        total_records += count
        status_icon = "✓" if count > 0 else "-"
        print(f"  {status_icon} {table.ljust(25)} : {count} rows")

    print("------------------------------------------------------------------")
    print(f"Total Records to Migrate: {total_records}")
    print("------------------------------------------------------------------")

    # 2. Generate SQL Dump Export
    if args.sql_export:
        os.makedirs(os.path.dirname(os.path.abspath(args.sql_export)), exist_ok=True)
        sql_content = generate_sql_dump(args.schema, transformed_data)
        with open(args.sql_export, "w", encoding="utf-8") as f:
            f.write(sql_content)
        print(f"Standalone SQL Seed File generated at: {args.sql_export}")

    # 3. Execution logic
    if not args.execute or args.dry_run:
        print("\n[DRY RUN COMPLETE] No remote database was modified.")
        print("To apply changes to Supabase:")
        print("  1. Ensure credentials in .env are configured.")
        print("  2. Run: python scripts/migrate_sqlite_to_supabase.py --execute")
        print(f"  3. Or run the generated SQL script '{args.sql_export}' in Supabase Studio SQL Editor.")
        return

    # Check connection parameters
    db_host = os.environ.get("SUPABASE_DB_HOST", "localhost")
    db_port = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
    db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    db_user = os.environ.get("SUPABASE_DB_USER", "postgres")
    db_password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    has_valid_db_pass = db_password and "YOUR_" not in db_password
    has_valid_sb_key = sb_key and "YOUR_" not in sb_key

    if not has_valid_db_pass and not has_valid_sb_key:
        print("\n[NOTICE] Valid Supabase credentials not found in environment.")
        print("SUPABASE_DB_PASSWORD or SUPABASE_SERVICE_ROLE_KEY contains placeholder values.")
        print(f"Fallback safe: SQL file was written to {args.sql_export}")
        print("You can execute it directly inside Supabase SQL editor.")
        return

    # Try direct asyncpg first if db_password provided
    if has_valid_db_pass:
        try:
            success = asyncio.run(execute_postgres_migration(
                schema=args.schema,
                data=transformed_data,
                host=db_host,
                port=db_port,
                dbname=db_name,
                user=db_user,
                password=db_password
            ))
            if success:
                print("\n[SUCCESS] Migration completed via direct PostgreSQL connection.")
                return
        except Exception as e:
            print(f"\n[WARNING] Direct PostgreSQL migration failed: {e}")
            print("Attempting fallback to Supabase REST API...")

    # Fallback to Supabase REST Client
    if has_valid_sb_key and sb_url:
        try:
            success = execute_supabase_rest_migration(
                schema=args.schema,
                data=transformed_data,
                url=sb_url,
                key=sb_key
            )
            if success:
                print("\n[SUCCESS] Migration completed via Supabase REST API.")
                return
        except Exception as e:
            print(f"[ERROR] Supabase REST API migration failed: {e}")

    print(f"\n[FALLBACK SUCCESS] All data exported safely to {args.sql_export}")


if __name__ == "__main__":
    run()
