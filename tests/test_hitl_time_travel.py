"""Fase 3 LGP v2.0: native interrupt()/Command(resume), idempotensi pra-interrupt, time travel & forking."""
import pytest
from langgraph.checkpoint.memory import MemorySaver

from packages.core.db import init_db, get_db_connection
from packages.orchestrator.atlas_engine import AtlasOrchestrator

AGENTS = ["clio", "vulcan", "athena", "themis"]


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


async def _count(sql, params):
    db = await get_db_connection()
    try:
        async with db.execute(sql, params) as cur:
            return (await cur.fetchone())[0]
    finally:
        await db.close()


async def _start(thread_id):
    orch = AtlasOrchestrator(checkpointer=MemorySaver())
    res = await orch.execute_run(thread_id=thread_id, objective="Fase3 HITL", requested_subagents=AGENTS)
    return orch, res


async def test_vulcan_and_themis_interrupt_then_resume():
    orch, res = await _start("th-f3-a")
    assert res["status"] == "interrupted" and res["hitl_id"].endswith("-vulcan")
    run_id = res["run_id"]

    res = await orch.resume_run("th-f3-a", {"decision": "approved", "approver": "human-1"})
    assert res["status"] == "interrupted" and res["hitl_id"].endswith("-themis")

    res = await orch.resume_run("th-f3-a", {"decision": "approved", "approver": "human-1"})
    assert res["status"] == "completed"
    assert {r["subagent"] for r in res["delegates_report"]} == set(AGENTS)

    # inbox: tepat 1 baris per gate, keduanya approved
    assert await _count("SELECT COUNT(*) FROM hitl_inbox WHERE run_id=? AND status='approved'", (run_id,)) == 2
    assert await _count("SELECT COUNT(*) FROM hitl_inbox WHERE run_id=?", (run_id,)) == 2


async def test_pre_interrupt_side_effects_idempotent():
    orch, res = await _start("th-f3-b")
    run_id = res["run_id"]
    # node approval dieksekusi ulang saat resume; event interrupt + inbox tetap 1 per gate
    await orch.resume_run("th-f3-b", {"decision": "approved", "approver": "human-1"})
    await orch.resume_run("th-f3-b", {"decision": "approved", "approver": "human-1"})
    for agent in ("vulcan", "themis"):
        assert await _count(
            "SELECT COUNT(*) FROM telemetry_events WHERE run_id=? AND subagent_id=? AND event_type='interrupt'",
            (run_id, agent)) == 1
        assert await _count(
            "SELECT COUNT(*) FROM hitl_inbox WHERE run_id=? AND subagent_id=?", (run_id, agent)) == 1


async def test_rejection_stops_run():
    orch, _ = await _start("th-f3-c")
    res = await orch.resume_run("th-f3-c", {"decision": "rejected", "approver": "human-1"})
    assert res["status"] == "rejected"
    assert await _count("SELECT COUNT(*) FROM runs WHERE run_id=? AND status='rejected'", (res["run_id"],)) == 1


async def test_time_travel_history_and_fork():
    orch, res = await _start("th-f3-d")
    run_id = res["run_id"]
    await orch.resume_run("th-f3-d", {"decision": "approved", "approver": "human-1"})
    await orch.resume_run("th-f3-d", {"decision": "approved", "approver": "human-1"})

    hist = await orch.get_history("th-f3-d")
    assert len(hist) >= 5
    # checkpoint tepat saat menunggu persetujuan vulcan
    pending = [h for h in hist if h["next"] == ["vulcan_approval"]]
    assert pending, "checkpoint pra-approval vulcan harus ada di history"
    cp = pending[-1]
    n_before = len(hist)

    # Cabang: replay dari checkpoint itu dengan keputusan berbeda lewat resume pada thread cabang
    fork = await orch.fork_from_checkpoint("th-f3-d", cp["checkpoint_id"])
    assert fork["status"] == "interrupted" and fork["hitl_id"].endswith("-vulcan")  # node berhenti lagi di interrupt

    # history bertambah (cabang baru), checkpoint asal tidak berubah
    hist2 = await orch.get_history("th-f3-d")
    assert len(hist2) > n_before
    orig = next(h for h in hist2 if h["checkpoint_id"] == cp["checkpoint_id"])
    assert orig["values"]["approvals"] == cp["values"]["approvals"] == []

    # State branching: override state di checkpoint lama -> cabang membawa nilai baru, histori asal utuh
    fork2 = await orch.fork_from_checkpoint("th-f3-d", cp["checkpoint_id"], values={"objective": "cabang-B"})
    assert fork2["status"] == "interrupted"
    assert fork2["fork_config"]["checkpoint_id"] != cp["checkpoint_id"]
    latest = (await orch.get_history("th-f3-d"))[0]
    assert latest["values"]["objective"] == "cabang-B"
    assert next(h for h in await orch.get_history("th-f3-d") if h["checkpoint_id"] == cp["checkpoint_id"])["values"]["objective"] == "Fase3 HITL"
    assert run_id
