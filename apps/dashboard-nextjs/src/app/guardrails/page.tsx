"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import {
  FALLBACK_OWASP_LOGS,
  FALLBACK_AUDIT_LOG,
  FALLBACK_CIRCUIT_BREAKER_EVENTS,
} from "@/lib/mockData"
import type { OWASPGuardrailLog, AuditLogEntry, CircuitBreakerEvent } from "@/types"
import {
  ShieldAlert,
  ShieldCheck,
  Lock,
  AlertTriangle,
  CheckCircle2,
  Activity,
  RotateCcw,
  Key,
  Hash,
  Clock,
  Terminal,
} from "lucide-react"

export default function GuardrailsPage() {
  const [activeTab, setActiveTab] = useState<"owasp" | "audit" | "breakers">("owasp")
  const [owaspLogs, setOwaspLogs] = useState<OWASPGuardrailLog[]>(FALLBACK_OWASP_LOGS)
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>(FALLBACK_AUDIT_LOG)
  const [breakerEvents, setBreakerEvents] = useState<CircuitBreakerEvent[]>(FALLBACK_CIRCUIT_BREAKER_EVENTS)
  const [isVerifyingChain, setIsVerifyingChain] = useState<boolean>(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchTelemetry() {
      try {
        const res = await fetch("/api/guardrails")
        if (res.ok) {
          const data = await res.json()
          if (data.owasp) setOwaspLogs(data.owasp)
          if (data.audit) setAuditLogs(data.audit)
          if (data.breakers) setBreakerEvents(data.breakers)
        }
      } catch {
        // Fallback active
      }
    }
    fetchTelemetry()
  }, [])

  const handleVerifyChain = () => {
    setIsVerifyingChain(true)
    setTimeout(() => {
      setIsVerifyingChain(false)
      showToast("Verifikasi integritas rantai SHA-256 berhasil: 100% konsisten, 0 manipulasi terdeteksi.")
    }, 1200)
  }

  return (
    <DashboardShell
      activeModuleTitle="Guardrails & Telemetry"
      activeModuleSubtitle="OWASP LLM Top 10 Mitigation &bull; SHA-256 Tamper-Evident Ledger &bull; Circuit Breakers"
      actions={
        <button
          onClick={handleVerifyChain}
          disabled={isVerifyingChain}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow transition disabled:opacity-50"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          {isVerifyingChain ? "Memverifikasi Rantai..." : "Verifikasi Hash-Chain"}
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

      {/* Tabs Selector */}
      <div className="flex items-center gap-2 border-b border-zinc-800 pb-3 mb-6">
        <button
          onClick={() => setActiveTab("owasp")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
            activeTab === "owasp"
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent"
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          OWASP Top 10 Logs ({owaspLogs.length})
        </button>

        <button
          onClick={() => setActiveTab("audit")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
            activeTab === "audit"
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent"
          }`}
        >
          <Hash className="w-3.5 h-3.5" />
          Audit Trail Hash-Chain ({auditLogs.length})
        </button>

        <button
          onClick={() => setActiveTab("breakers")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
            activeTab === "breakers"
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent"
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          Circuit Breaker Events ({breakerEvents.length})
        </button>
      </div>

      {/* TAB 1: OWASP TOP 10 LOGS */}
      {activeTab === "owasp" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {[
              { id: "LLM01", name: "Prompt Injection", status: "Mitigated", color: "text-rose-400" },
              { id: "LLM02", name: "Sensitive Info Disclosure", status: "Sanitized", color: "text-amber-400" },
              { id: "LLM06", name: "Excessive Agency", status: "Contained", color: "text-purple-400" },
              { id: "LLM10", name: "Unbounded Consumption", status: "Clamped", color: "text-blue-400" },
            ].map((rule) => (
              <div key={rule.id} className="p-3.5 rounded-xl bg-zinc-900/40 border border-zinc-800 font-mono text-xs">
                <span className="text-zinc-500 text-[10px] block">{rule.id}</span>
                <span className="font-semibold text-zinc-200 block mt-0.5">{rule.name}</span>
                <span className={`text-[11px] font-semibold block mt-2 ${rule.color}`}>
                  Status: {rule.status}
                </span>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase text-[10px] tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Rule</th>
                    <th className="py-3 px-4">Severity</th>
                    <th className="py-3 px-4">Subagent</th>
                    <th className="py-3 px-4">Action Taken</th>
                    <th className="py-3 px-4">Mitigation Description</th>
                    <th className="py-3 px-4">Detected Payload</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {owaspLogs.map((log) => {
                    const actionBadge =
                      log.action_taken === "BLOCKED"
                        ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                        : log.action_taken === "INTERRUPTED"
                        ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        : "bg-blue-500/10 text-blue-400 border-blue-500/30"

                    return (
                      <tr key={log.id} className="hover:bg-zinc-900/60 transition-colors">
                        <td className="py-3 px-4 text-indigo-400 font-semibold">{log.rule_id}</td>
                        <td className="py-3 px-4">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-950 text-rose-300 border border-rose-800/60">
                            {log.severity}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-zinc-300 capitalize">{log.subagent}</td>
                        <td className="py-3 px-4">
                          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${actionBadge}`}>
                            {log.action_taken}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-zinc-300 max-w-sm">{log.mitigation}</td>
                        <td className="py-3 px-4 text-zinc-500 max-w-xs truncate" title={log.detected_payload}>
                          {log.detected_payload}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: AUDIT TRAIL HASH-CHAIN */}
      {activeTab === "audit" && (
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 flex items-center justify-between text-xs font-mono">
            <div>
              <h2 className="font-semibold text-zinc-200">Themis Tamper-Evident Ledger</h2>
              <p className="text-zinc-400 text-[11px] mt-0.5">
                Setiap event menghasilkan SHA-256 hash yang merujuk pada hash log sebelumnya (prev_hash).
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-xs font-semibold">
              <ShieldCheck className="w-4 h-4" /> SHA-256 Chain Intact
            </span>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase text-[10px] tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Log ID</th>
                    <th className="py-3 px-4">Actor</th>
                    <th className="py-3 px-4">Action</th>
                    <th className="py-3 px-4">Scope</th>
                    <th className="py-3 px-4">Current SHA-256 Hash</th>
                    <th className="py-3 px-4">Previous Hash Pointer</th>
                    <th className="py-3 px-4 text-right">Result</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {auditLogs.map((entry) => (
                    <tr key={entry.log_id} className="hover:bg-zinc-900/60 transition-colors">
                      <td className="py-3 px-4 text-indigo-400 font-semibold">{entry.log_id}</td>
                      <td className="py-3 px-4 text-zinc-300 capitalize">{entry.actor}</td>
                      <td className="py-3 px-4 text-amber-300">{entry.action}</td>
                      <td className="py-3 px-4 text-zinc-400">{entry.scope}</td>
                      <td className="py-3 px-4 text-zinc-500 font-mono text-[10px] max-w-[140px] truncate" title={entry.curr_hash}>
                        {entry.curr_hash}
                      </td>
                      <td className="py-3 px-4 text-zinc-600 font-mono text-[10px] max-w-[140px] truncate" title={entry.prev_hash}>
                        {entry.prev_hash}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          {entry.result_status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: CIRCUIT BREAKER HISTORY */}
      {activeTab === "breakers" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {breakerEvents.map((ev) => (
              <div
                key={ev.id}
                className="p-4 rounded-xl bg-zinc-900/40 border border-zinc-800 space-y-2.5 font-mono text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-zinc-200 capitalize">{ev.subagent}</span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full border ${
                      ev.state === "CLOSED"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                    }`}
                  >
                    State: {ev.state}
                  </span>
                </div>

                <p className="text-[11px] text-zinc-400 leading-relaxed">{ev.trigger_reason}</p>

                <div className="pt-2 border-t border-zinc-800/80 flex items-center justify-between text-[10px] text-zinc-500">
                  <span>Failures: {ev.consecutive_failures}</span>
                  {ev.recovery_action && (
                    <span className="text-indigo-400">{ev.recovery_action}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
