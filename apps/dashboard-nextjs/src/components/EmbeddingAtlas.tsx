"use client"

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react"
import {
  Layers,
  Sparkles,
  RefreshCw,
  Search,
  Maximize2,
  ZoomIn,
  ZoomOut,
  Info,
  Database,
  Cpu,
  Compass,
  Plus,
  Send,
  X,
  Copy,
  Check,
} from "lucide-react"

export interface AtlasNode {
  id: string
  x: number
  y: number
  label: string
  space?: string
  text?: string
  model_id?: string
  color?: string
}

interface EmbeddingAtlasProps {
  width: number
  height: number
  onNodeSelect?: (node: AtlasNode | null) => void
}

const CLUSTER_COLORS: Record<string, string> = {
  architecture: "#6366f1", // Indigo
  memory: "#10b981", // Emerald
  embedding: "#0ea5e9", // Sky
  visualization: "#f59e0b", // Amber
  guardrails: "#ec4899", // Pink
  security: "#ef4444", // Red
  default: "#8b5cf6", // Purple
}

export default function EmbeddingAtlas({ width, height, onNodeSelect }: EmbeddingAtlasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [nodes, setNodes] = useState<AtlasNode[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<AtlasNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<AtlasNode | null>(null)
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null)

  // Zoom & Pan transform state
  const [zoom, setZoom] = useState<number>(1.0)
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const isDraggingRef = useRef<boolean>(false)
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })

  // Custom projection text input
  const [customInput, setCustomInput] = useState<string>("")
  const [isProjecting, setIsProjecting] = useState<boolean>(false)
  const [filterLabel, setFilterLabel] = useState<string>("all")
  const [copiedText, setCopiedText] = useState<boolean>(false)

  // Fetch initial Atlas points from live API
  const fetchAtlasData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch("/api/embedding/atlas")
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      const data = await res.json()
      if (data && Array.isArray(data.nodes)) {
        setNodes(data.nodes)
      } else {
        throw new Error("Invalid atlas payload")
      }
    } catch (err: any) {
      console.warn("Atlas fetch failed, using fallback points:", err.message)
      // High-signal fallback points
      setNodes([
        {
          id: "node-1",
          x: -33.97,
          y: 35.48,
          label: "architecture",
          space: "gemini_gemini_embedding_2_preview_1024",
          text: "LangGraph Supervisor multi-agent orchestration architecture",
          model_id: "gemini/gemini-embedding-2-preview",
        },
        {
          id: "node-2",
          x: -32.48,
          y: -53.66,
          label: "memory",
          space: "gemini_gemini_embedding_2_preview_1024",
          text: "Bi-temporal memory graph with FalkorDB openCypher vector indexes",
          model_id: "gemini/gemini-embedding-2-preview",
        },
        {
          id: "node-3",
          x: -5.23,
          y: 70.14,
          label: "embedding",
          space: "gemini_gemini_embedding_2_preview_1024",
          text: "Parallel Multi-Provider Embedding Fabric with 9Router gateway",
          model_id: "gemini/gemini-embedding-2-preview",
        },
        {
          id: "node-4",
          x: 100.0,
          y: -12.79,
          label: "embedding",
          space: "gemini_gemini_embedding_2_preview_1024",
          text: "Matryoshka Representation Learning dimension truncation to 1024",
          model_id: "gemini/gemini-embedding-2-preview",
        },
        {
          id: "node-5",
          x: -28.31,
          y: -39.16,
          label: "visualization",
          space: "gemini_gemini_embedding_2_preview_1024",
          text: "Obsidian Neuron Graph dynamic clustering and degree centrality",
          model_id: "gemini/gemini-embedding-2-preview",
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAtlasData()
  }, [fetchAtlasData])

  // Custom text projection via /api/embedding/umap
  const handleProjectCustomText = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!customInput.trim() || isProjecting) return
    setIsProjecting(true)
    try {
      // 1. Get embedding for the input
      const embedRes = await fetch("/api/embedding/embed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: customInput.trim(),
          model: "gemini/gemini-embedding-2-preview",
          pattern: "single",
          target_dim: 1024,
        }),
      })

      if (!embedRes.ok) throw new Error("Gagal embed teks")
      const embedData = await embedRes.json()
      const vector = embedData.data?.[0]?.vector

      if (!vector) throw new Error("Vektor embedding kosong")

      // 2. Project with existing vectors via UMAP
      const newId = `custom-${Date.now()}`
      const umapRes = await fetch("/api/embedding/umap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vectors: [vector],
          ids: [newId],
          labels: ["user_query"],
        }),
      })

      if (!umapRes.ok) throw new Error("Gagal proyeksi UMAP")
      const umapData = await umapRes.json()
      const projected = umapData.nodes?.[0]

      if (projected) {
        const newNode: AtlasNode = {
          id: newId,
          x: projected.x,
          y: projected.y,
          label: "user_query",
          space: "gemini_gemini_embedding_2_preview_1024",
          text: customInput.trim(),
          model_id: "gemini/gemini-embedding-2-preview",
        }
        setNodes((prev) => [...prev, newNode])
        setSelectedNode(newNode)
        if (onNodeSelect) onNodeSelect(newNode)
        setCustomInput("")
      }
    } catch (err: any) {
      console.error("Custom projection error:", err)
      alert(`Gagal memproyeksikan teks: ${err.message}`)
    } finally {
      setIsProjecting(false)
    }
  }

  // Bounding box computation for auto-fit
  const bounds = useMemo(() => {
    if (nodes.length === 0) return { minX: -100, maxX: 100, minY: -100, maxY: 100 }
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const n of nodes) {
      if (n.x < minX) minX = n.x
      if (n.x > maxX) maxX = n.x
      if (n.y < minY) minY = n.y
      if (n.y > maxY) maxY = n.y
    }
    // Add 25% padding
    const padX = Math.max((maxX - minX) * 0.25, 20)
    const padY = Math.max((maxY - minY) * 0.25, 20)
    return {
      minX: minX - padX,
      maxX: maxX + padX,
      minY: minY - padY,
      maxY: maxY + padY,
    }
  }, [nodes])

  // Coordinate transform from Atlas space to Canvas pixel space
  const worldToScreen = useCallback(
    (wx: number, wy: number) => {
      const cw = width || 800
      const ch = height || 600
      const cx = cw / 2 + pan.x
      const cy = ch / 2 + pan.y

      const spanX = Math.max(bounds.maxX - bounds.minX, 1)
      const spanY = Math.max(bounds.maxY - bounds.minY, 1)
      const scale = (Math.min(cw / spanX, ch / spanY) * 0.75) * zoom

      const sx = cx + (wx - (bounds.minX + bounds.maxX) / 2) * scale
      const sy = cy - (wy - (bounds.minY + bounds.maxY) / 2) * scale // invert Y for Cartesian
      return { sx, sy, scale }
    },
    [width, height, pan, zoom, bounds]
  )

  const screenToWorld = useCallback(
    (sx: number, sy: number) => {
      const cw = width || 800
      const ch = height || 600
      const cx = cw / 2 + pan.x
      const cy = ch / 2 + pan.y

      const spanX = Math.max(bounds.maxX - bounds.minX, 1)
      const spanY = Math.max(bounds.maxY - bounds.minY, 1)
      const scale = (Math.min(cw / spanX, ch / spanY) * 0.75) * zoom

      const wx = (sx - cx) / scale + (bounds.minX + bounds.maxX) / 2
      const wy = -((sy - cy) / scale) + (bounds.minY + bounds.maxY) / 2
      return { wx, wy }
    },
    [width, height, pan, zoom, bounds]
  )

  // Filtered nodes
  const displayNodes = useMemo(() => {
    if (filterLabel === "all") return nodes
    return nodes.filter((n) => n.label.toLowerCase() === filterLabel.toLowerCase())
  }, [nodes, filterLabel])

  // Render Canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = (width || 800) * dpr
    canvas.height = (height || 600) * dpr
    ctx.scale(dpr, dpr)

    const w = width || 800
    const h = height || 600

    // Clear background
    ctx.fillStyle = "#09090b"
    ctx.fillRect(0, 0, w, h)

    // Center coordinates
    const center = worldToScreen(0, 0)

    // Draw semantic contour rings
    ctx.lineWidth = 1
    for (let r = 50; r <= 350; r += 75) {
      const radius = r * (center.scale / 2)
      if (radius > 10 && radius < Math.max(w, h)) {
        ctx.beginPath()
        ctx.arc(center.sx, center.sy, radius, 0, 2 * Math.PI)
        ctx.strokeStyle = "rgba(99, 102, 241, 0.08)"
        ctx.setLineDash([4, 6])
        ctx.stroke()
        ctx.setLineDash([])
      }
    }

    // Draw Cartesian Axes
    ctx.beginPath()
    ctx.moveTo(0, center.sy)
    ctx.lineTo(w, center.sy)
    ctx.moveTo(center.sx, 0)
    ctx.lineTo(center.sx, h)
    ctx.strokeStyle = "rgba(113, 113, 122, 0.2)"
    ctx.lineWidth = 1
    ctx.stroke()

    // Axis labels
    ctx.font = "9px ui-monospace, SFMono-Regular, monospace"
    ctx.fillStyle = "rgba(161, 161, 170, 0.5)"
    ctx.fillText("UMAP Dim 1 →", w - 75, center.sy - 8)
    ctx.fillText("↑ UMAP Dim 2", center.sx + 8, 18)

    // Connect nodes within same label with subtle filaments
    const nodesByLabel: Record<string, AtlasNode[]> = {}
    for (const n of displayNodes) {
      if (!nodesByLabel[n.label]) nodesByLabel[n.label] = []
      nodesByLabel[n.label].push(n)
    }

    for (const [lbl, group] of Object.entries(nodesByLabel)) {
      if (group.length > 1) {
        ctx.beginPath()
        for (let i = 0; i < group.length; i++) {
          for (let j = i + 1; j < group.length; j++) {
            const p1 = worldToScreen(group[i].x, group[i].y)
            const p2 = worldToScreen(group[j].x, group[j].y)
            ctx.moveTo(p1.sx, p1.sy)
            ctx.lineTo(p2.sx, p2.sy)
          }
        }
        const col = CLUSTER_COLORS[lbl] || CLUSTER_COLORS.default
        ctx.strokeStyle = `${col}25` // 15% opacity
        ctx.lineWidth = 1
        ctx.stroke()
      }
    }

    // Draw Nodes
    for (const node of displayNodes) {
      const { sx, sy } = worldToScreen(node.x, node.y)
      const isSelected = selectedNode?.id === node.id
      const isHovered = hoveredNode?.id === node.id
      const baseColor = CLUSTER_COLORS[node.label] || CLUSTER_COLORS.default

      const radius = isSelected ? 8 : isHovered ? 7 : 5

      // Glow halo for selected / hovered
      if (isSelected || isHovered) {
        const grad = ctx.createRadialGradient(sx, sy, radius * 0.5, sx, sy, radius * 3.5)
        grad.addColorStop(0, `${baseColor}99`)
        grad.addColorStop(1, `${baseColor}00`)
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(sx, sy, radius * 3.5, 0, 2 * Math.PI)
        ctx.fill()
      }

      // Outer ring
      ctx.beginPath()
      ctx.arc(sx, sy, radius + 2, 0, 2 * Math.PI)
      ctx.strokeStyle = isSelected ? "#ffffff" : isHovered ? baseColor : "rgba(255,255,255,0.4)"
      ctx.lineWidth = isSelected ? 2 : 1
      ctx.stroke()

      // Inner dot
      ctx.beginPath()
      ctx.arc(sx, sy, radius, 0, 2 * Math.PI)
      ctx.fillStyle = baseColor
      ctx.fill()

      // Node text label
      ctx.font = isSelected
        ? "bold 11px ui-monospace, monospace"
        : "10px ui-monospace, monospace"
      ctx.fillStyle = isSelected ? "#ffffff" : isHovered ? "#e4e4e7" : "#a1a1aa"
      ctx.fillText(node.label, sx + radius + 6, sy + 3)
    }
  }, [width, height, displayNodes, selectedNode, hoveredNode, worldToScreen])

  // Mouse Interaction Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = true
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    setMousePos({ x: mx, y: my })

    if (isDraggingRef.current) {
      setPan({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      })
      return
    }

    // Detect hovered node
    let found: AtlasNode | null = null
    for (const node of displayNodes) {
      const { sx, sy } = worldToScreen(node.x, node.y)
      const dist = Math.hypot(mx - sx, my - sy)
      if (dist <= 14) {
        found = node
        break
      }
    }
    setHoveredNode(found)
  }

  const handleMouseUp = () => {
    isDraggingRef.current = false
  }

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    let found: AtlasNode | null = null
    for (const node of displayNodes) {
      const { sx, sy } = worldToScreen(node.x, node.y)
      const dist = Math.hypot(mx - sx, my - sy)
      if (dist <= 16) {
        found = node
        break
      }
    }

    setSelectedNode(found)
    if (onNodeSelect) onNodeSelect(found)
  }

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87
    setZoom((prev) => Math.min(Math.max(prev * zoomFactor, 0.2), 8.0))
  }

  const copyNodeSnippet = (text?: string) => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedText(true)
    setTimeout(() => setCopiedText(false), 1500)
  }

  const availableLabels = useMemo(() => {
    const set = new Set<string>()
    nodes.forEach((n) => set.add(n.label))
    return Array.from(set)
  }, [nodes])

  return (
    <div className="relative w-full h-full bg-zinc-950 overflow-hidden select-none">
      {/* CANVAS RENDERER */}
      <canvas
        ref={canvasRef}
        className="w-full h-full cursor-crosshair"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleClick}
        onWheel={handleWheel}
      />

      {/* TOP CONTROLS & HUD */}
      <div className="absolute top-3 left-3 right-3 flex flex-wrap items-center justify-between gap-2 pointer-events-none z-10">
        <div className="flex items-center gap-2 pointer-events-auto">
          {/* Badge Mode */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900/90 border border-zinc-800 rounded-lg text-xs font-mono text-zinc-300 backdrop-blur-md shadow-lg">
            <Compass className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span className="font-semibold text-zinc-100">Embedding Atlas</span>
            <span className="text-[10px] text-zinc-500 font-mono">(UMAP 2D Projection)</span>
          </div>

          {/* Model info pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900/80 border border-zinc-800/80 rounded-md text-[11px] font-mono text-zinc-400">
            <Database className="w-3 h-3 text-indigo-400" />
            <span>Dim: 1024</span>
            <span className="text-zinc-600">|</span>
            <span>MRL Normalized</span>
          </div>

          {/* Label Filter Pills */}
          <div className="flex items-center gap-1 bg-zinc-900/90 p-1 border border-zinc-800 rounded-lg backdrop-blur-md">
            <button
              onClick={() => setFilterLabel("all")}
              className={`px-2 py-0.5 text-[10px] font-mono rounded ${
                filterLabel === "all" ? "bg-zinc-800 text-zinc-100 font-bold" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              All ({nodes.length})
            </button>
            {availableLabels.map((lbl) => (
              <button
                key={lbl}
                onClick={() => setFilterLabel(lbl)}
                className={`px-2 py-0.5 text-[10px] font-mono rounded flex items-center gap-1 ${
                  filterLabel === lbl ? "bg-zinc-800 text-zinc-100 font-bold" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: CLUSTER_COLORS[lbl] || CLUSTER_COLORS.default }}
                />
                <span>{lbl}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Right Tools (Refresh, Zoom Reset) */}
        <div className="flex items-center gap-1.5 pointer-events-auto">
          <button
            onClick={() => {
              setZoom(1.0)
              setPan({ x: 0, y: 0 })
            }}
            className="p-1.5 bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg backdrop-blur-md shadow text-xs font-mono"
            title="Reset Zoom & Pan"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.min(z * 1.25, 8.0))}
            className="p-1.5 bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg backdrop-blur-md shadow text-xs font-mono"
            title="Zoom In"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.max(z * 0.8, 0.2))}
            className="p-1.5 bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg backdrop-blur-md shadow text-xs font-mono"
            title="Zoom Out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={fetchAtlasData}
            disabled={loading}
            className="p-1.5 bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg backdrop-blur-md shadow text-xs font-mono disabled:opacity-50"
            title="Refresh Atlas Data"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-indigo-400" : ""}`} />
          </button>
        </div>
      </div>

      {/* BOTTOM INPUT: Dynamic Embedding Projection */}
      <div className="absolute bottom-3 left-3 right-3 sm:right-auto sm:w-96 z-10 pointer-events-auto">
        <form
          onSubmit={handleProjectCustomText}
          className="flex items-center gap-1.5 p-1 bg-zinc-900/90 border border-zinc-800 focus-within:border-indigo-500/60 rounded-xl backdrop-blur-md shadow-2xl transition"
        >
          <input
            type="text"
            placeholder="Proyeksikan teks memori baru ke Atlas..."
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value)}
            disabled={isProjecting}
            className="flex-1 px-3 py-1.5 text-xs bg-transparent text-zinc-200 placeholder-zinc-500 focus:outline-none font-mono"
          />
          <button
            type="submit"
            disabled={!customInput.trim() || isProjecting}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 text-white disabled:text-zinc-500 text-xs font-mono font-medium rounded-lg transition flex items-center gap-1"
          >
            {isProjecting ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Send className="w-3 h-3" />
            )}
            <span>Project</span>
          </button>
        </form>
      </div>

      {/* NODE HOVER TOOLTIP */}
      {hoveredNode && !selectedNode && mousePos && (
        <div
          className="absolute pointer-events-none z-20 px-3 py-2 bg-zinc-900/95 border border-zinc-700 rounded-lg shadow-2xl backdrop-blur-md text-xs font-mono max-w-xs transition-all"
          style={{
            left: Math.min(mousePos.x + 12, (width || 800) - 260),
            top: Math.min(mousePos.y + 12, (height || 600) - 120),
          }}
        >
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="w-2 h-2 rounded-full"
              style={{
                backgroundColor: CLUSTER_COLORS[hoveredNode.label] || CLUSTER_COLORS.default,
              }}
            />
            <span className="font-bold text-zinc-100">{hoveredNode.label}</span>
            <span className="text-[10px] text-zinc-500 ml-auto font-mono">
              ({hoveredNode.x.toFixed(1)}, {hoveredNode.y.toFixed(1)})
            </span>
          </div>
          <p className="text-[11px] text-zinc-300 leading-snug line-clamp-3">
            {hoveredNode.text || "Tidak ada cuplikan teks"}
          </p>
          {hoveredNode.model_id && (
            <div className="mt-1.5 text-[9px] text-zinc-500 truncate">
              Model: {hoveredNode.model_id}
            </div>
          )}
        </div>
      )}

      {/* SELECTED NODE INSPECTOR PANEL */}
      {selectedNode && (
        <div className="absolute top-14 right-3 w-80 max-w-[calc(100vw-24px)] bg-zinc-900/95 border border-zinc-800 rounded-xl shadow-2xl backdrop-blur-md p-3.5 z-20 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{
                  backgroundColor: CLUSTER_COLORS[selectedNode.label] || CLUSTER_COLORS.default,
                }}
              />
              <span className="font-bold text-zinc-100 text-sm">{selectedNode.label}</span>
            </div>
            <button
              onClick={() => {
                setSelectedNode(null)
                if (onNodeSelect) onNodeSelect(null)
              }}
              className="p-1 text-zinc-500 hover:text-zinc-300 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-2.5 text-[11px]">
            <div>
              <div className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">
                Node ID
              </div>
              <div className="text-zinc-300 bg-zinc-950/70 p-1.5 rounded border border-zinc-800/60 font-mono">
                {selectedNode.id}
              </div>
            </div>

            <div>
              <div className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">
                Koordinat 2D UMAP
              </div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 bg-zinc-950/80 rounded border border-zinc-800 text-indigo-300">
                  X: {selectedNode.x.toFixed(2)}
                </span>
                <span className="px-2 py-0.5 bg-zinc-950/80 rounded border border-zinc-800 text-indigo-300">
                  Y: {selectedNode.y.toFixed(2)}
                </span>
              </div>
            </div>

            {selectedNode.space && (
              <div>
                <div className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">
                  Embedding Space
                </div>
                <div className="text-zinc-400 bg-zinc-950/70 p-1.5 rounded border border-zinc-800/60 text-[10px] truncate">
                  {selectedNode.space}
                </div>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between text-zinc-500 text-[10px] uppercase tracking-wider mb-1">
                <span>Isi Teks Semantik</span>
                {selectedNode.text && (
                  <button
                    onClick={() => copyNodeSnippet(selectedNode.text)}
                    className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300"
                  >
                    {copiedText ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedText ? "Tersalin" : "Salin"}</span>
                  </button>
                )}
              </div>
              <div className="text-zinc-200 bg-zinc-950/90 p-2 rounded border border-zinc-800/80 max-h-36 overflow-y-auto leading-relaxed">
                {selectedNode.text || "Tidak ada detail teks"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
