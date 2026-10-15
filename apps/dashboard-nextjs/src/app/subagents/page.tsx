"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { FALLBACK_SUBAGENTS } from "@/lib/mockData"
import type { Subagent } from "@/types"
import {
  GitFork,
  Shield,
  Zap,
  Sliders,
  AlertOctagon,
  CheckCircle2,
  Lock,
  Layers,
  DollarSign,
  Activity,
  RotateCcw,
  Search,
  Filter,
} from "lucide-react"

export default function SubagentsPage() {
  const [subagents, setSubagents] = useState<Subagent[]>(FALLBACK_SUBAGENTS)
  const [selectedPod, setSelectedPod] = useState<string>("All")
  const [searchQuery, setSearchQuery] = useState<string>("")
  const [editingAgent, setEditingAgent] = useState<Subagent | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchAgents() {
      try {
        const res = await fetch("/api/subagents")
        if (res.ok) {
          const data = await res.json()
          if (Array.isArray(data) && data.length > 0) {
            setSubagents(data)
          }
        }
      } catch {
        // Fallback remains active
      }
    }
    fetchAgents()
  }, [])

  const pods = ["All", "Koordinasi", "Riset & Rekayasa", "Platform", "Tata Kelola"]

  const filtered = subagents.filter((agent) => {
    const matchesPod = selectedPod === "All" || agent.pod === selectedPod
    const matchesSearch =
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.capabilities.some((c) => c.toLowerCase().includes(searchQuery.toLowerCase()))
    return matchesPod && matchesSearch
  })

  const toggleCircuitBreaker = (agentId: string) => {
    setSubagents((prev) =>
      prev.map((a) => {
        if (a.id === agentId) {
          const nextState = a.circuit_breaker === "closed" ? "open" : "closed"
          showToast(`Circuit breaker untuk ${a.name} dialihkan ke ${nextState.toUpperCase()}`)
          return {
            ...a,
            circuit_breaker: nextState,
            consecutive_failures: nextState === "closed" ? 0 : 3,
          }
        }
        return a
      })
    )
  }

  const handleSaveBudget = (updated: Subagent) => {
    setSubagents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)))
    setEditingAgent(null)
    showToast(`Konfigurasi budget untuk ${updated.name} berhasil disimpan`)
  }

  return (
    <DashboardShell
      activeModuleTitle="Subagent Pods Registry"
      activeModuleSubtitle="10 Operational Subagents &bull; RBAC Trust Level &bull; Circuit Breaker Enforced"
      actions={
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setSubagents(FALLBACK_SUBAGENTS)
              showToast("Data subagent di-reset ke baseline kontrak default")
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition"
          >
            <RotateCcw className="w-3.5 h-3.5 text-zinc-400" />
            Reset Baseline
          </button>
        </div>
      }
    >
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg bg-indigo-950 text-indigo-200 border border-indigo-500/40 text-xs font-mono shadow-xl flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mb-6">
        {/* Pod Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto p-1 bg-zinc-900/60 rounded-lg border border-zinc-800/80">
          {pods.map((pod) => (
            <button
              key={pod}
              onClick={() => setSelectedPod(pod)}
              className={`px-3 py-1.5 rounded-md text-xs font-mono whitespace-nowrap transition-colors ${
                selectedPod === pod
                  ? "bg-indigo-600 text-white font-medium shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              }`}
            >
              {pod === "All" ? "Semua Pod (10)" : pod}
            </button>
          ))}
        </div>

        {/* Search input */}
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Cari subagent, peran, capability..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Subagents Grid (10 Profile Cards) */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((agent) => {
          const isClosed = agent.circuit_breaker === "closed"
          const trustColor =
            agent.trust_level === "High"
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
              : agent.trust_level.includes("Low")
              ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
              : "bg-amber-500/10 text-amber-400 border-amber-500/30"

          return (
            <div
              key={agent.id}
              className={`rounded-xl border transition-all duration-200 p-5 flex flex-col justify-between ${
                isClosed
                  ? "bg-zinc-900/40 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900/60"
                  : "bg-rose-950/10 border-rose-800/50"
              }`}
            >
              <div>
                {/* Header: Name, Pod, Trust */}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-semibold text-zinc-100">{agent.name}</h2>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/60">
                        v{agent.version}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-400 font-mono mt-0.5">{agent.role}</p>
                  </div>

                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${trustColor}`}
                  >
                    Trust: {agent.trust_level}
                  </span>
                </div>

                {/* Pod & Model Policy */}
                <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] font-mono text-zinc-400">
                  <span className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800">
                    Pod: {agent.pod}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-indigo-300">
                    {agent.model_policy}
                  </span>
                </div>

                {/* Capabilities List */}
                <div className="mt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold">
                    Capabilities
                  </span>
                  <ul className="mt-1.5 space-y-1">
                    {agent.capabilities.map((cap, i) => (
                      <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                        <span className="text-indigo-400 mt-1">&bull;</span>
                        <span>{cap}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Tool Grants */}
                <div className="mt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold">
                    Tool Grants
                  </span>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {agent.tool_grants.map((tool, i) => (
                      <span
                        key={i}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-950 text-zinc-400 border border-zinc-800/80"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Bottom Card Footer: Budget Config & Circuit Breaker */}
              <div className="mt-4 pt-4 border-t border-zinc-800/80 space-y-3">
                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono bg-zinc-950/70 p-2.5 rounded-lg border border-zinc-800/60">
                  <div>
                    <span className="text-zinc-500 block text-[9px] uppercase">Budget Cap</span>
                    <span className="text-emerald-400 font-semibold">${agent.budget_config.max_usd.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-[9px] uppercase">Max Tokens</span>
                    <span className="text-zinc-300">
                      {(agent.budget_config.max_tokens / 1000).toLocaleString()}k
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-[9px] uppercase">Max Wall Time</span>
                    <span className="text-zinc-300">{agent.budget_config.max_wall_clock_s}s</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-[9px] uppercase">Circuit Breaker</span>
                    <span
                      className={`font-semibold ${
                        isClosed ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {agent.circuit_breaker.toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Interactive Controls */}
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => setEditingAgent(agent)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700/60 transition"
                  >
                    <Sliders className="w-3.5 h-3.5 text-zinc-400" />
                    Edit Budget
                  </button>

                  <button
                    onClick={() => toggleCircuitBreaker(agent.id)}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-mono border transition ${
                      isClosed
                        ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border-rose-500/30"
                        : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                    }`}
                  >
                    <AlertOctagon className="w-3.5 h-3.5" />
                    {isClosed ? "Trip Circuit" : "Reset Breaker"}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Edit Budget Modal */}
      {editingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-indigo-400" />
                Konfigurasi Budget — {editingAgent.name}
              </h3>
              <button
                onClick={() => setEditingAgent(null)}
                className="text-zinc-400 hover:text-zinc-100 text-xs font-mono"
              >
                Tutup
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-zinc-400 mb-1">Max USD Cap ($)</label>
                <input
                  type="number"
                  step="0.25"
                  value={editingAgent.budget_config.max_usd}
                  onChange={(e) =>
                    setEditingAgent({
                      ...editingAgent,
                      budget_config: {
                        ...editingAgent.budget_config,
                        max_usd: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-zinc-400 mb-1">Max Tokens</label>
                <input
                  type="number"
                  step="50000"
                  value={editingAgent.budget_config.max_tokens}
                  onChange={(e) =>
                    setEditingAgent({
                      ...editingAgent,
                      budget_config: {
                        ...editingAgent.budget_config,
                        max_tokens: parseInt(e.target.value) || 0,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-zinc-400 mb-1">Max Wall Clock Timeout (detik)</label>
                <input
                  type="number"
                  step="60"
                  value={editingAgent.budget_config.max_wall_clock_s}
                  onChange={(e) =>
                    setEditingAgent({
                      ...editingAgent,
                      budget_config: {
                        ...editingAgent.budget_config,
                        max_wall_clock_s: parseInt(e.target.value) || 0,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-zinc-400 mb-1">Trust Level</label>
                <select
                  value={editingAgent.trust_level}
                  onChange={(e) =>
                    setEditingAgent({
                      ...editingAgent,
                      trust_level: e.target.value as "High" | "Medium" | "Low" | "Low-Medium" | "Medium-High",
                    })
                  }
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="High">High (Supervisor / Core Orchestration)</option>
                  <option value="Medium-High">Medium-High (Security Auditor)</option>
                  <option value="Medium">Medium (Engineering & Platform Ops)</option>
                  <option value="Low-Medium">Low-Medium (MCP Hub)</option>
                  <option value="Low">Low (Untrusted Web Search)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setEditingAgent(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition"
              >
                Batal
              </button>
              <button
                onClick={() => handleSaveBudget(editingAgent)}
                className="px-4 py-1.5 rounded-lg text-xs font-mono bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow transition"
              >
                Simpan Perubahan
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
