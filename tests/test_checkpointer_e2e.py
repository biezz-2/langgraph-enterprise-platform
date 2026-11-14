import pytest
import os
import asyncio
from dotenv import load_dotenv

from packages.core.checkpointer import (
    get_async_postgres_saver,
    get_checkpointer_pool,
    close_checkpointer_pool,
    get_checkpointer
)
from packages.orchestrator.atlas_engine import AtlasOrchestrator

load_dotenv()

@pytest.mark.asyncio
async def test_postgres_checkpointer_e2e():
    """Uji verifikasi end-to-end persistensi checkpoint LGP v2.0 pada skema 'langgraph'."""
    schema = os.environ.get("SUPABASE_SCHEMA", "langgraph")
    saver = await get_async_postgres_saver(schema=schema)
    assert saver is not None, "AsyncPostgresSaver gagal diinisialisasi"

    # Inisialisasi AtlasOrchestrator dengan saver terhubung ke PostgreSQL
    orchestrator = AtlasOrchestrator(checkpointer=saver)

    thread_id = f"test-th-e2e-{os.urandom(4).hex()}"
    objective = "Audit dan verifikasi end-to-end StateGraph dengan AsyncPostgresSaver"
    subagents = ["clio", "vulcan", "athena"]

    # Eksekusi StateGraph run
    result = await orchestrator.execute_run(
        thread_id=thread_id,
        objective=objective,
        requested_subagents=subagents,
        checkpointer=saver
    )

    assert result["status"] == "interrupted"
    result = await orchestrator.resume_run(thread_id, {"decision": "approved", "approver": "human"})
    assert result["status"] == "completed"
    assert len(result["delegates_report"]) >= 2
    assert "cost_summary" in result

    # Verifikasi langsung pada checkpointer PostgreSQL
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    latest_tuple = await saver.aget_tuple(config)
    assert latest_tuple is not None, f"Checkpoint untuk thread {thread_id} tidak ditemukan di DB"
    assert latest_tuple.checkpoint is not None

    channel_vals = latest_tuple.checkpoint.get("channel_values", {})
    assert channel_vals.get("status") == "completed"
    assert len(channel_vals.get("delegates_report", [])) >= 2
    assert "final_answer" in channel_vals

    # Verifikasi riwayat snapshot checkpoint (step progression)
    history = [c async for c in saver.alist(config)]
    assert len(history) >= 2, f"Diharapkan minimal 2 snapshot checkpoint, didapat {len(history)}"

    print(f"End-to-End Checkpoint sukses: {len(history)} snapshot tersimpan di skema '{schema}'.")
