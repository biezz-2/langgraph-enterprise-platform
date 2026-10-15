import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from apps.admin_mcp.mcp_server_cli import mcp

@pytest.mark.asyncio
async def test_api_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["subagents_active"] == 10
        assert data["supervisor"] == "atlas"

@pytest.mark.asyncio
async def test_api_subagents():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/subagents")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 10

        # Filter by Pod
        res_pod = await ac.get("/api/subagents?pod=Koordinasi")
        assert res_pod.status_code == 200
        data_pod = res_pod.json()
        assert len(data_pod["subagents"]) == 1
        assert data_pod["subagents"][0]["id"] == "atlas"

@pytest.mark.asyncio
async def test_api_create_and_query_run():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "objective": "Analisis keamanan dan performa",
            "subagents": ["clio", "themis"]
        }
        res = await ac.post("/api/runs", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert len(data["delegates_report"]) == 2

        # Query runs list
        res_list = await ac.get("/api/runs")
        assert res_list.status_code == 200
        runs = res_list.json()
        assert len(runs) >= 1

@pytest.mark.asyncio
async def test_mcp_admin_tools_and_call():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Check MCP tools list
        res_tools = await ac.get("/mcp/admin/tools")
        assert res_tools.status_code == 200
        tools_data = res_tools.json()
        assert len(tools_data["tools"]) >= 17

        # Verify explicit annotations exist on all tools
        for tool in tools_data["tools"]:
            assert "annotations" in tool
            assert "readOnlyHint" in tool["annotations"]
            assert "destructiveHint" in tool["annotations"]

        # Call MCP tool: lgp_subagent_topology
        res_call = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_subagent_topology",
            "arguments": {}
        })
        assert res_call.status_code == 200
        topology = res_call.json()
        assert topology["topology"]["supervisor"] == "atlas"
        assert "Koordinasi" in topology["topology"]["pods"]

@pytest.mark.asyncio
async def test_mcp_long_term_memory_management():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Store new fact via MCP
        res = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_memory_store_fact",
            "arguments": {
                "subject": "System_Config",
                "predicate": "USES_MCP_PROTOCOL",
                "object": "FastMCP 2.0 dengan stdio dan HTTP",
                "episode_run_id": "run-mcp-test-01"
            }
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        fact_id = data["fact"]["fact_id"]

        # Query memory fact via MCP
        res_q = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_memory_query",
            "arguments": {"subject": "System_Config"}
        })
        assert res_q.status_code == 200
        facts = res_q.json()["facts"]
        assert len(facts) >= 1

        # Invalidate fact via MCP
        res_inv = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_memory_invalidate_fact",
            "arguments": {"fact_id": fact_id}
        })
        assert res_inv.status_code == 200
        assert res_inv.json()["status"] == "success"

@pytest.mark.asyncio
async def test_mcp_correlation_and_audit_setup():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Setup correlation weights via MCP
        res_setup = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_correlation_setup",
            "arguments": {"alpha": 0.5, "beta": 0.3, "gamma": 0.2, "n_min": 30}
        })
        assert res_setup.status_code == 200
        assert res_setup.json()["correlation_settings"]["n_min"] == 30

        # Query correlation matrix via MCP
        res_matrix = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_correlation_matrix",
            "arguments": {}
        })
        assert res_matrix.status_code == 200
        assert len(res_matrix.json()["subagents"]) == 10

        # Verify audit log chain integrity via MCP
        res_verify = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_audit_verify",
            "arguments": {}
        })
        assert res_verify.status_code == 200
        assert res_verify.json()["is_valid"] is True

@pytest.mark.asyncio
async def test_mcp_stdio_server_instance():
    tools = await mcp.list_tools()
    assert len(tools) == 37
    tool_names = [t.name for t in tools]
    assert "lgp_subagent_list" in tool_names
    assert "lgp_memory_store_fact" in tool_names
    assert "memory_recall" in tool_names
    assert "memory_store" in tool_names
    assert "lgp_correlation_setup" in tool_names
    assert "lgp_audit_verify" in tool_names
    assert "lgp_platform_health" in tool_names
    assert "lgp_hitl_inbox_list" in tool_names
    assert "lgp_memory_organized_summary" in tool_names
    assert "lgp_graphiti_neuron_graph" in tool_names
    assert "lgp_api_request" in tool_names

@pytest.mark.asyncio
async def test_mcp_new_api_and_dashboard_stream():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Test lgp_platform_health via MCP
        res_health = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_platform_health",
            "arguments": {}
        })
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"

        # Test lgp_hitl_inbox_list via MCP
        res_hitl = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_hitl_inbox_list",
            "arguments": {"status": "all"}
        })
        assert res_hitl.status_code == 200
        assert "interrupts" in res_hitl.json()

        # Test lgp_memory_organized_summary via MCP
        res_mem_org = await ac.post("/mcp/admin/call", json={
            "tool": "lgp_memory_organized_summary",
            "arguments": {}
        })
        assert res_mem_org.status_code == 200
        assert "categorized_facts" in res_mem_org.json()

        # Test broadcast endpoint
        res_bcast = await ac.post("/api/events/broadcast", json={
            "event": "test_ping",
            "data": {"msg": "hello"}
        })
        assert res_bcast.status_code == 200
        assert res_bcast.json()["status"] == "broadcasted"
