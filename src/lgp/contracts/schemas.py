"""
Pydantic contracts and schemas for LGP v2.0 (Enterprise LangGraph Platform).
Compliant with Pydantic v2, RFC 7807/9457 Problem Details, and MCP 2024-11-05/2025.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# ============================================================================
# 0. COMMON & RFC 7807 ERROR SPECIFICATION
# ============================================================================

class ErrorType(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN_ACCESS = "FORBIDDEN_ACCESS"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    LOOP_DETECTED = "LOOP_DETECTED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    HITL_APPROVAL_REQUIRED = "HITL_APPROVAL_REQUIRED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class ProblemDetails(BaseModel):
    """RFC 7807 / RFC 9457 standard problem details."""
    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        default="https://api.lgp.enterprise.io/errors/INTERNAL_SERVER_ERROR",
        description="URI reference identifying problem type."
    )
    title: str = Field(..., description="Short human-readable summary of problem.")
    status: int = Field(..., ge=100, le=599, description="HTTP status code.")
    detail: str = Field(..., description="Human-readable explanation specific to occurrence.")
    instance: str = Field(..., description="URI reference identifying specific occurrence of problem.")
    code: ErrorType = Field(..., description="LGP internal error code enum.")
    invalid_params: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Field-level validation errors if applicable."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of occurrence."
    )


# ============================================================================
# 1. ASSISTANTS & THREADS CONTRACTS
# ============================================================================

class AssistantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_id: str = Field(..., min_length=1, max_length=128, description="Graph DAG identifier.")
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable assistant name.")
    description: Optional[str] = Field(default=None, max_length=1024)
    config: Dict[str, Any] = Field(default_factory=dict, description="Runtime config override.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata labels.")


class AssistantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1024)
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AssistantResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    assistant_id: str = Field(..., description="UUID identifier.")
    graph_id: str
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    metadata: Dict[str, Any]
    version: int = Field(default=1)
    created_at: datetime
    updated_at: datetime


class ThreadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: Dict[str, Any] = Field(default_factory=dict, description="Thread labels, e.g. user_id, tenant_id.")


class ThreadStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: Dict[str, Any] = Field(..., description="State values to merge or overwrite.")
    checkpoint_id: Optional[str] = Field(default=None, description="Fork source checkpoint.")
    as_node: Optional[str] = Field(default=None, description="Inject state pretending to be node.")


class ThreadResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    thread_id: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
    current_checkpoint_id: Optional[str] = None
    values: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# 2. RUNS & HITL STREAM CONTRACTS
# ============================================================================

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BudgetLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tokens: int = Field(default=500_000, gt=0, description="Max allowed total LLM tokens.")
    max_usd: float = Field(default=2.5, gt=0.0, description="Max allowed cost in USD.")
    max_wall_clock_s: int = Field(default=900, gt=0, description="Max execution timeout in seconds.")
    max_steps: int = Field(default=30, gt=0, description="Max total graph node executions.")
    max_depth: int = Field(default=2, ge=1, le=2, description="Max recursion depth.")


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_id: str = Field(..., description="Target assistant identifier.")
    thread_id: str = Field(..., description="Target thread session.")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Initial input state payload.")
    budget: Optional[BudgetLimit] = Field(default=None, description="Inherited budget limit.")
    stream_mode: List[Literal["values", "updates", "events", "messages", "debug"]] = Field(
        default=["updates", "events"]
    )
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    thread_id: str
    assistant_id: str
    status: RunStatus
    tokens_used: int = 0
    cost_usd: float = 0.0
    elapsed_seconds: float = 0.0
    created_at: datetime
    finished_at: Optional[datetime] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class InterruptReason(str, Enum):
    HITL_APPROVAL = "hitl_approval"
    EFFORT_SCALE_CONFIRM = "effort_scale_confirm"
    LOOP_DETECTED = "loop_detected"
    BUDGET_WARNING = "budget_warning"


class InterruptItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    interrupt_id: str
    run_id: str
    thread_id: str
    reason: InterruptReason
    subagent_id: str
    node_name: str
    action_type: str = Field(..., description="e.g. promote_prod, grant_change, external_exec")
    payload: Dict[str, Any] = Field(..., description="Context payload needing review.")
    created_at: datetime


class RunResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "edit"] = Field(..., description="HITL resolution decision.")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="Updated values if action is edit.")
    comment: Optional[str] = Field(default=None, max_length=1000, description="Audit reason for decision.")
    idempotency_key: str = Field(..., min_length=1, max_length=128)


# ============================================================================
# 3. SUBAGENTS & CIRCUIT BREAKER CONTRACTS
# ============================================================================

class PodName(str, Enum):
    KOORDINASI = "Koordinasi"
    RISET_REKAYASA = "Riset & Rekayasa"
    PLATFORM = "Platform"
    TATA_KELOLA = "Tata Kelola"


class TrustLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SubagentContract(BaseModel):
    """Contract definition for 10 subagents in LGP v2.0."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Subagent ID, e.g. atlas, clio, vulcan.")
    role: str = Field(..., description="Role title, e.g. deep-researcher, software-engineer.")
    pod: PodName = Field(..., description="Subagent pod group.")
    capabilities: List[str] = Field(..., description="Declared capabilities.")
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema for input context packet.")
    output_schema: Dict[str, Any] = Field(..., description="JSON Schema for output payload.")
    allowed_tools: List[str] = Field(..., description="Allowlist tool names / patterns.")
    admin_mcp_access: bool = Field(default=False, description="Strict access flag to Admin FastMCP server.")
    can_self_promote: bool = Field(default=False, description="Whether agent can promote graphs without HITL.")
    can_view_secrets: bool = Field(default=False, description="Whether agent can view raw secret values.")
    model_policy: Dict[str, Any] = Field(..., description="Gateway routing policy (model tier, max reasoning).")
    budget_default: BudgetLimit = Field(..., description="Default allocated budget per delegation.")
    memory_scope: Dict[str, Any] = Field(..., description="Namespace and Graphiti scope.")
    trust_level: TrustLevel = Field(..., description="Runtime trust classification.")
    version: str = Field(default="1.0.0")


class CircuitBreakerStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subagent_id: str
    state: CircuitBreakerState
    consecutive_failures: int
    failure_threshold: int = 3
    last_failure_at: Optional[datetime] = None
    tripped_at: Optional[datetime] = None


class SubagentStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contract: SubagentContract
    active_instances: int
    max_concurrency: int
    circuit_breaker: CircuitBreakerStatus


class TopologyEdge(BaseModel):
    source: str
    target: str
    relation: Literal["DELEGATES_TO", "CRITICIZES"]
    description: str


class TopologyResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[TopologyEdge]


# ============================================================================
# 4. CORRELATION MATRIX 10x10 CONTRACTS
# ============================================================================

class CorrelationPolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class CorrelationPolaritySource(str, Enum):
    SEMANTIC = "semantic"
    OUTCOME = "outcome"


class CorrelationCell(BaseModel):
    """10x10 pair cell metrics."""
    model_config = ConfigDict(extra="forbid")

    source_agent: str
    target_agent: str
    sample_count: int = Field(..., ge=0, description="Sample count n.")
    is_sparse: bool = Field(..., description="True if n < n_min (data sedikit).")
    handoff_rate: float = Field(..., ge=0.0, le=1.0)
    npmi_coactivation: float = Field(..., ge=-1.0, le=1.0)
    success_lift: float = Field(...)
    latency_coupling: float = Field(..., ge=0.0, le=1.0)
    state_dependency: float = Field(..., ge=0.0, le=1.0)
    cost_share: float = Field(..., ge=0.0, le=1.0)
    failure_propagation: float = Field(..., ge=0.0, le=1.0)
    aggregate_weight: float = Field(..., ge=0.0, le=1.0, description="Aggregated w_ij weight.")
    polarity: CorrelationPolarity
    polarity_source: CorrelationPolaritySource


class CorrelationMatrixResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agents: List[str] = Field(..., description="List of 10 subagent IDs.")
    n_min_threshold: int = Field(default=50)
    matrix: List[CorrelationCell] = Field(..., description="100 cell entries for 10x10.")
    calculated_at: datetime


class CorrelationWeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(..., ge=1)
    alpha_handoff: float = Field(default=0.35, ge=0.0, le=1.0)
    beta_npmi: float = Field(default=0.40, ge=0.0, le=1.0)
    gamma_outcome: float = Field(default=0.25, ge=0.0, le=1.0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# 5. BI-TEMPORAL MEMORY CONTRACTS (GRAPHITI L2)
# ============================================================================

class TemporalFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    entity_source: str
    relation: str = Field(..., description="SCREAMING_SNAKE_CASE relation.")
    entity_target: str
    properties: Dict[str, Any] = Field(default_factory=dict)

    # Bi-temporal 4 timestamps:
    valid_at: datetime = Field(..., description="Start of validity in real world (T_v start).")
    invalid_at: Optional[datetime] = Field(default=None, description="End of validity in real world (T_v end).")
    created_at: datetime = Field(..., description="System transaction recording time (T_k start).")
    expired_at: Optional[datetime] = Field(default=None, description="System invalidation/deletion time (T_k end).")

    # Provenance citation:
    episode_id: str
    source_run_id: str
    step_index: int
    subagent_id: str


class TemporalQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Semantic or keyword search query.")
    as_of_valid_time: Optional[datetime] = Field(
        default=None,
        description="Time-travel slider T_v: State in real world at this timestamp."
    )
    as_of_known_time: Optional[datetime] = Field(
        default=None,
        description="Time-travel slider T_k: What the system knew at this timestamp."
    )
    entity_types: Optional[List[str]] = None
    subagent_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class TemporalQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facts: List[TemporalFact]
    as_of_valid_time: Optional[datetime] = None
    as_of_known_time: Optional[datetime] = None
    total_found: int


# ============================================================================
# 6. TAMPER-EVIDENT AUDIT LOG CONTRACTS
# ============================================================================

class ActorType(str, Enum):
    HUMAN = "human"
    AGENT_PRINCIPAL = "agent_principal"
    SYSTEM = "system"


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Audit entry UUID.")
    sequence: int = Field(..., ge=1, description="Monotonically increasing sequence number.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor_id: str = Field(..., description="Identifier of human user or agent principal.")
    actor_type: ActorType
    action: str = Field(..., description="e.g. run.create, subagent.register, hitl.resume, graph.promote")
    scope: str = Field(..., description="Resource target scope, e.g. runs:execute, graphs:write")
    args_hash: str = Field(..., description="SHA-256 hash of execution arguments.")
    result_status: Literal["SUCCESS", "FAILED", "INTERRUPTED", "BLOCKED"]
    prev_hash: str = Field(..., description="SHA-256 hash of previous log entry.")
    entry_hash: str = Field(..., description="SHA-256(prev_hash + sequence + timestamp + actor_id + action + args_hash)")
    signature: Optional[str] = Field(default=None, description="Optional HMAC or cryptographic signature.")


class AuditQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: Optional[str] = None
    subagent_id: Optional[str] = None
    actor_type: Optional[ActorType] = None
    action: Optional[str] = None
    from_time: Optional[datetime] = None
    to_time: Optional[datetime] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AuditQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entries: List[AuditLogEntry]
    total_count: int
    chain_intact: bool = Field(..., description="Whether cryptographic hash-chain is unbroken.")


class AuditVerifyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_valid: bool
    verified_entries: int
    broken_sequence_id: Optional[int] = None
    error_detail: Optional[str] = None


# ============================================================================
# 7. HEALTH CHECK CONTRACTS
# ============================================================================

class ComponentStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: ComponentStatus
    latency_ms: float
    message: Optional[str] = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: ComponentStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "2.0.0"
    components: Dict[str, ComponentHealth] = Field(
        ...,
        description="Keys: postgres, redis, falkordb, otel_collector, sandbox_runner, mcp_admin"
    )
