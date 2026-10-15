import os
import json
import hashlib
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urlparse
import aiosqlite
import asyncpg
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger("packages.core.db")

DB_PATH = os.environ.get("LGP_DB_PATH", os.path.join(os.path.dirname(__file__), "../../data/lgp.db"))
USE_SUPABASE = os.environ.get("USE_SUPABASE", "false").lower() == "true"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_SCHEMA = os.environ.get("SUPABASE_SCHEMA", "langgraph")

# State tracking for Supabase connection pool and automatic fallback
supabase_pool: Optional[asyncpg.Pool] = None
_supabase_attempted: bool = False
_supabase_available: bool = False

# Active database mode indicator
DB_TYPE = "supabase" if (USE_SUPABASE and SUPABASE_URL) else "sqlite"


def _convert_placeholders(query: str) -> str:
    """Konversi placeholder SQLite '?' ke format asyncpg/Postgres '$1, $2, ...'."""
    parts = []
    in_single_quote = False
    param_idx = 1
    for char in query:
        if char == "'":
            in_single_quote = not in_single_quote
            parts.append(char)
        elif char == "?" and not in_single_quote:
            parts.append(f"${param_idx}")
            param_idx += 1
        else:
            parts.append(char)
    return "".join(parts)


class PostgresCursor:
    """Cursor wrapper asyncpg untuk kompatibilitas antarmuka aiosqlite."""

    def __init__(self, raw_conn: asyncpg.Connection, query: str, params: Any = ()):
        self.raw_conn = raw_conn
        self.query = _convert_placeholders(query)
        if params is None:
            self.params = ()
        elif isinstance(params, (list, tuple)):
            self.params = tuple(params)
        else:
            self.params = (params,)
        self._records = None
        self._idx = 0
        self.rowcount = -1

    async def _ensure_executed(self):
        if self._records is None:
            converted_params = list(self.params)
            if self.params:
                try:
                    stmt = await self.raw_conn.prepare(self.query)
                    param_types = stmt.get_parameters()
                    new_params = []
                    for val, p in zip(self.params, param_types):
                        if p.name in ("timestamptz", "timestamp", "date") and isinstance(val, (int, float)):
                            new_params.append(datetime.fromtimestamp(val, tz=timezone.utc))
                        elif p.name in ("json", "jsonb") and isinstance(val, (dict, list)):
                            new_params.append(json.dumps(val))
                        else:
                            new_params.append(val)
                    converted_params = new_params
                except Exception as pe:
                    logger.debug("Parameter prep inspection notice: %s", pe)

            q_stripped = self.query.strip().upper()
            if q_stripped.startswith("SELECT") or "RETURNING" in q_stripped or q_stripped.startswith("WITH") or q_stripped.startswith("SHOW"):
                self._records = await self.raw_conn.fetch(self.query, *converted_params)
                self.rowcount = len(self._records)
            else:
                status = await self.raw_conn.execute(self.query, *converted_params)
                self._records = []
                if status and isinstance(status, str):
                    parts = status.split()
                    if parts and parts[-1].isdigit():
                        self.rowcount = int(parts[-1])
            self._idx = 0

    def __await__(self):
        async def _exec():
            await self._ensure_executed()
            return self
        return _exec().__await__()

    async def __aenter__(self):
        await self._ensure_executed()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def fetchone(self):
        await self._ensure_executed()
        if self._records and self._idx < len(self._records):
            rec = self._records[self._idx]
            self._idx += 1
            return rec
        return None

    async def fetchall(self):
        await self._ensure_executed()
        if not self._records:
            return []
        res = self._records[self._idx:]
        self._idx = len(self._records)
        return res

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row

    async def close(self):
        pass

    @property
    def description(self):
        if self._records and len(self._records) > 0:
            return [(k, None, None, None, None, None, None) for k in self._records[0].keys()]
        return None


class PostgresConnectionWrapper:
    """Wrapper koneksi asyncpg dengan API yang kompatibel dengan aiosqlite."""

    def __init__(self, raw_conn: asyncpg.Connection, pool: Optional[asyncpg.Pool] = None):
        self.raw_conn = raw_conn
        self.pool = pool
        self._closed = False
        self._row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, val):
        self._row_factory = val

    def execute(self, query: str, params: Any = ()):
        return PostgresCursor(self.raw_conn, query, params)

    async def executescript(self, script: str):
        return await self.raw_conn.execute(script)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        if not self._closed:
            self._closed = True
            if self.pool:
                await self.pool.release(self.raw_conn)
            else:
                await self.raw_conn.close()

    def transaction(self):
        return self.raw_conn.transaction()

    def __getattr__(self, name):
        return getattr(self.raw_conn, name)


async def get_supabase_pool() -> Optional[asyncpg.Pool]:
    """Menginisialisasi connection pool asyncpg ke Supabase/PostgreSQL."""
    global supabase_pool, _supabase_attempted, _supabase_available, DB_TYPE
    if not (USE_SUPABASE and SUPABASE_URL):
        return None

    if supabase_pool is not None:
        try:
            curr_loop = asyncio.get_running_loop()
            if supabase_pool._loop is curr_loop and not curr_loop.is_closed():
                return supabase_pool
            else:
                try:
                    supabase_pool.terminate()
                except Exception:
                    pass
        except Exception:
            try:
                supabase_pool.terminate()
            except Exception:
                pass
        supabase_pool = None

    try:
        parsed = urlparse(SUPABASE_URL)
        default_host = parsed.hostname or "localhost"
        default_port = parsed.port or 5432

        db_host = os.environ.get("SUPABASE_DB_HOST") or default_host
        db_port = int(os.environ.get("SUPABASE_DB_PORT", default_port))
        db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
        db_user = os.environ.get("SUPABASE_DB_USER", "postgres")
        db_password = os.environ.get("SUPABASE_DB_PASSWORD", "")

        if not db_password and SUPABASE_SERVICE_ROLE_KEY:
            db_password = SUPABASE_SERVICE_ROLE_KEY.split("_")[-1]

        if not db_password:
            raise ValueError("SUPABASE_DB_PASSWORD tidak dikonfigurasi.")

        async def _init_connection(conn: asyncpg.Connection):
            try:
                await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SUPABASE_SCHEMA};")
            except Exception as se:
                logger.debug("Schema initialization notice: %s", se)
            try:
                await conn.execute(f"SET search_path TO {SUPABASE_SCHEMA}, public;")
            except Exception as se:
                logger.debug("search_path setup notice: %s", se)

        supabase_pool = await asyncpg.create_pool(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            min_size=1,
            max_size=5,
            command_timeout=5.0,
            timeout=5.0,
            init=_init_connection,
            server_settings={"search_path": f"{SUPABASE_SCHEMA},public"}
        )
        _supabase_available = True
        DB_TYPE = "supabase"
        logger.info("Connected to Supabase/PostgreSQL pool with search_path=%s,public", SUPABASE_SCHEMA)
        return supabase_pool
    except Exception as e:
        _supabase_available = False
        DB_TYPE = "supabase"  # tetap supabase, biarkan error propagate ke caller
        supabase_pool = None
        logger.error("Supabase connection failed: %s", e)
        raise


async def get_db_connection() -> Union[aiosqlite.Connection, PostgresConnectionWrapper]:
    """Mendapatkan koneksi database.

    Jika USE_SUPABASE=true: selalu pakai Supabase/PostgreSQL, raise RuntimeError jika gagal.
    Jika USE_SUPABASE=false: pakai SQLite lokal.
    """
    global DB_TYPE
    if USE_SUPABASE and SUPABASE_URL:
        pool = await get_supabase_pool()
        if pool is None:
            raise RuntimeError(
                "USE_SUPABASE=true tetapi koneksi Supabase gagal diinisialisasi. "
                "Periksa SUPABASE_DB_HOST, SUPABASE_DB_USER, dan SUPABASE_DB_PASSWORD."
            )
        raw_conn = await pool.acquire()
        return PostgresConnectionWrapper(raw_conn, pool)

    # SQLite (hanya jika USE_SUPABASE=false)
    DB_TYPE = "sqlite"
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = aiosqlite.Row
    return db


async def close_db_connection(conn: Any):
    """Menutup atau me-release koneksi database baik untuk SQLite maupun Postgres."""
    if conn is None:
        return
    try:
        if isinstance(conn, PostgresConnectionWrapper):
            await conn.close()
        elif isinstance(conn, aiosqlite.Connection):
            await conn.close()
        elif supabase_pool and isinstance(conn, asyncpg.Connection):
            await supabase_pool.release(conn)
        elif hasattr(conn, "close"):
            await conn.close()
    except Exception as e:
        logger.debug("Error while closing DB connection: %s", e)


_db_initialized = False


async def init_db():
    """Menginisialisasi tabel skema dan seeding data pada SQLite maupun PostgreSQL."""
    global _db_initialized
    if _db_initialized:
        return
    db = await get_db_connection()
    try:
        if isinstance(db, PostgresConnectionWrapper):
            try:
                await db.execute("CREATE SCHEMA IF NOT EXISTS langgraph;")
                await db.execute("SET search_path TO langgraph, public;")
            except Exception as se:
                logger.debug("PostgreSQL schema setup notice: %s", se)
        else:
            await db.executescript("""
        CREATE TABLE IF NOT EXISTS subagent_registry (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            pod TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            input_schema TEXT NOT NULL,
            output_schema TEXT NOT NULL,
            tool_grants TEXT NOT NULL,
            model_policy TEXT NOT NULL,
            budget_config TEXT NOT NULL,
            memory_scope TEXT NOT NULL,
            trust_level TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            version TEXT NOT NULL DEFAULT '2.0.0'
        );

        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            status TEXT NOT NULL, -- queued, running, interrupted, completed, failed
            objective TEXT NOT NULL,
            current_subagent TEXT,
            context_packet_json TEXT,
            budget_allocated_json TEXT,
            budget_spent_json TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            circuit_open INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step INTEGER NOT NULL,
            state_hash TEXT NOT NULL,
            state_data_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS telemetry_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            subagent_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT DEFAULT '{}',
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            latency_ms REAL DEFAULT 0.0,
            timestamp REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correlation_edges (
            source_subagent TEXT NOT NULL,
            target_subagent TEXT NOT NULL,
            handoff_rate REAL DEFAULT 0.0,
            npmi_coactivation REAL DEFAULT 0.0,
            success_lift REAL DEFAULT 0.0,
            latency_coupling REAL DEFAULT 0.0,
            composite_weight REAL DEFAULT 0.0,
            polarity TEXT DEFAULT 'neutral',
            sample_count INTEGER DEFAULT 0,
            updated_at REAL NOT NULL,
            PRIMARY KEY (source_subagent, target_subagent)
        );

        CREATE TABLE IF NOT EXISTS temporal_facts (
            fact_id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            valid_at REAL NOT NULL,
            invalid_at REAL,
            created_at REAL NOT NULL,
            expired_at REAL,
            episode_run_id TEXT,
            pii_redacted INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            log_id TEXT PRIMARY KEY,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            scope TEXT NOT NULL,
            args_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            curr_hash TEXT NOT NULL,
            result_status TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hitl_inbox (
            interrupt_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            subagent_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            state_diff_json TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected
            approver TEXT,
            decision TEXT,
            created_at REAL NOT NULL,
            resolved_at REAL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS correlation_settings (
            workspace_id TEXT PRIMARY KEY DEFAULT 'default',
            alpha REAL NOT NULL DEFAULT 0.4,
            beta REAL NOT NULL DEFAULT 0.4,
            gamma REAL NOT NULL DEFAULT 0.2,
            n_min INTEGER NOT NULL DEFAULT 50,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kanban_boards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kanban_columns (
            id TEXT PRIMARY KEY,
            board_id TEXT NOT NULL,
            name TEXT NOT NULL,
            order_idx INTEGER NOT NULL,
            FOREIGN KEY (board_id) REFERENCES kanban_boards(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS kanban_cards (
            id TEXT PRIMARY KEY,
            column_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            assigned_to TEXT,
            metadata_json TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (column_id) REFERENCES kanban_columns(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS matrix_config (
            id TEXT PRIMARY KEY DEFAULT 'default',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            alpha REAL NOT NULL DEFAULT 0.4,
            beta REAL NOT NULL DEFAULT 0.4,
            gamma REAL NOT NULL DEFAULT 0.2,
            n_min INTEGER NOT NULL DEFAULT 50,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_telemetry_run ON telemetry_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_telemetry_agent ON telemetry_events(subagent_id);
        CREATE INDEX IF NOT EXISTS idx_temporal_subject ON temporal_facts(subject);
        CREATE INDEX IF NOT EXISTS idx_temporal_validity ON temporal_facts(valid_at, invalid_at);
        CREATE INDEX IF NOT EXISTS idx_kanban_cards_column ON kanban_cards(column_id);
        CREATE INDEX IF NOT EXISTS idx_kanban_columns_board ON kanban_columns(board_id);
        """)
            await db.commit()

        # Seed correlation settings jika belum ada
        async with db.execute("SELECT COUNT(*) as cnt FROM correlation_settings") as cursor:
            row = await cursor.fetchone()
            if row and row["cnt"] == 0:
                await db.execute("""
                    INSERT INTO correlation_settings (workspace_id, alpha, beta, gamma, n_min, updated_at)
                    VALUES ('default', 0.4, 0.4, 0.2, 50, ?)
                """, (time.time(),))
                await db.commit()

        # Seed 10 subagents jika belum ada
        async with db.execute("SELECT COUNT(*) as cnt FROM subagent_registry") as cursor:
            row = await cursor.fetchone()
            if row and row["cnt"] == 0:
                from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS
                for c in TEN_SUBAGENTS_CONTRACTS:
                    await db.execute("""
                        INSERT INTO subagent_registry (
                            id, role, name, pod, capabilities, input_schema, output_schema,
                            tool_grants, model_policy, budget_config, memory_scope, trust_level,
                            is_active, version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c.id, c.role, c.name, c.pod,
                        json.dumps(c.capabilities),
                        json.dumps(c.input_schema),
                        json.dumps(c.output_schema),
                        json.dumps(c.tool_grants),
                        c.model_policy,
                        json.dumps(c.budget_config),
                        c.memory_scope,
                        c.trust_level,
                        1 if c.is_active else 0,
                        c.version
                    ))
                await db.commit()
        _db_initialized = True
    finally:
        await close_db_connection(db)


async def record_audit_log(actor: str, action: str, scope: str, args: Any, result_status: str) -> str:
    """Mencatat entri audit log dengan cryptographic hash chaining."""
    db = await get_db_connection()
    try:
        args_str = json.dumps(args, sort_keys=True) if not isinstance(args, str) else args
        args_hash = hashlib.sha256(args_str.encode()).hexdigest()

        async with db.execute("SELECT curr_hash FROM audit_log ORDER BY created_at DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            prev_hash = row["curr_hash"] if row else "0" * 64

        timestamp = round(time.time(), 3)
        log_id = f"aud-{hashlib.sha256(f'{timestamp}-{action}'.encode()).hexdigest()[:12]}"

        # Hash chaining
        payload_to_hash = f"{prev_hash}:{log_id}:{actor}:{action}:{scope}:{args_hash}:{result_status}:{timestamp}"
        curr_hash = hashlib.sha256(payload_to_hash.encode()).hexdigest()

        await db.execute("""
            INSERT INTO audit_log (log_id, actor, action, scope, args_hash, prev_hash, curr_hash, result_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, actor, action, scope, args_hash, prev_hash, curr_hash, result_status, timestamp))
        await db.commit()

        # Real-time event broadcast ke dashboard aktif jika ada
        try:
            from packages.core.event_bus import GlobalEventBus
            GlobalEventBus.get_instance().publish_sync("audit_updated", {
                "log_id": log_id,
                "actor": actor,
                "action": action,
                "scope": scope,
                "result_status": result_status,
                "created_at": timestamp
            })
        except Exception:
            pass

        return log_id
    finally:
        await close_db_connection(db)
