import sys
import os
import asyncio
from typing import Optional, List, Dict, Any
from mcp.server.mcpserver import MCPServer
from packages.core.db import init_db
from packages.mcp.admin_server import AdminMCPServer

# Initialize MCPServer app for stdio / MCP protocol execution
mcp = MCPServer(
    name="Enterprise LangGraph Platform Admin MCP",
    version="2.0.0",
    description="Control plane FastMCP / MCPServer for 10 Subagents, Long-Term Memory, and 10x10 Correlation Matrix."
)

admin_backend = AdminMCPServer()

# Run DB initialization asynchronously before starting stdio loop
asyncio.run(init_db())

@mcp.tool(
    name="lgp_subagent_list",
    description="Menampilkan daftar seluruh subagent terdaftar (10 subagents) beserta pod, kontrak, dan status aktifnya."
)
async def lgp_subagent_list(pod: Optional[str] = None) -> dict:
    return await admin_backend.call_tool("lgp_subagent_list", {"pod": pod})

@mcp.tool(
    name="lgp_subagent_get",
    description="Mengambil kontrak lengkap suatu subagent berdasarkan ID (misal: atlas, clio, vulcan)."
)
async def lgp_subagent_get(subagent_id: str) -> dict:
    return await admin_backend.call_tool("lgp_subagent_get", {"subagent_id": subagent_id})

@mcp.tool(
    name="lgp_subagent_update_config",
    description="Memperbarui konfigurasi budget, trust level, atau status aktif subagent di registry."
)
async def lgp_subagent_update_config(
    subagent_id: str,
    max_usd: Optional[float] = None,
    max_tokens: Optional[int] = None,
    trust_level: Optional[str] = None,
    is_active: Optional[bool] = None
) -> dict:
    return await admin_backend.call_tool("lgp_subagent_update_config", {
        "subagent_id": subagent_id,
        "max_usd": max_usd,
        "max_tokens": max_tokens,
        "trust_level": trust_level,
        "is_active": is_active
    })

@mcp.tool(
    name="lgp_subagent_topology",
    description="Mendapatkan struktur topologi 4 Pod LGP v2.0 dan alur delegasi/handoff."
)
async def lgp_subagent_topology() -> dict:
    return await admin_backend.call_tool("lgp_subagent_topology", {})

@mcp.tool(
    name="lgp_circuit_breaker_reset",
    description="Mereset status Circuit Breaker untuk subagent yang dinonaktifkan akibat 3 kegagalan beruntun."
)
async def lgp_circuit_breaker_reset(subagent_id: str) -> dict:
    return await admin_backend.call_tool("lgp_circuit_breaker_reset", {"subagent_id": subagent_id})

@mcp.tool(
    name="lgp_run_create",
    description="Memicu eksekusi task baru melalui supervisor Atlas dengan alokasi budget dan context packet."
)
async def lgp_run_create(objective: str, subagents: Optional[List[str]] = None) -> dict:
    return await admin_backend.call_tool("lgp_run_create", {"objective": objective, "subagents": subagents})

@mcp.tool(
    name="lgp_run_get_state",
    description="Mendapatkan status eksekusi run, output delegates, dan ringkasan budget."
)
async def lgp_run_get_state(run_id: str) -> dict:
    return await admin_backend.call_tool("lgp_run_get_state", {"run_id": run_id})

@mcp.tool(
    name="lgp_run_list",
    description="Menampilkan daftar riwayat run yang telah dieksekusi di platform."
)
async def lgp_run_list(limit: Optional[int] = 20, status: Optional[str] = None) -> dict:
    return await admin_backend.call_tool("lgp_run_list", {"limit": limit, "status": status})

@mcp.tool(
    name="lgp_run_resume_hitl",
    description="Melanjutkan eksekusi yang diinterupsi oleh gerbang HITL (Human-in-the-Loop)."
)
async def lgp_run_resume_hitl(interrupt_id: str, approver: str, decision: str) -> dict:
    return await admin_backend.call_tool("lgp_run_resume_hitl", {
        "interrupt_id": interrupt_id,
        "approver": approver,
        "decision": decision
    })

@mcp.tool(
    name="lgp_memory_query",
    description="Kueri memori bi-temporal Graphiti L2 (fakta, subject, predicate, valid_at Tv, created_at Tk)."
)
async def lgp_memory_query(
    subject: Optional[str] = None,
    as_of_valid_time: Optional[float] = None,
    as_of_record_time: Optional[float] = None
) -> dict:
    return await admin_backend.call_tool("lgp_memory_query", {
        "subject": subject,
        "as_of_valid_time": as_of_valid_time,
        "as_of_record_time": as_of_record_time
    })

@mcp.tool(
    name="lgp_memory_store_fact",
    description="Menyimpan fakta bi-temporal baru ke dalam Long-Term Memory L2 dengan sanitasi PII otomatis."
)
async def lgp_memory_store_fact(
    subject: str,
    predicate: str,
    object: str,
    valid_at: Optional[float] = None,
    invalid_at: Optional[float] = None,
    episode_run_id: Optional[str] = None
) -> dict:
    return await admin_backend.call_tool("lgp_memory_store_fact", {
        "subject": subject,
        "predicate": predicate,
        "object": object,
        "valid_at": valid_at,
        "invalid_at": invalid_at,
        "episode_run_id": episode_run_id
    })

@mcp.tool(
    name="lgp_memory_invalidate_fact",
    description="Membatalkan/menonaktifkan fakta dalam memori temporal (mengisi invalid_at = timestamp saat ini)."
)
async def lgp_memory_invalidate_fact(fact_id: str) -> dict:
    return await admin_backend.call_tool("lgp_memory_invalidate_fact", {"fact_id": fact_id})

@mcp.tool(
    name="lgp_correlation_matrix",
    description="Mendapatkan matriks korelasi 10x10 antar-subagent (NPMI, handoff rate, success lift, composite weight)."
)
async def lgp_correlation_matrix() -> dict:
    return await admin_backend.call_tool("lgp_correlation_matrix", {})

@mcp.tool(
    name="lgp_correlation_setup",
    description="Mengonfigurasi bobot kalkulasi korelasi (alpha NPMI, beta success lift, gamma handoff rate) & threshold n_min."
)
async def lgp_correlation_setup(
    alpha: Optional[float] = 0.4,
    beta: Optional[float] = 0.4,
    gamma: Optional[float] = 0.2,
    n_min: Optional[int] = 50
) -> dict:
    return await admin_backend.call_tool("lgp_correlation_setup", {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "n_min": n_min
    })

@mcp.tool(
    name="lgp_telemetry_events_query",
    description="Membaca raw telemetri events L1 per run atau subagent."
)
async def lgp_telemetry_events_query(
    run_id: Optional[str] = None,
    subagent_id: Optional[str] = None,
    limit: Optional[int] = 50
) -> dict:
    return await admin_backend.call_tool("lgp_telemetry_events_query", {
        "run_id": run_id,
        "subagent_id": subagent_id,
        "limit": limit
    })

@mcp.tool(
    name="lgp_audit_query",
    description="Memeriksa catatan audit log append-only dengan verifikasi rantai hash SHA-256."
)
async def lgp_audit_query(limit: Optional[int] = 50) -> dict:
    return await admin_backend.call_tool("lgp_audit_query", {"limit": limit})

@mcp.tool(
    name="lgp_audit_verify",
    description="Memverifikasi integritas kriptografis seluruh rantai hash (hash chain SHA-256) audit log."
)
async def lgp_audit_verify() -> dict:
    return await admin_backend.call_tool("lgp_audit_verify", {})

@mcp.tool(
    name="lgp_platform_health",
    description="Mendapatkan status kesehatan platform, jumlah subagent aktif, mode storage, dan status supervisor."
)
async def lgp_platform_health() -> dict:
    return await admin_backend.call_tool("lgp_platform_health", {})

@mcp.tool(
    name="lgp_hitl_inbox_list",
    description="Melihat daftar interupsi Human-in-the-Loop (HITL) yang sedang pending atau telah selesai."
)
async def lgp_hitl_inbox_list(status: Optional[str] = "pending") -> dict:
    return await admin_backend.call_tool("lgp_hitl_inbox_list", {"status": status})

@mcp.tool(
    name="lgp_memory_organized_summary",
    description="Mendapatkan ringkasan memori yang telah dikurasi dan disortir berdasarkan taksonomi kategori."
)
async def lgp_memory_organized_summary() -> dict:
    return await admin_backend.call_tool("lgp_memory_organized_summary", {})

@mcp.tool(
    name="lgp_graphiti_neuron_graph",
    description="Mendapatkan graf neuron MiroFish Graphiti lengkap (node entitas fakta bi-temporal, relasi edge, dan bobot)."
)
async def lgp_graphiti_neuron_graph() -> dict:
    return await admin_backend.call_tool("lgp_graphiti_neuron_graph", {})

@mcp.tool(
    name="lgp_memory_seed",
    description="Memicu proses seeding fakta pengetahuan sistem secara otomatis ke dalam memori bi-temporal."
)
async def lgp_memory_seed() -> dict:
    return await admin_backend.call_tool("lgp_memory_seed", {})

@mcp.tool(
    name="lgp_api_request",
    description="Universal API Request: Mengeksekusi endpoint REST API LangGraph yang ada (GET, POST, PUT, DELETE) seperti /api/health, /api/runs, /api/subagents, dll."
)
async def lgp_api_request(
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None
) -> dict:
    return await admin_backend.call_tool("lgp_api_request", {
        "method": method,
        "endpoint": endpoint,
        "params": params,
        "body": body
    })

# Kanban Board Management Tools
@mcp.tool(
    name="lgp_kanban_list_boards",
    description="Menampilkan daftar seluruh Kanban board yang tersedia di platform."
)
async def lgp_kanban_list_boards() -> dict:
    return await admin_backend.call_tool("lgp_kanban_list_boards", {})

@mcp.tool(
    name="lgp_kanban_get_board",
    description="Mengambil detail lengkap Kanban board beserta semua kolom dan cards."
)
async def lgp_kanban_get_board(board_id: str) -> dict:
    return await admin_backend.call_tool("lgp_kanban_get_board", {"board_id": board_id})

@mcp.tool(
    name="lgp_kanban_create_board",
    description="Membuat Kanban board baru dengan kolom-kolom yang ditentukan."
)
async def lgp_kanban_create_board(
    name: str,
    columns: List[str]
) -> dict:
    columns_data = [{"name": col} for col in columns]
    return await admin_backend.call_tool("lgp_kanban_create_board", {
        "name": name,
        "columns": columns_data
    })

@mcp.tool(
    name="lgp_kanban_create_card",
    description="Membuat card baru di Kanban board pada kolom tertentu."
)
async def lgp_kanban_create_card(
    board_id: str,
    column_name: str,
    title: str,
    description: Optional[str] = "",
    priority: Optional[str] = "medium",
    assigned_to: Optional[str] = None
) -> dict:
    return await admin_backend.call_tool("lgp_kanban_create_card", {
        "board_id": board_id,
        "column_name": column_name,
        "title": title,
        "description": description,
        "priority": priority,
        "assigned_to": assigned_to
    })

@mcp.tool(
    name="lgp_kanban_move_card",
    description="Memindahkan card dari satu kolom ke kolom lain."
)
async def lgp_kanban_move_card(
    card_id: str,
    to_column_name: str
) -> dict:
    return await admin_backend.call_tool("lgp_kanban_move_card", {
        "card_id": card_id,
        "to_column_name": to_column_name
    })

# Matrix Configuration Management Tools
@mcp.tool(
    name="lgp_matrix_get_config",
    description="Mengambil konfigurasi matriks korelasi saat ini (alpha, beta, gamma, n_min, enabled status)."
)
async def lgp_matrix_get_config() -> dict:
    return await admin_backend.call_tool("lgp_matrix_get_config", {})

@mcp.tool(
    name="lgp_matrix_update_config",
    description="Memperbarui konfigurasi matriks korelasi untuk mengoptimalkan bobot perhitungan korelasi."
)
async def lgp_matrix_update_config(
    alpha: Optional[float] = None,
    beta: Optional[float] = None,
    gamma: Optional[float] = None,
    n_min: Optional[int] = None,
    enabled: Optional[bool] = None
) -> dict:
    return await admin_backend.call_tool("lgp_matrix_update_config", {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "n_min": n_min,
        "enabled": enabled
    })

@mcp.tool(
    name="lgp_matrix_recalculate",
    description="Memicu perhitungan ulang matriks korelasi 10x10 berdasarkan data telemetri terbaru."
)
async def lgp_matrix_recalculate() -> dict:
    return await admin_backend.call_tool("lgp_matrix_recalculate", {})

# Aliases for standard LangGraph MCP Memory protocol (mcp__langgraph-memory)
@mcp.tool(
    name="memory_recall",
    description="Recall / kueri fakta memori jangka panjang berdasarkan kata kunci atau subject."
)
async def memory_recall(
    query: Optional[str] = None,
    subject: Optional[str] = None,
    as_of_valid_time: Optional[float] = None,
    as_of_record_time: Optional[float] = None
) -> dict:
    sub = subject or query
    return await admin_backend.call_tool("lgp_memory_query", {
        "subject": sub,
        "as_of_valid_time": as_of_valid_time,
        "as_of_record_time": as_of_record_time
    })

@mcp.tool(
    name="memory_store",
    description="Simpan fakta atau preferensi ke memori jangka panjang bi-temporal."
)
async def memory_store(
    subject: Optional[str] = None,
    predicate: Optional[str] = None,
    object: Optional[str] = None,
    category: Optional[str] = None,
    key: Optional[str] = None,
    value: Optional[str] = None,
    valid_at: Optional[float] = None,
    invalid_at: Optional[float] = None,
    episode_run_id: Optional[str] = None
) -> dict:
    sub = subject
    if not sub and category:
        sub = f"{category}:{key}" if key else category
    pred = predicate or "has_value"
    obj = object or value or ""
    return await admin_backend.call_tool("lgp_memory_store_fact", {
        "subject": sub or "general",
        "predicate": pred,
        "object": obj,
        "valid_at": valid_at,
        "invalid_at": invalid_at,
        "episode_run_id": episode_run_id
    })

@mcp.tool(
    name="memory_forget",
    description="Nonaktifkan atau batalkan fakta memori jangka panjang berdasarkan fact_id."
)
async def memory_forget(fact_id: str) -> dict:
    return await admin_backend.call_tool("lgp_memory_invalidate_fact", {"fact_id": fact_id})

@mcp.tool(
    name="memory_list",
    description="Melihat ringkasan seluruh memori jangka panjang terstruktur."
)
async def memory_list() -> dict:
    return await admin_backend.call_tool("lgp_memory_organized_summary", {})

@mcp.tool(
    name="graph_query",
    description="Mendapatkan neuron graph dari knowledge graph memori."
)
async def graph_query(query: Optional[str] = None) -> dict:
    return await admin_backend.call_tool("lgp_graphiti_neuron_graph", {})

@mcp.tool(
    name="graph_stats",
    description="Mendapatkan statistik matriks korelasi dan graph."
)
async def graph_stats() -> dict:
    return await admin_backend.call_tool("lgp_correlation_matrix", {})

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enterprise LangGraph Platform Admin MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default=os.getenv("MCP_TRANSPORT", "stdio"))
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8787")))
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run("streamable-http", host=args.host, port=args.port)
    elif args.transport == "sse":
        mcp.run("sse", host=args.host, port=args.port)
    else:
        mcp.run("stdio")
