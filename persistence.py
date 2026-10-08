"""
LGP v2.0 Persistence Layer
Kompatibel SQLite (WAL mode) dan PostgreSQL 16+.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    Engine,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator


# -----------------------------------------------------------------------------
# SQLite WAL & Engine Setup
# -----------------------------------------------------------------------------

def configure_sqlite_pragmas(engine: Engine) -> None:
    """Mengaktifkan WAL mode, synchronous=NORMAL, foreign keys, dan busy timeout pada SQLite."""
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        if type(dbapi_connection).__module__.startswith("sqlite3"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()


# Dialect-neutral JSON variant (PostgreSQL JSONB, SQLite native/text JSON)
JSONVariant = JSON().with_variant(postgresql.JSONB, "postgresql")
BigIntAutoPK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class TrustLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TelemetryEventType(str, Enum):
    NODE_START = "node.start"
    NODE_END = "node.end"
    TOOL_CALL = "tool.call"
    DELEGATE = "delegate"
    STATE_READ = "state.read"
    STATE_WRITE = "state.write"
    INTERRUPT = "interrupt"
    ERROR = "error"


class PolarityType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AuditResultStatus(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class HITLStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


# -----------------------------------------------------------------------------
# SQLAlchemy 2.0 Declarative Models
# -----------------------------------------------------------------------------

class SubagentRegistry(Base):
    __tablename__ = "subagent_registry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    capabilities: Mapped[list[Any]] = mapped_column(JSONVariant, nullable=False, default=list)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    tool_grants: Mapped[list[Any]] = mapped_column(JSONVariant, nullable=False, default=list)
    model_policy: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    budget_config: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    memory_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    trust_level: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("trust_level IN ('low', 'medium', 'high')", name="ck_subagent_trust_level"),
        nullable=False,
        default=TrustLevel.MEDIUM.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="subagent_rel", foreign_keys="Run.current_subagent")


class Thread(Base):
    __tablename__ = "threads"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONVariant, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    runs: Mapped[list["Run"]] = relationship("Run", back_populates="thread", cascade="all, delete-orphan")
    checkpoints: Mapped[list["Checkpoint"]] = relationship("Checkpoint", back_populates="thread", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), ForeignKey("threads.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("status IN ('pending', 'running', 'interrupted', 'completed', 'failed', 'cancelled')", name="ck_run_status"),
        nullable=False,
        default=RunStatus.PENDING.value,
        index=True,
    )
    current_subagent: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("subagent_registry.id", ondelete="SET NULL"), nullable=True, index=True)
    context_packet: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    budget_allocated: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    budget_spent: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    checkpoints_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    thread: Mapped["Thread"] = relationship("Thread", back_populates="runs")
    subagent_rel: Mapped[Optional["SubagentRegistry"]] = relationship("SubagentRegistry", back_populates="runs", foreign_keys=[current_subagent])
    checkpoints: Mapped[list["Checkpoint"]] = relationship("Checkpoint", back_populates="run", cascade="all, delete-orphan")
    telemetry_events: Mapped[list["TelemetryEvent"]] = relationship("TelemetryEvent", back_populates="run", cascade="all, delete-orphan")
    hitl_interrupts: Mapped[list["HITLInbox"]] = relationship("HITLInbox", back_populates="run", cascade="all, delete-orphan")
    temporal_facts: Mapped[list["TemporalMemoryFact"]] = relationship("TemporalMemoryFact", back_populates="run", cascade="all, delete-orphan")


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), ForeignKey("threads.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    parent_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("checkpoints.checkpoint_id", ondelete="SET NULL"), nullable=True)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 state hash for loop detection
    state_data: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    run: Mapped["Run"] = relationship("Run", back_populates="checkpoints")
    thread: Mapped["Thread"] = relationship("Thread", back_populates="checkpoints")
    diffs_to: Mapped[list["StateDiff"]] = relationship("StateDiff", foreign_keys="StateDiff.to_checkpoint_id", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_checkpoints_run_step", "run_id", "step"),
        Index("idx_checkpoints_run_state_hash", "run_id", "state_hash"),  # Cepat hitung repetisi hash >= 3
    )


class StateDiff(Base):
    __tablename__ = "state_diffs"

    diff_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(64), ForeignKey("checkpoints.checkpoint_id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    from_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("checkpoints.checkpoint_id", ondelete="SET NULL"), nullable=True)
    to_checkpoint_id: Mapped[str] = mapped_column(String(64), ForeignKey("checkpoints.checkpoint_id", ondelete="CASCADE"), nullable=False)
    node_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    diff_data: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    subagent_id: Mapped[str] = mapped_column(String(64), ForeignKey("subagent_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint(
            "event_type IN ('node.start', 'node.end', 'tool.call', 'delegate', 'state.read', 'state.write', 'interrupt', 'error')",
            name="ck_telemetry_event_type"
        ),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    run: Mapped["Run"] = relationship("Run", back_populates="telemetry_events")

    __table_args__ = (
        Index("idx_telemetry_subagent_event", "subagent_id", "event_type"),
        Index("idx_telemetry_run_created", "run_id", "created_at"),
    )


class CorrelationEdge(Base):
    __tablename__ = "correlation_edges"

    source_subagent: Mapped[str] = mapped_column(String(64), ForeignKey("subagent_registry.id", ondelete="CASCADE"), primary_key=True)
    target_subagent: Mapped[str] = mapped_column(String(64), ForeignKey("subagent_registry.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")

    handoff_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    npmi_coactivation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # [-1.0, 1.0]
    success_lift: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_coupling: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_share: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    composite_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # w_ij
    polarity: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("polarity IN ('positive', 'negative', 'neutral')", name="ck_correlation_polarity"),
        nullable=False,
        default=PolarityType.NEUTRAL.value,
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # n untuk filter n < n_min
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_corr_source_ws", "source_subagent", "workspace_id"),
        Index("idx_corr_target_ws", "target_subagent", "workspace_id"),
        Index("idx_corr_composite_weight", "workspace_id", "composite_weight"),
    )


class TemporalMemoryFact(Base):
    __tablename__ = "temporal_memory_facts"

    fact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object: Mapped[str] = mapped_column(Text, nullable=False)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    invalid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    episode_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    pii_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    run: Mapped["Run"] = relationship("Run", back_populates="temporal_facts")

    __table_args__ = (
        Index("idx_temporal_subject_predicate", "subject", "predicate"),
        Index("idx_temporal_validity_window", "valid_at", "invalid_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id: Mapped[int] = mapped_column(BigIntAutoPK, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    curr_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    result_status: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("result_status IN ('success', 'denied', 'error')", name="ck_audit_result_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_audit_scope_action", "scope", "action"),
    )


class HITLInbox(Base):
    __tablename__ = "hitl_inbox"

    interrupt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    subagent_id: Mapped[str] = mapped_column(String(64), ForeignKey("subagent_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    state_diff: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'timed_out', 'cancelled')", name="ck_hitl_status"),
        nullable=False,
        default=HITLStatus.PENDING.value,
        index=True,
    )
    approver: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["Run"] = relationship("Run", back_populates="hitl_interrupts")

    __table_args__ = (
        CheckConstraint("approver IS NULL OR approver != subagent_id", name="ck_hitl_no_self_approval"),
        Index("idx_hitl_status_created", "status", "created_at"),
    )


# -----------------------------------------------------------------------------
# Pydantic v2 Models
# -----------------------------------------------------------------------------

class SubagentRegistryModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., max_length=64, description="ID unik subagent mis. 'atlas', 'clio'")
    role: str = Field(..., max_length=64)
    name: str = Field(..., max_length=128)
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    tool_grants: list[str] = Field(default_factory=list)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    budget_config: dict[str, Any] = Field(default_factory=dict)
    memory_scope: str = Field(..., max_length=128)
    trust_level: TrustLevel = Field(default=TrustLevel.MEDIUM)
    is_active: bool = True
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ContextPacketModel(BaseModel):
    packet_id: str
    run_id: str
    trace_id: Optional[str] = None
    objective: str
    boundaries: str
    output_format: dict[str, Any] = Field(default_factory=dict)
    tool_grants: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    memory_hints: list[str] = Field(default_factory=list)
    parent_check_ref: Optional[str] = None


class ThreadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread_id: str = Field(..., max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RunModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str = Field(..., max_length=64)
    thread_id: str = Field(..., max_length=64)
    status: RunStatus = Field(default=RunStatus.PENDING)
    current_subagent: Optional[str] = None
    context_packet: dict[str, Any] = Field(default_factory=dict)
    budget_allocated: dict[str, Any] = Field(default_factory=dict)
    budget_spent: dict[str, Any] = Field(default_factory=dict)
    checkpoints_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CheckpointModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    checkpoint_id: str = Field(..., max_length=64)
    run_id: str = Field(..., max_length=64)
    thread_id: str = Field(..., max_length=64)
    parent_checkpoint_id: Optional[str] = None
    state_hash: str = Field(..., max_length=64)
    state_data: dict[str, Any]
    step: int = 0
    timestamp: Optional[datetime] = None


class StateDiffModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    diff_id: str = Field(..., max_length=64)
    checkpoint_id: str = Field(..., max_length=64)
    run_id: str = Field(..., max_length=64)
    from_checkpoint_id: Optional[str] = None
    to_checkpoint_id: str = Field(..., max_length=64)
    node_name: Optional[str] = None
    diff_data: dict[str, Any]
    timestamp: Optional[datetime] = None


class TelemetryEventModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str = Field(..., max_length=64)
    run_id: str = Field(..., max_length=64)
    subagent_id: str = Field(..., max_length=64)
    event_type: TelemetryEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    created_at: Optional[datetime] = None


class CorrelationEdgeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_subagent: str = Field(..., max_length=64)
    target_subagent: str = Field(..., max_length=64)
    workspace_id: str = "default"
    handoff_rate: float = Field(0.0, ge=0.0, le=1.0)
    npmi_coactivation: float = Field(0.0, ge=-1.0, le=1.0)
    success_lift: float = 0.0
    latency_coupling: float = 0.0
    cost_share: float = Field(0.0, ge=0.0, le=1.0)
    composite_weight: float = Field(0.0, ge=0.0)
    polarity: PolarityType = PolarityType.NEUTRAL
    sample_count: int = Field(0, ge=0)
    updated_at: Optional[datetime] = None


class TemporalMemoryFactModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_id: str = Field(..., max_length=64)
    subject: str = Field(..., max_length=128)
    predicate: str = Field(..., max_length=64)
    object: str
    valid_at: datetime
    invalid_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    episode_run_id: str = Field(..., max_length=64)
    pii_redacted: bool = False


class AuditLogModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: Optional[int] = None
    actor: str = Field(..., max_length=64)
    action: str = Field(..., max_length=64)
    scope: str = Field(..., max_length=128)
    args_hash: str = Field(..., max_length=64)
    prev_hash: str = Field(..., max_length=64)
    curr_hash: str = Field(..., max_length=64)
    result_status: AuditResultStatus
    created_at: Optional[datetime] = None

    @classmethod
    def compute_hash(
        cls,
        prev_hash: str,
        actor: str,
        action: str,
        scope: str,
        args_hash: str,
        result_status: str,
        created_at_iso: str,
    ) -> str:
        """Menghitung SHA-256 hash untuk rantai audit log tamper-evident."""
        content = f"{prev_hash}|{actor}|{action}|{scope}|{args_hash}|{result_status}|{created_at_iso}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class HITLInboxModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interrupt_id: str = Field(..., max_length=64)
    run_id: str = Field(..., max_length=64)
    subagent_id: str = Field(..., max_length=64)
    reason: str = Field(..., max_length=64)
    state_diff: dict[str, Any] = Field(default_factory=dict)
    status: HITLStatus = HITLStatus.PENDING
    approver: Optional[str] = None
    decision: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    @model_validator(mode="after")
    def verify_no_self_approval(self) -> HITLInboxModel:
        if self.approver and self.approver == self.subagent_id:
            raise ValueError("AI tidak dapat menyetujui aksinya sendiri (approver != subagent_id).")
        return self
