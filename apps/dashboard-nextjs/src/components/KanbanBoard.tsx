"use client"

import { useState, useEffect, useCallback } from "react"
import { Plus, GripVertical, CheckCircle2, Clock, AlertTriangle, Sparkles } from "lucide-react"
import { Button } from "./ui/button"
import { KanbanBoard as KanbanBoardType, KanbanCard } from "@/types"
import { supabase } from "@/lib/supabase"

interface KanbanBoardProps {
  boardId?: string
}

const DEFAULT_SAMPLE_BOARD: KanbanBoardType = {
  id: "board-lgp-v2",
  name: "LGP v2.0 Multi-Agent Workflow",
  columns: [
    {
      id: "col-backlog",
      name: "Backlog",
      order: 0,
      cards: [
        {
          id: "card-1",
          column_id: "col-backlog",
          title: "Themis: UU PDP Compliance Audit",
          description: "Scan data retention rules and PII redaction pipeline for enterprise tenant compliance.",
          status: "backlog",
          priority: "high",
          assigned_to: "themis",
        },
        {
          id: "card-2",
          column_id: "col-backlog",
          title: "Metron: Drift Detection Evaluator",
          description: "Establish LLM-as-judge benchmark against +/-20% latency and token cost variations.",
          status: "backlog",
          priority: "medium",
          assigned_to: "metron",
        },
      ],
    },
    {
      id: "col-in-progress",
      name: "In Progress",
      order: 1,
      cards: [
        {
          id: "card-3",
          column_id: "col-in-progress",
          title: "Atlas: Dynamic Task Decomposition",
          description: "Partition incoming objectives across Clio, Vulcan, and Athena subagents.",
          status: "in-progress",
          priority: "critical",
          assigned_to: "atlas",
        },
        {
          id: "card-4",
          column_id: "col-in-progress",
          title: "Mnemosyne: Bi-Temporal Graphiti Memory",
          description: "Index episodic run checkpoints into bi-temporal memory graph with invalidation windows.",
          status: "in-progress",
          priority: "high",
          assigned_to: "mnemosyne",
        },
      ],
    },
    {
      id: "col-review",
      name: "Review & Verification",
      order: 2,
      cards: [
        {
          id: "card-5",
          column_id: "col-review",
          title: "Athena: Adversarial Code & Diff Review",
          description: "Verify AST node transformations submitted by Vulcan sandbox.",
          status: "review",
          priority: "medium",
          assigned_to: "athena",
        },
        {
          id: "card-6",
          column_id: "col-review",
          title: "Hermes: Incident Triage Runbook",
          description: "Validate circuit breaker recovery hooks and PM2 restart metrics.",
          status: "review",
          priority: "low",
          assigned_to: "hermes",
        },
      ],
    },
    {
      id: "col-done",
      name: "Completed",
      order: 3,
      cards: [
        {
          id: "card-7",
          column_id: "col-done",
          title: "Supabase Isolated Schema Migration",
          description: "Provisioned isolated 'langgraph' schema on self-hosted Supabase cluster.",
          status: "done",
          priority: "critical",
          assigned_to: "janus",
        },
        {
          id: "card-8",
          column_id: "col-done",
          title: "10-Subagent Contract Matrix Setup",
          description: "Synchronized NPMI, Success Lift, and Handoff rates for Atlas supervisor.",
          status: "done",
          priority: "high",
          assigned_to: "atlas",
        },
      ],
    },
  ],
}

export default function KanbanBoard({ boardId }: KanbanBoardProps) {
  const [board, setBoard] = useState<KanbanBoardType | null>(null)
  const [loading, setLoading] = useState(true)
  const [source, setSource] = useState<"supabase" | "api" | "local">("local")

  const loadBoard = useCallback(async () => {
    setLoading(true)

    // 1. Try Supabase schema 'langgraph'
    try {
      const { data: boards, error: bErr } = await supabase
        .from("kanban_boards")
        .select("*")
        .limit(1)

      if (!bErr && boards && boards.length > 0) {
        const activeBoard = boards[0]
        const { data: cols, error: cErr } = await supabase
          .from("kanban_columns")
          .select("*")
          .eq("board_id", activeBoard.id)
          .order("order_idx")

        if (!cErr && cols && cols.length > 0) {
          const columnsWithCards = await Promise.all(
            cols.map(async (col) => {
              const { data: cards } = await supabase
                .from("kanban_cards")
                .select("*")
                .eq("column_id", col.id)
                .order("created_at")

              return {
                id: col.id,
                name: col.name,
                order: col.order_idx,
                cards: (cards || []).map((c) => ({
                  id: c.id,
                  column_id: c.column_id,
                  title: c.title,
                  description: c.description || "",
                  status: col.name.toLowerCase().replace(/\s+/g, "-"),
                  priority: (c.priority || "medium") as KanbanCard["priority"],
                  assigned_to: c.assigned_to,
                  created_at: c.created_at,
                  updated_at: c.updated_at,
                })),
              }
            })
          )

          setBoard({
            id: activeBoard.id,
            name: activeBoard.name,
            columns: columnsWithCards,
            created_at: activeBoard.created_at,
            updated_at: activeBoard.updated_at,
          })
          setSource("supabase")
          setLoading(false)
          return
        }
      }
    } catch {
      // Supabase unavailable, fall through
    }

    // 2. Try REST API endpoint
    try {
      const url = boardId ? `/api/kanban/boards/${boardId}` : "/api/kanban/boards"
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data) && data.length > 0) {
          const singleRes = await fetch(`/api/kanban/boards/${data[0].id}`)
          if (singleRes.ok) {
            const singleData = await singleRes.json()
            if (singleData && Array.isArray(singleData.columns)) {
              setBoard(singleData)
              setSource("api")
              setLoading(false)
              return
            }
          }
        } else if (data && Array.isArray(data.columns)) {
          setBoard(data)
          setSource("api")
          setLoading(false)
          return
        }
      }
    } catch {
      // API fallback
    }

    // 3. Fallback to sample enterprise board
    setBoard(DEFAULT_SAMPLE_BOARD)
    setSource("local")
    setLoading(false)
  }, [boardId])

  useEffect(() => {
    loadBoard()
  }, [loadBoard])

  const createCard = async (columnId: string) => {
    const title = prompt("Enter task title:")
    if (!title || !title.trim()) return

    const newCard: KanbanCard = {
      id: `card-${Date.now()}`,
      column_id: columnId,
      title: title.trim(),
      description: "Dispatched from Enterprise Dashboard console",
      priority: "high",
      status: "active",
      assigned_to: "atlas",
      created_at: Date.now(),
    }

    // Update local state immediately
    setBoard((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        columns: prev.columns.map((col) => {
          if (col.id === columnId) {
            return { ...col, cards: [...col.cards, newCard] }
          }
          return col
        }),
      }
    })

    // Persist to Supabase if available
    try {
      await supabase.from("kanban_cards").insert({
        id: newCard.id,
        column_id: columnId,
        title: newCard.title,
        description: newCard.description,
        priority: newCard.priority,
        assigned_to: newCard.assigned_to,
        metadata_json: {},
      })
    } catch {
      // Try API fallback
      try {
        await fetch("/api/kanban/cards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            column_id: columnId,
            title: newCard.title,
            description: newCard.description,
            priority: newCard.priority,
            assigned_to: newCard.assigned_to,
          }),
        })
      } catch {
        // Handled via local state
      }
    }
  }

  const moveCard = async (cardId: string, targetColId: string) => {
    setBoard((prev) => {
      if (!prev) return prev
      let movedCard: KanbanCard | null = null

      const updatedCols = prev.columns.map((col) => {
        const filtered = col.cards.filter((c) => {
          if (c.id === cardId) {
            movedCard = c
            return false
          }
          return true
        })
        return { ...col, cards: filtered }
      })

      if (!movedCard) return prev

      return {
        ...prev,
        columns: updatedCols.map((col) => {
          if (col.id === targetColId) {
            return {
              ...col,
              cards: [...col.cards, { ...movedCard!, column_id: targetColId }],
            }
          }
          return col
        }),
      }
    })

    try {
      await supabase
        .from("kanban_cards")
        .update({ column_id: targetColId })
        .eq("id", cardId)
    } catch {
      try {
        await fetch(`/api/kanban/cards/${cardId}/move`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ to_column_id: targetColId }),
        })
      } catch {
        // State updated locally
      }
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-zinc-400 text-xs font-mono">
        <Clock className="w-4 h-4 mr-2 animate-spin text-zinc-500" />
        Synchronizing Kanban state...
      </div>
    )
  }

  if (!board || !board.columns || board.columns.length === 0) {
    return (
      <div className="p-8 text-center bg-zinc-900/30 border border-zinc-800 rounded-lg">
        <p className="text-zinc-400 mb-4 text-xs font-mono">No board found.</p>
        <Button size="sm" onClick={() => setBoard(DEFAULT_SAMPLE_BOARD)}>
          Load Default Workspace
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-zinc-100">{board.name}</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-zinc-900 text-zinc-400 border border-zinc-800">
            Source: {source.toUpperCase()}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <span className="flex items-center gap-1 font-mono text-[11px]">
            <Sparkles className="w-3 h-3 text-emerald-400" />
            Drag & drop supported
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {board.columns.map((column) => (
          <div
            key={column.id}
            className="flex flex-col bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-3 min-h-[520px]"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              const draggedId = e.dataTransfer.getData("cardId")
              if (draggedId) {
                moveCard(draggedId, column.id)
              }
            }}
          >
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-zinc-800/60">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-500" />
                <h3 className="text-xs font-semibold tracking-tight text-zinc-200">
                  {column.name}
                </h3>
              </div>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-400 border border-zinc-700/50">
                {column.cards.length}
              </span>
            </div>

            <div className="flex-1 space-y-2.5 overflow-y-auto">
              {column.cards.map((card) => {
                const priorityColor =
                  card.priority === "critical"
                    ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                    : card.priority === "high"
                    ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                    : card.priority === "medium"
                    ? "bg-blue-500/15 text-blue-400 border-blue-500/30"
                    : "bg-zinc-800 text-zinc-400 border-zinc-700"

                return (
                  <div
                    key={card.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("cardId", card.id)}
                    className="group bg-zinc-950/90 border border-zinc-800/90 hover:border-zinc-700 rounded-md p-3 transition shadow-sm cursor-grab active:cursor-grabbing"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-1">
                        <GripVertical className="w-3.5 h-3.5 text-zinc-600 opacity-40 group-hover:opacity-100 transition shrink-0" />
                        <h4 className="text-xs font-medium text-zinc-100 leading-snug">
                          {card.title}
                        </h4>
                      </div>
                      <span
                        className={`text-[9px] uppercase font-mono px-1.5 py-0.2 rounded border ${priorityColor}`}
                      >
                        {card.priority}
                      </span>
                    </div>

                    {card.description && (
                      <p className="text-[11px] text-zinc-400 mt-2 pl-5 line-clamp-3 leading-relaxed">
                        {card.description}
                      </p>
                    )}

                    <div className="mt-3 pt-2 border-t border-zinc-900 flex items-center justify-between text-[10px] text-zinc-500 font-mono">
                      <span>{card.assigned_to ? `@${card.assigned_to}` : "Unassigned"}</span>
                      <span className="text-zinc-600">ID: {card.id.slice(-6)}</span>
                    </div>
                  </div>
                )
              })}

              {column.cards.length === 0 && (
                <div className="h-28 border border-dashed border-zinc-800 rounded flex items-center justify-center text-[11px] text-zinc-600 font-mono">
                  Drop tasks here
                </div>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              className="w-full mt-3 text-xs text-zinc-300 border-zinc-800 hover:bg-zinc-800/60"
              onClick={() => createCard(column.id)}
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              Add Task
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
