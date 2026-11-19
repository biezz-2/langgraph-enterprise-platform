import type { SystemHealth } from "@/types"

// Satu-satunya fallback yang diizinkan: state netral saat health API belum merespons.
// Semua data lain HARUS berasal dari backend — jangan tambahkan mock di sini.
export const FALLBACK_HEALTH: SystemHealth = {
  status: "unknown",
  version: "2.0.0",
  platform: "Enterprise LangGraph Platform (LGP v2.0)",
  subagents_active: 0,
  supervisor: "atlas",
  storage: "Unknown (offline)",
  mcp_admin: "unknown",
  uptime_s: 0,
  avg_latency_ms: 0,
  active_circuits_open: 0,
}
