import os
import json
import hashlib
import time
from typing import List, Dict, Any, Optional
import aiosqlite

DB_PATH = os.environ.get("LGP_DB_PATH", os.path.join(os.path.dirname(__file__), "../../data/lgp.db"))

async def get_db_connection() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    db = await get_db_connection()
    try:
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

        CREATE INDEX IF NOT EXISTS idx_telemetry_run ON telemetry_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_telemetry_agent ON telemetry_events(subagent_id);
        CREATE INDEX IF NOT EXISTS idx_temporal_subject ON temporal_facts(subject);
        CREATE INDEX IF NOT EXISTS idx_temporal_validity ON temporal_facts(valid_at, invalid_at);
        """)
        await db.commit()

        # Seed correlation settings if empty
        async with db.execute("SELECT COUNT(*) as cnt FROM correlation_settings") as cursor:
            row = await cursor.fetchone()
            if row and row["cnt"] == 0:
                await db.execute("""
                    INSERT INTO correlation_settings (workspace_id, alpha, beta, gamma, n_min, updated_at)
                    VALUES ('default', 0.4, 0.4, 0.2, 50, ?)
                """, (time.time(),))
                await db.commit()

        # Seed 10 subagents if empty
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
    finally:
        await db.close()

async def record_audit_log(actor: str, action: str, scope: str, args: Any, result_status: str) -> str:
    db = await get_db_connection()
    try:
        args_str = json.dumps(args, sort_keys=True) if not isinstance(args, str) else args
        args_hash = hashlib.sha256(args_str.encode()).hexdigest()

        async with db.execute("SELECT curr_hash FROM audit_log ORDER BY created_at DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            prev_hash = row["curr_hash"] if row else "0" * 64

        timestamp = time.time()
        log_id = f"aud-{hashlib.sha256(f'{timestamp}-{action}'.encode()).hexdigest()[:12]}"

        # Hash chaining
        payload_to_hash = f"{prev_hash}:{log_id}:{actor}:{action}:{scope}:{args_hash}:{result_status}:{timestamp}"
        curr_hash = hashlib.sha256(payload_to_hash.encode()).hexdigest()

        await db.execute("""
            INSERT INTO audit_log (log_id, actor, action, scope, args_hash, prev_hash, curr_hash, result_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, actor, action, scope, args_hash, prev_hash, curr_hash, result_status, timestamp))
        await db.commit()
        return log_id
    finally:
        await db.close()
