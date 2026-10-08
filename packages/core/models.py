import uuid
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class BudgetEnvelope(BaseModel):
    max_tokens: int = 300000
    max_usd: float = 1.5
    max_wall_clock_s: int = 900
    depth_left: int = 1
    max_steps: int = 20
    spent_tokens: int = 0
    spent_usd: float = 0.0

    def can_afford(self, tokens: int, usd: float) -> bool:
        return (self.spent_tokens + tokens <= self.max_tokens) and (self.spent_usd + usd <= self.max_usd)

    def record_usage(self, tokens: int, usd: float):
        self.spent_tokens += tokens
        self.spent_usd += usd

    def spawn_child_budget(self, requested_tokens: int, requested_usd: float, requested_wall_clock_s: int = 300) -> "BudgetEnvelope":
        remaining_tokens = max(0, self.max_tokens - self.spent_tokens)
        remaining_usd = max(0.0, self.max_usd - self.spent_usd)

        alloc_tokens = min(requested_tokens, remaining_tokens)
        alloc_usd = min(requested_usd, remaining_usd)
        alloc_wall_clock = min(requested_wall_clock_s, self.max_wall_clock_s)

        if self.depth_left <= 0:
            raise ValueError("Maksimum kedalaman delegasi (depth_left=0) tercapai")

        return BudgetEnvelope(
            max_tokens=alloc_tokens,
            max_usd=alloc_usd,
            max_wall_clock_s=alloc_wall_clock,
            depth_left=self.depth_left - 1,
            max_steps=min(15, self.max_steps)
        )

class ContextPacket(BaseModel):
    packet_id: str = Field(default_factory=lambda: f"pkt-{uuid.uuid4().hex[:12]}")
    run_id: str
    trace_id: str = Field(default_factory=lambda: f"trc-{uuid.uuid4().hex[:12]}")
    caller_agent: str
    target_agent: str
    objective: str
    boundaries: str = "Hanya eksekusi sesuai grant dan schema yang ditentukan. Dilarang modifikasi platform config langsung."
    output_schema_ref: str
    tool_grants: List[str] = Field(default_factory=list)
    budget: BudgetEnvelope
    memory_hints: List[str] = Field(default_factory=list)
    parent_checkpoint_ref: Optional[str] = None
    state_input: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

class SubagentContract(BaseModel):
    id: str
    role: str
    name: str
    pod: str  # Coordination, Research & Engineering, Platform, Governance
    capabilities: List[str]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    tool_grants: List[str]
    model_policy: str
    budget_config: Dict[str, Any]
    memory_scope: str
    trust_level: str  # High, Medium, Low
    is_active: bool = True
    version: str = "2.0.0"

class TelemetryEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    run_id: str
    subagent_id: str
    event_type: str  # node.start, node.end, delegate, handoff, tool.call, state.read, state.write, interrupt, error
    payload: Dict[str, Any] = Field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)

class CorrelationEdge(BaseModel):
    source_subagent: str
    target_subagent: str
    handoff_rate: float = 0.0
    npmi_coactivation: float = 0.0
    success_lift: float = 0.0
    latency_coupling: float = 0.0
    composite_weight: float = 0.0
    polarity: str = "neutral"  # positive, negative, neutral
    sample_count: int = 0
    updated_at: float = Field(default_factory=time.time)

class TemporalFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: f"fact-{uuid.uuid4().hex[:12]}")
    subject: str
    predicate: str
    object: str
    valid_at: float = Field(default_factory=time.time)
    invalid_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    expired_at: Optional[float] = None
    episode_run_id: Optional[str] = None
    pii_redacted: bool = True

class AuditLogEntry(BaseModel):
    log_id: str = Field(default_factory=lambda: f"aud-{uuid.uuid4().hex[:12]}")
    actor: str
    action: str
    scope: str
    args_hash: str
    prev_hash: str
    curr_hash: str
    result_status: str
    created_at: float = Field(default_factory=time.time)

class HITLInterrupt(BaseModel):
    interrupt_id: str = Field(default_factory=lambda: f"hitl-{uuid.uuid4().hex[:12]}")
    run_id: str
    subagent_id: str
    reason: str
    state_diff: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending, approved, rejected
    approver: Optional[str] = None
    decision: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    resolved_at: Optional[float] = None
