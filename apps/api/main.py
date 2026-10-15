import os
import json
import time
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from packages.core.db import init_db, get_db_connection, record_audit_log
from packages.core.event_bus import GlobalEventBus
from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS, CONTRACTS_MAP
from packages.orchestrator.atlas_engine import AtlasOrchestrator
from packages.mcp.admin_server import AdminMCPServer
from packages.telemetry.correlation import CorrelationCalculator, CorrelationEdge
from packages.memory.curator import MemoryCuratorEngine
from packages.memory.graphiti import GraphitiMemoryEngine

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
            "storage": f"Supabase PostgreSQL (schema: {os.environ.get('SUPABASE_SCHEMA', 'langgraph')})" if os.environ.get("USE_SUPABASE", "false").lower() == "true" else "SQLite WAL Mode",
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
    use_deepagents: bool = False

@app.post("/api/runs")
async def create_run(req: CreateRunRequest, background_tasks: BackgroundTasks):
    thread_id = req.thread_id or f"th-{int(asyncio.get_event_loop().time() * 1000)}"

    # Create run queue for SSE
    queue = asyncio.Queue()

    async def event_listener(evt):
        evt_data = evt.model_dump()
        await queue.put(evt_data)
        GlobalEventBus.get_instance().publish_sync("telemetry_emitted", evt_data)

    # Broadcast run initiation
    GlobalEventBus.get_instance().publish_sync("run_updated", {
        "status": "initiated",
        "objective": req.objective,
        "thread_id": thread_id
    })

    # Run execution in background or directly
    result = await orchestrator.execute_run(
        thread_id=thread_id,
        objective=req.objective,
        requested_subagents=req.subagents,
        event_callback=event_listener,
        use_deepagents=req.use_deepagents
    )

    run_id = result.get("run_id")
    if run_id:
        run_event_queues[run_id] = queue
        GlobalEventBus.get_instance().publish_sync("run_updated", {
            "run_id": run_id,
            "status": result.get("status", "completed"),
            "final_answer": result.get("final_answer", "")
        })

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

# 7. Temporal Memory & Graphiti Knowledge Graph
@app.get("/api/memory/temporal")
async def get_temporal_facts(as_of_valid_time: Optional[float] = None, as_of_record_time: Optional[float] = None):
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM temporal_facts ORDER BY created_at DESC LIMIT 100") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

@app.get("/api/memory/organized")
async def get_organized_memory():
    return await MemoryCuratorEngine.get_organized_memory_summary()

@app.post("/api/memory/seed")
async def seed_memory_knowledge():
    res = await MemoryCuratorEngine.seed_system_knowledge()
    await record_audit_log("admin", "memory.seed", "memory:temporal", res, "success")
    GlobalEventBus.get_instance().publish_sync("memory_updated", {"action": "seed", "inserted": res.get("inserted", 0)})
    return res

@app.get("/api/graph/graphiti")
async def get_graphiti_neuron_graph():
    return await GraphitiMemoryEngine.build_neuron_graph()

class AddEpisodeApiRequest(BaseModel):
    name: str
    episode_body: str
    source_description: str = "LGP API Ingestion"
    reference_time: Optional[datetime] = None
    group_id: Optional[str] = None

@app.post("/api/memory/episodes")
async def add_memory_episode(req: AddEpisodeApiRequest):
    res = await GraphitiMemoryEngine.add_episode(
        name=req.name,
        episode_body=req.episode_body,
        source_description=req.source_description,
        reference_time=req.reference_time,
        group_id=req.group_id
    )
    await record_audit_log("admin", "memory.episode", f"episode:{req.name}", res, "success")
    GlobalEventBus.get_instance().publish_sync("memory_updated", {"action": "add_episode", "name": req.name})
    return res

# 8. FastMCP Admin Endpoints
@app.get("/mcp/admin/tools")
async def list_mcp_tools():
    return {
        "server": "Enterprise LangGraph Platform Admin MCP",
        "version": "2.0.0",
        "tools": AdminMCPServer.TOOL_DEFINITIONS
    }

# 9. Kanban Board Endpoints
class CreateBoardRequest(BaseModel):
    name: str
    columns: List[Dict[str, Any]]

class CreateCardRequest(BaseModel):
    column_id: str
    title: str
    description: str = ""
    priority: str = "medium"
    assigned_to: Optional[str] = None

class MoveCardRequest(BaseModel):
    to_column_id: str

@app.get("/api/kanban/boards")
async def list_kanban_boards():
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM kanban_boards ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

@app.get("/api/kanban/boards/{board_id}")
async def get_kanban_board(board_id: str):
    db = await get_db_connection()
    try:
        # Get board
        async with db.execute("SELECT * FROM kanban_boards WHERE id = ?", (board_id,)) as cursor:
            board_row = await cursor.fetchone()
            if not board_row:
                raise HTTPException(status_code=404, detail="Board not found")
        
        # Get columns
        async with db.execute("SELECT * FROM kanban_columns WHERE board_id = ? ORDER BY order_idx ASC", (board_id,)) as cursor:
            columns = [dict(r) for r in await cursor.fetchall()]
        
        # Get cards for each column
        for col in columns:
            async with db.execute("SELECT * FROM kanban_cards WHERE column_id = ? ORDER BY created_at ASC", (col["id"],)) as cursor:
                col["cards"] = [dict(r) for r in await cursor.fetchall()]
        
        return {**dict(board_row), "columns": columns}
    finally:
        await db.close()

@app.post("/api/kanban/boards")
async def create_kanban_board(req: CreateBoardRequest):
    db = await get_db_connection()
    try:
        board_id = f"board-{int(time.time() * 1000)}"
        await db.execute(
            "INSERT INTO kanban_boards (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (board_id, req.name, time.time(), time.time())
        )
        
        for i, col in enumerate(req.columns):
            col_id = f"col-{int(time.time() * 1000)}-{i}"
            await db.execute(
                "INSERT INTO kanban_columns (id, board_id, name, order_idx) VALUES (?, ?, ?, ?)",
                (col_id, board_id, col["name"], i)
            )
        
        await db.commit()
        await record_audit_log("admin", "kanban.board.create", "kanban", {"board_id": board_id}, "success")
        GlobalEventBus.get_instance().publish_sync("kanban_updated", {"board_id": board_id})
        return {"board_id": board_id, "status": "created"}
    finally:
        await db.close()

@app.post("/api/kanban/cards")
async def create_kanban_card(req: CreateCardRequest):
    db = await get_db_connection()
    try:
        card_id = f"card-{int(time.time() * 1000)}"
        await db.execute(
            "INSERT INTO kanban_cards (id, column_id, title, description, priority, assigned_to, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (card_id, req.column_id, req.title, req.description, req.priority, req.assigned_to, time.time(), time.time())
        )
        await db.commit()
        await record_audit_log("admin", "kanban.card.create", "kanban", {"card_id": card_id}, "success")
        GlobalEventBus.get_instance().publish_sync("kanban_updated", {"card_id": card_id})
        return {"card_id": card_id, "status": "created"}
    finally:
        await db.close()

@app.post("/api/kanban/cards/{card_id}/move")
async def move_kanban_card(card_id: str, req: MoveCardRequest):
    db = await get_db_connection()
    try:
        await db.execute(
            "UPDATE kanban_cards SET column_id = ?, updated_at = ? WHERE id = ?",
            (req.to_column_id, time.time(), card_id)
        )
        await db.commit()
        await record_audit_log("admin", "kanban.card.move", "kanban", {"card_id": card_id}, "success")
        GlobalEventBus.get_instance().publish_sync("kanban_updated", {"card_id": card_id})
        return {"status": "moved"}
    finally:
        await db.close()

# 10. Matrix Configuration Endpoints
class MatrixConfigRequest(BaseModel):
    alpha: float = 0.4
    beta: float = 0.4
    gamma: float = 0.2
    n_min: int = 50
    enabled: bool = True

@app.get("/api/matrix/config")
async def get_matrix_config():
    db = await get_db_connection()
    try:
        async with db.execute("SELECT * FROM matrix_config WHERE id = 'default'") as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            # Return default config if not exists
            return {
                "id": "default",
                "name": "Default Configuration",
                "description": "Default correlation matrix weights",
                "alpha": 0.4,
                "beta": 0.4,
                "gamma": 0.2,
                "n_min": 50,
                "enabled": True,
                "created_at": time.time()
            }
    finally:
        await db.close()

@app.post("/api/matrix/config")
async def update_matrix_config(req: MatrixConfigRequest):
    db = await get_db_connection()
    try:
        await db.execute("""
            INSERT INTO matrix_config (id, name, description, alpha, beta, gamma, n_min, enabled, created_at)
            VALUES ('default', 'Default Configuration', 'Default correlation matrix weights', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET alpha=?, beta=?, gamma=?, n_min=?, enabled=?
        """, (req.alpha, req.beta, req.gamma, req.n_min, req.enabled, time.time(),
              req.alpha, req.beta, req.gamma, req.n_min, req.enabled))
        await db.commit()
        await record_audit_log("admin", "matrix.config.update", "matrix", req.dict(), "success")
        GlobalEventBus.get_instance().publish_sync("matrix_updated", req.dict())
        return {"status": "updated"}
    finally:
        await db.close()

@app.post("/api/matrix/recalculate")
async def recalculate_matrix():
    db = await get_db_connection()
    try:
        # Trigger recalculation
        async with db.execute("SELECT * FROM correlation_edges") as cursor:
            rows = await cursor.fetchall()
            edges = [CorrelationEdge(**dict(r)) for r in rows]
        
        matrix = correlation_calc.generate_10x10_matrix(edges)
        
        await record_audit_log("admin", "matrix.recalculate", "matrix", {"edges_count": len(edges)}, "success")
        GlobalEventBus.get_instance().publish_sync("correlation_updated", matrix)
        return {"status": "recalculated", "matrix": matrix}
    finally:
        await db.close()

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}
    actor: str = "AdminClient"

@app.post("/mcp/admin/call")
async def call_mcp_tool(req: MCPCallRequest):
    return await mcp_server.call_tool(req.tool, req.arguments, req.actor)

# 9. Real-Time Dashboard SSE Stream & Event Broadcast
class BroadcastEventRequest(BaseModel):
    event: str
    data: Dict[str, Any] = {}

@app.post("/api/events/broadcast")
async def broadcast_event(req: BroadcastEventRequest):
    GlobalEventBus.get_instance().publish_sync(req.event, req.data)
    return {"status": "broadcasted", "event": req.event}

@app.get("/api/dashboard/stream")
async def dashboard_stream():
    queue = GlobalEventBus.get_instance().subscribe()

    async def event_generator():
        try:
            # Initial handshake
            yield {
                "event": "connected",
                "data": json.dumps({"status": "connected", "timestamp": time.time()})
            }
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": evt.get("event", "update"),
                        "data": json.dumps(evt.get("data", {}))
                    }
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": time.time()})
                    }
        finally:
            GlobalEventBus.get_instance().unsubscribe(queue)

    return EventSourceResponse(event_generator())

# 10. API Gateway Root (Web UI migrated to Next.js dashboard)
@app.get("/")
async def root_api():
    return {
        "status": "online",
        "platform": "Enterprise LangGraph Platform (LGP v2.0)",
        "version": "2.0.0",
        "architecture": "MiroFish Spiking Neuron & Multi-Agent Swarm",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "health_url": "/api/health",
        "websocket_url": "/ws/dashboard",
        "subagents_count": 10,
        "active_pods": ["Koordinasi", "Riset & Rekayasa", "Platform", "Tata Kelola"]
    }

# 11. Real-time WebSocket Gateway
class DashboardWebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_dashboard_manager = DashboardWebSocketManager()

@app.websocket("/ws/dashboard")
@app.websocket("/ws")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    await ws_dashboard_manager.connect(websocket)
    queue = GlobalEventBus.get_instance().subscribe()

    try:
        await websocket.send_json({
            "type": "handshake",
            "status": "connected",
            "protocol": "WebSocket",
            "timestamp": time.time(),
            "server": "Enterprise LangGraph Platform (LGP v2.0)"
        })
    except Exception:
        GlobalEventBus.get_instance().unsubscribe(queue)
        ws_dashboard_manager.disconnect(websocket)
        return

    async def forward_events():
        try:
            while True:
                evt = await queue.get()
                await websocket.send_json({
                    "type": "platform_event",
                    "event": evt.get("event", "update"),
                    "data": evt.get("data", {}),
                    "timestamp": evt.get("timestamp", time.time())
                })
        except (asyncio.CancelledError, Exception):
            pass

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(5.0)
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "status": "active"
                })
        except (asyncio.CancelledError, Exception):
            pass

    forward_task = asyncio.create_task(forward_events())
    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
            else:
                try:
                    payload = json.loads(msg)
                    if payload.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": time.time()})
                except Exception:
                    pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        forward_task.cancel()
        heartbeat_task.cancel()
        GlobalEventBus.get_instance().unsubscribe(queue)
        ws_dashboard_manager.disconnect(websocket)

