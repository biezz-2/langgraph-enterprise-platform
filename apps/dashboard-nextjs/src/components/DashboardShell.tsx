"use client"

import React, { useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Activity,
  Sparkles,
  GitFork,
  GitBranch,
  UserCheck,
  Database,
  Network,
  LayoutGrid,
  ShieldAlert,
  FileCode2,
  Menu,
  X,
  RefreshCw,
  Bell,
  Cpu,
  Layers,
  ChevronRight,
  Radio,
  ExternalLink,
} from "lucide-react"
import { FALLBACK_HEALTH, FALLBACK_HITL_INBOX } from "@/lib/mockData"
import type { SystemHealth } from "@/types"

export interface NavItem {
  id: string
  label: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  badge?: string | number
  badgeColor?: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview & Control", href: "/", icon: Activity },
  { id: "neuron-graph", label: "3D Neuron Graph", href: "/neuron-graph", icon: Sparkles, badge: "3D" },
  { id: "subagents", label: "Subagent Registry", href: "/subagents", icon: GitFork, badge: "10" },
  { id: "runs", label: "Runs & Execution DAG", href: "/runs", icon: GitBranch },
  { id: "hitl", label: "HITL Inbox", href: "/hitl", icon: UserCheck, badge: 3, badgeColor: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  { id: "memory", label: "Bi-Temporal Memory", href: "/memory", icon: Database },
  { id: "matrix", label: "Correlation Matrix", href: "/matrix", icon: Network, badge: "NPMI" },
  { id: "kanban", label: "Phase-Gate Kanban", href: "/kanban", icon: LayoutGrid, badge: "AGENTS" },
  { id: "guardrails", label: "Guardrails & Telemetry", href: "/guardrails", icon: ShieldAlert, badge: "OWASP" },
  { id: "api-docs", label: "API & FastMCP Explorer", href: "/api-docs", icon: FileCode2 },
]

export default function DashboardShell({
  children,
  activeModuleTitle,
  activeModuleSubtitle,
  actions,
}: {
  children: React.ReactNode
  activeModuleTitle?: string
  activeModuleSubtitle?: string
  actions?: React.ReactNode
}) {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [health, setHealth] = useState<SystemHealth>(FALLBACK_HEALTH)
  const [backendOnline, setBackendOnline] = useState<boolean>(false)
  const [wsStatus, setWsStatus] = useState<"connected" | "connecting" | "offline">("offline")
  const [pendingHITLCount, setPendingHITLCount] = useState<number>(3)
  const wsRef = useRef<WebSocket | null>(null)

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/health")
      if (res.ok) {
        const data = await res.json()
        setHealth(data)
        setBackendOnline(true)
      } else {
        setBackendOnline(false)
      }
    } catch {
      setBackendOnline(false)
    }
  }, [])

  const connectWS = useCallback(() => {
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
        setBackendOnline(true)
      }
      ws.onerror = () => {
        setWsStatus("offline")
      }
      ws.onclose = () => {
        setWsStatus("offline")
      }
    } catch {
      setWsStatus("offline")
    }
  }, [])

  useEffect(() => {
    checkHealth()
    connectWS()
    const interval = setInterval(checkHealth, 30000)
    return () => {
      clearInterval(interval)
      wsRef.current?.close()
    }
  }, [checkHealth, connectWS])

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col antialiased selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Top Header */}
      <header className="sticky top-0 z-50 border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md">
        <div className="w-full px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {/* Mobile menu button */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 border border-zinc-800"
              aria-label="Toggle navigation"
            >
              {sidebarOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>

            {/* Platform Brand */}
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-700 text-white font-black text-xs flex items-center justify-center tracking-tight shadow-md shadow-indigo-500/20 group-hover:scale-105 transition-transform">
                LG
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs sm:text-sm font-semibold tracking-tight text-zinc-100">
                    Enterprise LangGraph
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-900 text-indigo-400 font-mono border border-indigo-500/30 font-medium">
                    v2.0
                  </span>
                </div>
                <p className="text-[10px] text-zinc-500 font-mono hidden sm:block">
                  Control Plane &bull; 10 Subagents &bull; AGENTS.md
                </p>
              </div>
            </Link>
          </div>

          {/* Header Status Indicators */}
          <div className="flex items-center gap-2 sm:gap-3">
            {/* WebSocket status */}
            <span
              className={`inline-flex items-center gap-1.5 px-2 sm:px-2.5 py-0.5 rounded-full text-[10px] font-mono border transition-colors ${
                wsStatus === "connected"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : wsStatus === "connecting"
                  ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  : "bg-zinc-900 text-zinc-400 border-zinc-800"
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
              <span className="hidden sm:inline">
                {wsStatus === "connected" ? "Live WS Stream" : wsStatus === "connecting" ? "WS Connecting" : "WS Emulated"}
              </span>
              <span className="sm:hidden font-mono">
                {wsStatus === "connected" ? "WS Live" : "WS Off"}
              </span>
            </span>

            {/* Backend connectivity indicator */}
            <span
              className={`inline-flex items-center gap-1.5 px-2 sm:px-2.5 py-0.5 rounded-full text-[10px] font-mono border ${
                backendOnline
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : "bg-indigo-500/10 text-indigo-300 border-indigo-500/30"
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${backendOnline ? "bg-emerald-400" : "bg-indigo-400"}`} />
              <span className="hidden sm:inline">
                {backendOnline ? "API Online :8000" : "Offline Fallback"}
              </span>
              <span className="sm:hidden">
                {backendOnline ? "API" : "Local"}
              </span>
            </span>

            {/* HITL Pending Badge */}
            <Link
              href="/hitl"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 transition"
              title="Human-in-the-Loop Pending Approvals"
            >
              <Bell className="w-3 h-3 text-amber-400 animate-bounce" />
              <span>{pendingHITLCount}</span>
              <span className="hidden md:inline text-[10px] text-amber-400/80">Pending</span>
            </Link>

            {/* Quick API Docs Button */}
            <Link
              href="/api-docs"
              className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono text-zinc-400 hover:text-zinc-100 border border-zinc-800 hover:bg-zinc-900 transition"
            >
              <FileCode2 className="w-3.5 h-3.5 text-indigo-400" />
              <span>FastMCP</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Container with Sidebar + Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar Navigation */}
        <aside
          className={`fixed inset-y-0 left-0 z-40 w-64 bg-zinc-950 border-r border-zinc-800/80 pt-16 flex flex-col transition-transform duration-200 lg:static lg:pt-0 lg:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {/* Sidebar Nav Items */}
          <div className="p-3 space-y-1 overflow-y-auto flex-1">
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider font-semibold text-zinc-500 font-mono">
              Operational Modules
            </div>

            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href))

              return (
                <Link
                  key={item.id}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all group ${
                    isActive
                      ? "bg-indigo-600/15 text-indigo-200 border border-indigo-500/30 font-semibold shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/70 border border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2.5 truncate">
                    <Icon
                      className={`w-4 h-4 flex-shrink-0 transition-colors ${
                        isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-300"
                      }`}
                    />
                    <span className="truncate">{item.label}</span>
                  </div>

                  {item.badge && (
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded border font-mono ${
                        item.badgeColor ||
                        (isActive
                          ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                          : "bg-zinc-900 text-zinc-500 border-zinc-800")
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </Link>
              )
            })}

            {/* Architecture specs card in sidebar */}
            <div className="pt-4 px-2">
              <div className="rounded-lg p-3 bg-zinc-900/50 border border-zinc-800/70 space-y-2">
                <div className="flex items-center gap-1.5 text-[10px] font-semibold text-zinc-400 uppercase font-mono">
                  <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />
                  Cluster Telemetry
                </div>
                <div className="text-[10px] font-mono space-y-1 text-zinc-500">
                  <div className="flex justify-between">
                    <span>Supervisor:</span>
                    <span className="text-zinc-300">Atlas</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Pods:</span>
                    <span className="text-zinc-300">4 Active</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Subagents:</span>
                    <span className="text-emerald-400">10 / 10 Active</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Memory:</span>
                    <span className="text-zinc-300">Bi-Temporal</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Circuit Breaker:</span>
                    <span className="text-emerald-400">10 Closed (0 Trip)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sidebar Footer */}
          <div className="p-3 border-t border-zinc-800/80 bg-zinc-950/60">
            <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
              <span>Schema: langgraph</span>
              <span className="text-emerald-400">WAL OK</span>
            </div>
          </div>
        </aside>

        {/* Backdrop for mobile */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/60 backdrop-blur-xs lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto flex flex-col min-w-0">
          {/* Module Banner / Header */}
          {(activeModuleTitle || actions) && (
            <div className="border-b border-zinc-800/60 bg-zinc-950/40 px-4 sm:px-6 py-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h1 className="text-base sm:text-lg font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
                    {activeModuleTitle}
                  </h1>
                  {activeModuleSubtitle && (
                    <p className="text-xs text-zinc-400 mt-0.5 font-mono">{activeModuleSubtitle}</p>
                  )}
                </div>
                {actions && <div className="flex items-center gap-2">{actions}</div>}
              </div>
            </div>
          )}

          {/* Children Content */}
          <div className="flex-1 p-4 sm:p-6 w-full max-w-7xl mx-auto">{children}</div>

          {/* Unified Footer */}
          <footer className="border-t border-zinc-800/80 bg-zinc-950/80 text-center py-3 px-4">
            <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-[10px] text-zinc-500 font-mono">
              <p>
                Enterprise LangGraph Platform &bull; LGP v2.0 &bull; Supabase Schema: <span className="text-zinc-400">langgraph</span>
              </p>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> All 10 Pods Operational
                </span>
                <span>&bull;</span>
                <span className="text-zinc-400">AGENTS.md Phase-Gate Enforced</span>
              </div>
            </div>
          </footer>
        </main>
      </div>
    </div>
  )
}
