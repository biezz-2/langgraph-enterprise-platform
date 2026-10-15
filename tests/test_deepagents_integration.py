import pytest
import asyncio
import time
from typing import List, Any
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from packages.subagents.contracts import (
    to_deepagents_subagent,
    get_deepagents_subagents,
    CONTRACTS_MAP,
    TEN_SUBAGENTS_CONTRACTS,
)
from packages.memory.temporal import TemporalMemoryStore
from packages.core.models import TemporalFact
from packages.orchestrator.atlas_engine import AtlasOrchestrator
from packages.core.db import get_db_connection
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemPermission


class ToolCallingFakeChatModel(FakeListChatModel):
    """Fake chat model yang kompatibel dengan Pydantic & deepagents bind_tools."""
    def bind_tools(self, tools: Any, **kwargs: Any) -> "ToolCallingFakeChatModel":
        object.__setattr__(self, "bound_tools", tools)
        return self


@pytest.mark.asyncio
async def test_subagent_contract_conversion():
    """Memverifikasi konversi SubagentContract LGP v2.0 ke DeepAgents SubAgent."""
    subagents = get_deepagents_subagents()
    assert len(subagents) == 9  # 10 contracts minus root atlas
    
    subagent_map = {s["name"]: s for s in subagents}
    assert "clio" in subagent_map
    assert "vulcan" in subagent_map
    assert "athena" in subagent_map
    assert "iris" in subagent_map

    # Clio filesystem sandboxing
    clio = subagent_map["clio"]
    clio_perms = clio.get("permissions", [])
    assert len(clio_perms) == 2
    assert any(p.paths == ["/workspace"] and p.operations == ["read"] for p in clio_perms)
    assert any(p.paths == ["/"] and p.mode == "deny" for p in clio_perms)

    # Vulcan filesystem sandboxing
    vulcan = subagent_map["vulcan"]
    vulcan_perms = vulcan.get("permissions", [])
    assert len(vulcan_perms) == 2
    assert any(p.paths == ["/workspace"] and set(p.operations) == {"read", "write"} for p in vulcan_perms)
    assert any(set(p.paths) == {"/etc", "/admin", "/root"} and p.mode == "deny" for p in vulcan_perms)


@pytest.mark.asyncio
async def test_temporal_facts_to_agents_markdown():
    """Memverifikasi serialisasi temporal facts ke format markdown AGENTS.md."""
    fact = TemporalFact(
        subject="User_Config",
        predicate="PREFERS",
        object="Dark_Mode",
        valid_at=time.time(),
        invalid_at=None,
        created_at=time.time(),
        expired_at=time.time() + 3600,
        episode_run_id="run-test-md",
        pii_redacted=True
    )
    md = TemporalMemoryStore.to_agents_markdown([fact])
    assert "# AGENTS MEMORY" in md
    assert "User_Config" in md
    assert "PREFERS" in md
    assert "Dark_Mode" in md


@pytest.mark.asyncio
async def test_deepagents_graph_compilation_and_execution():
    """Memverifikasi create_deep_agent mengompilasi dan mengeksekusi graf dengan memory middleware."""
    fake_model = ToolCallingFakeChatModel(responses=["Analisis selesai dengan sukses."])
    agent = create_deep_agent(
        model=fake_model,
        subagents=get_deepagents_subagents(model=fake_model),
        memory=["/memory/AGENTS.md"],
        backend=StateBackend()
    )

    memory_content = "# AGENTS MEMORY\n- Atlas mengoordinasikan 9 subagen."
    input_state = {
        "messages": [HumanMessage(content="Jalankan riset awal")],
        "files": {
            "/memory/AGENTS.md": {
                "content": memory_content,
                "encoding": "utf-8"
            }
        }
    }

    res = await agent.ainvoke(input_state)
    assert "messages" in res
    assert len(res["messages"]) >= 2
    assert res["messages"][-1].content == "Analisis selesai dengan sukses."


@pytest.mark.asyncio
async def test_atlas_orchestrator_deepagents_runtime():
    """Memverifikasi eksekusi AtlasOrchestrator menggunakan DeepAgents backend."""
    fake_model = ToolCallingFakeChatModel(responses=["Riset diselesaikan oleh Atlas via DeepAgents."])
    orchestrator = AtlasOrchestrator(deepagent_model=fake_model)

    events_captured = []
    async def capture_event(evt):
        events_captured.append(evt)

    res = await orchestrator.execute_run(
        thread_id="th-deepagents-test",
        objective="Lakukan audit keamanan sistem",
        event_callback=capture_event,
        use_deepagents=True
    )

    assert res["status"] == "completed"
    assert "DeepAgents" in res["final_answer"] or "selesai" in res["final_answer"]
    assert res["cost_summary"]["total_tokens"] > 0

    # Pastikan database mencatat run
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM runs WHERE run_id = ?", (res["run_id"],)) as cursor:
            run_row = await cursor.fetchone()
            assert run_row is not None
            assert run_row["status"] == "completed"

        async with db.execute("SELECT * FROM audit_log WHERE scope = ?", (f"run:{res['run_id']}",)) as cursor:
            audit_rows = await cursor.fetchall()
            assert len(audit_rows) > 0
    finally:
        await db.close()

    # Pastikan telemetry event ter-emit
    event_types = [e.event_type for e in events_captured]
    assert "node.start" in event_types
    assert "node.end" in event_types
