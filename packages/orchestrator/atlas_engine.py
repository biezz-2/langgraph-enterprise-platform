import uuid
import time
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple

from packages.core.models import (
    BudgetEnvelope,
    ContextPacket,
    TelemetryEvent,
    HITLInterrupt,
    TemporalFact
)
from packages.core.db import get_db_connection, record_audit_log
from packages.subagents.contracts import CONTRACTS_MAP, TEN_SUBAGENTS_CONTRACTS
from packages.guardrails.guards import (
    InheritedBudgetManager,
    CircuitBreaker,
    LoopDetector,
    SecurityToolGuard
)
from packages.telemetry.correlation import CorrelationCalculator
from packages.memory.temporal import TemporalMemoryStore

class AtlasOrchestrator:
    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self.loop_detector = LoopDetector()
        self.budget_manager = InheritedBudgetManager()
        self.correlation_calc = CorrelationCalculator()

    def determine_effort_scaling(self, objective: str, requested_subagents: Optional[List[str]] = None) -> Tuple[int, List[str], bool]:
        if requested_subagents:
            agents = requested_subagents
        else:
            obj_lower = objective.lower()
            if "research" in obj_lower or "riset" in obj_lower:
                agents = ["clio", "iris"]
            elif "code" in obj_lower or "koding" in obj_lower or "fitur" in obj_lower:
                agents = ["vulcan", "athena", "themis"]
            elif "incident" in obj_lower or "insiden" in obj_lower or "ops" in obj_lower:
                agents = ["hermes", "themis", "iris"]
            elif "full" in obj_lower or "komprehensif" in obj_lower or "enterprise" in obj_lower:
                agents = ["clio", "vulcan", "athena", "themis", "metron", "mnemosyne", "iris"]
            else:
                agents = ["clio"]

        count = len(agents)
        requires_human_confirmation = count > 4
        return count, agents[:10], requires_human_confirmation

    async def execute_run(
        self,
        thread_id: str,
        objective: str,
        requested_subagents: Optional[List[str]] = None,
        event_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        now = time.time()

        # 1. Effort scaling check
        count, selected_agents, needs_confirm = self.determine_effort_scaling(objective, requested_subagents)

        # Atlas Master Budget
        atlas_budget = BudgetEnvelope(
            max_tokens=1500000,
            max_usd=10.0,
            max_wall_clock_s=2700,
            depth_left=2,
            max_steps=60
        )

        db = await get_db_connection()
        try:
            # Ensure thread exists
            await db.execute("""
                INSERT OR IGNORE INTO threads (thread_id, title, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (thread_id, objective[:50], "{}", now, now))

            await db.execute("""
                INSERT INTO runs (
                    run_id, thread_id, status, objective, current_subagent,
                    budget_allocated_json, budget_spent_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, thread_id, "running", objective, "atlas",
                json.dumps(atlas_budget.model_dump()), json.dumps({"spent_tokens": 0, "spent_usd": 0.0}),
                now, now
            ))
            await db.commit()
        finally:
            await db.close()

        await record_audit_log("atlas", "run.start", f"run:{run_id}", {"objective": objective, "agents": selected_agents}, "success")

        delegates_report: List[Dict[str, Any]] = []
        citations: List[str] = []
        handoffs_record: List[Tuple[str, str]] = []

        async def emit_event(subagent_id: str, event_type: str, payload: Dict[str, Any], tokens: int = 0, cost: float = 0.0, latency_ms: float = 0.0):
            evt = TelemetryEvent(
                run_id=run_id,
                subagent_id=subagent_id,
                event_type=event_type,
                payload=payload,
                tokens_in=tokens,
                tokens_out=tokens // 2,
                cost_usd=cost,
                latency_ms=latency_ms
            )
            db_conn = await get_db_connection()
            try:
                await db_conn.execute("""
                    INSERT INTO telemetry_events (event_id, run_id, subagent_id, event_type, payload_json, tokens_in, tokens_out, cost_usd, latency_ms, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (evt.event_id, evt.run_id, evt.subagent_id, evt.event_type, json.dumps(evt.payload), evt.tokens_in, evt.tokens_out, evt.cost_usd, evt.latency_ms, evt.timestamp))
                await db_conn.commit()
            finally:
                await db_conn.close()

            if event_callback:
                await event_callback(evt)

        await emit_event("atlas", "node.start", {"objective": objective, "selected_agents": selected_agents})

        # Process each subagent sequentially or with handoffs
        critic_loop_done = False
        for agent_id in selected_agents:
            if self.circuit_breaker.is_open(agent_id):
                await emit_event(agent_id, "circuit.tripped", {"reason": "Subagent dinonaktifkan karena 3 kegagalan beruntun"})
                continue

            contract = CONTRACTS_MAP.get(agent_id)
            if not contract:
                continue

            # Inherited Budget allocation
            req_tokens = min(contract.budget_config.get("max_tokens", 200000), 200000)
            req_usd = min(contract.budget_config.get("max_usd", 1.0), 1.0)

            try:
                child_budget = self.budget_manager.validate_delegation_budget(atlas_budget, req_tokens, req_usd)
            except ValueError as ve:
                await emit_event("atlas", "budget.exceeded", {"error": str(ve)})
                break

            # Create ContextPacket
            pkt = ContextPacket(
                run_id=run_id,
                caller_agent="atlas",
                target_agent=agent_id,
                objective=f"Eksekusi bagian dari '{objective}' sesuai kapabilitas {contract.name}",
                output_schema_ref=f"schema:{agent_id}",
                tool_grants=contract.tool_grants,
                budget=child_budget,
                state_input={"task": objective}
            )

            # Loop check
            state_hash = self.loop_detector.compute_state_hash(agent_id, "delegate", {"target": agent_id}, pkt.state_input)
            if self.loop_detector.record_and_check(state_hash):
                # Trigger HITL interrupt
                hitl_id = f"hitl-{uuid.uuid4().hex[:12]}"
                db_conn = await get_db_connection()
                try:
                    await db_conn.execute("""
                        INSERT INTO hitl_inbox (interrupt_id, run_id, subagent_id, reason, state_diff_json, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'pending', ?)
                    """, (hitl_id, run_id, agent_id, "Deteksi state loop berulang >= 3", json.dumps({"state_hash": state_hash}), time.time()))
                    await db_conn.execute("UPDATE runs SET status='interrupted' WHERE run_id=?", (run_id,))
                    await db_conn.commit()
                finally:
                    await db_conn.close()
                await emit_event(agent_id, "interrupt", {"hitl_id": hitl_id, "reason": "Loop detected >= 3"})
                return {
                    "run_id": run_id,
                    "status": "interrupted",
                    "hitl_id": hitl_id,
                    "message": "Eksekusi diinterupsi oleh Loop Detector. Membutuhkan persetujuan manusia."
                }

            await emit_event("atlas", "delegate", {"to": agent_id, "packet_id": pkt.packet_id})
            handoffs_record.append(("atlas", agent_id))

            # Simulate subagent execution
            t_start = time.time()
            step_tokens = 15000
            step_cost = 0.08
            child_budget.record_usage(step_tokens, step_cost)
            atlas_budget.record_usage(step_tokens, step_cost)

            # Subagent specific behavior
            result_payload: Dict[str, Any] = {}
            if agent_id == "clio":
                # Security tool guard test: Clio has NO Admin MCP
                allowed, reason = SecurityToolGuard.validate_subagent_tool_access("clio", "web_search", {})
                result_payload = {
                    "findings": [
                        f"Hasil riset mendalam untuk: '{objective}'",
                        "Literatur multi-agent mendukung pola supervisor-via-tools",
                        "Bi-temporal memory memisahkan valid_at dan created_at"
                    ],
                    "sources": ["https://arxiv.org/abs/2501.13956", "https://anthropic.com/research/multi-agent"]
                }
                citations.extend(result_payload["sources"])

            elif agent_id == "vulcan":
                # Vulcan creates proposed code & enters critic loop with Athena
                result_payload = {
                    "code_diff": "diff --git a/graph.py b/graph.py\n+ def execute_node(state): return state",
                    "status": "proposed"
                }

                # Check Vulcan -> Athena handoff swarm (Critic Loop)
                if "athena" in selected_agents and not critic_loop_done:
                    await emit_event("vulcan", "handoff", {"target": "athena", "type": "CRITICIZES"})
                    handoffs_record.append(("vulcan", "athena"))

                    # Athena reviews
                    await emit_event("athena", "node.start", {"reviewing": "vulcan_diff"})
                    athena_tokens = 8000
                    athena_cost = 0.04
                    atlas_budget.record_usage(athena_tokens, athena_cost)

                    # Athena gives feedback & revision
                    critique = "Kode bersih, lulus sanitasi AST, lolos audit keamanan."
                    await emit_event("athena", "handoff", {"target": "vulcan", "status": "APPROVED", "critique": critique})
                    handoffs_record.append(("athena", "vulcan"))
                    critic_loop_done = True

                    delegates_report.append({
                        "subagent": "athena",
                        "status": "completed",
                        "critique": critique,
                        "approved": True
                    })

            elif agent_id == "themis":
                # Themis security check
                # Verify secret hygiene & tamper-evident audit
                result_payload = {
                    "integrity_verified": True,
                    "secret_hygiene": "Semua rahasia menggunakan referensi 'secret://' - tidak ada plain secret bocor",
                    "violations_count": 0
                }

            elif agent_id == "hermes":
                result_payload = {
                    "system_health": "100% OK",
                    "latency_p95_ms": 120.4,
                    "active_workers": 4
                }

            elif agent_id == "mnemosyne":
                # Ingest temporal fact
                fact = TemporalMemoryStore.create_fact(
                    subject=f"Run_{run_id}",
                    predicate="ACCOMPLISHED",
                    obj=objective,
                    episode_run_id=run_id
                )
                db_conn = await get_db_connection()
                try:
                    await db_conn.execute("""
                        INSERT INTO temporal_facts (fact_id, subject, predicate, object, valid_at, invalid_at, created_at, expired_at, episode_run_id, pii_redacted)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (fact.fact_id, fact.subject, fact.predicate, fact.object, fact.valid_at, fact.invalid_at, fact.created_at, fact.expired_at, fact.episode_run_id, 1))
                    await db_conn.commit()
                finally:
                    await db_conn.close()
                result_payload = {"facts_ingested": 1, "fact_id": fact.fact_id}

            elif agent_id == "metron":
                result_payload = {
                    "eval_score": 0.96,
                    "cost_drift_pct": 2.1,
                    "regression_gate": "PASSED"
                }

            elif agent_id == "iris":
                result_payload = {
                    "documentation": f"Laporan eksekutif tersusun rapi untuk target: '{objective}'"
                }

            elif agent_id == "janus":
                result_payload = {
                    "mcp_servers_healthy": 3,
                    "tool_annotations_validated": True
                }

            latency_ms = (time.time() - t_start) * 1000
            await emit_event(agent_id, "node.end", result_payload, tokens=step_tokens, cost=step_cost, latency_ms=latency_ms)

            delegates_report.append({
                "subagent": agent_id,
                "name": contract.name,
                "pod": contract.pod,
                "status": "completed",
                "tokens": step_tokens,
                "cost_usd": step_cost,
                "output": result_payload
            })

        # Update run status in DB
        db_conn = await get_db_connection()
        try:
            await db_conn.execute("""
                UPDATE runs
                SET status = 'completed',
                    budget_spent_json = ?,
                    updated_at = ?
                WHERE run_id = ?
            """, (json.dumps({"spent_tokens": atlas_budget.spent_tokens, "spent_usd": atlas_budget.spent_usd}), time.time(), run_id))

            # Update correlation edges for recorded handoffs
            for src, tgt in handoffs_record:
                edge = self.correlation_calc.compute_edge(
                    source=src,
                    target=tgt,
                    handoffs=1,
                    total_source_handoffs=len([h for h in handoffs_record if h[0] == src]),
                    co_activations=1,
                    source_activations=1,
                    target_activations=1,
                    total_runs=1,
                    co_successes=1,
                    total_successes=1
                )
                await db_conn.execute("""
                    INSERT INTO correlation_edges (
                        source_subagent, target_subagent, handoff_rate, npmi_coactivation,
                        success_lift, composite_weight, polarity, sample_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_subagent, target_subagent) DO UPDATE SET
                        handoff_rate = excluded.handoff_rate,
                        composite_weight = excluded.composite_weight,
                        polarity = excluded.polarity,
                        sample_count = correlation_edges.sample_count + 1,
                        updated_at = excluded.updated_at
                """, (
                    edge.source_subagent, edge.target_subagent, edge.handoff_rate,
                    edge.npmi_coactivation, edge.success_lift, edge.composite_weight,
                    edge.polarity, edge.sample_count, edge.updated_at
                ))
            await db_conn.commit()
        finally:
            await db_conn.close()

        final_answer = f"Tugas '{objective}' telah selesai diproses oleh tim {len(delegates_report)} subagent dengan pola supervisor Atlas dan handoff terukur."
        await record_audit_log("atlas", "run.complete", f"run:{run_id}", {"total_tokens": atlas_budget.spent_tokens, "total_cost": atlas_budget.spent_usd}, "success")

        return {
            "run_id": run_id,
            "status": "completed",
            "final_answer": final_answer,
            "citations": list(set(citations)),
            "delegates_report": delegates_report,
            "cost_summary": {
                "total_tokens": atlas_budget.spent_tokens,
                "total_usd": atlas_budget.spent_usd,
                "daily_budget_remaining": InheritedBudgetManager.DAILY_HARD_STOP_USD - atlas_budget.spent_usd
            }
        }
