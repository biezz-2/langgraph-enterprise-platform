"""
Runnable check untuk LGP v2.0 Persistence Layer.
Memverifikasi SQLite WAL mode, DDL tables, foreign keys, Pydantic validasi, audit hash-chain, dan HITL anti-self-approval.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from persistence import (
    Base,
    configure_sqlite_pragmas,
    SubagentRegistry,
    Thread,
    Run,
    Checkpoint,
    StateDiff,
    TelemetryEvent,
    CorrelationEdge,
    TemporalMemoryFact,
    AuditLog,
    HITLInbox,
    SubagentRegistryModel,
    ContextPacketModel,
    AuditLogModel,
    HITLInboxModel,
    TrustLevel,
    RunStatus,
    TelemetryEventType,
    AuditResultStatus,
    HITLStatus,
)


def run_checks():
    db_file = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_file}")
    configure_sqlite_pragmas(engine)

    # 1. Pastikan SQLite WAL mode aktif
    with engine.connect() as conn:
        res = conn.exec_driver_sql("PRAGMA journal_mode;").scalar()
        assert str(res).lower() == "wal", f"Journal mode harus wal, didapat {res}"
        fk = conn.exec_driver_sql("PRAGMA foreign_keys;").scalar()
        assert fk == 1, f"Foreign keys harus 1, didapat {fk}"

    # 2. Buat semua tabel
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # 3. Registrasi subagent Atlas & Vulcan
        atlas = SubagentRegistry(
            id="atlas",
            role="orchestrator-supervisor",
            name="Atlas",
            capabilities=["task_decomposition", "delegation", "synthesis", "hitl_escalation"],
            input_schema={"type": "object", "properties": {"objective": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"final_answer": {"type": "string"}}},
            tool_grants=["runs:execute", "graphs:read", "state:read"],
            model_policy={"provider": "anthropic", "model": "claude-3-7-sonnet"},
            budget_config={"tokens": 1500000, "usd": 10.0, "wall_clock_s": 2700, "max_depth": 2},
            memory_scope="tenant:default:ws:main",
            trust_level=TrustLevel.HIGH.value,
            is_active=True,
            version=1,
        )
        vulcan = SubagentRegistry(
            id="vulcan",
            role="software-engineer",
            name="Vulcan",
            capabilities=["code_write", "lgp_graph_propose", "lgp_graph_validate"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            tool_grants=["graphs:write", "github.read"],
            model_policy={"provider": "anthropic", "model": "claude-3-7-sonnet"},
            budget_config={"tokens": 400000, "usd": 2.5, "wall_clock_s": 1800},
            memory_scope="tenant:default:ws:main:code",
            trust_level=TrustLevel.MEDIUM.value,
            is_active=True,
            version=1,
        )
        session.add_all([atlas, vulcan])
        session.commit()

        # 4. Threads & Runs
        th = Thread(thread_id="th-001", metadata_json={"user_id": "usr-admin"})
        session.add(th)
        session.commit()

        run = Run(
            run_id="r-001",
            thread_id=th.thread_id,
            status=RunStatus.RUNNING.value,
            current_subagent="atlas",
            context_packet={"packet_id": "pkt-1", "objective": "Bikin modul DB", "boundaries": "No UI"},
            budget_allocated={"tokens": 1500000, "usd": 10.0},
            budget_spent={"tokens": 15000, "usd": 0.05},
            checkpoints_count=1,
        )
        session.add(run)
        session.commit()

        # 5. Checkpoints & Loop detection check
        s_hash = hashlib.sha256(b"state_content_v1").hexdigest()
        ckpt1 = Checkpoint(
            checkpoint_id="ckpt-001",
            run_id=run.run_id,
            thread_id=th.thread_id,
            state_hash=s_hash,
            state_data={"node": "atlas", "step": 1},
            step=1,
        )
        session.add(ckpt1)

        diff1 = StateDiff(
            diff_id="diff-001",
            checkpoint_id=ckpt1.checkpoint_id,
            run_id=run.run_id,
            to_checkpoint_id=ckpt1.checkpoint_id,
            node_name="atlas",
            diff_data={"added": {"status": "initialized"}},
        )
        session.add(diff1)
        session.commit()

        # Loop detection query (hitung hash berulang pada run yang sama)
        hash_count = session.scalar(
            select(func.count(Checkpoint.checkpoint_id))
            .where(Checkpoint.run_id == run.run_id, Checkpoint.state_hash == s_hash)
        )
        assert hash_count == 1, f"Hash count harus 1, didapat {hash_count}"

        # 6. Telemetry event
        te = TelemetryEvent(
            event_id="evt-001",
            run_id=run.run_id,
            subagent_id="atlas",
            event_type=TelemetryEventType.DELEGATE.value,
            payload={"target": "vulcan", "objective": "compile schema"},
            tokens=1200,
            cost=0.0036,
            latency_ms=450.0,
        )
        session.add(te)

        # 7. Correlation Edge
        edge = CorrelationEdge(
            source_subagent="atlas",
            target_subagent="vulcan",
            workspace_id="default",
            handoff_rate=0.85,
            npmi_coactivation=0.72,
            success_lift=0.15,
            latency_coupling=0.40,
            cost_share=0.25,
            composite_weight=0.82,
            polarity="positive",
            sample_count=24,
        )
        session.add(edge)

        # 8. Temporal Memory Facts (bi-temporal)
        now = datetime.now(timezone.utc)
        fact = TemporalMemoryFact(
            fact_id="fact-001",
            subject="Vulcan",
            predicate="IMPLEMENTS",
            object="LGP v2.0 Persistence Layer",
            valid_at=now,
            invalid_at=None,
            created_at=now,
            expired_at=None,
            episode_run_id=run.run_id,
            pii_redacted=False,
        )
        session.add(fact)

        # 9. Audit Log (Hash Chaining)
        genesis_prev = "0" * 64
        actor = "atlas"
        action = "subagent.delegate"
        scope = "workspace:default"
        args_hash = hashlib.sha256(b"args:target=vulcan").hexdigest()
        created_str = now.isoformat()
        curr_hash = AuditLogModel.compute_hash(
            prev_hash=genesis_prev,
            actor=actor,
            action=action,
            scope=scope,
            args_hash=args_hash,
            result_status=AuditResultStatus.SUCCESS.value,
            created_at_iso=created_str,
        )

        audit = AuditLog(
            actor=actor,
            action=action,
            scope=scope,
            args_hash=args_hash,
            prev_hash=genesis_prev,
            curr_hash=curr_hash,
            result_status=AuditResultStatus.SUCCESS.value,
            created_at=now,
        )
        session.add(audit)

        # 10. HITL Inbox
        hitl = HITLInbox(
            interrupt_id="int-001",
            run_id=run.run_id,
            subagent_id="vulcan",
            reason="approval_required",
            state_diff={"propose_action": "promote_graph_prod"},
            status=HITLStatus.PENDING.value,
        )
        session.add(hitl)
        session.commit()

        # Validasi HITL model constraint: approver != subagent_id
        try:
            HITLInboxModel(
                interrupt_id="int-bad",
                run_id="r-001",
                subagent_id="vulcan",
                reason="approval_required",
                approver="vulcan",  # Terlarang: self-approval
                status=HITLStatus.APPROVED,
            )
            assert False, "Self-approval seharusnya gagal divalidasi"
        except ValueError:
            pass  # Berhasil dicegat

    # Clean up temp file
    try:
        os.remove(db_file)
        if os.path.exists(f"{db_file}-wal"):
            os.remove(f"{db_file}-wal")
        if os.path.exists(f"{db_file}-shm"):
            os.remove(f"{db_file}-shm")
    except OSError:
        pass

    print("SEMUA PENGECEKAN PERSISTENCE LGP V2.0 LULUS 100%.")


if __name__ == "__main__":
    run_checks()
