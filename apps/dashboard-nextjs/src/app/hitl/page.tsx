"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { FALLBACK_HITL_INBOX } from "@/lib/mockData"
import type { HITLItem } from "@/types"
import {
  UserCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Edit3,
  ShieldAlert,
  ArrowRight,
  Clock,
  RotateCcw,
  Check,
  X,
  FileText,
} from "lucide-react"

export default function HITLPage() {
  const [items, setItems] = useState<HITLItem[]>(FALLBACK_HITL_INBOX)
  const [selectedStatus, setSelectedStatus] = useState<string>("all")
  const [modifyingItem, setModifyingItem] = useState<HITLItem | null>(null)
  const [modifiedPayload, setModifiedPayload] = useState<string>("")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchHITL() {
      try {
        const res = await fetch("/api/hitl")
        if (res.ok) {
          const data = await res.json()
          if (Array.isArray(data) && data.length > 0) {
            setItems(data)
          }
        }
      } catch {
        // Fallback active
      }
    }
    fetchHITL()
  }, [])

  const handleDecision = (id: string, decision: "approved" | "rejected") => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status: decision } : item))
    )
    showToast(
      `Tindakan interupsi ${id} berhasil di-${
        decision === "approved" ? "SETUJUI (APPROVED)" : "TOLAK (REJECTED)"
      }`
    )
  }

  const openModifyModal = (item: HITLItem) => {
    setModifyingItem(item)
    setModifiedPayload(JSON.stringify(item.proposed_payload, null, 2))
  }

  const saveModificationAndApprove = () => {
    if (!modifyingItem) return
    try {
      const parsed = JSON.parse(modifiedPayload)
      setItems((prev) =>
        prev.map((item) =>
          item.id === modifyingItem.id
            ? { ...item, proposed_payload: parsed, status: "approved" }
            : item
        )
      )
      setModifyingItem(null)
      showToast(`Payload dimodifikasi dan interupsi ${modifyingItem.id} DISETUJUI`)
    } catch {
      alert("Format JSON tidak valid. Silakan periksa kembali sintaks.")
    }
  }

  const filteredItems = items.filter((item) => {
    if (selectedStatus === "all") return true
    return item.status === selectedStatus
  })

  const pendingCount = items.filter((i) => i.status === "pending").length

  return (
    <DashboardShell
      activeModuleTitle="Human-in-the-Loop Inbox (HITL)"
      activeModuleSubtitle="Tinjau & Otorisasi Operasi Kritis Subagent &bull; LangGraph Interruption Guard"
      actions={
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setItems(FALLBACK_HITL_INBOX)
              showToast("Daftar inbox HITL di-reset ke baseline")
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition"
          >
            <RotateCcw className="w-3.5 h-3.5 text-zinc-400" />
            Reset Baseline
          </button>
        </div>
      }
    >
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg bg-indigo-950 text-indigo-200 border border-indigo-500/40 text-xs font-mono shadow-xl flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Filter Tabs & Quick KPI */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-2">
          {["all", "pending", "approved", "rejected"].map((st) => (
            <button
              key={st}
              onClick={() => setSelectedStatus(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono uppercase transition ${
                selectedStatus === st
                  ? "bg-indigo-600 text-white font-medium shadow"
                  : "bg-zinc-900/60 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 border border-zinc-800/80"
              }`}
            >
              {st} {st === "pending" && `(${pendingCount})`}
            </button>
          ))}
        </div>

        <div className="text-xs font-mono text-zinc-400 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-400" />
          <span>{pendingCount} Tindakan Memerlukan Otorisasi Manusia</span>
        </div>
      </div>

      {/* HITL Cards List */}
      <div className="space-y-4">
        {filteredItems.length === 0 ? (
          <div className="p-12 text-center rounded-xl bg-zinc-900/30 border border-zinc-800 text-zinc-500 font-mono text-xs">
            Tidak ada item interupsi dengan status &quot;{selectedStatus}&quot;.
          </div>
        ) : (
          filteredItems.map((item) => {
            const isPending = item.status === "pending"
            const riskColor =
              item.risk_level === "critical"
                ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                : item.risk_level === "high"
                ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                : "bg-blue-500/10 text-blue-400 border-blue-500/30"

            const statusBadge =
              item.status === "approved"
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                : item.status === "rejected"
                ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                : "bg-amber-500/10 text-amber-300 border-amber-500/30"

            return (
              <div
                key={item.id}
                className={`rounded-xl border p-5 transition-all ${
                  isPending
                    ? "bg-zinc-900/70 border-zinc-700/80 shadow-md shadow-zinc-950/50"
                    : "bg-zinc-900/30 border-zinc-800/60 opacity-80"
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="text-xs font-mono font-semibold text-zinc-200">
                        {item.interrupt_id}
                      </span>
                      <span
                        className={`text-[9px] font-mono uppercase px-2 py-0.5 rounded-full border ${riskColor}`}
                      >
                        Risk: {item.risk_level}
                      </span>
                      <span
                        className={`text-[9px] font-mono uppercase px-2 py-0.5 rounded-full border ${statusBadge}`}
                      >
                        {item.status}
                      </span>
                    </div>

                    <h2 className="text-sm font-medium text-zinc-100 pt-1">
                      {item.description}
                    </h2>

                    <div className="flex items-center gap-4 text-[11px] font-mono text-zinc-400 pt-1">
                      <span>Subagent: <strong className="text-zinc-200">{item.subagent}</strong></span>
                      <span>Action: <strong className="text-indigo-400">{item.action_type}</strong></span>
                      <span>Run ID: <span className="text-zinc-300">{item.run_id}</span></span>
                    </div>
                  </div>

                  {/* Actions for Pending State */}
                  {isPending && (
                    <div className="flex items-center gap-2 pt-2 md:pt-0">
                      <button
                        onClick={() => handleDecision(item.id, "approved")}
                        className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition"
                      >
                        <Check className="w-3.5 h-3.5" />
                        Setujui
                      </button>

                      <button
                        onClick={() => openModifyModal(item)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition"
                      >
                        <Edit3 className="w-3.5 h-3.5 text-zinc-400" />
                        Modifikasi
                      </button>

                      <button
                        onClick={() => handleDecision(item.id, "rejected")}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 transition"
                      >
                        <X className="w-3.5 h-3.5" />
                        Tolak
                      </button>
                    </div>
                  )}
                </div>

                {/* Proposed Payload Inspector */}
                <div className="mt-4 pt-3 border-t border-zinc-800/80">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold block mb-1.5">
                    Proposed Action Payload
                  </span>
                  <pre className="p-3 rounded-lg bg-zinc-950 border border-zinc-800/80 text-xs text-zinc-300 font-mono overflow-x-auto max-h-48">
                    {JSON.stringify(item.proposed_payload, null, 2)}
                  </pre>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Modify & Approve Modal */}
      {modifyingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-xl w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-indigo-400" />
                Modifikasi Payload — {modifyingItem.interrupt_id}
              </h3>
              <button
                onClick={() => setModifyingItem(null)}
                className="text-zinc-400 hover:text-zinc-100 text-xs font-mono"
              >
                Tutup
              </button>
            </div>

            <p className="text-xs text-zinc-400">
              Ubah parameter JSON payload di bawah ini sebelum memberikan otorisasi eksekusi kepada subagent.
            </p>

            <div>
              <textarea
                rows={10}
                value={modifiedPayload}
                onChange={(e) => setModifiedPayload(e.target.value)}
                className="w-full p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs font-mono text-zinc-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setModifyingItem(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition"
              >
                Batal
              </button>
              <button
                onClick={saveModificationAndApprove}
                className="px-4 py-1.5 rounded-lg text-xs font-mono bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow transition"
              >
                Simpan & Setujui Eksekusi
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
