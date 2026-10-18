"use client"

import React, { useState, useEffect, useCallback } from "react"
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
  RefreshCw,
  Tag,
  HelpCircle,
  FileCheck,
  FolderGit2,
} from "lucide-react"

interface BoardSummary {
  id: string
  name: string
  created_at?: string | number
  updated_at?: string | number
}

function normalizeColStatus(name: string): string {
  const s = (name || "").toUpperCase().replace(/[- ]/g, "_")
  if (s.includes("BACKLOG")) return "BACKLOG"
  if (s.includes("PROGRESS")) return "IN_PROGRESS"
  if (s.includes("REWORK")) return "REWORK"
  if (s.includes("VALIDATION")) return "IN_VALIDATION"
  if (s.includes("VALIDATED") || s.includes("DONE")) return "VALIDATED"
  if (s.includes("IMPLEMENTED")) return "IMPLEMENTED"
  return s
}

export default function KanbanPage() {
  const [board, setBoard] = useState<KanbanBoard>(FALLBACK_KANBAN_BOARD)
  const [boardsList, setBoardsList] = useState<BoardSummary[]>([])
  const [selectedBoardId, setSelectedBoardId] = useState<string>("")
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isSyncing, setIsSyncing] = useState<boolean>(false)

  const [newCardModal, setNewCardModal] = useState<boolean>(false)
  const [targetColumnId, setTargetColumnId] = useState<string>("")
  const [cardTitle, setCardTitle] = useState<string>("")
  const [cardDesc, setCardDesc] = useState<string>("")
  const [cardPriority, setCardPriority] = useState<"low" | "medium" | "high" | "critical">("medium")
  const [cardAssignee, setCardAssignee] = useState<string>("hermes")
  const [cardPhaseRef, setCardPhaseRef] = useState<string>("p01")
  const [cardSeverity, setCardSeverity] = useState<"BLOCKER" | "MAJOR" | "MINOR" | "">("")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3500)
  }

  // 1. Fetch available boards
  const fetchBoardsList = useCallback(async () => {
    try {
      const res = await fetch("/api/kanban/boards")
      if (res.ok) {
        const list: BoardSummary[] = await res.json()
        if (Array.isArray(list) && list.length > 0) {
          setBoardsList(list)
          if (!selectedBoardId) {
            setSelectedBoardId(list[0].id)
          }
        }
      }
    } catch (err) {
      console.warn("Failed to fetch boards list:", err)
    }
  }, [selectedBoardId])

  // 2. Fetch specific board by ID
  const fetchBoard = useCallback(async (boardId?: string) => {
    setIsLoading(true)
    try {
      const url = boardId ? `/api/kanban/boards/${boardId}` : "/api/kanban"
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        if (data && data.columns) {
          setBoard(data)
          if (data.id && (!selectedBoardId || selectedBoardId !== data.id)) {
            setSelectedBoardId(data.id)
          }
          if (data.columns.length > 0 && !targetColumnId) {
            setTargetColumnId(data.columns[0].id)
          }
        }
      }
    } catch (err) {
      console.warn("Failed fetching board, using fallback:", err)
    } finally {
      setIsLoading(false)
    }
  }, [selectedBoardId, targetColumnId])

  useEffect(() => {
    fetchBoardsList()
    fetchBoard()
  }, [fetchBoardsList, fetchBoard])

  const handleSelectBoard = (bId: string) => {
    setSelectedBoardId(bId)
    fetchBoard(bId)
  }

  // 3. Bi-directional Sync with Hermes
  const handleSyncHermes = async () => {
    setIsSyncing(true)
    try {
      const res = await fetch("/api/kanban/sync", { method: "POST" })
      if (res.ok) {
        const syncRes = await res.json()
        const exported = syncRes?.db_to_hermes?.exported_boards || 0
        const cards = syncRes?.hermes_to_db?.cards_synced || 0
        showToast(`Sync Hermes Berhasil: ${exported} boards terdaftar, ${cards} kartu sinkron.`)
        await fetchBoardsList()
        await fetchBoard(selectedBoardId)
      } else {
        showToast("Gagal sinkronisasi dengan Hermes.")
      }
    } catch (e) {
      showToast("Error sinkronisasi: " + String(e))
    } finally {
      setIsSyncing(false)
    }
  }

  // 4. Move Card between columns (API + Optimistic UI)
  const moveCard = async (cardId: string, currentColId: string, targetColId: string) => {
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

      const targetCol = board.columns.find((c) => c.id === targetColId)
      showToast(`Kartu dipindahkan ke kolom ${targetCol?.name || targetColId}`)

      // Persist to API
      try {
        await fetch(`/api/kanban/cards/${cardId}/move`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ to_column_id: targetColId }),
        })
      } catch (err) {
        console.error("Failed persisting card move:", err)
      }
    }
  }

  // 5. Add Card (API + Optimistic UI)
  const handleAddCard = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!cardTitle.trim()) return

    const actualTargetColId = targetColumnId || (board.columns.length > 0 ? board.columns[0].id : "col-backlog")

    const newCard: KanbanCard = {
      id: `card-${Date.now()}`,
      column_id: actualTargetColId,
      title: cardTitle.trim(),
      description: cardDesc.trim(),
      priority: cardPriority,
      phase_ref: cardPhaseRef || "p01",
      severity: cardSeverity ? (cardSeverity as "BLOCKER" | "MAJOR" | "MINOR") : null,
      assigned_to: cardAssignee,
      created_at: Date.now(),
    }

    const updatedColumns = board.columns.map((col) => {
      if (col.id === actualTargetColId) {
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
    showToast(`Kartu "${newCard.title}" berhasil ditambahkan & disimpan ke Hermes.`)

    try {
      await fetch("/api/kanban/cards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          column_id: actualTargetColId,
          title: newCard.title,
          description: newCard.description,
          priority: newCard.priority,
          assigned_to: newCard.assigned_to,
        }),
      })
      if (selectedBoardId) {
        fetchBoard(selectedBoardId)
      }
    } catch (err) {
      console.error("Failed to persist card creation:", err)
    }
  }

  return (
    <DashboardShell
      activeModuleTitle="AGENTS.md Phase-Gate Kanban"
      activeModuleSubtitle="Card Lifecycle: BACKLOG → IN PROGRESS → IMPLEMENTED → IN VALIDATION → VALIDATED / REWORK"
      actions={
        <div className="flex items-center gap-2 flex-wrap">
          {/* Board Selector */}
          <div className="flex items-center gap-1.5 bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1 text-xs font-mono text-zinc-300">
            <FolderGit2 className="w-3.5 h-3.5 text-indigo-400" />
            <select
              value={selectedBoardId}
              onChange={(e) => handleSelectBoard(e.target.value)}
              className="bg-transparent border-none text-zinc-200 text-xs font-mono focus:outline-none cursor-pointer max-w-[200px] truncate"
            >
              {boardsList.map((b) => (
                <option key={b.id} value={b.id} className="bg-zinc-900 text-zinc-200">
                  {b.name || b.id}
                </option>
              ))}
            </select>
          </div>

          {/* Sync with Hermes Button */}
          <button
            onClick={handleSyncHermes}
            disabled={isSyncing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-emerald-400 border border-emerald-800/40 transition disabled:opacity-50"
            title="Sinkronisasi state board, kartu, dan memory dengan ~/.state/boards Hermes"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
            {isSyncing ? "Syncing..." : "Sync Hermes"}
          </button>

          {/* Add Card Button */}
          <button
            onClick={() => {
              if (board.columns.length > 0 && !targetColumnId) {
                setTargetColumnId(board.columns[0].id)
              }
              setNewCardModal(true)
            }}
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
              Board Aktif: <span className="text-indigo-300 font-bold">{board.name || selectedBoardId}</span>
            </span>
            <span className="text-zinc-400 text-[11px] block sm:inline sm:ml-2">
              (P2 Directive: Selesai build fase baru setengah jalan. Wajib lolos validasi independen hingga status <strong className="text-emerald-400">VALIDATED</strong>)
            </span>
          </div>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-900 text-indigo-300 border border-indigo-500/30 whitespace-nowrap">
          AGENTS.md &bull; Hermes Persisted
        </span>
      </div>

      {/* Dynamic Phase-Gate Kanban Columns */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5 items-start">
        {board.columns.map((col, colIdx) => {
          const colName = col.name
          const normStatus = normalizeColStatus(colName)
          const isDoneCol = normStatus === "VALIDATED"
          const isReworkCol = normStatus === "REWORK"
          const isValidatingCol = normStatus === "IN_VALIDATION"

          // Determine next and previous columns
          const prevCol = colIdx > 0 ? board.columns[colIdx - 1] : null
          const nextCol = colIdx < board.columns.length - 1 ? board.columns[colIdx + 1] : null
          const reworkCol = board.columns.find((c) => normalizeColStatus(c.name) === "REWORK")

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
                          <span>Assignee:</span>
                          <span className="text-indigo-400 font-semibold uppercase">
                            {card.assigned_to || "HERMES"}
                          </span>
                        </div>

                        {/* Fast Move Action Buttons */}
                        <div className="flex items-center gap-1.5 pt-1">
                          {prevCol && (
                            <button
                              onClick={() => moveCard(card.id, col.id, prevCol.id)}
                              className="flex-1 py-1 px-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-[10px] font-mono text-zinc-400 border border-zinc-800 truncate"
                              title={`Pindah mundur ke ${prevCol.name}`}
                            >
                              &larr; {prevCol.name}
                            </button>
                          )}

                          {/* Reject to Rework shortcut on Validation Column */}
                          {isValidatingCol && reworkCol && (
                            <button
                              onClick={() => moveCard(card.id, col.id, reworkCol.id)}
                              className="py-1 px-1.5 rounded bg-rose-950/40 hover:bg-rose-900/50 text-[10px] font-mono text-rose-300 border border-rose-800/40 truncate"
                              title="Tolak hasil gate ke REWORK"
                            >
                              Rework
                            </button>
                          )}

                          {nextCol && (
                            <button
                              onClick={() => moveCard(card.id, col.id, nextCol.id)}
                              className="flex-1 py-1 px-1.5 rounded bg-indigo-600/20 hover:bg-indigo-600/40 text-[10px] font-mono text-indigo-300 border border-indigo-500/30 font-medium truncate"
                              title={`Pindah maju ke ${nextCol.name}`}
                            >
                              {nextCol.name} &rarr;
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
                Tambah Kartu Phase-Gate Baru ({board.name})
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
                    {board.columns.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-zinc-400 mb-1">Subagent Penanggung Jawab</label>
                  <select
                    value={cardAssignee}
                    onChange={(e) => setCardAssignee(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500 capitalize"
                  >
                    {["hermes", "primary_ai", "atlas", "clio", "vulcan", "athena", "mnemosyne", "janus", "themis", "metron", "iris"].map(
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
