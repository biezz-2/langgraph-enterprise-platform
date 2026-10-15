"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { FALLBACK_KANBAN_BOARD } from "@/lib/mockData"
import type { KanbanBoard, KanbanCard, KanbanColumn } from "@/types"
import {
  LayoutGrid,
  Plus,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Shield,
  ArrowRight,
  RotateCcw,
  Tag,
  HelpCircle,
  FileCheck,
} from "lucide-react"

export default function KanbanPage() {
  const [board, setBoard] = useState<KanbanBoard>(FALLBACK_KANBAN_BOARD)
  const [newCardModal, setNewCardModal] = useState<boolean>(false)
  const [targetColumnId, setTargetColumnId] = useState<string>("col-backlog")
  const [cardTitle, setCardTitle] = useState<string>("")
  const [cardDesc, setCardDesc] = useState<string>("")
  const [cardPriority, setCardPriority] = useState<"low" | "medium" | "high" | "critical">("medium")
  const [cardAssignee, setCardAssignee] = useState<string>("atlas")
  const [cardPhaseRef, setCardPhaseRef] = useState<string>("p01")
  const [cardSeverity, setCardSeverity] = useState<"BLOCKER" | "MAJOR" | "MINOR" | "">("")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchBoard() {
      try {
        const res = await fetch("/api/kanban")
        if (res.ok) {
          const data = await res.json()
          if (data && data.columns) {
            setBoard(data)
          }
        }
      } catch {
        // Fallback active
      }
    }
    fetchBoard()
  }, [])

  const moveCard = (cardId: string, currentColId: string, targetColId: string) => {
    let cardToMove: KanbanCard | null = null

    const updatedColumns = board.columns.map((col) => {
      if (col.id === currentColId) {
        const card = col.cards.find((c) => c.id === cardId)
        if (card) {
          cardToMove = { ...card, column_id: targetColId }
        }
        return {
          ...col,
          cards: col.cards.filter((c) => c.id !== cardId),
        }
      }
      return col
    })

    if (cardToMove) {
      const finalColumns = updatedColumns.map((col) => {
        if (col.id === targetColId) {
          return {
            ...col,
            cards: [...col.cards, cardToMove!],
          }
        }
        return col
      })

      setBoard({ ...board, columns: finalColumns })
      showToast(`Kartu dipindahkan ke kolom ${targetColId.replace("col-", "").toUpperCase()}`)
    }
  }

  const handleAddCard = (e: React.FormEvent) => {
    e.preventDefault()
    if (!cardTitle.trim()) return

    const newCard: KanbanCard = {
      id: `card-${Date.now().toString(36)}`,
      column_id: targetColumnId,
      title: cardTitle.trim(),
      description: cardDesc.trim(),
      priority: cardPriority,
      phase_ref: cardPhaseRef || "p01",
      severity: cardSeverity ? (cardSeverity as "BLOCKER" | "MAJOR" | "MINOR") : null,
      assigned_to: cardAssignee,
      created_at: Date.now(),
    }

    const updatedColumns = board.columns.map((col) => {
      if (col.id === targetColumnId) {
        return {
          ...col,
          cards: [...col.cards, newCard],
        }
      }
      return col
    })

    setBoard({ ...board, columns: updatedColumns })
    setNewCardModal(false)
    setCardTitle("")
    setCardDesc("")
    showToast(`Kartu ${newCard.title} berhasil dibuat pada ${targetColumnId}`)
  }

  const columnTransitions: Record<string, { next: string; nextLabel: string; prev?: string; prevLabel?: string }> = {
    "col-backlog": { next: "col-in-progress", nextLabel: "Start" },
    "col-in-progress": { next: "col-implemented", nextLabel: "Implement", prev: "col-backlog", prevLabel: "Backlog" },
    "col-implemented": { next: "col-in-validation", nextLabel: "Validate Gate", prev: "col-in-progress", prevLabel: "In Progress" },
    "col-in-validation": { next: "col-validated", nextLabel: "Pass Gate", prev: "col-rework", prevLabel: "Reject to Rework" },
    "col-validated": { next: "", nextLabel: "", prev: "col-in-validation", prevLabel: "Re-check" },
    "col-rework": { next: "col-in-progress", nextLabel: "Fix in Progress", prev: "col-in-validation", prevLabel: "Back" },
  }

  return (
    <DashboardShell
      activeModuleTitle="AGENTS.md Phase-Gate Kanban"
      activeModuleSubtitle="Card Lifecycle: BACKLOG → IN PROGRESS → IMPLEMENTED → IN VALIDATION → VALIDATED / REWORK"
      actions={
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setBoard(FALLBACK_KANBAN_BOARD)
              showToast("Papan Kanban di-reset ke baseline AGENTS.md")
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition"
          >
            <RotateCcw className="w-3.5 h-3.5 text-zinc-400" />
            Reset Baseline
          </button>
          <button
            onClick={() => setNewCardModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Tambah Kartu
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

      {/* Prime Directive Banner */}
      <div className="mb-6 p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 font-mono text-xs">
        <div className="flex items-center gap-2.5">
          <FileCheck className="w-4 h-4 text-indigo-400 flex-shrink-0" />
          <div>
            <span className="font-semibold text-zinc-200">
              P2 Directive: &quot;IMPLEMENTED&quot; &ne; &quot;DONE&quot;
            </span>
            <span className="text-zinc-400 text-[11px] block sm:inline sm:ml-2">
              Selesai build fase baru setengah jalan. Wajib lolos validasi independen Athena (V1-V8) hingga status <strong className="text-emerald-400">VALIDATED</strong>.
            </span>
          </div>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-900 text-indigo-300 border border-indigo-500/30 whitespace-nowrap">
          AGENTS.md v1.0.0
        </span>
      </div>

      {/* 6-Column Phase-Gate Kanban Board */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5 items-start">
        {board.columns.map((col) => {
          const colName = col.name
          const isDoneCol = col.id === "col-validated"
          const isReworkCol = col.id === "col-rework"
          const isValidatingCol = col.id === "col-in-validation"

          return (
            <div
              key={col.id}
              className={`rounded-xl border flex flex-col max-h-[820px] transition-all ${
                isDoneCol
                  ? "bg-emerald-950/10 border-emerald-800/40"
                  : isReworkCol
                  ? "bg-rose-950/10 border-rose-800/40"
                  : isValidatingCol
                  ? "bg-indigo-950/15 border-indigo-500/40"
                  : "bg-zinc-900/40 border-zinc-800/80"
              }`}
            >
              {/* Column Header */}
              <div className="p-3 border-b border-zinc-800/80 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isDoneCol
                        ? "bg-emerald-400"
                        : isReworkCol
                        ? "bg-rose-400"
                        : isValidatingCol
                        ? "bg-indigo-400"
                        : "bg-zinc-400"
                    }`}
                  />
                  <h3 className="text-xs font-semibold font-mono tracking-tight text-zinc-200">
                    {colName}
                  </h3>
                </div>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-950 text-zinc-400 border border-zinc-800">
                  {col.cards.length}
                </span>
              </div>

              {/* Cards Container */}
              <div className="p-2.5 space-y-2.5 overflow-y-auto flex-1">
                {col.cards.map((card) => {
                  const transition = columnTransitions[col.id]

                  const sevColor =
                    card.severity === "BLOCKER"
                      ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                      : card.severity === "MAJOR"
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                      : card.severity === "MINOR"
                      ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                      : null

                  return (
                    <div
                      key={card.id}
                      className="p-3 rounded-lg bg-zinc-950/90 border border-zinc-800/80 hover:border-zinc-700 transition shadow-xs flex flex-col justify-between space-y-2.5"
                    >
                      <div>
                        {/* Phase & Severity Badges */}
                        <div className="flex items-center justify-between gap-1 text-[10px] font-mono">
                          <span className="text-zinc-500 font-semibold uppercase">
                            {card.phase_ref || "p01"}
                          </span>
                          {sevColor && (
                            <span className={`px-1.5 py-0.2 rounded border font-semibold ${sevColor}`}>
                              {card.severity}
                            </span>
                          )}
                        </div>

                        {/* Card Title */}
                        <h4 className="text-xs font-medium text-zinc-200 mt-1 leading-snug">
                          {card.title}
                        </h4>

                        {/* Description */}
                        {card.description && (
                          <p className="text-[11px] text-zinc-400 mt-1 line-clamp-3">
                            {card.description}
                          </p>
                        )}
                      </div>

                      {/* Card Footer: Assignee & Move Actions */}
                      <div className="pt-2 border-t border-zinc-800/80 space-y-2">
                        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400">
                          <span>Subagent:</span>
                          <span className="text-indigo-400 font-semibold capitalize">
                            {card.assigned_to || "atlas"}
                          </span>
                        </div>

                        {/* Fast Move Buttons */}
                        <div className="flex items-center gap-1.5 pt-1">
                          {transition?.prev && (
                            <button
                              onClick={() => moveCard(card.id, col.id, transition.prev!)}
                              className="flex-1 py-1 px-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-[10px] font-mono text-zinc-400 border border-zinc-800 truncate"
                              title={`Pindah ke ${transition.prevLabel}`}
                            >
                              &larr; {transition.prevLabel}
                            </button>
                          )}
                          {transition?.next && (
                            <button
                              onClick={() => moveCard(card.id, col.id, transition.next)}
                              className="flex-1 py-1 px-1.5 rounded bg-indigo-600/20 hover:bg-indigo-600/40 text-[10px] font-mono text-indigo-300 border border-indigo-500/30 font-medium truncate"
                              title={`Pindah ke ${transition.nextLabel}`}
                            >
                              {transition.nextLabel} &rarr;
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}

                {col.cards.length === 0 && (
                  <div className="py-8 text-center text-zinc-600 font-mono text-[10px]">
                    Kosong
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Add Card Modal */}
      {newCardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <form
            onSubmit={handleAddCard}
            className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4 font-mono"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Plus className="w-4 h-4 text-indigo-400" />
                Tambah Kartu Phase-Gate Baru
              </h3>
              <button
                type="button"
                onClick={() => setNewCardModal(false)}
                className="text-zinc-400 hover:text-zinc-100 text-xs"
              >
                Tutup
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-zinc-400 mb-1">Judul Task</label>
                <input
                  type="text"
                  required
                  placeholder="Misal: Vulcan: Sandbox AST Parsing Verification"
                  value={cardTitle}
                  onChange={(e) => setCardTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-zinc-400 mb-1">Deskripsi & Acceptance Criteria</label>
                <textarea
                  rows={3}
                  placeholder="Rincian checklist V1-V8 yang harus dipenuhi..."
                  value={cardDesc}
                  onChange={(e) => setCardDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-zinc-400 mb-1">Kolom Target</label>
                  <select
                    value={targetColumnId}
                    onChange={(e) => setTargetColumnId(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="col-backlog">BACKLOG</option>
                    <option value="col-in-progress">IN PROGRESS</option>
                    <option value="col-implemented">IMPLEMENTED</option>
                    <option value="col-in-validation">IN VALIDATION</option>
                    <option value="col-validated">VALIDATED</option>
                    <option value="col-rework">REWORK</option>
                  </select>
                </div>

                <div>
                  <label className="block text-zinc-400 mb-1">Subagent Penanggung Jawab</label>
                  <select
                    value={cardAssignee}
                    onChange={(e) => setCardAssignee(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500 capitalize"
                  >
                    {["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"].map(
                      (agent) => (
                        <option key={agent} value={agent}>
                          {agent}
                        </option>
                      )
                    )}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-zinc-400 mb-1">Phase Ref (Fase)</label>
                  <input
                    type="text"
                    value={cardPhaseRef}
                    onChange={(e) => setCardPhaseRef(e.target.value)}
                    placeholder="p01"
                    className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-zinc-400 mb-1">Severity / Tingkat Temuan</label>
                  <select
                    value={cardSeverity}
                    onChange={(e) => setCardSeverity(e.target.value as any)}
                    className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="">Normal (Tidak ada temuan)</option>
                    <option value="BLOCKER">BLOCKER (Menghambat Gate)</option>
                    <option value="MAJOR">MAJOR (Wajib Rework)</option>
                    <option value="MINOR">MINOR (Conditional Pass)</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setNewCardModal(false)}
                className="px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
              >
                Batal
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-lg text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow"
              >
                Buat Kartu
              </button>
            </div>
          </form>
        </div>
      )}
    </DashboardShell>
  )
}
