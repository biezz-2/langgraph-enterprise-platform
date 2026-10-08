"""
Self-check runner for LGP v2.0 API & FastMCP Admin Contracts.
Verifies:
1. OpenAPI generation & path coverage.
2. Pydantic v2 serialization & RFC 7807 schema.
3. FastMCP tool annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint).
4. Security isolation rules (Clio exclusion, Vulcan self-promote ban, Themis secret scrubbing).
"""

import asyncio
import sys
from datetime import datetime, timezone

# Add source path
sys.path.insert(0, "/home/biezz/Documents/Project/coding/langgraph/src")

from lgp.contracts.admin_mcp import AccessIsolationPolicy, mcp_admin_server
from lgp.contracts.api_router import create_app
from lgp.contracts.schemas import (
    AuditLogEntry,
    CorrelationCell,
    CorrelationPolarity,
    CorrelationPolaritySource,
    ProblemDetails,
    RunCreate,
    SubagentContract,
    TemporalFact,
)


def test_openapi_contract():
    app = create_app()
    spec = app.openapi()
    assert spec["openapi"].startswith("3."), "Invalid OpenAPI version"
    paths = spec["paths"]

    expected_paths = [
        "/api/assistants",
        "/api/threads",
        "/api/runs",
        "/api/runs/{run_id}/stream",
        "/api/runs/{run_id}/interrupts",
        "/api/subagents",
        "/api/subagents/topology",
        "/api/subagents/{subagent_id}/status",
        "/api/correlations/matrix",
        "/api/correlations/weights",
        "/api/memory/temporal/facts",
        "/api/audit",
        "/api/health",
    ]
    for p in expected_paths:
        assert p in paths, f"Missing expected REST path: {p}"
    print("ASSERT OK: All 13 core REST endpoints present in OpenAPI schema.")


def test_pydantic_schemas():
    # Test ProblemDetails
    pd = ProblemDetails(
        type="https://api.lgp.enterprise.io/errors/FORBIDDEN_ACCESS",
        title="Forbidden Access",
        status=403,
        detail="Subagent clio is barred from Admin MCP.",
        instance="/api/mcp/admin",
        code="FORBIDDEN_ACCESS",
    )
    assert pd.status == 403
    assert pd.code.value == "FORBIDDEN_ACCESS"

    # Test Bi-temporal Fact (4 timestamps)
    now = datetime.now(timezone.utc)
    tf = TemporalFact(
        fact_id="fact-001",
        entity_source="Vulcan",
        relation="CRITICIZES",
        entity_target="Athena",
        valid_at=now,
        created_at=now,
        episode_id="ep-01",
        source_run_id="run-01",
        step_index=1,
        subagent_id="vulcan",
    )
    assert tf.invalid_at is None
    assert tf.expired_at is None

    # Test Correlation Matrix cell
    cell = CorrelationCell(
        source_agent="vulcan",
        target_agent="athena",
        sample_count=65,
        is_sparse=False,
        handoff_rate=0.85,
        npmi_coactivation=0.72,
        success_lift=0.35,
        latency_coupling=0.20,
        state_dependency=0.65,
        cost_share=0.40,
        failure_propagation=0.02,
        aggregate_weight=0.78,
        polarity=CorrelationPolarity.POSITIVE,
        polarity_source=CorrelationPolaritySource.OUTCOME,
    )
    assert cell.aggregate_weight == 0.78

    print("ASSERT OK: Pydantic schemas serialized and validated.")


async def test_fastmcp_annotations():
    tools = await mcp_admin_server.list_tools()
    tool_map = {t.name: t for t in tools}
    assert len(tool_map) == 9, f"Expected 9 FastMCP tools, got {len(tool_map)}"

    # Required tools
    expected_tools = {
        "lgp_subagent_list": {"read": True, "destruct": False, "idemp": True, "open": False},
        "lgp_subagent_get": {"read": True, "destruct": False, "idemp": True, "open": False},
        "lgp_subagent_topology": {"read": True, "destruct": False, "idemp": True, "open": False},
        "lgp_run_create": {"read": False, "destruct": False, "idemp": False, "open": False},
        "lgp_run_get_state": {"read": True, "destruct": False, "idemp": True, "open": False},
        "lgp_run_resume_hitl": {"read": False, "destruct": False, "idemp": False, "open": False},
        "lgp_correlation_matrix": {"read": True, "destruct": False, "idemp": True, "open": False},
        "lgp_audit_query": {"read": True, "destruct": False, "idemp": True, "open": False},
        "lgp_memory_query": {"read": True, "destruct": False, "idemp": True, "open": False},
    }

    for name, exp in expected_tools.items():
        assert name in tool_map, f"Missing MCP tool {name}"
        t = tool_map[name]
        assert t.annotations is not None, f"Tool {name} missing annotations"
        assert t.annotations.read_only_hint == exp["read"], f"Mismatch readOnlyHint for {name}"
        assert t.annotations.destructive_hint == exp["destruct"], f"Mismatch destructiveHint for {name}"
        assert t.annotations.idempotent_hint == exp["idemp"], f"Mismatch idempotentHint for {name}"
        assert t.annotations.open_world_hint == exp["open"], f"Mismatch openWorldHint for {name}"

    print("ASSERT OK: All 9 FastMCP tools and annotations verified.")


def test_access_isolation():
    # Rule 1: Clio banned from Admin MCP
    try:
        AccessIsolationPolicy.enforce_clio_admin_ban("clio")
        assert False, "Should have raised PermissionError for clio"
    except PermissionError as e:
        assert "clio" in str(e).lower()

    # Rule 2: Vulcan banned from self-promoting to production
    try:
        AccessIsolationPolicy.enforce_vulcan_self_promotion(caller_id="vulcan", is_human=False, target_env="production")
        assert False, "Should have raised PermissionError for vulcan self-promotion"
    except PermissionError as e:
        assert "vulcan" in str(e).lower()

    # Allowed for human
    AccessIsolationPolicy.enforce_vulcan_self_promotion(caller_id="vulcan", is_human=True, target_env="production")

    # Rule 3: Themis receives zero plaintext secrets
    sensitive_payload = {
        "service": "database",
        "db_secret_key": "super_secret_password_123",
        "vault_ref": "secret://vault/db_pass",
        "nested": {"token_value": "tok_xyz987", "safe_val": 42},
    }
    scrubbed = AccessIsolationPolicy.sanitize_secrets_for_themis("themis", sensitive_payload)
    assert scrubbed["db_secret_key"] == "REDACTED_BY_THEMIS_POLICY"
    assert scrubbed["vault_ref"] == "secret://vault/db_pass"
    assert scrubbed["nested"]["token_value"] == "REDACTED_BY_THEMIS_POLICY"
    assert scrubbed["nested"]["safe_val"] == 42

    print("ASSERT OK: Access isolation guardrails (Clio, Vulcan, Themis) verified.")


def main():
    test_openapi_contract()
    test_pydantic_schemas()
    asyncio.run(test_fastmcp_annotations())
    test_access_isolation()
    print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
