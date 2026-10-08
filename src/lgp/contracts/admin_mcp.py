"""
FastMCP Admin Server implementation and tool definitions for LGP v2.0.
Explicitly defines tool annotations: readOnlyHint, destructiveHint, idempotentHint, openWorldHint.
Enforces access isolation: Clio excluded, Vulcan cannot self-promote, Themis gets no secrets.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from lgp.contracts.schemas import (
    AuditLogEntry,
    AuditQueryResponse,
    BudgetLimit,
    CorrelationCell,
    CorrelationMatrixResponse,
    CorrelationPolarity,
    CorrelationPolaritySource,
    PodName,
    ProblemDetails,
    RunResponse,
    RunResumeRequest,
    RunStatus,
    SubagentContract,
    TemporalFact,
    TemporalQueryResponse,
    TopologyEdge,
    TopologyResponse,
    TrustLevel,
)

# Initialize MCP Admin Server
mcp_admin_server = MCPServer("lgp-admin-server")


# ============================================================================
# ACCESS ISOLATION POLICY ENFORCEMENT
# ============================================================================

class AccessIsolationPolicy:
    """Security guardrails for subagent access isolation."""

    @staticmethod
    def enforce_clio_admin_ban(caller_id: str) -> None:
        """PR-SEC-02: Clio has untrusted context, forbidden from Admin MCP."""
        if caller_id.lower() == "clio":
            raise PermissionError("FORBIDDEN: Subagent 'clio' is barred from Admin MCP access (PR-SEC-02).")

    @staticmethod
    def enforce_vulcan_self_promotion(caller_id: str, is_human: bool, target_env: str) -> None:
        """PR-SEC-03: Vulcan cannot self-promote; promote prod requires human approver."""
        if caller_id.lower() == "vulcan" and target_env.lower() == "production" and not is_human:
            raise PermissionError("FORBIDDEN: Subagent 'vulcan' cannot self-promote to production without human approval (PR-SEC-03).")

    @staticmethod
    def sanitize_secrets_for_themis(caller_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """PR-SEC-04: Themis must never receive plaintext secret values."""
        if caller_id.lower() != "themis":
            return payload

        # Deep sanitize any secret values
        sanitized = {}
        for k, v in payload.items():
            if any(s in k.lower() for s in ["secret", "token", "password", "key", "credential"]):
                if isinstance(v, str) and v.startswith("secret://"):
                    sanitized[k] = v  # Keep reference URI
                else:
                    sanitized[k] = "REDACTED_BY_THEMIS_POLICY"
            elif isinstance(v, dict):
                sanitized[k] = AccessIsolationPolicy.sanitize_secrets_for_themis(caller_id, v)
            else:
                sanitized[k] = v
        return sanitized


# ============================================================================
# TOOL 1: lgp_subagent_list
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_subagent_list",
    description="List all 10 registered subagents in the workspace with capability summary and pod grouping.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_subagent_list(caller_id: str, pod: Optional[str] = None) -> List[Dict[str, Any]]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    # Stub response conforming to schema
    return [
        {"id": "atlas", "role": "orchestrator-supervisor", "pod": PodName.KOORDINASI.value},
        {"id": "clio", "role": "deep-researcher", "pod": PodName.RISET_REKAYASA.value},
        {"id": "vulcan", "role": "software-engineer", "pod": PodName.RISET_REKAYASA.value},
        {"id": "athena", "role": "critic-reviewer", "pod": PodName.RISET_REKAYASA.value},
        {"id": "hermes", "role": "platform-ops", "pod": PodName.PLATFORM.value},
        {"id": "mnemosyne", "role": "memory-curator", "pod": PodName.PLATFORM.value},
        {"id": "janus", "role": "integration-mcp-hub", "pod": PodName.PLATFORM.value},
        {"id": "themis", "role": "security-compliance", "pod": PodName.TATA_KELOLA.value},
        {"id": "metron", "role": "evaluation-data", "pod": PodName.TATA_KELOLA.value},
        {"id": "iris", "role": "documentation-writer", "pod": PodName.TATA_KELOLA.value},
    ]


# ============================================================================
# TOOL 2: lgp_subagent_get
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_subagent_get",
    description="Retrieve the full immutable contract and budget of a specific subagent.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_subagent_get(caller_id: str, subagent_id: str) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    contract = SubagentContract(
        id=subagent_id,
        role="spec-role",
        pod=PodName.KOORDINASI if subagent_id == "atlas" else PodName.RISET_REKAYASA,
        capabilities=["general-delegation"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        allowed_tools=["mcp:test"],
        admin_mcp_access=(subagent_id != "clio"),
        can_self_promote=False,
        can_view_secrets=(subagent_id != "themis"),
        model_policy={"model": "claude-3-7-sonnet"},
        budget_default=BudgetLimit(max_tokens=300000, max_usd=1.5, max_wall_clock_s=900, max_steps=20, max_depth=1),
        memory_scope={"namespace": "default"},
        trust_level=TrustLevel.HIGH if subagent_id == "atlas" else TrustLevel.MEDIUM,
    )
    return contract.model_dump()


# ============================================================================
# TOOL 3: lgp_subagent_topology
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_subagent_topology",
    description="Get multi-agent DAG topology (Atlas supervisor delegation and Vulcan-Athena swarm loop).",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_subagent_topology(caller_id: str) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    edges = [
        TopologyEdge(source="atlas", target="clio", relation="DELEGATES_TO", description="Research tasks"),
        TopologyEdge(source="atlas", target="vulcan", relation="DELEGATES_TO", description="Coding tasks"),
        TopologyEdge(source="vulcan", target="athena", relation="CRITICIZES", description="Swarm code review loop"),
        TopologyEdge(source="athena", target="vulcan", relation="CRITICIZES", description="Review feedback"),
    ]
    return TopologyResponse(
        nodes=[{"id": "atlas"}, {"id": "clio"}, {"id": "vulcan"}, {"id": "athena"}],
        edges=edges,
    ).model_dump()


# ============================================================================
# TOOL 4: lgp_run_create
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_run_create",
    description="Enqueue and execute a new workflow run on a thread.",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
async def lgp_run_create(
    caller_id: str,
    assistant_id: str,
    thread_id: str,
    input_data: Dict[str, Any],
    idempotency_key: str,
    budget: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    run_res = RunResponse(
        run_id=f"run-{idempotency_key[:8]}",
        thread_id=thread_id,
        assistant_id=assistant_id,
        status=RunStatus.RUNNING,
        tokens_used=100,
        cost_usd=0.002,
        elapsed_seconds=0.5,
        created_at=datetime.now(timezone.utc),
    )
    return run_res.model_dump()


# ============================================================================
# TOOL 5: lgp_run_get_state
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_run_get_state",
    description="Retrieve the latest checkpoint state and execution telemetry of a run.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_run_get_state(caller_id: str, run_id: str, thread_id: str) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "checkpoint_id": "ckpt-001",
        "values": {"status": "in_progress"},
        "pending_interrupts": [],
    }


# ============================================================================
# TOOL 6: lgp_run_resume_hitl
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_run_resume_hitl",
    description="Resume an interrupted run following human review or policy confirmation.",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
async def lgp_run_resume_hitl(
    caller_id: str,
    run_id: str,
    interrupt_id: str,
    action: str,
    idempotency_key: str,
    payload: Optional[Dict[str, Any]] = None,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    # Check if Vulcan is attempting self-promotion
    if action == "approve" and payload and payload.get("action_type") == "promote_prod":
        AccessIsolationPolicy.enforce_vulcan_self_promotion(caller_id=caller_id, is_human=False, target_env="production")

    return {
        "run_id": run_id,
        "interrupt_id": interrupt_id,
        "resumed": True,
        "action_taken": action,
        "resumed_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# TOOL 7: lgp_correlation_matrix
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_correlation_matrix",
    description="Retrieve the 10x10 subagent correlation matrix based on L1 deterministic telemetry.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_correlation_matrix(caller_id: str, min_samples: int = 50) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    cell = CorrelationCell(
        source_agent="vulcan",
        target_agent="athena",
        sample_count=60,
        is_sparse=False,
        handoff_rate=0.85,
        npmi_coactivation=0.72,
        success_lift=0.35,
        latency_coupling=0.20,
        state_dependency=0.65,
        cost_share=0.40,
        failure_propagation=0.05,
        aggregate_weight=0.78,
        polarity=CorrelationPolarity.POSITIVE,
        polarity_source=CorrelationPolaritySource.OUTCOME,
    )
    res = CorrelationMatrixResponse(
        agents=["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"],
        n_min_threshold=min_samples,
        matrix=[cell],
        calculated_at=datetime.now(timezone.utc),
    )
    return res.model_dump()


# ============================================================================
# TOOL 8: lgp_audit_query
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_audit_query",
    description="Query tamper-evident SHA-256 hash-chained audit log with actor and action filters.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_audit_query(
    caller_id: str,
    action: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    entry = AuditLogEntry(
        id="aud-1",
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        actor_id=caller_id,
        actor_type="agent_principal",
        action=action or "run.execute",
        scope="runs:execute",
        args_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        result_status="SUCCESS",
        prev_hash="0000000000000000000000000000000000000000000000000000000000000000",
        entry_hash="a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
    )
    # Themis secret scrubbing
    raw_payload = entry.model_dump()
    sanitized = AccessIsolationPolicy.sanitize_secrets_for_themis(caller_id, raw_payload)
    return sanitized


# ============================================================================
# TOOL 9: lgp_memory_query
# ============================================================================
@mcp_admin_server.tool(
    name="lgp_memory_query",
    description="Query Graphiti L2 bi-temporal knowledge graph with valid-time (T_v) and known-time (T_k) filters.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def lgp_memory_query(
    caller_id: str,
    query: str,
    as_of_valid_time: Optional[datetime] = None,
    as_of_known_time: Optional[datetime] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    AccessIsolationPolicy.enforce_clio_admin_ban(caller_id)
    fact = TemporalFact(
        fact_id="fact-1",
        entity_source="Vulcan",
        relation="PROPOSED_ARCHITECTURE",
        entity_target="GraphitiService",
        properties={"version": "2.0"},
        valid_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        episode_id="ep-101",
        source_run_id="run-001",
        step_index=3,
        subagent_id="vulcan",
    )
    res = TemporalQueryResponse(
        facts=[fact],
        as_of_valid_time=as_of_valid_time,
        as_of_known_time=as_of_known_time,
        total_found=1,
    )
    return res.model_dump()
