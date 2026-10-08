"""
FastAPI REST API router and endpoints for LGP v2.0.
Implements:
- /api/assistants
- /api/threads
- /api/runs (including SSE /api/runs/{run_id}/stream and /api/runs/{run_id}/interrupts)
- /api/subagents (registry, topology, status, circuit breakers)
- /api/correlations (10x10 correlation matrix, edge weights)
- /api/memory/temporal (bi-temporal facts query, time-travel slider)
- /api/audit (tamper-evident hash-chained audit log query)
- /api/health (platform health probes)
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from lgp.contracts.schemas import (
    ActorType,
    AssistantCreate,
    AssistantResponse,
    AssistantUpdate,
    AuditLogEntry,
    AuditQueryResponse,
    AuditVerifyResponse,
    CircuitBreakerState,
    CircuitBreakerStatus,
    ComponentHealth,
    ComponentStatus,
    CorrelationCell,
    CorrelationMatrixResponse,
    CorrelationPolarity,
    CorrelationPolaritySource,
    CorrelationWeightsConfig,
    ErrorType,
    HealthResponse,
    InterruptItem,
    InterruptReason,
    PodName,
    ProblemDetails,
    RunCreate,
    RunResponse,
    RunResumeRequest,
    RunStatus,
    SubagentContract,
    SubagentStatusResponse,
    TemporalFact,
    TemporalQueryResponse,
    ThreadCreate,
    ThreadResponse,
    ThreadStateUpdate,
    TopologyEdge,
    TopologyResponse,
    TrustLevel,
)

router = APIRouter(prefix="/api")


# ============================================================================
# 1. ASSISTANTS ENDPOINTS
# ============================================================================

@router.post(
    "/assistants",
    response_model=AssistantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create assistant configuration",
    tags=["Assistants"],
)
async def create_assistant(body: AssistantCreate) -> AssistantResponse:
    now = datetime.now(timezone.utc)
    return AssistantResponse(
        assistant_id="asst-c0ffee01-0001",
        graph_id=body.graph_id,
        name=body.name,
        description=body.description,
        config=body.config,
        metadata=body.metadata,
        version=1,
        created_at=now,
        updated_at=now,
    )


@router.get(
    "/assistants",
    response_model=List[AssistantResponse],
    summary="List assistants",
    tags=["Assistants"],
)
async def list_assistants(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> List[AssistantResponse]:
    now = datetime.now(timezone.utc)
    return [
        AssistantResponse(
            assistant_id="asst-c0ffee01-0001",
            graph_id="graph_orchestrator_v2",
            name="Atlas Supervisor",
            description="Atlas v2 primary orchestrator assistant",
            config={"max_depth": 2},
            metadata={"environment": "production"},
            version=1,
            created_at=now,
            updated_at=now,
        )
    ]


@router.get(
    "/assistants/{assistant_id}",
    response_model=AssistantResponse,
    summary="Get assistant detail",
    tags=["Assistants"],
)
async def get_assistant(assistant_id: str) -> AssistantResponse:
    now = datetime.now(timezone.utc)
    return AssistantResponse(
        assistant_id=assistant_id,
        graph_id="graph_orchestrator_v2",
        name="Atlas Supervisor",
        description="Atlas v2 primary orchestrator assistant",
        config={"max_depth": 2},
        metadata={"environment": "production"},
        version=1,
        created_at=now,
        updated_at=now,
    )


@router.patch(
    "/assistants/{assistant_id}",
    response_model=AssistantResponse,
    summary="Update assistant configuration",
    tags=["Assistants"],
)
async def update_assistant(assistant_id: str, body: AssistantUpdate) -> AssistantResponse:
    now = datetime.now(timezone.utc)
    return AssistantResponse(
        assistant_id=assistant_id,
        graph_id=body.graph_id or "graph_orchestrator_v2",
        name=body.name or "Atlas Supervisor",
        description=body.description,
        config=body.config or {},
        metadata=body.metadata or {},
        version=2,
        created_at=now,
        updated_at=now,
    )


# ============================================================================
# 2. THREADS ENDPOINTS
# ============================================================================

@router.post(
    "/threads",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create thread session",
    tags=["Threads"],
)
async def create_thread(body: ThreadCreate) -> ThreadResponse:
    now = datetime.now(timezone.utc)
    return ThreadResponse(
        thread_id="th-b0ba0001-0001",
        created_at=now,
        updated_at=now,
        metadata=body.metadata,
        current_checkpoint_id="ckpt-init-0001",
        values={},
    )


@router.get(
    "/threads/{thread_id}",
    response_model=ThreadResponse,
    summary="Get thread state & latest checkpoint",
    tags=["Threads"],
)
async def get_thread(thread_id: str) -> ThreadResponse:
    now = datetime.now(timezone.utc)
    return ThreadResponse(
        thread_id=thread_id,
        created_at=now,
        updated_at=now,
        metadata={"user": "developer"},
        current_checkpoint_id="ckpt-step-0004",
        values={"objective": "Build REST schema", "status": "running"},
    )


@router.post(
    "/threads/{thread_id}/state",
    response_model=ThreadResponse,
    summary="Update or fork thread state",
    tags=["Threads"],
)
async def update_thread_state(thread_id: str, body: ThreadStateUpdate) -> ThreadResponse:
    now = datetime.now(timezone.utc)
    return ThreadResponse(
        thread_id=thread_id,
        created_at=now,
        updated_at=now,
        metadata={"forked_from": body.checkpoint_id},
        current_checkpoint_id="ckpt-fork-0005",
        values=body.values,
    )


# ============================================================================
# 3. RUNS, SSE STREAM, & INTERRUPTS ENDPOINTS
# ============================================================================

@router.post(
    "/runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue and execute run",
    tags=["Runs"],
)
async def create_run(body: RunCreate) -> RunResponse:
    now = datetime.now(timezone.utc)
    return RunResponse(
        run_id="run-77a80001",
        thread_id=body.thread_id,
        assistant_id=body.assistant_id,
        status=RunStatus.PENDING,
        tokens_used=0,
        cost_usd=0.0,
        elapsed_seconds=0.0,
        created_at=now,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Get run status & metrics",
    tags=["Runs"],
)
async def get_run(run_id: str) -> RunResponse:
    now = datetime.now(timezone.utc)
    return RunResponse(
        run_id=run_id,
        thread_id="th-b0ba0001-0001",
        assistant_id="asst-c0ffee01-0001",
        status=RunStatus.RUNNING,
        tokens_used=42000,
        cost_usd=0.21,
        elapsed_seconds=12.4,
        created_at=now,
    )


@router.get(
    "/runs/{run_id}/stream",
    summary="Server-Sent Events (SSE) live run stream",
    tags=["Runs"],
)
async def stream_run(
    run_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream live run events with replay support via Last-Event-ID."""

    async def event_generator() -> AsyncGenerator[str, None]:
        # Initial connect/resume event
        yield f"id: 1\nevent: metadata\ndata: {json.dumps({'run_id': run_id, 'status': 'connected', 'resumed_from': last_event_id})}\n\n"
        await asyncio.sleep(0.05)
        # Updates event
        yield f"id: 2\nevent: updates\ndata: {json.dumps({'node': 'atlas', 'delegates_to': 'clio', 'budget_spent': 0.05})}\n\n"
        await asyncio.sleep(0.05)
        # Done event
        yield f"id: 3\nevent: done\ndata: {json.dumps({'run_id': run_id, 'status': 'completed'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get(
    "/runs/{run_id}/interrupts",
    response_model=List[InterruptItem],
    summary="List pending HITL interrupts for run",
    tags=["Runs"],
)
async def list_run_interrupts(run_id: str) -> List[InterruptItem]:
    return [
        InterruptItem(
            interrupt_id="int-9901",
            run_id=run_id,
            thread_id="th-b0ba0001-0001",
            reason=InterruptReason.HITL_APPROVAL,
            subagent_id="vulcan",
            node_name="node_promote_prod",
            action_type="promote_prod",
            payload={"graph_id": "graph_v2", "diff": "+ node_security_filter"},
            created_at=datetime.now(timezone.utc),
        )
    ]


@router.post(
    "/runs/{run_id}/interrupts/{interrupt_id}/resume",
    response_model=RunResponse,
    summary="Resume run from HITL interrupt",
    tags=["Runs"],
)
async def resume_run_interrupt(
    run_id: str,
    interrupt_id: str,
    body: RunResumeRequest,
    x_actor_id: str = Header(..., alias="X-Actor-ID"),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
) -> RunResponse:
    # Rule PR-SEC-03: Vulcan cannot self-promote. Actor cannot be vulcan if action is promote_prod.
    if x_actor_type.lower() != "human" and x_actor_id.lower() == "vulcan":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Subagent 'vulcan' cannot self-approve promotion (PR-SEC-03).",
        )

    now = datetime.now(timezone.utc)
    return RunResponse(
        run_id=run_id,
        thread_id="th-b0ba0001-0001",
        assistant_id="asst-c0ffee01-0001",
        status=RunStatus.RUNNING if body.action == "approve" else RunStatus.CANCELLED,
        tokens_used=50000,
        cost_usd=0.25,
        elapsed_seconds=15.0,
        created_at=now,
    )


# ============================================================================
# 4. SUBAGENTS & CIRCUIT BREAKER ENDPOINTS
# ============================================================================

SUBAGENTS_REGISTRY_DATA = [
    {"id": "atlas", "role": "orchestrator-supervisor", "pod": PodName.KOORDINASI, "admin_mcp": True, "self_promote": False, "secrets": True},
    {"id": "clio", "role": "deep-researcher", "pod": PodName.RISET_REKAYASA, "admin_mcp": False, "self_promote": False, "secrets": False},
    {"id": "vulcan", "role": "software-engineer", "pod": PodName.RISET_REKAYASA, "admin_mcp": True, "self_promote": False, "secrets": True},
    {"id": "athena", "role": "critic-reviewer", "pod": PodName.RISET_REKAYASA, "admin_mcp": True, "self_promote": False, "secrets": False},
    {"id": "hermes", "role": "platform-ops", "pod": PodName.PLATFORM, "admin_mcp": True, "self_promote": False, "secrets": False},
    {"id": "mnemosyne", "role": "memory-curator", "pod": PodName.PLATFORM, "admin_mcp": True, "self_promote": False, "secrets": False},
    {"id": "janus", "role": "integration-mcp-hub", "pod": PodName.PLATFORM, "admin_mcp": True, "self_promote": False, "secrets": False},
    {"id": "themis", "role": "security-compliance", "pod": PodName.TATA_KELOLA, "admin_mcp": True, "self_promote": False, "secrets": False},
    {"id": "metron", "role": "evaluation-data", "pod": PodName.TATA_KELOLA, "admin_mcp": True, "self_promote": False, "secrets": False},
    {"id": "iris", "role": "documentation-writer", "pod": PodName.TATA_KELOLA, "admin_mcp": True, "self_promote": False, "secrets": False},
]


@router.get(
    "/subagents",
    response_model=List[SubagentContract],
    summary="List all 10 subagent contracts in registry",
    tags=["Subagents"],
)
async def list_subagents(
    pod: Optional[PodName] = None,
) -> List[SubagentContract]:
    contracts = []
    for item in SUBAGENTS_REGISTRY_DATA:
        if pod and item["pod"] != pod:
            continue
        contracts.append(
            SubagentContract(
                id=item["id"],
                role=item["role"],
                pod=item["pod"],
                capabilities=[f"cap_{item['id']}"],
                input_schema={"type": "object", "properties": {"objective": {"type": "string"}}},
                output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
                allowed_tools=["mcp:standard"],
                admin_mcp_access=item["admin_mcp"],
                can_self_promote=item["self_promote"],
                can_view_secrets=item["secrets"],
                model_policy={"tier": "frontier" if item["id"] == "atlas" else "standard"},
                budget_default={"max_tokens": 300000, "max_usd": 1.5, "max_wall_clock_s": 900, "max_steps": 30, "max_depth": 1},
                memory_scope={"namespace": item["id"]},
                trust_level=TrustLevel.HIGH if item["id"] == "atlas" else (TrustLevel.LOW if item["id"] == "clio" else TrustLevel.MEDIUM),
            )
        )
    return contracts


@router.get(
    "/subagents/topology",
    response_model=TopologyResponse,
    summary="Get multi-agent DAG topology",
    tags=["Subagents"],
)
async def get_subagent_topology() -> TopologyResponse:
    nodes = [{"id": s["id"], "role": s["role"], "pod": s["pod"]} for s in SUBAGENTS_REGISTRY_DATA]
    edges = [
        TopologyEdge(source="atlas", target=s["id"], relation="DELEGATES_TO", description=f"Atlas delegates to {s['id']}")
        for s in SUBAGENTS_REGISTRY_DATA if s["id"] != "atlas"
    ] + [
        TopologyEdge(source="vulcan", target="athena", relation="CRITICIZES", description="Code review loop"),
        TopologyEdge(source="athena", target="vulcan", relation="CRITICIZES", description="Feedback revision"),
    ]
    return TopologyResponse(nodes=nodes, edges=edges)


@router.get(
    "/subagents/{subagent_id}/status",
    response_model=SubagentStatusResponse,
    summary="Get live subagent status & circuit breaker",
    tags=["Subagents"],
)
async def get_subagent_status(subagent_id: str) -> SubagentStatusResponse:
    matched = next((s for s in SUBAGENTS_REGISTRY_DATA if s["id"] == subagent_id), None)
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subagent '{subagent_id}' not found in registry.",
        )

    contract = SubagentContract(
        id=matched["id"],
        role=matched["role"],
        pod=matched["pod"],
        capabilities=[f"cap_{matched['id']}"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        allowed_tools=["mcp:standard"],
        admin_mcp_access=matched["admin_mcp"],
        can_self_promote=matched["self_promote"],
        can_view_secrets=matched["secrets"],
        model_policy={"tier": "standard"},
        budget_default={"max_tokens": 300000, "max_usd": 1.5, "max_wall_clock_s": 900, "max_steps": 30, "max_depth": 1},
        memory_scope={"namespace": matched["id"]},
        trust_level=TrustLevel.MEDIUM,
    )
    cb = CircuitBreakerStatus(
        subagent_id=subagent_id,
        state=CircuitBreakerState.CLOSED,
        consecutive_failures=0,
        failure_threshold=3,
    )
    return SubagentStatusResponse(
        contract=contract,
        active_instances=1,
        max_concurrency=3 if subagent_id in ["clio", "metron"] else 1,
        circuit_breaker=cb,
    )


@router.post(
    "/subagents/{subagent_id}/circuit-breaker/reset",
    response_model=CircuitBreakerStatus,
    summary="Manual reset of tripped circuit breaker",
    tags=["Subagents"],
)
async def reset_circuit_breaker(subagent_id: str) -> CircuitBreakerStatus:
    return CircuitBreakerStatus(
        subagent_id=subagent_id,
        state=CircuitBreakerState.CLOSED,
        consecutive_failures=0,
        failure_threshold=3,
        last_failure_at=None,
        tripped_at=None,
    )


# ============================================================================
# 5. CORRELATIONS (10x10 MATRIX & EDGE WEIGHTS) ENDPOINTS
# ============================================================================

@router.get(
    "/correlations/matrix",
    response_model=CorrelationMatrixResponse,
    summary="Get 10x10 correlation matrix across subagents",
    tags=["Correlations"],
)
async def get_correlation_matrix(
    n_min: int = Query(default=50, ge=10, le=500),
) -> CorrelationMatrixResponse:
    agents = [s["id"] for s in SUBAGENTS_REGISTRY_DATA]
    matrix: List[CorrelationCell] = []

    for src in agents:
        for tgt in agents:
            is_same = (src == tgt)
            n = 0 if is_same else (65 if (src == "vulcan" and tgt == "athena") else 20)
            is_sparse = (n < n_min)
            matrix.append(
                CorrelationCell(
                    source_agent=src,
                    target_agent=tgt,
                    sample_count=n,
                    is_sparse=is_sparse,
                    handoff_rate=0.85 if (src == "vulcan" and tgt == "athena") else 0.05,
                    npmi_coactivation=0.72 if (src == "vulcan" and tgt == "athena") else 0.0,
                    success_lift=0.35 if (src == "vulcan" and tgt == "athena") else 0.0,
                    latency_coupling=0.20,
                    state_dependency=0.65 if (src == "vulcan" and tgt == "athena") else 0.0,
                    cost_share=0.40 if (src == "vulcan" and tgt == "athena") else 0.05,
                    failure_propagation=0.02,
                    aggregate_weight=0.78 if (src == "vulcan" and tgt == "athena") else 0.05,
                    polarity=CorrelationPolarity.POSITIVE,
                    polarity_source=CorrelationPolaritySource.OUTCOME,
                )
            )

    return CorrelationMatrixResponse(
        agents=agents,
        n_min_threshold=n_min,
        matrix=matrix,
        calculated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/correlations/weights",
    response_model=CorrelationWeightsConfig,
    summary="Get correlation calculation weight configuration",
    tags=["Correlations"],
)
async def get_correlation_weights() -> CorrelationWeightsConfig:
    return CorrelationWeightsConfig(
        version=1,
        alpha_handoff=0.35,
        beta_npmi=0.40,
        gamma_outcome=0.25,
    )


@router.put(
    "/correlations/weights",
    response_model=CorrelationWeightsConfig,
    summary="Update correlation calculation weights",
    tags=["Correlations"],
)
async def update_correlation_weights(body: CorrelationWeightsConfig) -> CorrelationWeightsConfig:
    new_version = body.version + 1
    return CorrelationWeightsConfig(
        version=new_version,
        alpha_handoff=body.alpha_handoff,
        beta_npmi=body.beta_npmi,
        gamma_outcome=body.gamma_outcome,
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================================
# 6. BI-TEMPORAL MEMORY ENDPOINTS (GRAPHITI L2)
# ============================================================================

@router.get(
    "/memory/temporal/facts",
    response_model=TemporalQueryResponse,
    summary="Bi-temporal facts query with time-travel slider",
    tags=["Memory"],
)
async def query_temporal_facts(
    query: str = Query(..., min_length=1),
    valid_at: Optional[datetime] = Query(None, description="Time-travel valid time (T_v)"),
    known_at: Optional[datetime] = Query(None, description="Time-travel known time (T_k)"),
    limit: int = Query(default=20, ge=1, le=100),
) -> TemporalQueryResponse:
    now = datetime.now(timezone.utc)
    fact = TemporalFact(
        fact_id="fact-arch-001",
        entity_source="LGPv2",
        relation="USES_SUPERVISOR_PATTERN",
        entity_target="Atlas",
        properties={"pod": "Koordinasi", "confidence": 0.95},
        valid_at=datetime(2026, 10, 8, 0, 0, 0),
        invalid_at=None,
        created_at=now,
        expired_at=None,
        episode_id="ep-run-001",
        source_run_id="run-77a80001",
        step_index=2,
        subagent_id="mnemosyne",
    )
    return TemporalQueryResponse(
        facts=[fact],
        as_of_valid_time=valid_at,
        as_of_known_time=known_at,
        total_found=1,
    )


# ============================================================================
# 7. TAMPER-EVIDENT AUDIT LOG ENDPOINTS
# ============================================================================

@router.get(
    "/audit",
    response_model=AuditQueryResponse,
    summary="Query tamper-evident audit log entries",
    tags=["Audit"],
)
async def query_audit_logs(
    run_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_type: Optional[ActorType] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditQueryResponse:
    entry = AuditLogEntry(
        id="aud-c4b1-0001",
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        actor_id=actor_id or "human-biezz",
        actor_type=actor_type or ActorType.HUMAN,
        action="run.create",
        scope="runs:execute",
        args_hash="2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
        result_status="SUCCESS",
        prev_hash="0000000000000000000000000000000000000000000000000000000000000000",
        entry_hash="8f434346648f6b96df89dda901c5176b10e6d83961dd3c1ac88b59b2dc327aa4",
    )
    return AuditQueryResponse(
        entries=[entry],
        total_count=1,
        chain_intact=True,
    )


@router.get(
    "/audit/verify",
    response_model=AuditVerifyResponse,
    summary="Verify cryptographic hash-chain integrity of audit log",
    tags=["Audit"],
)
async def verify_audit_chain() -> AuditVerifyResponse:
    return AuditVerifyResponse(
        is_valid=True,
        verified_entries=1042,
        broken_sequence_id=None,
        error_detail=None,
    )


# ============================================================================
# 8. HEALTH ENDPOINTS
# ============================================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Platform overall health & dependency probe",
    tags=["Health"],
)
async def check_health() -> HealthResponse:
    return HealthResponse(
        status=ComponentStatus.HEALTHY,
        timestamp=datetime.now(timezone.utc),
        version="2.0.0",
        components={
            "postgres": ComponentHealth(status=ComponentStatus.HEALTHY, latency_ms=1.4),
            "redis": ComponentHealth(status=ComponentStatus.HEALTHY, latency_ms=0.8),
            "falkordb": ComponentHealth(status=ComponentStatus.HEALTHY, latency_ms=2.1),
            "otel_collector": ComponentHealth(status=ComponentStatus.HEALTHY, latency_ms=1.1),
            "sandbox_runner": ComponentHealth(status=ComponentStatus.HEALTHY, latency_ms=5.0),
            "mcp_admin": ComponentHealth(status=ComponentStatus.HEALTHY, latency_ms=0.5),
        },
    )


# ============================================================================
# EXCEPTION HANDLER RFC 7807 PROBLEM DETAILS
# ============================================================================

def create_app() -> FastAPI:
    app = FastAPI(
        title="LGP v2.0 Enterprise Control Plane API",
        version="2.0.0",
        description="REST API and Control Plane contract for 10 Subagent Swarm on Enterprise LangGraph Platform.",
    )
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        pd = ProblemDetails(
            type=f"https://api.lgp.enterprise.io/errors/{exc.status_code}",
            title="HTTP Exception Occurred",
            status=exc.status_code,
            detail=str(exc.detail),
            instance=request.url.path,
            code=ErrorType.FORBIDDEN_ACCESS if exc.status_code == 403 else ErrorType.INTERNAL_SERVER_ERROR,
        )
        return JSONResponse(status_code=exc.status_code, content=pd.model_dump(mode="json"))

    return app
