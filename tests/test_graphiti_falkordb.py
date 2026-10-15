import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from packages.memory.graphiti import GraphitiMemoryEngine


@pytest.mark.asyncio
async def test_falkordb_connectivity():
    """Memverifikasi koneksi FalkorDriver ke container lgp-falkordb di port 6382."""
    driver = await GraphitiMemoryEngine.get_driver()
    assert driver is not None, "FalkorDriver gagal terhubung ke FalkorDB"

    res = await driver.execute_query("RETURN 1 AS num")
    assert len(res) > 0
    assert res[0][0]["num"] == 1


@pytest.mark.asyncio
async def test_falkordb_cypher_bitemporal_edge():
    """Memverifikasi penulisan dan pembacaan node & edge bi-temporal langsung via Cypher."""
    driver = await GraphitiMemoryEngine.get_driver()
    assert driver is not None

    # Tulis test nodes dan edge bi-temporal dengan valid_at dan invalid_at
    cypher_insert = (
        "MERGE (a:Entity {uuid: 'test-agent-athena', name: 'Athena Subagent'}) "
        "MERGE (b:Entity {uuid: 'test-policy-core', name: 'Security Policy Core'}) "
        "MERGE (a)-[r:RELATES_TO {name: 'ENFORCES', fact: 'Athena enforces security policies'}]->(b) "
        "SET r.valid_at = '2026-10-15T12:00:00Z' "
        "RETURN a.name, type(r), r.valid_at, r.invalid_at, b.name"
    )
    insert_res = await driver.execute_query(cypher_insert)
    assert len(insert_res) > 0

    # Query Cypher untuk memverifikasi atribut bi-temporal
    cypher_query = (
        "MATCH (a:Entity {uuid: 'test-agent-athena'})-[r:RELATES_TO]->(b:Entity {uuid: 'test-policy-core'}) "
        "RETURN a.name AS src, type(r) AS rel, r.name AS rel_name, r.valid_at AS valid_at, r.invalid_at AS invalid_at, b.name AS tgt"
    )
    query_res = await driver.execute_query(cypher_query)
    assert len(query_res) > 0
    record = query_res[0][0]
    assert record["src"] == "Athena Subagent"
    assert record["tgt"] == "Security Policy Core"
    assert record["valid_at"] == "2026-10-15T12:00:00Z"
    assert record["invalid_at"] is None


@pytest.mark.asyncio
async def test_build_neuron_graph():
    """Memverifikasi agregasi graph neuron FalkorDB + Subagents + Categories."""
    graph = await GraphitiMemoryEngine.build_neuron_graph()
    assert "nodes" in graph
    assert "edges" in graph
    assert "stats" in graph
    assert graph["stats"]["subagents"] == 10
    assert graph["stats"]["categories"] == 5

    # Verifikasi keberadaan category hubs
    category_nodes = [n for n in graph["nodes"] if n.get("type") == "category"]
    assert len(category_nodes) == 5

    # Verifikasi keberadaan subagent nodes
    subagent_nodes = [n for n in graph["nodes"] if n.get("type") == "subagent"]
    assert len(subagent_nodes) == 10

    # Verifikasi edge bi-temporal
    bitemporal_edges = [e for e in graph["edges"] if e.get("bitemporal") is True]
    assert len(bitemporal_edges) > 0
    for edge in bitemporal_edges:
        assert "valid_at" in edge
        assert "invalid_at" in edge


@pytest.mark.asyncio
async def test_api_get_graph_graphiti():
    """Memverifikasi endpoint REST GET /api/graph/graphiti."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/graph/graphiti")
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 15
        assert "stats" in data


@pytest.mark.asyncio
async def test_api_post_memory_episodes():
    """Memverifikasi endpoint REST POST /api/memory/episodes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "name": "Integration Test Episode",
            "episode_body": "Janus UI coordinator synchronized telemetry streams with Metron monitoring agent.",
            "source_description": "Pytest integration suite",
            "reference_time": datetime.now(timezone.utc).isoformat()
        }
        res = await ac.post("/api/memory/episodes", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("success", "fallback_recorded")
        assert data["name"] == "Integration Test Episode"


@pytest.mark.asyncio
async def test_graceful_fallback_resilience():
    """Memverifikasi bahwa jika FalkorDB tidak tersedia, engine beralih ke SQLite fallback tanpa crash."""
    orig_port = GraphitiMemoryEngine.FALKORDB_PORT
    GraphitiMemoryEngine.FALKORDB_PORT = 9999
    GraphitiMemoryEngine._driver = None
    GraphitiMemoryEngine._graphiti = None

    try:
        data = await GraphitiMemoryEngine.build_neuron_graph()
        assert "nodes" in data
        assert "edges" in data
        assert "Fallback" in data.get("engine", "")
    finally:
        GraphitiMemoryEngine.FALKORDB_PORT = orig_port
        GraphitiMemoryEngine._driver = None
        GraphitiMemoryEngine._graphiti = None
