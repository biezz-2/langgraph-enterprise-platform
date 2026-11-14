"""
LangGraph Server API Router - Phase 2 Implementation
API parity dengan LangGraph Server: /threads, /runs, /assistants, /store
7 mode SSE streaming dengan resumable Last-Event-ID
Postgres Task Queue dengan SELECT FOR UPDATE SKIP LOCKED
"""

from __future__ import annotations

import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select, update, delete, func, and_, or_, text, String, Text, Integer, Index, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, mapped_column

from persistence import (
    Base,
    Thread,
    Run,
    Checkpoint,
    RunStatus,
    get_async_session,
    init_db,
    engine,
    JSONVariant,
)

# =============================================================================
# Pydantic Models - LangGraph Server API Compatible
# =============================================================================

class AssistantCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    assistant_id: Optional[str] = None
    graph_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    if_exists: str = "raise"  # "raise" | "do_nothing"


class AssistantUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    graph_id: Optional[str] = None
    version: Optional[int] = None


class AssistantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    assistant_id: str
    graph_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: int = 1


class ThreadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    thread_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "idle"  # "idle" | "busy" | "interrupted" | "error"
    values: Optional[dict[str, Any]] = None
    interrupts: Optional[list[dict[str, Any]]] = None
    extracted: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RunModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    thread_id: str
    assistant_id: Optional[str] = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    multitask_strategy: str = "enqueue"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AssistantSearch(BaseModel):
    graph_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    limit: int = 10
    offset: int = 0


class ThreadCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    thread_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    if_exists: str = "raise"


class ThreadUpdate(BaseModel):
    metadata: Optional[dict[str, Any]] = None
    action: Optional[str] = None  # "interrupt" | "rollback"


class ThreadSearch(BaseModel):
    ids: Optional[list[str]] = None
    status: Optional[str] = None  # "idle" | "busy" | "interrupted" | "error"
    metadata: Optional[dict[str, Any]] = None
    values: Optional[dict[str, Any]] = None
    limit: int = 10
    offset: int = 0


class RunSearch(BaseModel):
    thread_id: Optional[str] = None
    assistant_id: Optional[str] = None
    status: Optional[str] = None  # "pending" | "running" | "completed" | "failed" | "cancelled" | "interrupted"
    limit: int = 10
    offset: int = 0


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    thread_id: Optional[str] = None
    assistant_id: str
    run_id: Optional[str] = None
    status: str = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)
    prevent_insert_if_inflight: bool = False
    multitask_strategy: str = "enqueue"  # "interrupt" | "rollback" | "reject" | "enqueue"
    if_not_exists: str = "create"  # "reject" | "create"
    after_seconds: Optional[float] = None
    kwargs: dict[str, Any] = Field(default_factory=dict)


class RunUpdate(BaseModel):
    metadata: Optional[dict[str, Any]] = None


class StorePut(BaseModel):
    namespace: list[str]
    key: str
    value: dict[str, Any]


class StoreGet(BaseModel):
    namespace: Optional[list[str]] = None
    key: str


class StoreSearch(BaseModel):
    namespace: Optional[list[str]] = None
    filter: Optional[dict[str, Any]] = None
    limit: int = 10
    offset: int = 0
    query: Optional[str] = None


class StoreListNamespaces(BaseModel):
    namespace: Optional[list[str]] = None
    suffix: Optional[list[str]] = None
    max_depth: Optional[int] = None
    limit: int = 10
    offset: int = 0


class StoreDelete(BaseModel):
    namespace: Optional[list[str]] = None
    key: str


# =============================================================================
# Pydantic Models - LangGraph Server API Compatible
# =============================================================================
class Assistant(Base):
    __tablename__ = "assistants"

    assistant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict[str, Any]] = mapped_column("metadata_dict", JSONVariant, nullable=False, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Store Item Model
class StoreItem(Base):
    __tablename__ = "store_items"

    namespace: Mapped[str] = mapped_column(String(512), primary_key=True)  # JSON-serialized list
    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_store_namespace", "namespace"),
    )


# Task Queue Model for Postgres Task Queue
class TaskQueue(Base):
    __tablename__ = "task_queue"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # "run", "cron", "webhook"
    payload: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)  # "pending" | "running" | "completed" | "failed" | "cancelled"
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_task_queue_status_priority", "status", "priority", "scheduled_at"),
    )


# SSE Event Types (7 modes)
class SSEEventType(str, Enum):
    VALUES = "values"           # Full state values
    UPDATES = "updates"         # State diffs/updates
    MESSAGES = "messages"       # Message events
    EVENTS = "events"           # Node/tool events
    CHECKPOINTS = "checkpoints" # Checkpoint snapshots
    DEBUG = "debug"             # Debug/trace events
    ERROR = "error"             # Error events


# =============================================================================
# Database Dependency
# =============================================================================

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_async_session():
        yield session


# =============================================================================
# Task Queue Implementation (SELECT FOR UPDATE SKIP LOCKED)
# =============================================================================

class TaskQueueManager:
    """Postgres Task Queue dengan SELECT FOR UPDATE SKIP LOCKED untuk concurrent workers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_attempts: int = 3,
        scheduled_at: Optional[datetime] = None,
    ) -> str:
        """Tambah task ke queue."""
        task_id = str(uuid.uuid4())
        task = TaskQueue(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            scheduled_at=scheduled_at or datetime.now(timezone.utc),
        )
        self.session.add(task)
        await self.session.flush()
        return task_id

    async def dequeue(self, worker_id: str, task_types: Optional[list[str]] = None, limit: int = 10) -> list[TaskQueue]:
        """Ambil task yang tersedia dengan SELECT FOR UPDATE SKIP LOCKED."""
        query = (
            select(TaskQueue)
            .where(
                and_(
                    TaskQueue.status == "pending",
                    TaskQueue.scheduled_at <= datetime.now(timezone.utc),
                    TaskQueue.attempts < TaskQueue.max_attempts,
                )
            )
            .order_by(TaskQueue.priority.desc(), TaskQueue.scheduled_at.asc())
            .limit(limit)
        )

        if task_types:
            query = query.where(TaskQueue.task_type.in_(task_types))

        # SELECT FOR UPDATE SKIP LOCKED - Postgres specific
        query = query.with_for_update(skip_locked=True)

        result = await self.session.execute(query)
        tasks = result.scalars().all()

        # Mark as running
        for task in tasks:
            task.status = "running"
            task.worker_id = worker_id
            task.started_at = datetime.now(timezone.utc)
            task.attempts += 1

        await self.session.flush()
        return list(tasks)

    async def complete(self, task_id: str, success: bool = True, error: Optional[str] = None) -> bool:
        """Tandai task selesai."""
        task = await self.session.get(TaskQueue, task_id)
        if not task:
            return False

        if success:
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
        else:
            task.error = error
            if task.attempts >= task.max_attempts:
                task.status = "failed"
                task.completed_at = datetime.now(timezone.utc)
            else:
                task.status = "pending"
                task.worker_id = None
                task.started_at = None

        task.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def cancel(self, task_id: str) -> bool:
        """Batalkan task."""
        task = await self.session.get(TaskQueue, task_id)
        if not task or task.status in ("completed", "failed", "cancelled"):
            return False

        task.status = "cancelled"
        task.completed_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True


# =============================================================================
# SSE Streaming Manager (7 modes + Last-Event-ID resumable)
# =============================================================================

class SSEStreamManager:
    """Manager untuk 7 mode SSE streaming dengan resumable Last-Event-ID."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._subscribers: dict[str, asyncio.Queue] = {}

    async def subscribe(self, run_id: str, last_event_id: Optional[str] = None) -> AsyncGenerator[dict[str, Any], None]:
        """Subscribe ke stream run dengan dukungan Last-Event-ID untuk resumable."""
        queue: asyncio.Queue = asyncio.Queue()
        subscriber_id = f"{run_id}:{uuid.uuid4().hex[:8]}"
        self._subscribers[subscriber_id] = queue

        # Jika ada last_event_id, kirim events yang terlewat (replay)
        if last_event_id:
            await self._replay_events(run_id, last_event_id, queue)

        try:
            while True:
                event = await queue.get()
                if event is None:  # Sentinel untuk close
                    break
                yield event
        finally:
            self._subscribers.pop(subscriber_id, None)

    async def _replay_events(self, run_id: str, last_event_id: str, queue: asyncio.Queue):
        """Replay events setelah last_event_id dari checkpoint/history."""
        # Parse last_event_id format: "run_id:checkpoint_step:event_seq"
        try:
            parts = last_event_id.split(":")
            if len(parts) >= 3:
                checkpoint_step = int(parts[1])
                # Ambil checkpoints setelah step tersebut
                query = (
                    select(Checkpoint)
                    .where(and_(Checkpoint.run_id == run_id, Checkpoint.step > checkpoint_step))
                    .order_by(Checkpoint.step.asc())
                )
                result = await self.session.execute(query)
                checkpoints = result.scalars().all()

                for cp in checkpoints:
                    event_data = {
                        "event": SSEEventType.CHECKPOINTS.value,
                        "data": {
                            "checkpoint_id": cp.checkpoint_id,
                            "step": cp.step,
                            "state_data": cp.state_data,
                            "timestamp": cp.timestamp.isoformat(),
                        },
                        "id": f"{run_id}:{cp.step}:0",
                    }
                    await queue.put(event_data)
        except (ValueError, IndexError):
            pass  # Invalid last_event_id, skip replay

    async def publish(self, run_id: str, event_type: SSEEventType, data: dict[str, Any], step: int = 0, event_seq: int = 0):
        """Publish event ke semua subscriber run."""
        event_id = f"{run_id}:{step}:{event_seq}"
        event = {
            "event": event_type.value,
            "data": data,
            "id": event_id,
        }

        for sub_id, queue in self._subscribers.items():
            if sub_id.startswith(f"{run_id}:"):
                await queue.put(event)

    async def close(self, run_id: str):
        """Tutup semua subscriber untuk run."""
        for sub_id, queue in list(self._subscribers.items()):
            if sub_id.startswith(f"{run_id}:"):
                await queue.put(None)
                self._subscribers.pop(sub_id, None)


# =============================================================================
# Router
# =============================================================================

router = APIRouter(tags=["LangGraph Server"])


# -----------------------------------------------------------------------------
# Assistants Endpoints
# -----------------------------------------------------------------------------

@router.post("/assistants", response_model=AssistantRead, status_code=status.HTTP_201_CREATED)
async def create_assistant(
    assistant: AssistantCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new assistant."""
    assistant_id = assistant.assistant_id or str(uuid.uuid4())

    # Check if exists
    existing = await db.get(Assistant, assistant_id)
    if existing:
        if assistant.if_exists == "do_nothing":
            return AssistantRead.model_validate(existing)
        raise HTTPException(status_code=409, detail=f"Assistant {assistant_id} already exists")

    new_assistant = Assistant(
        assistant_id=assistant_id,
        graph_id=assistant.graph_id,
        name=assistant.name,
        description=assistant.description,
        metadata=assistant.metadata,
        config=assistant.config,
        context=assistant.context,
    )
    db.add(new_assistant)
    await db.flush()
    return AssistantRead.model_validate(new_assistant)


@router.post("/assistants/search", response_model=list[AssistantRead])
async def search_assistants(
    search: AssistantSearch,
    db: AsyncSession = Depends(get_db),
):
    """Search assistants with filters."""
    query = select(Assistant)
    if search.graph_id:
        query = query.where(Assistant.graph_id == search.graph_id)
    if search.metadata:
        # JSONB contains query
        for k, v in search.metadata.items():
            query = query.where(Assistant.metadata_json[k].astext == str(v))

    query = query.order_by(Assistant.created_at.desc()).offset(search.offset).limit(search.limit)
    result = await db.execute(query)
    assistants = result.scalars().all()
    return [AssistantRead.model_validate(a) for a in assistants]


@router.get("/assistants/{assistant_id}", response_model=AssistantRead)
async def get_assistant(assistant_id: str, db: AsyncSession = Depends(get_db)):
    """Get assistant by ID."""
    assistant = await db.get(Assistant, assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return AssistantRead.model_validate(assistant)


@router.patch("/assistants/{assistant_id}", response_model=AssistantRead)
async def update_assistant(
    assistant_id: str,
    update: AssistantUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update assistant."""
    assistant = await db.get(Assistant, assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "metadata":
            assistant.metadata = value
        else:
            setattr(assistant, key, value)

    assistant.version += 1
    assistant.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return AssistantRead.model_validate(assistant)


@router.delete("/assistants/{assistant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assistant(assistant_id: str, db: AsyncSession = Depends(get_db)):
    """Delete assistant."""
    assistant = await db.get(Assistant, assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")
    await db.delete(assistant)
    await db.flush()


# -----------------------------------------------------------------------------
# Threads Endpoints
# -----------------------------------------------------------------------------

@router.post("/threads", response_model=ThreadModel, status_code=status.HTTP_201_CREATED)
async def create_thread(
    thread: ThreadCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new thread."""
    thread_id = thread.thread_id or str(uuid.uuid4())

    existing = await db.get(Thread, thread_id)
    if existing:
        if thread.if_exists == "do_nothing":
            return ThreadModel(thread_id=existing.thread_id, metadata=existing.metadata_json, created_at=existing.created_at, updated_at=existing.updated_at)
        raise HTTPException(status_code=409, detail=f"Thread {thread_id} already exists")

    new_thread = Thread(thread_id=thread_id, metadata_json=thread.metadata)
    db.add(new_thread)
    await db.flush()
    return ThreadModel(
        thread_id=new_thread.thread_id,
        metadata=new_thread.metadata_json,
        status="idle",
        values=None,
        interrupts=None,
        extracted=None,
        created_at=new_thread.created_at,
        updated_at=new_thread.updated_at,
    )


@router.post("/threads/search", response_model=list[ThreadModel])
async def search_threads(
    search: ThreadSearch,
    db: AsyncSession = Depends(get_db),
):
    """Search threads with filters."""
    query = select(Thread)

    if search.ids:
        query = query.where(Thread.thread_id.in_(search.ids))

    if search.metadata:
        for k, v in search.metadata.items():
            query = query.where(Thread.metadata_json[k].astext == str(v))

    # Status filter requires join with runs
    if search.status:
        subquery = (
            select(Run.thread_id)
            .where(and_(Run.status == search.status, Run.thread_id == Thread.thread_id))
            .exists()
        )
        if search.status == "idle":
            # Idle = no running runs
            subquery = (
                select(Run.thread_id)
                .where(and_(Run.status.in_(["running", "pending"]), Run.thread_id == Thread.thread_id))
                .exists()
            )
            query = query.where(~subquery)
        else:
            query = query.where(subquery)

    query = query.order_by(Thread.updated_at.desc()).offset(search.offset).limit(search.limit)
    result = await db.execute(query)
    threads = result.scalars().all()
    return [
        ThreadModel(
            thread_id=t.thread_id,
            metadata=t.metadata_json,
            status=t.status,
            values=t.values_json,
            interrupts=t.interrupts_json,
            extracted=t.extracted_json,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in threads
    ]


@router.get("/threads/{thread_id}", response_model=ThreadModel)
async def get_thread(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Get thread by ID."""
    thread = await db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadModel(thread_id=thread.thread_id, metadata=thread.metadata_json, created_at=thread.created_at, updated_at=thread.updated_at)


@router.patch("/threads/{thread_id}", response_model=ThreadModel)
async def update_thread(
    thread_id: str,
    update: ThreadUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update thread metadata or trigger action."""
    thread = await db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if update.metadata is not None:
        thread.metadata_json = update.metadata
        thread.updated_at = datetime.now(timezone.utc)

    if update.action == "interrupt":
        # Interrupt running runs
        await db.execute(
            update(Run)
            .where(and_(Run.thread_id == thread_id, Run.status == "running"))
            .values(status=RunStatus.INTERRUPTED, updated_at=datetime.now(timezone.utc))
        )
    elif update.action == "rollback":
        # Rollback to latest checkpoint (handled by worker)
        pass

    await db.flush()
    return ThreadModel.model_validate(thread)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    run_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Delete thread. If run_id provided, delete specific run first."""
    thread = await db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if run_id:
        run = await db.get(Run, run_id)
        if run and run.thread_id == thread_id:
            if run.status in ("running", "pending"):
                raise HTTPException(status_code=409, detail="Cancel run before deletion")
            await db.delete(run)
        else:
            raise HTTPException(status_code=404, detail="Run not found")
    else:
        await db.delete(thread)

    await db.flush()


@router.get("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get thread checkpoint history."""
    thread = await db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    query = (
        select(Checkpoint)
        .where(Checkpoint.thread_id == thread_id)
        .order_by(Checkpoint.step.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    checkpoints = result.scalars().all()

    return [
        {
            "checkpoint_id": cp.checkpoint_id,
            "run_id": cp.run_id,
            "step": cp.step,
            "state_hash": cp.state_hash,
            "state_data": cp.state_data,
            "timestamp": cp.timestamp.isoformat(),
        }
        for cp in checkpoints
    ]


@router.post("/threads/{thread_id}/copy", response_model=ThreadModel)
async def copy_thread(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Create independent copy of thread."""
    thread = await db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    new_thread_id = str(uuid.uuid4())
    new_thread = Thread(
        thread_id=new_thread_id,
        metadata_json=thread.metadata_json.copy(),
    )
    db.add(new_thread)
    await db.flush()
    return ThreadModel.model_validate(new_thread)


# -----------------------------------------------------------------------------
# Runs Endpoints
# -----------------------------------------------------------------------------

@router.post("/runs", response_model=RunModel, status_code=status.HTTP_201_CREATED)
async def create_run(
    run: RunCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a background run."""
    # Verify assistant exists
    assistant = await db.get(Assistant, run.assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    # Handle thread
    if run.thread_id:
        thread = await db.get(Thread, run.thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
    else:
        thread = Thread(thread_id=str(uuid.uuid4()))
        db.add(thread)
        await db.flush()
        run.thread_id = thread.thread_id

    # Check for inflight runs if prevent_insert_if_inflight
    if run.prevent_insert_if_inflight:
        inflight = await db.execute(
            select(Run).where(
                and_(
                    Run.thread_id == run.thread_id,
                    Run.status.in_(["pending", "running"]),
                )
            )
        )
        if inflight.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Thread has inflight run")

    # Handle multitask_strategy
    if run.multitask_strategy == "interrupt":
        await db.execute(
            update(Run)
            .where(and_(Run.thread_id == run.thread_id, Run.status == "running"))
            .values(status=RunStatus.INTERRUPTED, updated_at=datetime.now(timezone.utc))
        )
    elif run.multitask_strategy == "rollback":
        # Worker handles rollback
        pass
    elif run.multitask_strategy == "reject":
        running = await db.execute(
            select(Run).where(and_(Run.thread_id == run.thread_id, Run.status == "running"))
        )
        if running.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Thread has running run")

    run_id = run.run_id or str(uuid.uuid4())

    new_run = Run(
        run_id=run_id,
        thread_id=run.thread_id,
        assistant_id=run.assistant_id,
        status=run.status,
        metadata_json=run.metadata,
        kwargs=run.kwargs,
        multitask_strategy=run.multitask_strategy,
        context_packet=run.kwargs,
    )
    db.add(new_run)

    # Enqueue to task queue for worker processing
    task_queue = TaskQueueManager(db)
    await task_queue.enqueue(
        task_type="run",
        payload={
            "run_id": run_id,
            "thread_id": run.thread_id,
            "assistant_id": run.assistant_id,
            "kwargs": run.kwargs,
            "after_seconds": run.after_seconds,
        },
        scheduled_at=datetime.now(timezone.utc) + asyncio.sleep(run.after_seconds) if run.after_seconds else None,
    )

    await db.flush()
    return RunModel(
        run_id=new_run.run_id,
        thread_id=new_run.thread_id,
        assistant_id=new_run.assistant_id,
        status=new_run.status,
        metadata=new_run.metadata_json,
        kwargs=new_run.kwargs,
        multitask_strategy=new_run.multitask_strategy,
        created_at=new_run.created_at,
        updated_at=new_run.updated_at,
        started_at=new_run.started_at,
        completed_at=new_run.completed_at,
    )


@router.post("/runs/search", response_model=list[RunModel])
async def search_runs(
    search: RunSearch,
    db: AsyncSession = Depends(get_db),
):
    """Search runs."""
    query = select(Run)

    if search.thread_id:
        query = query.where(Run.thread_id == search.thread_id)

    if search.assistant_id:
        query = query.where(Run.assistant_id == search.assistant_id)

    if search.status:
        query = query.where(Run.status == search.status)

    query = query.order_by(Run.created_at.desc()).offset(search.offset).limit(search.limit)
    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        RunModel(
            run_id=r.run_id,
            thread_id=r.thread_id,
            assistant_id=r.assistant_id,
            status=r.status,
            metadata=r.metadata_json,
            kwargs=r.kwargs,
            multitask_strategy=r.multitask_strategy,
            created_at=r.created_at,
            updated_at=r.updated_at,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.post("/runs/wait")
async def create_run_wait(
    run: RunCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create ephemeral run and wait for completion."""
    # Create run
    run_response = await create_run(run, db)
    run_id = run_response.run_id

    # Poll for completion (simplified - in production use WebSocket or long-poll)
    max_wait = 300  # 5 minutes
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < max_wait:
        current = await db.get(Run, run_id)
        if current and current.status in ("completed", "failed", "cancelled", "interrupted"):
            return RunModel.model_validate(current)
        await asyncio.sleep(0.5)

    raise HTTPException(status_code=408, detail="Run timed out")


@router.post("/runs/stream")
async def create_run_stream(
    run: RunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create ephemeral run and stream output."""
    run_response = await create_run(run, db)
    run_id = run_response.run_id

    sse_manager = SSEStreamManager(db)

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        async for event in sse_manager.subscribe(run_id):
            if await request.is_disconnected():
                break
            yield event

    return EventSourceResponse(event_generator())


@router.get("/runs/{run_id}", response_model=RunModel)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Get run by ID."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunModel(
        run_id=run.run_id,
        thread_id=run.thread_id,
        assistant_id=run.assistant_id,
        status=run.status,
        metadata=run.metadata_json,
        kwargs=run.kwargs,
        multitask_strategy=run.multitask_strategy,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/threads/{thread_id}/runs", response_model=list[RunModel])
async def list_thread_runs_endpoint(
    thread_id: str,
    limit: int = 10,
    offset: int = 0,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List runs for a thread (SDK-compatible endpoint)."""
    query = select(Run).where(Run.thread_id == thread_id)

    if status:
        query = query.where(Run.status == status)

    query = query.order_by(Run.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        RunModel(
            run_id=r.run_id,
            thread_id=r.thread_id,
            assistant_id=r.assistant_id,
            status=r.status,
            metadata=r.metadata_json,
            kwargs=r.kwargs,
            multitask_strategy=r.multitask_strategy,
            created_at=r.created_at,
            updated_at=r.updated_at,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.patch("/runs/{run_id}", response_model=RunModel)
async def update_run(run_id: str, update: RunUpdate, db: AsyncSession = Depends(get_db)):
    """Update run metadata."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if update.metadata is not None:
        run.metadata_json = update.metadata
        run.updated_at = datetime.now(timezone.utc)
        await db.flush()

    return RunModel(
        run_id=run.run_id,
        thread_id=run.thread_id,
        assistant_id=run.assistant_id,
        status=run.status,
        metadata=run.metadata_json,
        kwargs=run.kwargs,
        multitask_strategy=run.multitask_strategy,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel a run."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Run already {run.status}")

    run.status = "cancelled"
    run.updated_at = datetime.now(timezone.utc)

    # Cancel task queue entry
    task_queue = TaskQueueManager(db)
    await task_queue.cancel(run_id)

    await db.flush()
    return RunModel(
        run_id=run.run_id,
        thread_id=run.thread_id,
        assistant_id=run.assistant_id,
        status=run.status,
        metadata=run.metadata_json,
        kwargs=run.kwargs,
        multitask_strategy=run.multitask_strategy,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a finished run."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status not in ("completed", "failed", "cancelled", "interrupted"):
        raise HTTPException(status_code=409, detail="Cancel run before deletion")

    await db.delete(run)
    await db.flush()


@router.get("/runs/{run_id}/wait")
async def wait_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Wait for run to finish, return final output."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("completed", "failed", "cancelled", "interrupted"):
        # Return latest checkpoint as output
        latest_cp = await db.execute(
            select(Checkpoint)
            .where(Checkpoint.run_id == run_id)
            .order_by(Checkpoint.step.desc())
            .limit(1)
        )
        cp = latest_cp.scalar_one_or_none()
        return {
            "run": RunModel(
                run_id=run.run_id,
                thread_id=run.thread_id,
                assistant_id=run.assistant_id,
                status=run.status,
                metadata=run.metadata_json,
                kwargs=run.kwargs,
                multitask_strategy=run.multitask_strategy,
                created_at=run.created_at,
                updated_at=run.updated_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
            ),
            "output": cp.state_data if cp else {},
        }

    # Long poll
    max_wait = 300
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < max_wait:
        await db.refresh(run)
        if run.status in ("completed", "failed", "cancelled", "interrupted"):
            latest_cp = await db.execute(
                select(Checkpoint)
                .where(Checkpoint.run_id == run_id)
                .order_by(Checkpoint.step.desc())
                .limit(1)
            )
            cp = latest_cp.scalar_one_or_none()
            return {
                "run": RunModel(
                    run_id=run.run_id,
                    thread_id=run.thread_id,
                    assistant_id=run.assistant_id,
                    status=run.status,
                    metadata=run.metadata_json,
                    kwargs=run.kwargs,
                    multitask_strategy=run.multitask_strategy,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                ),
                "output": cp.state_data if cp else {},
            }
        await asyncio.sleep(0.5)

    raise HTTPException(status_code=408, detail="Run timed out")


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Join output stream of existing run with Last-Event-ID resumable support."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    sse_manager = SSEStreamManager(db)

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        async for event in sse_manager.subscribe(run_id, last_event_id):
            if await request.is_disconnected():
                break
            yield event

    return EventSourceResponse(event_generator())


@router.get("/threads/{thread_id}/runs", response_model=list[RunModel])
async def list_thread_runs(
    thread_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List runs for a thread."""
    thread = await db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    query = select(Run).where(Run.thread_id == thread_id)
    if status:
        query = query.where(Run.status == status)
    query = query.order_by(Run.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    runs = result.scalars().all()
    return [
        RunModel(
            run_id=r.run_id,
            thread_id=r.thread_id,
            assistant_id=r.assistant_id,
            status=r.status,
            metadata=r.metadata_json,
            kwargs=r.kwargs,
            multitask_strategy=r.multitask_strategy,
            created_at=r.created_at,
            updated_at=r.updated_at,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


# -----------------------------------------------------------------------------
# Store Endpoints (Long-term Memory)
# -----------------------------------------------------------------------------

@router.put("/store/items")
async def put_store_item(
    item: StorePut,
    db: AsyncSession = Depends(get_db),
):
    """Create or update a store item."""
    namespace_str = json.dumps(item.namespace)
    stmt = pg_insert(StoreItem).values(
        namespace=namespace_str,
        key=item.key,
        value=item.value,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["namespace", "key"],
        set_=dict(value=item.value, updated_at=datetime.now(timezone.utc)),
    )
    await db.execute(stmt)
    await db.flush()
    return {"namespace": item.namespace, "key": item.key, "status": "ok"}


@router.get("/store/items")
async def get_store_item(
    namespace: Optional[list[str]] = Query(None),
    key: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get a store item."""
    namespace_str = json.dumps(namespace) if namespace else None
    query = select(StoreItem).where(StoreItem.key == key)
    if namespace_str:
        query = query.where(StoreItem.namespace == namespace_str)

    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return {
        "namespace": json.loads(item.namespace),
        "key": item.key,
        "value": item.value,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


@router.post("/store/items/search")
async def search_store_items(
    search: StoreSearch,
    db: AsyncSession = Depends(get_db),
):
    """Search store items."""
    query = select(StoreItem)

    if search.namespace:
        query = query.where(StoreItem.namespace == json.dumps(search.namespace))

    if search.filter:
        for k, v in search.filter.items():
            query = query.where(StoreItem.value[k].astext == str(v))

    if search.query:
        # Simple text search in value
        query = query.where(StoreItem.value.astext.ilike(f"%{search.query}%"))

    query = query.order_by(StoreItem.updated_at.desc()).offset(search.offset).limit(search.limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        {
            "namespace": json.loads(item.namespace),
            "key": item.key,
            "value": item.value,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in items
    ]


@router.post("/store/namespaces")
async def list_store_namespaces(
    request: StoreListNamespaces,
    db: AsyncSession = Depends(get_db),
):
    """List store namespaces."""
    query = select(StoreItem.namespace).distinct()

    if request.namespace:
        query = query.where(StoreItem.namespace == json.dumps(request.namespace))

    if request.suffix:
        # Filter by suffix
        for suf in request.suffix:
            query = query.where(StoreItem.namespace.op("@>")([suf]))

    query = query.limit(request.limit).offset(request.offset)
    result = await db.execute(query)
    namespaces = [json.loads(row[0]) for row in result.all()]

    return {"namespaces": namespaces}


@router.delete("/store/items")
async def delete_store_item(
    namespace: Optional[list[str]] = Query(None),
    key: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Delete a store item."""
    namespace_str = json.dumps(namespace) if namespace else None
    query = delete(StoreItem).where(StoreItem.key == key)
    if namespace_str:
        query = query.where(StoreItem.namespace == namespace_str)

    result = await db.execute(query)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.flush()
    return {"status": "deleted"}


# -----------------------------------------------------------------------------
# Task Queue Endpoints (Worker API)
# -----------------------------------------------------------------------------

@router.post("/tasks/dequeue")
async def dequeue_tasks(
    worker_id: str = Query(...),
    task_types: Optional[list[str]] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Worker endpoint: dequeue tasks with SELECT FOR UPDATE SKIP LOCKED."""
    task_queue = TaskQueueManager(db)
    tasks = await task_queue.dequeue(worker_id, task_types, limit)
    return [
        {
            "task_id": t.task_id,
            "task_type": t.task_type,
            "payload": t.payload,
            "priority": t.priority,
            "attempts": t.attempts,
            "max_attempts": t.max_attempts,
        }
        for t in tasks
    ]


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    success: bool = Query(True),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Worker endpoint: mark task complete."""
    task_queue = TaskQueueManager(db)
    ok = await task_queue.complete(task_id, success, error)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok"}


# -----------------------------------------------------------------------------
# Health & Info
# -----------------------------------------------------------------------------

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0", "service": "langgraph-server"}


@router.get("/info")
async def server_info():
    """Server info."""
    return {
        "version": "2.0.0",
        "features": {
            "threads": True,
            "runs": True,
            "assistants": True,
            "store": True,
            "streaming": True,
            "streaming_modes": [e.value for e in SSEEventType],
            "task_queue": True,
        },
    }


# =============================================================================
# Database Initialization (create tables)
# =============================================================================

async def create_langgraph_tables():
    """Create LangGraph Server tables if not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            Assistant.__table__,
            StoreItem.__table__,
            TaskQueue.__table__,
        ])


# Export router
__all__ = ["router", "create_langgraph_tables", "TaskQueueManager", "SSEStreamManager", "SSEEventType"]