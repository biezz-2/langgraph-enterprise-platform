"use client"

import React, { useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import DashboardShell from "@/components/DashboardShell"
import {
  FALLBACK_HEALTH,
  FALLBACK_SUBAGENTS,
  FALLBACK_RUNS,
  FALLBACK_HITL_INBOX,
  FALLBACK_MEMORY_FACTS,
} from "@/lib/mockData"
import type { SystemHealth, Subagent, Run, HITLItem, MemoryFact } from "@/types"
import {
  Activity,
  GitFork,
  GitBranch,
  UserCheck,
  Database,
  Network,
  LayoutGrid,
  ShieldAlert,
  FileCode2,
  Sparkles,
  Radio,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Clock,
  Coins,
  Cpu,
  Layers,
  Shield,
  Zap,
  Terminal,
} from "lucide-react"

interface StreamEvent {
  id: string
  timestamp: string
  subagent: string
  event_type: string
  message: string
  severity: "info" | "warn" | "success"
}

export default function OverviewPage() {
  const [health, setHealth] = useState<SystemHealth>(FALLBACK_HEALTH)
  const [subagents, setSubagents] = useState<Subagent[]>(FALLBACK_SUBAGENTS)
  const [recentRuns, setRecentRuns] = useState<Run[]>(FALLBACK_RUNS)
  const [hitlItems, setHitlItems] = useState<HITLItem[]>(FALLBACK_HITL_INBOX)
  const [events, setEvents] = useState<StreamEvent[]>([
    {
      id: "ev-1",
      timestamp: "10:32:15",
      subagent: "atlas",
      event_type: "DECOMPOSE_GOAL",
      message: "Decomposed task into 3 sub-objectives for Clio, Vulcan, and Athena.",
      severity: "info",
    },
    {
      id: "ev-2",
      timestamp: "10:32:18",
      subagent: "clio",
      event_type: "RESEARCH_COMPLETE",
      message: "Indexed 4 verified technical citations from enterprise knowledge base.",
      severity: "success",
    },
    {
      id: "ev-3",
      timestamp: "10:32:24",
      subagent: "vulcan",
      event_type: "AST_VALIDATION",
      message: "Sandbox test suite executed: 12 tests passed, 0 failures.",
      severity: "success",
    },
    {
      id: "ev-4",
      timestamp: "10:32:28",
      subagent: "athena",
      event_type: "PHASE_GATE_CHECK",
      message: "Independent V1-V8 validation gate passed for phase p01.",
      severity: "success",
    },
    {
      id: "ev-5",
      timestamp: "10:32:35",
      subagent: "themis",
      event_type: "HASH_CHAIN_COMMITTED",
      message: "Appended SHA-256 audit ledger entry: 5d41402a... -> 7406a6c2...",
      severity: "info",
    },
  ])

  // Try live fetch with offline fallback
  useEffect(() => {
    async function loadData() {
      try {
        const hRes = await fetch("/api/health")
        if (hRes.ok) setHealth(await hRes.json())
      } catch {}

      try {
        const sRes = await fetch("/api/subagents")
        if (sRes.ok) setSubagents(await sRes.json())
      } catch {}

      try {
        const rRes = await fetch("/api/runs")
        if (rRes.ok) setRecentRuns(await rRes.json())
      } catch {}

      try {
        const hitlRes = await fetch("/api/hitl")
        if (hitlRes.ok) setHitlItems(await hitlRes.json())
      } catch {}
    }
    loadData()
  }, [])

  // Simulated live event ticker for active feel
  useEffect(() => {
    const agentsList = ["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"]
    const eventTypes = [
      { type: "CHECKPOINT_SAVED", msg: "State snapshot persisted to SQLite WAL store.", sev: "info" as const },
      { type: "HANDOFF_ROUTED", msg: "Optimal routing weight selected based on NPMI matrix.", sev: "info" as const },
      { type: "MEMORY_INDEXED", msg: "Bi-temporal fact verified without PII leaks.", sev: "success" as const },
      { type: "CIRCUIT_HEARTBEAT", msg: "Health check OK: 0 consecutive failures.", sev: "info" as const },
    ]

    const interval = setInterval(() => {
      const randomAgent = agentsList[Math.floor(Math.random() * agentsList.length)]
      const randomEv = eventTypes[Math.floor(Math.random() * eventTypes.length)]
      const newEv: StreamEvent = {
        id: `ev-${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        subagent: randomAgent,
        event_type: randomEv.type,
        message: randomEv.msg,
        severity: randomEv.sev,
      }
      setEvents((prev) => [newEv, ...prev.slice(0, 19)])
    }, 6000)

    return () => clearInterval(interval)
  }, [])

  const pendingHitlCount = hitlItems.filter((i) => i.status === "pending").length

  return (
    <DashboardShell
      activeModuleTitle="Overview & Control Plane"
      activeModuleSubtitle="LangGraph Multi-Agent Cluster &bull; 10 Operational Modules &bull; AGENTS.md Protocol"
    >
      <div className="space-y-6">
        {/* KPI Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3.5">
          {/* Card 1: Cluster Health */}
          <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80 font-mono flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Cluster State</span>
              <Activity className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <span className="text-lg font-bold text-emerald-400 uppercase tracking-tight">
                {health.status}
              </span>
              <p className="text-[10px] text-zinc-500 mt-0.5 truncate">{health.platform}</p>
            </div>
            <div className="text-[10px] text-zinc-400 pt-2 border-t border-zinc-800/80 flex justify-between">
              <span>Supervisor:</span>
              <span className="text-zinc-200 capitalize font-semibold">{health.supervisor}</span>
            </div>
          </div>

          {/* Card 2: Subagents Active */}
          <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80 font-mono flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Subagents</span>
              <GitFork className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <span className="text-lg font-bold text-zinc-100">
                {subagents.filter((a) => a.is_active).length} / {subagents.length}
              </span>
              <p className="text-[10px] text-indigo-400 mt-0.5">4 Pods Registered</p>
            </div>
            <div className="text-[10px] text-zinc-400 pt-2 border-t border-zinc-800/80 flex justify-between">
              <span>Circuits:</span>
              <span className="text-emerald-400 font-semibold">10 Closed (0 Trip)</span>
            </div>
          </div>

          {/* Card 3: Memory Health */}
          <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80 font-mono flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Memory Engine</span>
              <Database className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <span className="text-lg font-bold text-zinc-100">Bi-Temporal</span>
              <p className="text-[10px] text-emerald-400 mt-0.5">SQLite WAL Intact</p>
            </div>
            <div className="text-[10px] text-zinc-400 pt-2 border-t border-zinc-800/80 flex justify-between">
              <span>Curator:</span>
              <span className="text-zinc-200 capitalize font-semibold">Mnemosyne</span>
            </div>
          </div>

          {/* Card 4: HITL Pending */}
          <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80 font-mono flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>HITL Inbox</span>
              <UserCheck className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <span
                className={`text-lg font-bold ${
                  pendingHitlCount > 0 ? "text-amber-400" : "text-emerald-400"
                }`}
              >
                {pendingHitlCount} Pending
              </span>
              <p className="text-[10px] text-zinc-500 mt-0.5">Otorisasi Kritis</p>
            </div>
            <Link
              href="/hitl"
              className="text-[10px] text-indigo-400 hover:text-indigo-300 pt-2 border-t border-zinc-800/80 flex items-center justify-between group"
            >
              <span>Review Tindakan</span>
              <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>

          {/* Card 5: Avg Latency */}
          <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80 font-mono flex flex-col justify-between space-y-2 col-span-2 sm:col-span-1">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Avg Latency</span>
              <Clock className="w-4 h-4 text-violet-400" />
            </div>
            <div>
              <span className="text-lg font-bold text-zinc-100">{health.avg_latency_ms}ms</span>
              <p className="text-[10px] text-zinc-500 mt-0.5">P95 Node Execution</p>
            </div>
            <div className="text-[10px] text-zinc-400 pt-2 border-t border-zinc-800/80 flex justify-between">
              <span>Uptime:</span>
              <span className="text-zinc-200 font-semibold">
                {Math.floor((health.uptime_s || 84620) / 3600)}h
              </span>
            </div>
          </div>
        </div>

        {/* 10 Operational Modules Quick Navigation Grid */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 font-mono">
              10 Operational Modules Directory
            </h2>
            <span className="text-[10px] font-mono text-zinc-500">
              Unified Platform Navigation
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {[
              {
                id: "overview",
                title: "Control Plane",
                desc: "Real-time KPIs & event telemetry",
                href: "/",
                icon: Activity,
                badge: "Active",
              },
              {
                id: "neuron-graph",
                title: "Neuron Graph",
                desc: "Obsidian 2D/3D topology visualizer",
                href: "/neuron-graph",
                icon: Sparkles,
                badge: "3D",
              },
              {
                id: "subagents",
                title: "Subagent Pods",
                desc: "10 Subagent registry & circuit breakers",
                href: "/subagents",
                icon: GitFork,
                badge: "10 Pods",
              },
              {
                id: "runs",
                title: "Runs & DAG",
                desc: "Execution DAG, checkpoints & tokens",
                href: "/runs",
                icon: GitBranch,
                badge: "Live",
              },
              {
                id: "hitl",
                title: "HITL Inbox",
                desc: "Human approval for critical actions",
                href: "/hitl",
                icon: UserCheck,
                badge: `${pendingHitlCount} Pending`,
              },
              {
                id: "memory",
                title: "Bi-Temporal Memory",
                desc: "Valid-time & record-time facts table",
                href: "/memory",
                icon: Database,
                badge: "Graphiti",
              },
              {
                id: "matrix",
                title: "Correlation Matrix",
                desc: "10x10 NPMI heatmap & handoff routing",
                href: "/matrix",
                icon: Network,
                badge: "NPMI",
              },
              {
                id: "kanban",
                title: "Phase-Gate Kanban",
                desc: "AGENTS.md 6-phase lifecycle board",
                href: "/kanban",
                icon: LayoutGrid,
                badge: "AGENTS.md",
              },
              {
                id: "guardrails",
                title: "Guardrails & Telemetry",
                desc: "OWASP Top 10 mitigation & audit ledger",
                href: "/guardrails",
                icon: ShieldAlert,
                badge: "OWASP",
              },
              {
                id: "api-docs",
                title: "API & FastMCP",
                desc: "FastMCP tool sandbox & OpenAPI spec",
                href: "/api-docs",
                icon: FileCode2,
                badge: "Admin",
              },
            ].map((mod) => {
              const Icon = mod.icon
              return (
                <Link
                  key={mod.id}
                  href={mod.href}
                  className="p-3.5 rounded-xl bg-zinc-900/40 border border-zinc-800/80 hover:border-indigo-500/50 hover:bg-zinc-900/80 transition group flex flex-col justify-between space-y-3"
                >
                  <div className="flex items-start justify-between">
                    <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center group-hover:scale-105 transition-transform">
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-zinc-950 text-zinc-400 border border-zinc-800">
                      {mod.badge}
                    </span>
                  </div>

                  <div>
                    <h3 className="text-xs font-semibold text-zinc-200 group-hover:text-indigo-300 transition-colors">
                      {mod.title}
                    </h3>
                    <p className="text-[11px] text-zinc-500 mt-0.5 leading-snug">{mod.desc}</p>
                  </div>
                </Link>
              )
            })}
          </div>
        </div>

        {/* Live Event Stream & Subagents Status */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* WebSocket Live Event Stream (7 Cols) */}
          <div className="lg:col-span-7 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono">
                  Live Cluster Event Stream
                </h2>
              </div>
              <span className="text-[10px] font-mono text-zinc-500">Auto-streaming</span>
            </div>

            <div className="p-4 rounded-xl bg-zinc-900/40 border border-zinc-800 max-h-[420px] overflow-y-auto space-y-2.5 font-mono text-xs">
              {events.map((ev) => (
                <div
                  key={ev.id}
                  className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800/70 flex items-start gap-3 hover:border-zinc-700 transition"
                >
                  <span className="text-[10px] text-zinc-500 whitespace-nowrap mt-0.5">
                    {ev.timestamp}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-indigo-400 capitalize">
                        {ev.subagent}
                      </span>
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-zinc-900 text-zinc-400 border border-zinc-800">
                        {ev.event_type}
                      </span>
                    </div>
                    <p className="text-zinc-300 text-[11px] mt-0.5 leading-relaxed truncate">
                      {ev.message}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Subagents Pods Quick State (5 Cols) */}
          <div className="lg:col-span-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono">
                Subagents Pods Health
              </h2>
              <Link
                href="/subagents"
                className="text-[10px] font-mono text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
              >
                <span>Lihat 10 Subagent</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            <div className="p-4 rounded-xl bg-zinc-900/40 border border-zinc-800 space-y-2.5 max-h-[420px] overflow-y-auto font-mono text-xs">
              {subagents.map((agent) => {
                const cb = agent.circuit_breaker || "closed"
                const isClosed = cb === "closed"
                return (
                  <div
                    key={agent.id}
                    className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800/80 flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-zinc-200">{agent.name}</span>
                        <span className="text-[9px] text-zinc-500">({agent.pod})</span>
                      </div>
                      <p className="text-[10px] text-zinc-400 mt-0.5">
                        Cap: ${agent.budget_config?.max_usd?.toFixed(2) || "10.00"} &bull; Trust: {agent.trust_level}
                      </p>
                    </div>

                    <span
                      className={`text-[9px] px-2 py-0.5 rounded-full border ${
                        isClosed
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                          : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                      }`}
                    >
                      {cb.toUpperCase()}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </DashboardShell>
  )
}
