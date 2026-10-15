"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { FALLBACK_RUNS } from "@/lib/mockData"
import type { Run, RunStep, CheckpointRecord } from "@/types"
import {
  GitBranch,
  Play,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Coins,
  ChevronRight,
  Database,
  ArrowRight,
  RefreshCw,
  Plus,
  Terminal,
} from "lucide-react"

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>(FALLBACK_RUNS)
  const [selectedRunId, setSelectedRunId] = useState<string>(FALLBACK_RUNS[0].run_id)
  const [selectedStep, setSelectedStep] = useState<RunStep | null>(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<CheckpointRecord | null>(null)
  const [newRunModal, setNewRunModal] = useState<boolean>(false)
  const [newObjective, setNewObjective] = useState<string>("")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchRuns() {
      try {
        const res = await fetch("/api/runs")
        if (res.ok) {
          const data = await res.json()
          if (Array.isArray(data) && data.length > 0) {
            setRuns(data)
          }
        }
      } catch {
        // Fallback active
      }
    }
    fetchRuns()
  }, [])

  const selectedRun = runs.find((r) => r.run_id === selectedRunId) || runs[0]

  useEffect(() => {
    if (selectedRun?.steps && selectedRun.steps.length > 0) {
      setSelectedStep(selectedRun.steps[0])
    }
    if (selectedRun?.checkpoints && selectedRun.checkpoints.length > 0) {
      setSelectedCheckpoint(selectedRun.checkpoints[0])
    }
  }, [selectedRunId])

  const handleCreateRun = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newObjective.trim()) return

    const newRun: Run = {
      run_id: `run-${Date.now().toString(36)}`,
      thread_id: `th-${Math.random().toString(36).substring(2, 8)}`,
      objective: newObjective.trim(),
      status: "running",
      created_at: Date.now(),
      budget_used: 0.05,
      current_subagent: "atlas",
      total_latency_s: 0.8,
      total_tokens: 4200,
      steps: [
        {
          id: "step-init-1",
          node_name: "decompose_objective",
          subagent: "atlas",
          status: "running",
          latency_ms: 320,
          token_usage: { input_tokens: 1200, output_tokens: 450, total_tokens: 1650, cost_usd: 0.04 },
          started_at: new Date().toLocaleTimeString(),
        },
      ],
      checkpoints: [
        {
          checkpoint_id: `chk-${Date.now().toString(36)}`,
          step_index: 1,
          node: "atlas",
          timestamp: new Date().toLocaleTimeString(),
          state_snapshot: { objective: newObjective.trim(), supervisor: "atlas", status: "decomposing" },
        },
      ],
    }

    setRuns([newRun, ...runs])
    setSelectedRunId(newRun.run_id)
    setNewRunModal(false)
    setNewObjective("")
    showToast(`Run baru ${newRun.run_id} berhasil dibuat dan dijadwalkan ke Atlas supervisor`)
  }

  return (
    <DashboardShell
      activeModuleTitle="LangGraph Runs & Execution DAG"
      activeModuleSubtitle="Thread Inspector &bull; Visual DAG Step Flow &bull; Checkpoint State Inspector"
      actions={
        <button
          onClick={() => setNewRunModal(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow transition"
        >
          <Plus className="w-3.5 h-3.5" />
          Eksekusi Run Baru
        </button>
      }
    >
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg bg-indigo-950 text-indigo-200 border border-indigo-500/40 text-xs font-mono shadow-xl flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Main Grid: Thread Selector (Left) + DAG & Details (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Thread & Run List */}
        <div className="lg:col-span-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 font-mono">
              Thread & Runs History
            </h2>
            <span className="text-[10px] font-mono text-zinc-500">{runs.length} Runs</span>
          </div>

          <div className="space-y-2">
            {runs.map((r) => {
              const isSelected = r.run_id === selectedRunId
              const statusColor =
                r.status === "completed"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : r.status === "running"
                  ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                  : r.status === "interrupted"
                  ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/30"

              return (
                <div
                  key={r.run_id}
                  onClick={() => setSelectedRunId(r.run_id)}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                    isSelected
                      ? "bg-indigo-950/20 border-indigo-500/50 shadow-sm"
                      : "bg-zinc-900/40 border-zinc-800/80 hover:bg-zinc-900/70 hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-mono font-semibold text-zinc-200 truncate">
                      {r.run_id}
                    </span>
                    <span
                      className={`text-[9px] font-mono uppercase px-2 py-0.5 rounded-full border ${statusColor}`}
                    >
                      {r.status}
                    </span>
                  </div>

                  <p className="text-xs text-zinc-400 line-clamp-2 mt-1.5">{r.objective}</p>

                  <div className="mt-3 flex items-center justify-between text-[10px] font-mono text-zinc-500 border-t border-zinc-800/60 pt-2">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-zinc-400" />
                      {r.total_latency_s?.toFixed(1) || 0}s
                    </span>
                    <span className="flex items-center gap-1">
                      <Coins className="w-3 h-3 text-emerald-400" />${r.budget_used?.toFixed(2) || 0}
                    </span>
                    <span className="text-zinc-400 uppercase">
                      Subagent: {r.current_subagent || "atlas"}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right Column: Active Run DAG Flow & Checkpoint Inspector */}
        <div className="lg:col-span-8 space-y-6">
          {selectedRun && (
            <>
              {/* Run Overview Banner */}
              <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-semibold text-zinc-100 font-mono">
                        {selectedRun.run_id}
                      </h2>
                      <span className="text-xs text-zinc-400 font-mono">
                        Thread: {selectedRun.thread_id}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-300 mt-1">{selectedRun.objective}</p>
                  </div>

                  <div className="flex items-center gap-3 text-xs font-mono">
                    <div className="text-right">
                      <span className="text-zinc-500 block text-[9px] uppercase">Total Tokens</span>
                      <span className="text-zinc-200">
                        {selectedRun.total_tokens?.toLocaleString() || 0}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-zinc-500 block text-[9px] uppercase">Cost</span>
                      <span className="text-emerald-400 font-semibold">
                        ${selectedRun.budget_used?.toFixed(3) || 0}
                      </span>
                    </div>
                  </div>
                </div>

                {selectedRun.final_answer && (
                  <div className="mt-2 p-2.5 rounded-lg bg-zinc-950 border border-zinc-800/80 text-xs text-zinc-300 font-mono">
                    <span className="text-indigo-400 font-semibold block text-[10px] uppercase mb-0.5">
                      Final Output:
                    </span>
                    {selectedRun.final_answer}
                  </div>
                )}
              </div>

              {/* Visual DAG Step Flow */}
              <div className="rounded-xl bg-zinc-900/40 border border-zinc-800 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-indigo-400" />
                    Execution DAG Step Flow ({selectedRun.steps?.length || 0} steps)
                  </h3>
                  <span className="text-[10px] font-mono text-zinc-500">
                    Klik node untuk melihat state input & output
                  </span>
                </div>

                {/* Horizontal Step Sequence */}
                <div className="flex items-center gap-2 overflow-x-auto pb-3 pt-1">
                  {selectedRun.steps?.map((step, idx) => {
                    const isSelected = selectedStep?.id === step.id
                    const isCompleted = step.status === "completed"

                    return (
                      <React.Fragment key={step.id}>
                        <button
                          onClick={() => setSelectedStep(step)}
                          className={`flex-shrink-0 p-3 rounded-xl border text-left transition-all ${
                            isSelected
                              ? "bg-indigo-950/40 border-indigo-500 ring-1 ring-indigo-500"
                              : isCompleted
                              ? "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
                              : "bg-amber-950/20 border-amber-500/40"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-[10px] font-mono text-indigo-400 font-semibold">
                              #{idx + 1}
                            </span>
                            <span
                              className={`w-2 h-2 rounded-full ${
                                isCompleted
                                  ? "bg-emerald-400"
                                  : step.status === "running"
                                  ? "bg-blue-400 animate-pulse"
                                  : "bg-amber-400"
                              }`}
                            />
                          </div>

                          <div className="text-xs font-mono font-semibold text-zinc-200 mt-1 truncate max-w-[130px]">
                            {step.node_name}
                          </div>
                          <div className="text-[10px] font-mono text-zinc-400 capitalize">
                            Subagent: {step.subagent}
                          </div>

                          <div className="mt-2 text-[9px] font-mono text-zinc-500 flex items-center gap-1.5">
                            <Clock className="w-2.5 h-2.5" />
                            {step.latency_ms}ms &bull; ${step.token_usage?.cost_usd.toFixed(2) || "0.00"}
                          </div>
                        </button>

                        {idx < (selectedRun.steps?.length || 0) - 1 && (
                          <ArrowRight className="w-4 h-4 text-zinc-600 flex-shrink-0" />
                        )}
                      </React.Fragment>
                    )
                  })}
                </div>

                {/* Selected Step Inspector */}
                {selectedStep && (
                  <div className="mt-4 p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-3 font-mono text-xs">
                    <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                      <div className="flex items-center gap-2">
                        <Terminal className="w-4 h-4 text-indigo-400" />
                        <span className="font-semibold text-zinc-200">{selectedStep.node_name}</span>
                        <span className="text-zinc-500">({selectedStep.subagent})</span>
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-zinc-400">
                        <span>Latency: {selectedStep.latency_ms}ms</span>
                        <span>Tokens: {selectedStep.token_usage?.total_tokens.toLocaleString()}</span>
                        <span className="text-emerald-400 font-semibold">
                          ${selectedStep.token_usage?.cost_usd.toFixed(3)}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                      <div>
                        <span className="text-[10px] uppercase text-zinc-500 font-semibold block mb-1">
                          Input Payload Snapshot
                        </span>
                        <pre className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800/80 text-[11px] text-zinc-300 overflow-x-auto max-h-40">
                          {JSON.stringify(selectedStep.input_preview || { status: "received" }, null, 2)}
                        </pre>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase text-zinc-500 font-semibold block mb-1">
                          Output Result Snapshot
                        </span>
                        <pre className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800/80 text-[11px] text-emerald-300 overflow-x-auto max-h-40">
                          {JSON.stringify(selectedStep.output_preview || { status: "completed" }, null, 2)}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Checkpoint State Inspector */}
              <div className="rounded-xl bg-zinc-900/40 border border-zinc-800 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono flex items-center gap-2">
                    <Database className="w-4 h-4 text-emerald-400" />
                    Checkpoint State Inspector ({selectedRun.checkpoints?.length || 0} checkpoints)
                  </h3>
                  <span className="text-[10px] font-mono text-zinc-500">
                    SQLite WAL Snapshot Persistence
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {selectedRun.checkpoints?.map((chk) => (
                    <div
                      key={chk.checkpoint_id}
                      onClick={() => setSelectedCheckpoint(chk)}
                      className={`p-3 rounded-lg border cursor-pointer transition-all ${
                        selectedCheckpoint?.checkpoint_id === chk.checkpoint_id
                          ? "bg-indigo-950/30 border-indigo-500"
                          : "bg-zinc-950 border-zinc-800/80 hover:border-zinc-700"
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-mono">
                        <span className="font-semibold text-zinc-200">{chk.checkpoint_id}</span>
                        <span className="text-[10px] text-zinc-500">{chk.timestamp}</span>
                      </div>
                      <div className="text-[11px] font-mono text-zinc-400 mt-1">
                        Node: {chk.node} &bull; Step #{chk.step_index}
                      </div>
                    </div>
                  ))}
                </div>

                {selectedCheckpoint && (
                  <div className="p-3.5 rounded-lg bg-zinc-950 border border-zinc-800 font-mono text-xs">
                    <div className="flex items-center justify-between text-[11px] text-zinc-400 mb-2 border-b border-zinc-800/80 pb-1.5">
                      <span>Checkpoint: {selectedCheckpoint.checkpoint_id}</span>
                      <span>Recorded Node: {selectedCheckpoint.node}</span>
                    </div>
                    <pre className="text-[11px] text-zinc-300 overflow-x-auto max-h-48">
                      {JSON.stringify(selectedCheckpoint.state_snapshot, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* New Run Modal */}
      {newRunModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <form
            onSubmit={handleCreateRun}
            className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Play className="w-4 h-4 text-emerald-400" />
                Eksekusi Run Baru — LangGraph Platform
              </h3>
              <button
                type="button"
                onClick={() => setNewRunModal(false)}
                className="text-zinc-400 hover:text-zinc-100 text-xs font-mono"
              >
                Tutup
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-zinc-400 mb-1">Objective / Goal Eksekusi</label>
                <textarea
                  rows={4}
                  required
                  placeholder="Misal: Lakukan analisis performa query database Supabase dan buat usulan indeks b-tree..."
                  value={newObjective}
                  onChange={(e) => setNewObjective(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="p-3 rounded-lg bg-zinc-950/80 border border-zinc-800/80 text-[11px] text-zinc-400 space-y-1">
                <p>&bull; Supervisor node: <span className="text-zinc-200">Atlas (Frontier)</span></p>
                <p>&bull; Target delegates: <span className="text-zinc-200">Clio, Vulcan, Athena</span></p>
                <p>&bull; Checkpointing: <span className="text-emerald-400">SQLite WAL Active</span></p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setNewRunModal(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition"
              >
                Batal
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-lg text-xs font-mono bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow transition"
              >
                Jalankan Run
              </button>
            </div>
          </form>
        </div>
      )}
    </DashboardShell>
  )
}
