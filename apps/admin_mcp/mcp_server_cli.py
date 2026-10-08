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

if __name__ == "__main__":
    mcp.run("stdio")
