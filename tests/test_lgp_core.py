import pytest
import asyncio
from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS, CONTRACTS_MAP
from packages.guardrails.guards import (
    InheritedBudgetManager,
    CircuitBreaker,
    LoopDetector,
    SecurityToolGuard
)
from packages.core.models import BudgetEnvelope, ContextPacket
from packages.telemetry.correlation import CorrelationCalculator, SUBAGENT_IDS
from packages.memory.temporal import TemporalMemoryStore
from packages.mcp.admin_server import AdminMCPServer
from packages.orchestrator.atlas_engine import AtlasOrchestrator
from packages.core.db import init_db

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()

def test_ten_subagents_registry_complete():
    assert len(TEN_SUBAGENTS_CONTRACTS) == 10
    expected_ids = {"atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"}
    actual_ids = {c.id for c in TEN_SUBAGENTS_CONTRACTS}
    assert actual_ids == expected_ids

    # Verify each contract has required fields
    for c in TEN_SUBAGENTS_CONTRACTS:
        assert c.role
        assert c.pod in ["Koordinasi", "Riset & Rekayasa", "Platform", "Tata Kelola"]
        assert len(c.capabilities) > 0
        assert c.trust_level in ["High", "Medium", "Low", "Medium-High", "Low-Medium"]

def test_security_rules_clio_vulcan_themis():
    # Clio: Dilarang akses Admin MCP
    allowed, msg = SecurityToolGuard.validate_subagent_tool_access("clio", "admin:manage_users", {})
    assert not allowed
    assert "dilarang" in msg.lower() or "akses ditolak" in msg.lower()

    # Vulcan: Dilarang self-promote ke prod
    allowed, msg = SecurityToolGuard.validate_subagent_tool_access("vulcan", "graphs:promote_prod", {})
    assert not allowed
    assert "self-promote" in msg.lower() or "persetujuan manusia" in msg.lower()

    # Themis: Dilarang menerima raw secret value
    allowed, msg = SecurityToolGuard.validate_subagent_tool_access("themis", "audit:verify", {"secret_val": "12345"})
    assert not allowed
    assert "secret://" in msg

    # Themis: Diizinkan jika menggunakan secret_ref
    allowed, msg = SecurityToolGuard.validate_subagent_tool_access("themis", "audit:verify", {"db_ref": "secret://db_password"})
    assert allowed

def test_inherited_budget_enforcement():
    mgr = InheritedBudgetManager(daily_spent_usd=2.0)
    parent = BudgetEnvelope(max_tokens=100000, max_usd=2.0, depth_left=2)

    # Valid child
    child = mgr.validate_delegation_budget(parent, 50000, 1.0)
    assert child.max_tokens == 50000
    assert child.max_usd == 1.0
    assert child.depth_left == 1

    # Over budget child should raise ValueError
    with pytest.raises(ValueError, match="Budget violation"):
        mgr.validate_delegation_budget(parent, 150000, 1.0)

def test_circuit_breaker():
    cb = CircuitBreaker()
    agent = "clio"
    assert not cb.is_open(agent)

    cb.record_failure(agent)
    assert not cb.is_open(agent)
    cb.record_failure(agent)
    assert not cb.is_open(agent)
    tripped = cb.record_failure(agent)
    assert tripped
    assert cb.is_open(agent)

    cb.reset(agent)
    assert not cb.is_open(agent)

def test_loop_detector():
    ld = LoopDetector()
    h = ld.compute_state_hash("vulcan", "write_code", {"file": "main.py"}, {"state": 1})
    assert not ld.record_and_check(h)
    assert not ld.record_and_check(h)
    assert ld.record_and_check(h)  # 3rd time triggers loop detection

def test_correlation_calculator():
    calc = CorrelationCalculator()
    edge = calc.compute_edge(
        source="atlas",
        target="clio",
        handoffs=5,
        total_source_handoffs=10,
        co_activations=8,
        source_activations=10,
        target_activations=8,
        total_runs=10,
        co_successes=8,
        total_successes=9
    )
    assert edge.source_subagent == "atlas"
    assert edge.target_subagent == "clio"
    assert -1.0 <= edge.npmi_coactivation <= 1.0
    assert edge.polarity in ["positive", "neutral", "negative"]

    matrix = calc.generate_10x10_matrix([edge])
    assert len(matrix["subagents"]) == 10
    assert len(matrix["matrix"]) == 10

def test_bitemporal_memory_and_pii_redaction():
    text = "Kontak user: john.doe@example.com, telp 081234567890, NIK 3201012345670001"
    redacted = TemporalMemoryStore.redact_pii(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_NIK]" in redacted

    now = 1000.0
    fact1 = TemporalMemoryStore.create_fact("UserA", "PREFERS", "Dark mode", valid_at=900, invalid_at=1100)
    fact1.created_at = 950

    results = TemporalMemoryStore.filter_bitemporal([fact1], as_of_valid_time=1000, as_of_record_time=1000)
    assert len(results) == 1

    # Future record time
    results_past = TemporalMemoryStore.filter_bitemporal([fact1], as_of_valid_time=1000, as_of_record_time=900)
    assert len(results_past) == 0

@pytest.mark.asyncio
async def test_atlas_run_execution():
    orchestrator = AtlasOrchestrator()
    result = await orchestrator.execute_run(
        thread_id="test-th-1",
        objective="Uji coba integrasi riset dan koding",
        requested_subagents=["clio", "vulcan", "athena"]
    )
    assert result["status"] == "completed"
    assert result["run_id"].startswith("run-")
    assert len(result["delegates_report"]) >= 2
    assert "cost_summary" in result
