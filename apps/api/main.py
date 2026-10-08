import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from packages.core.db import init_db, get_db_connection, record_audit_log
from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS, CONTRACTS_MAP
from packages.orchestrator.atlas_engine import AtlasOrchestrator
from packages.mcp.admin_server import AdminMCPServer
from packages.telemetry.correlation import CorrelationCalculator, CorrelationEdge

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await record_audit_log("system", "platform.startup", "platform:lifecycle", {}, "success")
    yield

app = FastAPI(
    title="Enterprise LangGraph Platform (LGP v2.0)",
    description="Control plane for 10 Subagents multi-agent enterprise platform",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = AtlasOrchestrator()
mcp_server = AdminMCPServer()
correlation_calc = CorrelationCalculator()

# In-memory event queues for live SSE per run
run_event_queues: Dict[str, asyncio.Queue] = {}

# 1. Health Endpoint
@app.get("/api/health")
async def health_check():
    db = await get_db_connection()
    try:
        async with db.execute("SELECT COUNT(*) as subagents_count FROM subagent_registry") as cursor:
            row = await cursor.fetchone()
            subagent_count = row["subagents_count"] if row else 0
        return {
            "status": "healthy",
            "version": "2.0.0",
            "platform": "Enterprise LangGraph Platform (LGP v2.0)",
            "subagents_active": subagent_count,
            "supervisor": "atlas",
            "storage": "SQLite WAL Mode (Enterprise Ready)",
            "mcp_admin": "active"
        }
    finally:
        await db.close()

# 2. Subagents Endpoints
@app.get("/api/subagents")
async def list_subagents(pod: Optional[str] = None):
    results = [c.model_dump() for c in TEN_SUBAGENTS_CONTRACTS]
    if pod:
        results = [c for c in results if c["pod"].lower() == pod.lower()]
    return {"subagents": results, "total": len(results)}

@app.get("/api/subagents/{subagent_id}")
async def get_subagent(subagent_id: str):
    contract = CONTRACTS_MAP.get(subagent_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Subagent not found")
    return contract.model_dump()

# 3. Runs Endpoints
class CreateRunRequest(BaseModel):
    objective: str
    thread_id: Optional[str] = None
    subagents: Optional[List[str]] = None

@app.post("/api/runs")
async def create_run(req: CreateRunRequest, background_tasks: BackgroundTasks):
    thread_id = req.thread_id or f"th-{int(asyncio.get_event_loop().time() * 1000)}"

    # Create run queue for SSE
    queue = asyncio.Queue()

    async def event_listener(evt):
        await queue.put(evt.model_dump())

    # Run execution in background or directly
    result = await orchestrator.execute_run(
        thread_id=thread_id,
        objective=req.objective,
        requested_subagents=req.subagents,
        event_callback=event_listener
    )

    run_id = result.get("run_id")
    if run_id:
        run_event_queues[run_id] = queue

    return result

@app.get("/api/runs")
async def list_runs(limit: int = 20):
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Run not found")
            return dict(row)
    finally:
        await db.close()

@app.get("/api/runs/{run_id}/stream")
async def stream_run_events(run_id: str):
    async def event_generator():
        # First send existing telemetry events
        db = await get_db_connection()
        try:
            async with db.execute("SELECT * FROM telemetry_events WHERE run_id = ? ORDER BY timestamp ASC", (run_id,)) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    yield {
                        "event": "telemetry",
                        "data": json.dumps(dict(r))
                    }
        finally:
            await db.close()

        # Then stream live queue events if available
        queue = run_event_queues.get(run_id)
        if queue:
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield {
                        "event": "telemetry",
                        "data": json.dumps(evt)
                    }
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield {
                        "event": "ping",
                        "data": "{}"
                    }
                    # Check if run completed
                    db_check = await get_db_connection()
                    try:
                        async with db_check.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)) as cur:
                            r = await cur.fetchone()
                            if r and r["status"] in ["completed", "failed", "interrupted"]:
                                break
                    finally:
                        await db_check.close()

    return EventSourceResponse(event_generator())

# 4. Correlations & Heatmap
@app.get("/api/correlations")
async def get_correlations():
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM correlation_edges") as cursor:
            rows = await cursor.fetchall()
            edges = [CorrelationEdge(**dict(r)) for r in rows]
        return correlation_calc.generate_10x10_matrix(edges)
    finally:
        await db.close()

# 5. HITL Inbox & Approvals
class ResolveHITLRequest(BaseModel):
    interrupt_id: str
    approver: str
    decision: str  # approved, rejected

@app.get("/api/hitl/inbox")
async def get_hitl_inbox():
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM hitl_inbox ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

@app.post("/api/hitl/resolve")
async def resolve_hitl(req: ResolveHITLRequest):
    res = await mcp_server.call_tool(
        "lgp_run_resume_hitl",
        {
            "interrupt_id": req.interrupt_id,
            "approver": req.approver,
            "decision": req.decision
        },
        actor=req.approver
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

# 6. Audit Log
@app.get("/api/audit")
async def get_audit_log(limit: int = 50):
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

# 7. Temporal Memory
@app.get("/api/memory/temporal")
async def get_temporal_facts(as_of_valid_time: Optional[float] = None, as_of_record_time: Optional[float] = None):
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM temporal_facts ORDER BY created_at DESC LIMIT 100") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

# 8. FastMCP Admin Endpoints
@app.get("/mcp/admin/tools")
async def list_mcp_tools():
    return {
        "server": "Enterprise LangGraph Platform Admin MCP",
        "version": "2.0.0",
        "tools": AdminMCPServer.TOOL_DEFINITIONS
    }

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}
    actor: str = "AdminClient"

@app.post("/mcp/admin/call")
async def call_mcp_tool(req: MCPCallRequest):
    return await mcp_server.call_tool(req.tool, req.arguments, req.actor)

# 9. Serve Web Dashboard
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "../dashboard/index.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>LGP v2.0 API is active</h1><p>Visit /api/health or /docs</p>"
