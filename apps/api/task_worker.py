"""
LGP Task Queue Worker — mengonsumsi TaskQueue (task_type='run') dan mengeksekusi
run melalui AtlasOrchestrator. Berjalan sebagai asyncio task di dalam proses API.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from persistence import async_session_factory
from apps.api.routers.langgraph_server import TaskQueueManager
from packages.orchestrator.atlas_engine import AtlasOrchestrator

logger = logging.getLogger("apps.api.task_worker")

POLL_INTERVAL_S = float(os.environ.get("TASK_WORKER_POLL_INTERVAL", "2.0"))
WORKER_ID = f"api-worker-{uuid.uuid4().hex[:8]}"
MAX_CONCURRENT = int(os.environ.get("TASK_WORKER_CONCURRENCY", "2"))

_orchestrator: Optional[AtlasOrchestrator] = None
_semaphore: Optional[asyncio.Semaphore] = None


def _get_orchestrator() -> AtlasOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AtlasOrchestrator()
    return _orchestrator


def _get_event_queues():
    # Lazy import untuk menghindari circular import dengan apps.api.main
    from apps.api.main import run_event_queues
    return run_event_queues


def _extract_objective(payload: Dict[str, Any]) -> Optional[str]:
    objective = payload.get("objective")
    if objective:
        return str(objective)
    kwargs = payload.get("kwargs") or {}
    if isinstance(kwargs, dict):
        obj = kwargs.get("objective") or kwargs.get("input") or kwargs.get("task") or kwargs.get("query")
        if obj:
            return str(obj)
        # Payload umum LangGraph: {"messages": [{"role": "user", "content": ...}]}
        messages = kwargs.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                content = last.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = [p.get("text", "") for p in content if isinstance(p, dict)]
                    joined = " ".join(t for t in texts if t)
                    if joined:
                        return joined
    return None


async def _execute_task(task) -> None:
    payload = task.payload or {}
    run_id = payload.get("run_id") or f"run-{uuid.uuid4().hex[:12]}"
    thread_id = payload.get("thread_id") or f"th-{uuid.uuid4().hex[:12]}"
    objective = _extract_objective(payload)

    if not objective:
        raise ValueError(f"Task {task.task_id} tidak memiliki objective di payload")

    queues = _get_event_queues()
    queue = queues.setdefault(run_id, asyncio.Queue())

    async def event_listener(evt):
        try:
            await queue.put(evt.model_dump())
        except Exception:
            pass
        try:
            from packages.core.event_bus import GlobalEventBus
            GlobalEventBus.get_instance().publish_sync("telemetry_emitted", evt.model_dump())
        except Exception:
            pass

    orchestrator = _get_orchestrator()
    result = await orchestrator.execute_run(
        thread_id=thread_id,
        objective=objective,
        requested_subagents=payload.get("subagents") or payload.get("requested_subagents"),
        event_callback=event_listener,
        use_deepagents=bool(payload.get("use_deepagents", False)),
        run_id=run_id,
    )

    # Update status Run ORM (best effort — tabel mungkin tidak ada di mode SQLite)
    try:
        from persistence import Run, RunStatus
        async with async_session_factory() as session:
            orm_run = await session.get(Run, run_id)
            if orm_run is None:
                orm_run = await session.get(Run, payload.get("run_id") or run_id)
            if orm_run is not None:
                orm_run.status = RunStatus.COMPLETED if result.get("status") == "completed" else RunStatus.FAILED
                orm_run.completed_at = orm_run.updated_at = _utcnow()
                await session.commit()
    except Exception as orm_err:
        logger.debug("Update status Run ORM gagal (non-fatal): %s", orm_err)

    try:
        from packages.core.event_bus import GlobalEventBus
        GlobalEventBus.get_instance().publish_sync("run_updated", {
            "run_id": run_id,
            "status": result.get("status", "completed"),
            "final_answer": (result.get("final_answer") or "")[:500],
        })
    except Exception:
        pass

    logger.info("Task %s (run %s) selesai: %s", task.task_id, run_id, result.get("status"))


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


async def _task_worker_loop(stop_event: asyncio.Event) -> None:
    global _semaphore
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    logger.info("Task worker '%s' aktif (poll=%.1fs, concurrency=%d)", WORKER_ID, POLL_INTERVAL_S, MAX_CONCURRENT)

    while not stop_event.is_set():
        try:
            async with async_session_factory() as session:
                tqm = TaskQueueManager(session)
                tasks = await tqm.dequeue(WORKER_ID, task_types=["run"], limit=MAX_CONCURRENT)
                if not tasks:
                    await session.commit()
                    await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_S)
                    continue
                await session.commit()  # persist status 'running'

            for task in tasks:
                asyncio.create_task(_run_task_guarded(task))
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.warning("Task worker poll error: %s", e)
            await asyncio.sleep(POLL_INTERVAL_S)


async def _run_task_guarded(task) -> None:
    async with _semaphore:
        try:
            await _execute_task(task)
            async with async_session_factory() as session:
                await TaskQueueManager(session).complete(task.task_id, success=True)
                await session.commit()
        except Exception as e:
            logger.error("Task %s gagal: %s", task.task_id, e)
            try:
                async with async_session_factory() as session:
                    await TaskQueueManager(session).complete(task.task_id, success=False, error=str(e)[:1000])
                    await session.commit()
            except Exception as ce:
                logger.error("Gagal mark task %s failed: %s", task.task_id, ce)


async def enqueue_run_task(
    run_id: str,
    thread_id: str,
    objective: str,
    subagents: Optional[list] = None,
    use_deepagents: bool = False,
    after_seconds: int = 0,
) -> Optional[str]:
    """Enqueue run ke TaskQueue; return task_id atau None jika enqueue gagal."""
    from datetime import datetime, timezone, timedelta
    try:
        async with async_session_factory() as session:
            tqm = TaskQueueManager(session)
            task_id = await tqm.enqueue(
                task_type="run",
                payload={
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "objective": objective,
                    "subagents": subagents,
                    "use_deepagents": use_deepagents,
                },
                scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=after_seconds) if after_seconds else None,
            )
            await session.commit()
            return task_id
    except Exception as e:
        logger.warning("Enqueue run task gagal (fallback ke background task): %s", e)
        return None


def start_task_worker() -> asyncio.Task:
    stop_event = asyncio.Event()
    task = asyncio.create_task(_task_worker_loop(stop_event))
    task._stop_event = stop_event  # type: ignore[attr-defined]
    return task


async def stop_task_worker(task: Optional[asyncio.Task]) -> None:
    if task is None:
        return
    try:
        task._stop_event.set()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    except Exception:
        task.cancel()
