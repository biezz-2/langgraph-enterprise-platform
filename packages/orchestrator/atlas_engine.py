import uuid
import os
import time
import json
import asyncio
import logging
import operator
from typing import Dict, List, Any, Optional, Tuple, Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.base import BaseCheckpointSaver

from packages.core.models import (
    BudgetEnvelope,
    ContextPacket,
    TelemetryEvent,
    HITLInterrupt,
    TemporalFact
)
from packages.core.db import get_db_connection, record_audit_log
from packages.core.checkpointer import get_checkpointer
from packages.subagents.contracts import CONTRACTS_MAP, TEN_SUBAGENTS_CONTRACTS, get_deepagents_subagents
from packages.guardrails.guards import (
    InheritedBudgetManager,
    CircuitBreaker,
    LoopDetector,
    SecurityToolGuard
)
from packages.telemetry.correlation import CorrelationCalculator
from packages.memory.temporal import TemporalMemoryStore

logger = logging.getLogger("packages.orchestrator.atlas_engine")

try:
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend, FilesystemBackend
    from langchain_core.messages import HumanMessage, AIMessage
    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False
    StateBackend = None  # type: ignore
    FilesystemBackend = None  # type: ignore
    create_deep_agent = None  # type: ignore


class AtlasState(TypedDict):
    """Skema StateGraph Atlas LGP v2.0 dengan reducer eksplisit."""
    thread_id: str
    run_id: str
    objective: str
    selected_agents: List[str]
    current_subagent: str
    delegates_report: Annotated[List[Dict[str, Any]], operator.add]
    citations: Annotated[List[str], operator.add]
    handoffs_record: Annotated[List[Tuple[str, str]], operator.add]
    tokens_spent: Annotated[int, operator.add]
    cost_spent: Annotated[float, operator.add]
    final_answer: str
    status: str
    interrupted: bool
    hitl_id: Optional[str]
    error: Optional[str]
    approvals: Annotated[List[Dict[str, Any]], operator.add]


# Subagent yang outputnya wajib disetujui manusia (native interrupt) sebelum lanjut.
HITL_GATES: Tuple[str, ...] = ("vulcan", "themis")


class AtlasOrchestrator:
    def __init__(
        self,
        deepagent_model: Optional[Any] = None,
        backend: Optional[Any] = None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        hitl_gates: Tuple[str, ...] = HITL_GATES
    ):
        self.hitl_gates = tuple(hitl_gates)
        self.circuit_breaker = CircuitBreaker()
        self.loop_detector = LoopDetector()
        self.budget_manager = InheritedBudgetManager()
        self.correlation_calc = CorrelationCalculator()
        self.deepagent_model = deepagent_model
        self.backend = backend or (StateBackend() if DEEPAGENTS_AVAILABLE else None)
        self.checkpointer = checkpointer
        self._compiled_deepagent = None
        self._active_callback = None

    def get_or_build_deep_agent(
        self,
        model: Optional[Any] = None,
        memory_sources: Optional[List[str]] = None,
        tools: Optional[List[Any]] = None
    ) -> Optional[Any]:
        """Menyusun dan mengompilasi runtime DeepAgents untuk Atlas Supervisor."""
        if not DEEPAGENTS_AVAILABLE:
            return None
        target_model = model or self.deepagent_model
        if target_model is None:
            return None
        
        sources = memory_sources or ["/memory/AGENTS.md"]
        subagents = get_deepagents_subagents(model=target_model)
        
        system_prompt = (
            "Kamu adalah Atlas — Supervisor Orchestrator LGP v2.0.\n"
            "Tugasmu adalah menganalisis objective pengguna, mengalokasikan konteks tugas, "
            "dan mendelegasikan ke subagent terspesialisasi (Clio, Vulcan, Athena, dsb.) via tool task.\n"
            "Gunakan referensi memory/AGENTS.md untuk panduan konsistensi dan fakta bi-temporal."
        )

        return create_deep_agent(
            model=target_model,
            subagents=subagents,
            memory=sources,
            tools=tools or [],
            backend=self.backend or StateBackend(),
            system_prompt=system_prompt
        )

    def determine_effort_scaling(
        self,
        objective: str,
        requested_subagents: Optional[List[str]] = None
    ) -> Tuple[int, List[str], bool]:
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

    async def _call_subagent_llm(
        self,
        agent_id: str,
        objective: str,
        run_id: str
    ) -> Dict[str, Any]:
        """Eksekusi subagent via LLM nyata (9router OpenAI-compatible /v1/chat/completions).

        Mengembalikan {"output": dict, "citations": [...], "tokens": int, "cost_usd": float}.
        Raise exception jika LLM tidak tersedia/gagal — caller menangani circuit breaker.
        """
        base_url = os.environ.get("ROUTER_BASE_URL", "https://9router.biezz.my.id/v1").rstrip("/")
        api_key = os.environ.get("ROUTER_API_KEY") or os.environ.get("NINE_ROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("ROUTER_API_KEY tidak terkonfigurasi")
        # Chain model: env ROUTER_LLM_MODEL diutamakan, fallback ke model yang
        # terverifikasi aktif di 9router (comma-separated via ROUTER_LLM_FALLBACKS).
        primary = os.environ.get("ROUTER_LLM_MODEL") or ""
        fallbacks = [m.strip() for m in os.environ.get(
            "ROUTER_LLM_FALLBACKS",
            "groq/openai/gpt-oss-120b,kc/nvidia/nemotron-3-ultra-550b-a55b:free"
        ).split(",") if m.strip()]
        models = [m for m in [primary, *fallbacks] if m]

        contract = CONTRACTS_MAP.get(agent_id)
        role = contract.role if contract else agent_id
        pod = contract.pod if contract else "unknown"
        caps = ", ".join(contract.capabilities[:4]) if contract else ""

        instructions = {
            "clio": "Riset mendalam: berikan findings substantif dan sources/citations relevan.",
            "vulcan": "Software engineer: hasilkan code_diff/usulan implementasi konkret (format unified diff atau penjelasan patch).",
            "athena": "Critic reviewer: berikan critique tajam, approved true/false, dan isu yang ditemukan.",
            "themis": "Security & compliance: laporkan integrity_verified, secret_hygiene, violations_count, dan temuan.",
            "hermes": "Platform ops: laporkan system_health, latency, worker status, dan observasi infrastruktur.",
            "mnemosyne": "Memory curator: ekstrak fakta penting (subject/predicate/object) dari objective.",
            "metron": "Evaluation: berikan eval_score, cost_drift_pct, regression_gate (PASSED/FAILED), dan metrik.",
            "iris": "Documentation writer: hasilkan dokumentasi/laporan eksekutif yang rapi.",
            "janus": "Integration MCP hub: laporkan status integrasi MCP, tool annotations, dan konektivitas.",
            "atlas": "Supervisor: sintesis delegasi dan rencana orkestrasi.",
        }
        instruction = instructions.get(agent_id, "Kerjakan tugas sesuai peranmu.")

        system_prompt = (
            f"Kamu adalah subagen {contract.name if contract else agent_id} "
            f"(role: {role}, pod: {pod}{', capabilities: ' + caps if caps else ''}) "
            f"dalam platform multi-agent LGP v2.0.\n"
            f"{instruction}\n"
            "Balas HANYA dengan JSON valid (tanpa markdown fence) dengan struktur "
            '{"output": {...field relevan untuk peranmu...}, "citations": ["..."]}.'
        )
        user_prompt = f"Objective run {run_id}:\n{objective}"

        from openai import AsyncOpenAI, APIError
        client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=120.0)

        last_err: Optional[Exception] = None
        resp = None
        used_model = ""
        for model in models:
            try:
                kwargs: Dict[str, Any] = {}
                if model.startswith("groq/"):
                    kwargs["extra_body"] = {"reasoning_effort": "low"}
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=4096,
                    **kwargs,
                )
                used_model = model
                break
            except APIError as e:
                last_err = e
                logger.warning("LLM model %s gagal untuk %s: %s", model, agent_id, str(e)[:200])
                continue
        if resp is None:
            raise last_err or RuntimeError("Semua model LLM fallback gagal")

        content = resp.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()

        usage = getattr(resp, "usage", None)
        tokens = getattr(usage, "total_tokens", 0) or 0
        # Estimasi biaya konservatif $0.000002/token untuk model router internal
        cost_usd = round(tokens * 0.000002, 6)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"output": {"result": content}}

        output = parsed.get("output", parsed if isinstance(parsed, dict) else {})
        citations = parsed.get("citations", []) if isinstance(parsed, dict) else []
        if not isinstance(output, dict):
            output = {"result": str(output)}
        if not isinstance(citations, list):
            citations = []

        return {
            "output": output,
            "citations": [str(c) for c in citations[:10]],
            "tokens": tokens,
            "cost_usd": cost_usd,
            "model": used_model,
        }

    async def _emit_event(
        self,
        run_id: str,
        subagent_id: str,
        event_type: str,
        payload: Dict[str, Any],
        tokens: int = 0,
        cost: float = 0.0,
        latency_ms: float = 0.0,
        event_id: Optional[str] = None
    ):
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
        if event_id:  # ID deterministik: re-eksekusi node setelah resume tidak menggandakan event
            evt.event_id = event_id
        db_conn = await get_db_connection()
        try:
            if event_id:
                async with db_conn.execute("SELECT 1 FROM telemetry_events WHERE event_id = ?", (event_id,)) as cur:
                    if await cur.fetchone():
                        return
            await db_conn.execute("""
                INSERT INTO telemetry_events (
                    event_id, run_id, subagent_id, event_type, payload_json,
                    tokens_in, tokens_out, cost_usd, latency_ms, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                evt.event_id, evt.run_id, evt.subagent_id, evt.event_type,
                json.dumps(evt.payload), evt.tokens_in, evt.tokens_out,
                evt.cost_usd, evt.latency_ms, evt.timestamp
            ))
            await db_conn.commit()
        finally:
            await db_conn.close()

        if self._active_callback:
            try:
                res = self._active_callback(evt)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def build_graph(self, checkpointer: Optional[BaseCheckpointSaver] = None):
        """Menyusun StateGraph LGP v2.0 dengan reducer eksplisit dan routing terkelola."""
        builder = StateGraph(AtlasState)

        # 1. Supervisor Node
        async def supervisor_node(state: AtlasState) -> Dict[str, Any]:
            return {
                "current_subagent": "atlas",
                "status": "running"
            }

        # Subagent execution builder
        def make_subagent_node(agent_id: str):
            async def node(state: AtlasState) -> Dict[str, Any]:
                run_id = state["run_id"]
                objective = state["objective"]

                # Cek Circuit Breaker
                if self.circuit_breaker.is_open(agent_id):
                    await self._emit_event(
                        run_id, agent_id, "circuit.tripped",
                        {"reason": "Subagent dinonaktifkan karena kegagalan beruntun"}
                    )
                    return {
                        "current_subagent": agent_id,
                        "delegates_report": [{
                            "subagent": agent_id,
                            "status": "tripped",
                            "error": "Circuit breaker is open"
                        }]
                    }

                # Cek Loop Detector
                state_hash = self.loop_detector.compute_state_hash(agent_id, "delegate", {"target": agent_id}, {"task": objective})
                if self.loop_detector.record_and_check(state_hash):
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

                    await self._emit_event(run_id, agent_id, "interrupt", {"hitl_id": hitl_id, "reason": "Loop detected >= 3"})
                    return {
                        "current_subagent": agent_id,
                        "status": "interrupted",
                        "interrupted": True,
                        "hitl_id": hitl_id
                    }

                t_start = time.time()
                step_tokens = 0
                step_cost = 0.0
                handoffs: List[Tuple[str, str]] = [("atlas", agent_id)]
                citations_new: List[str] = []
                report_entry: Dict[str, Any] = {
                    "subagent": agent_id,
                    "status": "completed",
                    "tokens": step_tokens,
                    "cost_usd": step_cost
                }

                await self._emit_event(run_id, "atlas", "delegate", {"to": agent_id})

                # Guardrail: budget harian + least-privilege tool access check
                if not self.budget_manager.check_daily_limit(step_cost):
                    self.circuit_breaker.record_failure(agent_id)
                    report_entry["status"] = "budget_exceeded"
                    report_entry["output"] = {"denied": True, "reason": "daily_hard_stop"}
                    return {
                        "current_subagent": agent_id,
                        "delegates_report": [report_entry],
                        "citations": citations_new,
                        "handoffs_record": handoffs,
                        "tokens_spent": 0,
                        "cost_spent": 0.0,
                    }
                allowed, deny_reason = SecurityToolGuard.validate_subagent_tool_access(
                    agent_id, "llm:delegate", {"objective": objective[:200]}
                )
                if not allowed:
                    self.circuit_breaker.record_failure(agent_id)
                    report_entry["status"] = "denied"
                    report_entry["output"] = {"denied": True, "reason": deny_reason}
                    return {
                        "current_subagent": agent_id,
                        "delegates_report": [report_entry],
                        "citations": citations_new,
                        "handoffs_record": handoffs,
                        "tokens_spent": 0,
                        "cost_spent": 0.0,
                    }

                # Eksekusi subagent nyata via LLM (9router OpenAI-compatible)
                try:
                    llm_result = await self._call_subagent_llm(agent_id, objective, run_id)
                    report_entry["output"] = llm_result.get("output", {})
                    if llm_result.get("model"):
                        report_entry["model"] = llm_result["model"]
                    if llm_result.get("citations"):
                        citations_new.extend(llm_result["citations"])
                    if llm_result.get("tokens"):
                        step_tokens = llm_result["tokens"]
                    if llm_result.get("cost_usd") is not None:
                        step_cost = llm_result["cost_usd"]
                except Exception as llm_err:
                    logger.warning("LLM call subagent %s gagal: %s", agent_id, llm_err)
                    self.circuit_breaker.record_failure(agent_id)
                    report_entry["status"] = "failed"
                    report_entry["output"] = {"error": str(llm_err)}
                    return {
                        "current_subagent": agent_id,
                        "delegates_report": [report_entry],
                        "citations": citations_new,
                        "handoffs_record": handoffs,
                        "tokens_spent": step_tokens,
                        "cost_spent": step_cost,
                    }

                # Efek samping khusus Mnemosyne: persist fakta ke temporal store
                if agent_id == "mnemosyne":
                    try:
                        fact = TemporalMemoryStore.create_fact(
                            subject=f"Run_{run_id}",
                            predicate="ACCOMPLISHED",
                            obj=objective,
                            episode_run_id=run_id
                        )
                        db_conn = await get_db_connection()
                        try:
                            await db_conn.execute("""
                                INSERT INTO temporal_facts (
                                    fact_id, subject, predicate, object, valid_at,
                                    invalid_at, created_at, expired_at, episode_run_id, pii_redacted
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                fact.fact_id, fact.subject, fact.predicate, fact.object,
                                fact.valid_at, fact.invalid_at, fact.created_at,
                                fact.expired_at, fact.episode_run_id, 1
                            ))
                            await db_conn.commit()
                        finally:
                            await db_conn.close()
                        report_entry["output"]["facts_ingested"] = 1
                        report_entry["output"]["fact_id"] = fact.fact_id
                    except Exception as mem_err:
                        logger.warning("Mnemosyne persist gagal: %s", mem_err)

                # Critic loop Vulcan <-> Athena tetap dipertahankan
                if agent_id == "athena" and "vulcan" in (state.get("selected_agents") or []):
                    handoffs.extend([("vulcan", "athena"), ("athena", "vulcan")])

                self.circuit_breaker.record_success(agent_id)
                self.budget_manager.daily_spent_usd += step_cost

                latency_ms = (time.time() - t_start) * 1000
                await self._emit_event(
                    run_id, agent_id, "node.end",
                    report_entry.get("output", {}),
                    tokens=step_tokens,
                    cost=step_cost,
                    latency_ms=latency_ms
                )

                contract = CONTRACTS_MAP.get(agent_id)
                if contract:
                    report_entry["name"] = contract.name
                    report_entry["pod"] = contract.pod

                return {
                    "current_subagent": agent_id,
                    "delegates_report": [report_entry],
                    "citations": citations_new,
                    "handoffs_record": handoffs,
                    "tokens_spent": step_tokens,
                    "cost_spent": step_cost
                }

            return node

        # HITL approval node: interrupt() native + resume via Command(resume=payload).
        # LangGraph mengeksekusi ulang node dari awal saat resume, jadi semua efek
        # samping SEBELUM interrupt() wajib idempoten (ID deterministik + ON CONFLICT DO NOTHING).
        def make_approval_node(agent_id: str):
            async def approval_node(state: AtlasState) -> Dict[str, Any]:
                run_id = state["run_id"]
                report = next(
                    (r for r in reversed(state.get("delegates_report", [])) if r.get("subagent") == agent_id),
                    {}
                )
                hitl_id = f"hitl-{run_id}-{agent_id}"
                now = time.time()
                diff = {"kind": "approval", "thread_id": state["thread_id"], "output": report.get("output", {})}

                # --- efek samping pra-interrupt (idempoten) ---
                db_conn = await get_db_connection()
                try:
                    await db_conn.execute("""
                        INSERT INTO hitl_inbox (interrupt_id, run_id, subagent_id, reason, state_diff_json, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'pending', ?)
                        ON CONFLICT (interrupt_id) DO NOTHING
                    """, (hitl_id, run_id, agent_id, f"Persetujuan manusia untuk output {agent_id}", json.dumps(diff), now))
                    await db_conn.execute("UPDATE runs SET status='interrupted', updated_at=? WHERE run_id=?", (now, run_id))
                    await db_conn.commit()
                finally:
                    await db_conn.close()
                await self._emit_event(
                    run_id, agent_id, "interrupt",
                    {"hitl_id": hitl_id, "reason": "approval_required"},
                    event_id=f"evt-{hitl_id}-interrupt"
                )

                # --- titik jeda: resume mengembalikan payload dari Command(resume=...) ---
                payload = interrupt({"hitl_id": hitl_id, "subagent": agent_id, "output": report.get("output", {})})
                payload = payload if isinstance(payload, dict) else {"decision": str(payload)}
                decision = str(payload.get("decision", "rejected")).lower()
                approved = decision in ("approved", "approve")
                approver = payload.get("approver", "human")

                # --- pasca-interrupt: berjalan sekali ---
                db_conn = await get_db_connection()
                try:
                    await db_conn.execute(
                        "UPDATE runs SET status=?, updated_at=? WHERE run_id=?",
                        ("running" if approved else "rejected", time.time(), run_id)
                    )
                    await db_conn.execute(
                        "UPDATE hitl_inbox SET status=?, approver=?, decision=?, resolved_at=? WHERE interrupt_id=?",
                        ("approved" if approved else "rejected", approver, decision, time.time(), hitl_id)
                    )
                    await db_conn.commit()
                finally:
                    await db_conn.close()
                await record_audit_log(
                    approver, "hitl.resume", f"run:{run_id}",
                    {"hitl_id": hitl_id, "subagent": agent_id, "decision": decision}, "success"
                )
                out: Dict[str, Any] = {
                    "current_subagent": agent_id,
                    "approvals": [{"subagent": agent_id, "hitl_id": hitl_id, "decision": decision, "approver": approver}],
                    "hitl_id": hitl_id,
                }
                if not approved:
                    out["status"] = "rejected"
                return out

            return approval_node

        # 2. Tambahkan node subagent
        for aid in ["clio", "vulcan", "athena", "themis", "hermes", "mnemosyne", "metron", "iris", "janus"]:
            builder.add_node(aid, make_subagent_node(aid))

        # 3. Synthesizer Node
        async def synthesizer_node(state: AtlasState) -> Dict[str, Any]:
            run_id = state["run_id"]
            objective = state["objective"]
            reports = state.get("delegates_report", [])
            handoffs = state.get("handoffs_record", [])
            tokens = state.get("tokens_spent", 0)
            cost = round(state.get("cost_spent", 0.0), 4)

            # Update status run di DB
            db_conn = await get_db_connection()
            try:
                await db_conn.execute("""
                    UPDATE runs
                    SET status = 'completed',
                        budget_spent_json = ?,
                        updated_at = ?
                    WHERE run_id = ?
                """, (json.dumps({"spent_tokens": tokens, "spent_usd": cost}), time.time(), run_id))

                # Update correlation edges untuk handoff
                for src, tgt in handoffs:
                    edge = self.correlation_calc.compute_edge(
                        source=src,
                        target=tgt,
                        handoffs=1,
                        total_source_handoffs=len([h for h in handoffs if h[0] == src]),
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

            final_ans = f"Tugas '{objective}' telah selesai diproses oleh tim {len(reports)} subagent dengan StateGraph LGP v2.0 dan handoff terukur."
            await record_audit_log(
                "atlas", "run.complete", f"run:{run_id}",
                {"total_tokens": tokens, "total_cost": cost}, "success"
            )

            return {
                "current_subagent": "atlas",
                "final_answer": final_ans,
                "status": "completed"
            }

        for gate in self.hitl_gates:
            builder.add_node(f"{gate}_approval", make_approval_node(gate))

        builder.add_node("supervisor", supervisor_node)
        builder.add_node("synthesizer", synthesizer_node)

        # 4. Conditional Edge Router
        def route_next(state: AtlasState) -> str:
            if state.get("interrupted") or state.get("status") == "rejected":
                return END

            cur_ = state.get("current_subagent")
            approved_ids = {a["subagent"] for a in state.get("approvals", [])}
            ran_ids = {r["subagent"] for r in state.get("delegates_report", []) if r.get("status") == "completed"}
            if cur_ in self.hitl_gates and cur_ in ran_ids and cur_ not in approved_ids:
                return f"{cur_}_approval"

            done_agents = [r["subagent"] for r in state.get("delegates_report", []) if r.get("status") == "completed"]
            terminal_agents = {r["subagent"] for r in state.get("delegates_report", []) if r.get("status") in ("completed", "tripped", "failed", "denied", "budget_exceeded", "interrupted")}
            cur = state.get("current_subagent")
            selected = state.get("selected_agents", [])

            # Critic Loop Swarm: Vulcan -> Athena jika keduanya terpilih
            if cur == "vulcan" and "athena" in selected and "athena" not in done_agents and "athena" not in terminal_agents:
                return "athena"

            for agent in selected:
                if agent not in terminal_agents:
                    if agent in ["clio", "vulcan", "athena", "themis", "hermes", "mnemosyne", "metron", "iris", "janus"]:
                        return agent

            if cur != "synthesizer" and state.get("status") != "completed":
                return "synthesizer"

            return END

        builder.add_edge(START, "supervisor")

        nodes_with_router = [
            "supervisor", "clio", "vulcan", "athena", "themis",
            "hermes", "mnemosyne", "metron", "iris", "janus"
        ]
        routing_targets = {
            "clio": "clio", "vulcan": "vulcan", "athena": "athena",
            "themis": "themis", "hermes": "hermes", "mnemosyne": "mnemosyne",
            "metron": "metron", "iris": "iris", "janus": "janus",
            "synthesizer": "synthesizer", END: END
        }

        nodes_with_router = nodes_with_router + [f"{g}_approval" for g in self.hitl_gates]
        routing_targets.update({f"{g}_approval": f"{g}_approval" for g in self.hitl_gates})
        for n in nodes_with_router:
            builder.add_conditional_edges(n, route_next, routing_targets)

        builder.add_edge("synthesizer", END)

        return builder.compile(checkpointer=checkpointer)

    async def execute_run(
        self,
        thread_id: str,
        objective: str,
        requested_subagents: Optional[List[str]] = None,
        event_callback: Optional[Any] = None,
        use_deepagents: bool = False,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        now = time.time()
        self._active_callback = event_callback
        # Scope LoopDetector per run agar run berbeda tidak saling false-positive
        try:
            self.loop_detector.history.clear()
        except Exception:
            pass

        # 1. Effort scaling
        count, selected_agents, needs_confirm = self.determine_effort_scaling(objective, requested_subagents)

        atlas_budget = BudgetEnvelope(
            max_tokens=1500000,
            max_usd=10.0,
            max_wall_clock_s=2700,
            depth_left=2,
            max_steps=60
        )

        db = await get_db_connection()
        try:
            await db.execute("""
                INSERT INTO threads (thread_id, title, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (thread_id) DO NOTHING
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

        await record_audit_log(
            "atlas", "run.start", f"run:{run_id}",
            {"objective": objective, "agents": selected_agents}, "success"
        )
        await self._emit_event(
            run_id, "atlas", "node.start",
            {"objective": objective, "selected_agents": selected_agents}
        )

        # Jalur DeepAgents Runtime jika diminta
        if use_deepagents and DEEPAGENTS_AVAILABLE and self.deepagent_model is not None:
            agent = self.get_or_build_deep_agent()
            if agent:
                db_conn = await get_db_connection()
                facts = []
                try:
                    async with db_conn.execute("SELECT * FROM temporal_facts WHERE invalid_at IS NULL OR invalid_at > ?", (now,)) as cursor:
                        for row in await cursor.fetchall():
                            facts.append(TemporalFact(**dict(row)))
                finally:
                    await db_conn.close()

                memory_md = TemporalMemoryStore.to_agents_markdown(facts)
                input_state: Dict[str, Any] = {
                    "messages": [HumanMessage(content=objective)],
                }
                if isinstance(self.backend, StateBackend) or self.backend is None:
                    input_state["files"] = {
                        "/memory/AGENTS.md": {
                            "content": memory_md,
                            "encoding": "utf-8"
                        }
                    }

                t0 = time.time()
                res = await agent.ainvoke(input_state)
                duration = time.time() - t0

                messages = res.get("messages", [])
                final_answer = ""
                delegates_report_da: List[Dict[str, Any]] = []
                for msg in messages:
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if tc.get("name") == "task":
                                target = tc.get("args", {}).get("subagent", "subagent")
                                sub_task = tc.get("args", {}).get("task", "")
                                await self._emit_event(run_id, "atlas", "delegate", {"to": target, "task": sub_task})
                                delegates_report_da.append({
                                    "subagent": target,
                                    "status": "completed",
                                    "task": sub_task
                                })
                    if isinstance(msg, AIMessage) and msg.content:
                        final_answer = str(msg.content)

                if not final_answer:
                    final_answer = f"Tugas '{objective}' telah selesai diproses via DeepAgents runtime."

                tokens_spent = 20000
                cost_spent = 0.10
                atlas_budget.record_usage(tokens_spent, cost_spent)

                await self._emit_event(
                    run_id, "atlas", "node.end",
                    {"output": final_answer},
                    tokens=tokens_spent, cost=cost_spent, latency_ms=duration * 1000
                )

                db_conn = await get_db_connection()
                try:
                    await db_conn.execute("""
                        UPDATE runs
                        SET status = 'completed',
                            budget_spent_json = ?,
                            updated_at = ?
                        WHERE run_id = ?
                    """, (json.dumps({"spent_tokens": atlas_budget.spent_tokens, "spent_usd": atlas_budget.spent_usd}), time.time(), run_id))
                    await db_conn.commit()
                finally:
                    await db_conn.close()

                await record_audit_log(
                    "atlas", "run.complete", f"run:{run_id}",
                    {"engine": "deepagents", "total_tokens": atlas_budget.spent_tokens, "total_cost": atlas_budget.spent_usd},
                    "success"
                )

                return {
                    "run_id": run_id,
                    "status": "completed",
                    "final_answer": final_answer,
                    "citations": [],
                    "delegates_report": delegates_report_da,
                    "cost_summary": {
                        "total_tokens": atlas_budget.spent_tokens,
                        "total_usd": atlas_budget.spent_usd,
                        "daily_budget_remaining": InheritedBudgetManager.DAILY_HARD_STOP_USD - atlas_budget.spent_usd
                    }
                }

        # Jalur Native StateGraph dengan checkpointer
        active_checkpointer = checkpointer or self.checkpointer
        if active_checkpointer is None:
            active_checkpointer = await get_checkpointer()
        self.checkpointer = active_checkpointer  # dipakai ulang oleh resume/time travel

        graph = self.build_graph(checkpointer=active_checkpointer)

        initial_state: AtlasState = {
            "thread_id": thread_id,
            "run_id": run_id,
            "objective": objective,
            "selected_agents": selected_agents,
            "current_subagent": "atlas",
            "delegates_report": [],
            "citations": [],
            "handoffs_record": [],
            "tokens_spent": 0,
            "cost_spent": 0.0,
            "final_answer": "",
            "status": "pending",
            "interrupted": False,
            "hitl_id": None,
            "error": None,
            "approvals": []
        }

        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        try:
            final_state = await graph.ainvoke(initial_state, config=config)
            return await self._finalize(final_state, run_id)
        except Exception as e:
            logger.error("execute_run gagal untuk run %s: %s", run_id, e)
            db = await get_db_connection()
            try:
                await db.execute(
                    "UPDATE runs SET status = 'failed', updated_at = ? WHERE run_id = ?",
                    (time.time(), run_id)
                )
                await db.commit()
            finally:
                await db.close()
            await record_audit_log("atlas", "run.failed", f"run:{run_id}", {"error": str(e)}, "error")
            await self._emit_event(run_id, "atlas", "node.error", {"error": str(e)})
            return {"run_id": run_id, "status": "failed", "error": str(e)}

    async def _finalize(self, final_state: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        if final_state.get("__interrupt__"):
            intr = final_state["__interrupt__"][0].value
            return {
                "run_id": run_id,
                "status": "interrupted",
                "hitl_id": intr.get("hitl_id"),
                "message": f"Menunggu persetujuan manusia untuk '{intr.get('subagent')}'.",
            }

        if final_state.get("status") == "rejected":
            return {"run_id": run_id, "status": "rejected", "hitl_id": final_state.get("hitl_id"),
                    "message": "Ditolak oleh manusia.", "delegates_report": final_state.get("delegates_report", [])}

        if final_state.get("interrupted"):
            return {
                "run_id": run_id,
                "status": "interrupted",
                "hitl_id": final_state.get("hitl_id"),
                "message": "Eksekusi diinterupsi oleh Loop Detector. Membutuhkan persetujuan manusia."
            }

        reports = final_state.get("delegates_report", [])
        citations_list = list(dict.fromkeys(final_state.get("citations", [])))
        total_tokens = final_state.get("tokens_spent", 0)
        total_cost = round(final_state.get("cost_spent", 0.0), 4)

        return {
            "run_id": run_id,
            "status": final_state.get("status", "completed"),
            "final_answer": final_state.get("final_answer"),
            "citations": citations_list,
            "delegates_report": reports,
            "cost_summary": {
                "total_tokens": total_tokens,
                "total_usd": total_cost,
                "daily_budget_remaining": InheritedBudgetManager.DAILY_HARD_STOP_USD - total_cost
            }
        }

    # ---- Resume & Time Travel ----
    def _graph(self):
        if self.checkpointer is None:
            raise RuntimeError("Belum ada checkpointer: jalankan execute_run terlebih dahulu.")
        return self.build_graph(checkpointer=self.checkpointer)

    async def resume_run(self, thread_id: str, payload: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
        """Lanjutkan run yang di-interrupt: Command(resume=payload) pada thread yang sama."""
        graph = self._graph()
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        snap = await graph.aget_state(config)
        if not snap.next:
            raise ValueError(f"Thread '{thread_id}' tidak memiliki interrupt yang menunggu.")
        run_id = run_id or snap.values.get("run_id", "")
        final_state = await graph.ainvoke(Command(resume=payload), config=config)
        return await self._finalize(final_state, run_id)

    async def get_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """Riwayat checkpoint (terbaru dulu) untuk time travel."""
        graph = self._graph()
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        return [
            {
                "checkpoint_id": s.config["configurable"]["checkpoint_id"],
                "step": s.metadata.get("step"),
                "next": list(s.next),
                "values": s.values,
            }
            async for s in graph.aget_state_history(config)
        ]

    async def fork_from_checkpoint(
        self, thread_id: str, checkpoint_id: str, values: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Cabangkan state dari checkpoint lama (opsional override values), lalu jalankan cabang baru.

        Checkpoint asal tidak berubah; cabang mendapat checkpoint_id baru di thread yang sama.
        """
        graph = self._graph()
        base = {"configurable": {"thread_id": thread_id, "checkpoint_ns": "", "checkpoint_id": checkpoint_id}}
        snap = await graph.aget_state(base)
        run_id = snap.values.get("run_id", "")
        fork_cfg = await graph.aupdate_state(base, values) if values else base
        final_state = await graph.ainvoke(None, config=fork_cfg)
        res = await self._finalize(final_state, run_id)
        res["fork_config"] = fork_cfg["configurable"]
        return res
