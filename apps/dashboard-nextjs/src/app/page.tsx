"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import {
  Activity,
  GitFork,
  LayoutGrid,
  Network,
  Database,
  ScrollText,
  Shield,
  Server,
  Cpu,
  ChevronDown,
  ChevronRight,
  Circle,
  RefreshCw,
  AlertCircle,
  FileCode2,
  ExternalLink,
  Sparkles,
} from "lucide-react"
import KanbanBoard from "@/components/KanbanBoard"
import MatrixManagement from "@/components/MatrixManagement"
import NeuronGraph from "@/components/NeuronGraph"
import { Button } from "@/components/ui/button"
import type { SystemHealth, Subagent, MemoryFact, AuditLogEntry } from "@/types"

const TABS = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "kanban", label: "Kanban Board", icon: LayoutGrid },
  { id: "matrix", label: "Correlation Matrix", icon: Network },
  { id: "neuron-graph", label: "3D Neuron Graph", icon: Sparkles },
  { id: "agents", label: "Subagent Registry", icon: GitFork },
  { id: "memory", label: "Memory & Audit", icon: Database },
  { id: "api-docs", label: "API Docs", icon: FileCode2 },
] as const

type TabId = (typeof TABS)[number]["id"]

const POD_COLORS: Record<string, string> = {
  "Koordinasi": "bg-amber-500/20 text-amber-300 border-amber-500/30",
  "Riset & Rekayasa": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  "Platform": "bg-blue-500/20 text-blue-300 border-blue-500/30",
  "Tata Kelola": "bg-violet-500/20 text-violet-300 border-violet-500/30",
}

const TRUST_BADGE: Record<string, string> = {
  High: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  "Medium-High": "bg-amber-500/15 text-amber-400 border-amber-500/30",
  Medium: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  Low: "bg-zinc-700 text-zinc-400 border-zinc-600",
  "Low-Medium": "bg-zinc-700 text-zinc-400 border-zinc-600",
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("overview")
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [agents, setAgents] = useState<Subagent[]>([])
  const [facts, setFacts] = useState<MemoryFact[]>([])
  const [audit, setAudit] = useState<AuditLogEntry[]>([])
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null)
  const [loadingFacts, setLoadingFacts] = useState(false)
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("disconnected")
  const [wsLog, setWsLog] = useState<string[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/health")
      if (res.ok) setHealth(await res.json())
    } catch {
      // API offline
    }
  }, [])

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch("/api/subagents")
      if (res.ok) {
        const data = await res.json()
        setAgents(Array.isArray(data.subagents) ? data.subagents : [])
      }
    } catch {
      // Fallback empty
    }
  }, [])

  const fetchMemory = useCallback(async () => {
    if (facts.length > 0) return
    setLoadingFacts(true)
    try {
      const [factRes, auditRes] = await Promise.all([
        fetch("/api/memory/temporal"),
        fetch("/api/audit"),
      ])
      if (factRes.ok) {
        const data = await factRes.json()
        setFacts(Array.isArray(data) ? data.slice(0, 50) : [])
      }
      if (auditRes.ok) {
        const aData = await auditRes.json()
        setAudit(Array.isArray(aData) ? aData.slice(0, 30) : [])
      }
    } catch {
      // Error
    } finally {
      setLoadingFacts(false)
    }
  }, [facts.length])

  const connectWebSocket = useCallback(() => {
    if (wsRef.current) {
      try {
        wsRef.current.close()
      } catch {}
    }
    setWsStatus("connecting")
    const protocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:"
    const host = typeof window !== "undefined" ? window.location.hostname || "localhost" : "localhost"
    const wsUrl = `${protocol}//${host}:8000/ws/dashboard`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setWsStatus("connected")
        const line = `[${new Date().toLocaleTimeString()}] WebSocket connected to ${wsUrl}`
        setWsLog((prev) => [line, ...prev].slice(0, 50))
      }

      ws.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          if (payload.type === "platform_event") {
            const line = `[${new Date().toLocaleTimeString()}] ${payload.event || "event"}: ${JSON.stringify(payload.data || {}).slice(0, 80)}`
            setWsLog((prev) => [line, ...prev].slice(0, 50))
          } else if (payload.type === "handshake") {
            const line = `[${new Date().toLocaleTimeString()}] WebSocket Online: ${payload.server}`
            setWsLog((prev) => [line, ...prev].slice(0, 50))
          }
        } catch {
          // ignore non-json
        }
      }

      ws.onerror = () => {
        setWsStatus("disconnected")
      }

      ws.onclose = () => {
        setWsStatus("disconnected")
      }
    } catch {
      setWsStatus("disconnected")
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    fetchAgents()
    connectWebSocket()
    const interval = setInterval(fetchHealth, 30000)
    return () => {
      clearInterval(interval)
      wsRef.current?.close()
    }
  }, [fetchHealth, fetchAgents, connectWebSocket])

  useEffect(() => {
    if (activeTab === "memory") fetchMemory()
  }, [activeTab, fetchMemory])

  const formatTimestamp = (ts: number | string | undefined | null) => {
    if (!ts) return "N/A"
    const d = typeof ts === "number" ? new Date(ts * (ts < 1e12 ? 1000 : 1)) : new Date(ts)
    return d.toLocaleString("en-GB", { dateStyle: "short", timeStyle: "medium" })
  }

  const parseJson = (str: string | unknown): string => {
    if (!str) return ""
    if (typeof str === "string") {
      try {
        const p = JSON.parse(str)
        return Array.isArray(p) ? p.join(", ") : JSON.stringify(p)
      } catch {
        return str
      }
    }
    return JSON.stringify(str)
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-zinc-100 text-zinc-950 font-bold text-xs flex items-center justify-center tracking-tight shadow-sm">
              LG
            </div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold tracking-tight text-zinc-100">
                Enterprise LangGraph Platform
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-900 text-zinc-400 font-mono border border-zinc-800">
                v2.0
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* WebSocket Status */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono border ${
                wsStatus === "connected"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : wsStatus === "connecting"
                  ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  : "bg-zinc-900 text-zinc-500 border-zinc-800"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  wsStatus === "connected"
                    ? "bg-emerald-400 animate-pulse"
                    : wsStatus === "connecting"
                    ? "bg-amber-400 animate-pulse"
                    : "bg-zinc-500"
                }`}
              />
              {wsStatus === "connected" ? "WebSocket Active" : wsStatus === "connecting" ? "WS Connecting" : "WS Offline"}
            </span>

            {/* Health badge */}
            {health && (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono bg-zinc-900 text-emerald-400 border border-zinc-800">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                {health.subagents_active} Active
              </span>
            )}

            <button
              onClick={() => setActiveTab("api-docs")}
              className="text-xs text-zinc-400 hover:text-zinc-100 px-2.5 py-1 rounded-md border border-zinc-800 hover:bg-zinc-900 transition flex items-center gap-1.5"
            >
              <FileCode2 className="w-3.5 h-3.5 text-indigo-400" />
              API Docs
            </button>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full pt-4">
        <div className="flex gap-1 border-b border-zinc-800/80 overflow-x-auto">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 pb-3 text-xs font-medium whitespace-nowrap transition-colors border-b-2 ${
                activeTab === id
                  ? "text-zinc-100 border-zinc-100"
                  : "text-zinc-400 border-transparent hover:text-zinc-200"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full">
        {/* TAB: Overview */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* System Status Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                {
                  label: "Active Subagents",
                  value: health?.subagents_active != null ? `${health.subagents_active} / 10` : "—",
                  sub: "4 Pods",
                  icon: Cpu,
                  color: "text-emerald-400",
                },
                {
                  label: "Platform Status",
                  value: health?.status === "healthy" ? "Healthy" : health ? "Degraded" : "Loading",
                  sub: health?.supervisor ? `Supervisor: ${health.supervisor}` : "Connecting...",
                  icon: Activity,
                  color: health?.status === "healthy" ? "text-emerald-400" : "text-amber-400",
                },
                {
                  label: "Storage",
                  value: "SQLite WAL",
                  sub: health?.storage?.includes("Enterprise") ? "Enterprise Ready" : "Active",
                  icon: Database,
                  color: "text-blue-400",
                },
                {
                  label: "MCP Admin",
                  value: health?.mcp_admin === "active" ? "Active" : "—",
                  sub: "Port :8787",
                  icon: Server,
                  color: "text-violet-400",
                },
              ].map(({ label, value, sub, icon: Icon, color }) => (
                <div
                  key={label}
                  className="bg-zinc-900/40 border border-zinc-800/80 p-4 rounded-lg flex flex-col gap-1"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] uppercase tracking-wider font-semibold text-zinc-400">
                      {label}
                    </p>
                    <Icon className={`w-4 h-4 ${color}`} />
                  </div>
                  <p className="text-xl font-semibold text-zinc-100">{value}</p>
                  <p className="text-xs text-zinc-500 font-mono">{sub}</p>
                </div>
              ))}
            </div>

            {/* Architecture Overview */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-5">
                <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
                  <Shield className="w-3.5 h-3.5 text-violet-400" />
                  Platform Architecture
                </h3>
                <dl className="space-y-2 text-xs font-mono">
                  {[
                    { k: "Supervision Pattern", v: "Hierarchical (Atlas Supervisor)" },
                    { k: "Context Protocol", v: "ContextPacket v2.0" },
                    { k: "Hard Stop Budget", v: "$15.00 USD / run" },
                    { k: "Isolation Level", v: "Least Privilege (Tool Grants)" },
                    { k: "Circuit Breaker", v: "3x consecutive fail → open" },
                    { k: "Memory Engine", v: "Bi-temporal SQLite + Graphiti" },
                    { k: "HITL Mechanism", v: "Interrupt on trust escalation" },
                    { k: "Schema Isolation", v: "Supabase schema: langgraph" },
                  ].map(({ k, v }) => (
                    <div key={k} className="flex justify-between gap-4">
                      <dt className="text-zinc-500 flex-shrink-0">{k}</dt>
                      <dd className="text-zinc-300 text-right">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              {/* Live WebSocket Feed */}
              <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-5 flex flex-col">
                <div className="flex items-center justify-between pb-3 border-b border-zinc-800/60 mb-3">
                  <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Live Telemetry Stream (WebSocket)
                  </h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={connectWebSocket}
                    className="text-[10px] h-6 px-2 text-zinc-500 hover:text-zinc-200"
                  >
                    <RefreshCw className="w-3 h-3 mr-1" />
                    Reconnect
                  </Button>
                </div>
                <div className="flex-1 overflow-y-auto font-mono text-[10px] space-y-1 min-h-32 max-h-56">
                  {wsLog.length === 0 ? (
                    <p className="text-zinc-600 italic">Awaiting platform events via WebSocket...</p>
                  ) : (
                    wsLog.map((line, i) => (
                      <p key={i} className="text-zinc-400 leading-relaxed">
                        {line}
                      </p>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB: Kanban Board */}
        {activeTab === "kanban" && (
          <div>
            <KanbanBoard />
          </div>
        )}

        {/* TAB: Correlation Matrix */}
        {activeTab === "matrix" && (
          <div>
            <MatrixManagement />
          </div>
        )}

        {/* TAB: Neuron Graph */}
        {activeTab === "neuron-graph" && (
          <div className="h-[calc(100vh-240px)]">
            <NeuronGraph />
          </div>
        )}

        {/* TAB: Subagent Registry */}
        {activeTab === "agents" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                  <GitFork className="w-4 h-4 text-emerald-400" />
                  Subagent Registry
                </h2>
                <p className="text-xs text-zinc-400 mt-1">
                  {agents.length} subagents across 4 pods. Click a card to expand capabilities.
                </p>
              </div>
            </div>

            {agents.length === 0 ? (
              <div className="text-center py-16 text-zinc-500 text-xs font-mono">
                <AlertCircle className="w-5 h-5 mx-auto mb-2 text-zinc-600" />
                No subagents returned. Check API connectivity at localhost:8000.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {agents.map((agent) => {
                  const isExpanded = expandedAgent === agent.id
                  const podStyle = POD_COLORS[agent.pod] || "bg-zinc-800 text-zinc-300 border-zinc-700"
                  const trustStyle = TRUST_BADGE[agent.trust_level] || "bg-zinc-700 text-zinc-400 border-zinc-600"
                  const caps = Array.isArray(agent.capabilities)
                    ? agent.capabilities
                    : JSON.parse(agent.capabilities as unknown as string || "[]")

                  return (
                    <div
                      key={agent.id}
                      className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-4 space-y-3 hover:border-zinc-700/60 transition"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Circle
                            className={`w-2.5 h-2.5 flex-shrink-0 ${
                              agent.is_active ? "fill-emerald-400 text-emerald-400" : "fill-zinc-600 text-zinc-600"
                            }`}
                          />
                          <div>
                            <h3 className="text-xs font-semibold text-zinc-100 font-mono">{agent.id}</h3>
                            <p className="text-[10px] text-zinc-400">{agent.name}</p>
                          </div>
                        </div>
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded border font-mono uppercase ${trustStyle}`}
                        >
                          {agent.trust_level}
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-1.5">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono ${podStyle}`}>
                          {agent.pod}
                        </span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded border font-mono bg-zinc-800 text-zinc-400 border-zinc-700">
                          v{agent.version || "2.0.0"}
                        </span>
                      </div>

                      <div className="text-[10px] font-mono text-zinc-500">
                        <span className="text-zinc-600">Model: </span>
                        <span className="text-zinc-300">{agent.model_policy || "—"}</span>
                      </div>

                      <button
                        className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-200 transition"
                        onClick={() => setExpandedAgent(isExpanded ? null : agent.id)}
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                        {caps.length} capabilities
                      </button>

                      {isExpanded && (
                        <ul className="pt-2 border-t border-zinc-800/60 space-y-1">
                          {caps.map((cap: string, i: number) => (
                            <li
                              key={i}
                              className="text-[10px] text-zinc-400 font-mono flex gap-1.5 items-start"
                            >
                              <span className="text-emerald-500/70 mt-0.5">·</span>
                              {cap}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB: Memory & Audit */}
        {activeTab === "memory" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {/* Temporal Facts */}
              <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-5">
                <div className="flex items-center justify-between pb-3 border-b border-zinc-800/60 mb-4">
                  <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
                    <Database className="w-3.5 h-3.5 text-blue-400" />
                    Temporal Facts
                  </h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setFacts([]); fetchMemory() }}
                    className="text-[10px] h-6 px-2 text-zinc-500"
                  >
                    <RefreshCw className="w-3 h-3 mr-1" />
                    Refresh
                  </Button>
                </div>

                {loadingFacts ? (
                  <div className="text-center py-10 text-xs font-mono text-zinc-500">
                    Querying temporal memory store...
                  </div>
                ) : facts.length === 0 ? (
                  <p className="text-xs text-zinc-500 font-mono text-center py-8">
                    No facts in memory store.
                  </p>
                ) : (
                  <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                    {facts.map((fact) => (
                      <div
                        key={fact.fact_id}
                        className="text-[11px] font-mono bg-zinc-950/80 border border-zinc-800/80 rounded-md p-3"
                      >
                        <div className="flex items-start justify-between gap-2 mb-1.5">
                          <span className="text-zinc-300 font-medium">
                            {fact.subject}
                          </span>
                          {fact.invalid_at ? (
                            <span className="text-[9px] px-1.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 whitespace-nowrap">
                              Invalidated
                            </span>
                          ) : (
                            <span className="text-[9px] px-1.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 whitespace-nowrap">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-zinc-400">
                          <span className="text-zinc-500">{fact.predicate}</span>{" "}
                          &rarr; {fact.object.slice(0, 120)}{fact.object.length > 120 ? "..." : ""}
                        </p>
                        <div className="mt-2 text-zinc-600 text-[9px] flex items-center gap-2">
                          <span>Valid: {formatTimestamp(fact.valid_at)}</span>
                          {fact.episode_run_id && (
                            <>
                              <span>·</span>
                              <span>Run: {fact.episode_run_id}</span>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Audit Log */}
              <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-5">
                <div className="flex items-center justify-between pb-3 border-b border-zinc-800/60 mb-4">
                  <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
                    <ScrollText className="w-3.5 h-3.5 text-violet-400" />
                    Recent Audit Log
                  </h3>
                  <span className="text-[10px] font-mono text-zinc-500">{audit.length} entries</span>
                </div>

                {audit.length === 0 ? (
                  <p className="text-xs text-zinc-500 font-mono text-center py-8">
                    No audit log entries loaded.
                  </p>
                ) : (
                  <div className="space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
                    {audit.map((entry) => {
                      const statusColor =
                        entry.result_status === "success"
                          ? "text-emerald-400"
                          : entry.result_status === "failed"
                          ? "text-rose-400"
                          : "text-zinc-400"

                      return (
                        <div
                          key={entry.log_id}
                          className="text-[10px] font-mono bg-zinc-950/80 border border-zinc-800/80 rounded-md p-2.5 flex items-start gap-2"
                        >
                          <span className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusColor}`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-zinc-300 truncate">
                                <span className="text-zinc-500">[{entry.actor}]</span>{" "}
                                {entry.action}
                              </span>
                              <span className="text-zinc-600 whitespace-nowrap text-[9px]">
                                {formatTimestamp(entry.created_at)}
                              </span>
                            </div>
                            <div className="text-zinc-600 text-[9px] mt-0.5 truncate">
                              Scope: {entry.scope}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB: API Docs (Embedded Swagger UI) */}
        {activeTab === "api-docs" && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-3 sm:px-5">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
                  <FileCode2 className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-xs font-semibold text-zinc-100 flex items-center gap-2">
                    FastAPI OpenAPI Specification & Swagger Explorer
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-400 border border-zinc-700 font-mono">
                      v2.0.0
                    </span>
                  </h2>
                  <p className="text-[10px] text-zinc-400 font-mono">
                    Gateway URL: http://192.168.101.39:8000/docs &bull; WebSocket: /ws/dashboard
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href="/openapi.json"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
                >
                  Raw openapi.json
                </a>
                <a
                  href="http://192.168.101.39:8000/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-[11px] font-mono px-3 py-1.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 transition font-medium"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Direct Swagger Window
                </a>
              </div>
            </div>

            <div className="w-full h-[calc(100vh-220px)] min-h-[600px] rounded-xl border border-zinc-800/80 overflow-hidden bg-white shadow-2xl">
              <iframe
                src="/docs"
                title="LGP v2.0 API Swagger Documentation"
                className="w-full h-full border-0"
              />
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800/80 text-center py-3">
        <p className="text-[10px] text-zinc-600 font-mono">
          Enterprise LangGraph Platform v2.0 &mdash; Supabase schema: <span className="text-zinc-500">langgraph</span> &mdash; SQLite WAL Mode
        </p>
      </footer>
    </div>
  )
}
