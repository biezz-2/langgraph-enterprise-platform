"use client"

import { useState, useEffect, useMemo, useRef, useCallback } from "react"
import dynamic from "next/dynamic"
import {
  X,
  Info,
  Cpu,
  Database,
  Shield,
  Activity,
  RotateCw,
  Maximize2,
  Search,
  Sparkles,
  Zap,
  Layers,
  Sliders,
  Play,
  Pause,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  ChevronRight,
  Code2,
  History,
  Radio,
  Eye,
  RefreshCw,
} from "lucide-react"
import { NeuronGraphData, NeuronNode, NeuronLink, ObsidianPhysicsConfig } from "@/types/neuron"
import { MOCK_GRAPHITI_DATA, processNeuronGraphData } from "@/lib/mockNeuronData"

// Dynamic import for 2D Canvas (Obsidian Classic aesthetic)
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => <GraphLoadingIndicator label="Memuat Engine Canvas 2D..." />,
})

// Dynamic import for 3D WebGL (Spiking Neural Mesh)
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), {
  ssr: false,
  loading: () => <GraphLoadingIndicator label="Memuat Engine 3D WebGL..." />,
})

function GraphLoadingIndicator({ label }: { label: string }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-zinc-950/80 backdrop-blur-sm z-30">
      <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      <p className="text-xs font-mono text-zinc-400">{label}</p>
    </div>
  )
}

const DEFAULT_PHYSICS: ObsidianPhysicsConfig = {
  repelForce: -260,
  linkDistance: 70,
  centerGravity: 0.14,
  particleSpeed: 0.005,
  nodeSizeScale: 1.0,
  particleDensity: 2,
}

export default function NeuronGraph() {
  const containerRef = useRef<HTMLDivElement>(null)
  // Store graph ref
  const fgRef = useRef<Record<string, unknown> | null>(null)

  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d")
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
  const [rawData, setRawData] = useState<NeuronGraphData>({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState<NeuronNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<NeuronNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [isRotating, setIsRotating] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedFilter, setSelectedFilter] = useState<"all" | "subagent" | "category" | "fact_entity" | "invalid">("all")

  // Physics settings popover
  const [physics, setPhysics] = useState<ObsidianPhysicsConfig>(DEFAULT_PHYSICS)
  const [showPhysicsPanel, setShowPhysicsPanel] = useState(false)

  // Bi-temporal timeline controls
  const [timeBounds, setTimeBounds] = useState<{ min: number; max: number }>({
    min: Date.now() - 14 * 86400000,
    max: Date.now(),
  })
  const [timelineTime, setTimelineTime] = useState<number>(Date.now())
  const [isPlayingTimeline, setIsPlayingTimeline] = useState(false)
  const [copiedCypher, setCopiedCypher] = useState(false)

  const rotationAngleRef = useRef(0)

  // Measure container dimensions
  useEffect(() => {
    if (!containerRef.current) return
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 650,
        })
      }
    }
    updateSize()
    const observer = new ResizeObserver(updateSize)
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  // Fetch Graphiti bi-temporal neuron data with safe mock fallback
  const fetchGraph = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/graph/graphiti")
      if (!res.ok) throw new Error(`API status: ${res.status}`)
      const data = await res.json()

      const rawNodes = data.nodes || []
      const rawLinks = data.edges || data.links || []

      if (!rawNodes.length) {
        throw new Error("Data graph kosong dari server, beralih ke mock fallback")
      }

      const processed = processNeuronGraphData({ nodes: rawNodes, links: rawLinks })
      setRawData(processed)
      setIsLiveApi(true)
      setError(null)
    } catch {
      // Seamless mock fallback for resilience
      const fallback = MOCK_GRAPHITI_DATA()
      const processed = processNeuronGraphData(fallback)
      setRawData(processed)
      setIsLiveApi(false)
      setError(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // Initial load
    const timeout = setTimeout(() => {
      fetchGraph()
    }, 0)
    return () => clearTimeout(timeout)
  }, [fetchGraph])

  // Extract min and max timestamps for bi-temporal facts
  useEffect(() => {
    const timestamps: number[] = []
    rawData.nodes.forEach((n) => {
      if (n.valid_at) timestamps.push(new Date(n.valid_at).getTime())
      if (n.invalid_at) timestamps.push(new Date(n.invalid_at).getTime())
    })

    if (timestamps.length > 0) {
      const min = Math.min(...timestamps)
      const max = Math.max(...timestamps, Date.now())
      setTimeBounds({ min, max })
      setTimelineTime(max)
    }
  }, [rawData.nodes])

  // Timeline auto-play timer
  useEffect(() => {
    if (!isPlayingTimeline) return
    const interval = setInterval(() => {
      setTimelineTime((prev) => {
        const step = (timeBounds.max - timeBounds.min) / 40
        if (prev + step >= timeBounds.max) {
          setIsPlayingTimeline(false)
          return timeBounds.max
        }
        return prev + step
      })
    }, 400)
    return () => clearInterval(interval)
  }, [isPlayingTimeline, timeBounds])

  // Apply bi-temporal and search filtering
  const filteredData = useMemo(() => {
    const nodes = rawData.nodes
      .map((node) => {
        const n = { ...node }
        // Bi-temporal evaluation
        if (n.type === "fact_entity" || n.type === "fact") {
          const vTime = n.valid_at ? new Date(n.valid_at).getTime() : 0
          const ivTime = n.invalid_at ? new Date(n.invalid_at).getTime() : Infinity

          if (vTime > timelineTime) {
            // Fact not yet born at timeline position
            return null
          }
          if (timelineTime >= ivTime) {
            n.status = "invalid"
            n.color = "#f43f5e" // Rose 500
          } else {
            n.status = "active"
            n.color = "#10b981" // Emerald 500
          }
        }
        return n
      })
      .filter((n): n is NeuronNode => n !== null)

    // Category / Tag filter
    let visibleNodes = nodes
    if (selectedFilter === "subagent") {
      visibleNodes = visibleNodes.filter((n) => n.type === "subagent")
    } else if (selectedFilter === "category") {
      visibleNodes = visibleNodes.filter((n) => n.type === "category" || n.type === "hub")
    } else if (selectedFilter === "fact_entity") {
      visibleNodes = visibleNodes.filter((n) => n.type === "fact_entity" && n.status !== "invalid")
    } else if (selectedFilter === "invalid") {
      visibleNodes = visibleNodes.filter((n) => n.status === "invalid")
    }

    // Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      visibleNodes = visibleNodes.filter(
        (n) =>
          n.label.toLowerCase().includes(q) ||
          n.id.toLowerCase().includes(q) ||
          (n.group && n.group.toLowerCase().includes(q)) ||
          (n.role && n.role.toLowerCase().includes(q)) ||
          (n.description && n.description.toLowerCase().includes(q))
      )
    }

    const nodeIds = new Set(visibleNodes.map((n) => n.id))
    const links = rawData.links.filter((l) => {
      const src = typeof l.source === "object" && l.source !== null ? (l.source as NeuronNode).id : String(l.source)
      const tgt = typeof l.target === "object" && l.target !== null ? (l.target as NeuronNode).id : String(l.target)
      return nodeIds.has(src) && nodeIds.has(tgt)
    })

    return { nodes: visibleNodes, links }
  }, [rawData, timelineTime, selectedFilter, searchQuery])

  // Neighbor Spotlight calculation (1st & 2nd degree)
  const spotlightSets = useMemo(() => {
    const active = hoveredNode || selectedNode
    if (!active) return null

    const directNeighbors = new Set<string>()
    const secondNeighbors = new Set<string>()
    const highlightedLinks = new Set<string>()

    // Direct (1st degree)
    filteredData.links.forEach((l) => {
      const src = typeof l.source === "object" && l.source !== null ? (l.source as NeuronNode).id : String(l.source)
      const tgt = typeof l.target === "object" && l.target !== null ? (l.target as NeuronNode).id : String(l.target)
      const linkId = l.id || `${src}-${tgt}`

      if (src === active.id) {
        directNeighbors.add(tgt)
        highlightedLinks.add(linkId)
      } else if (tgt === active.id) {
        directNeighbors.add(src)
        highlightedLinks.add(linkId)
      }
    })

    // 2nd degree neighbors
    filteredData.links.forEach((l) => {
      const src = typeof l.source === "object" && l.source !== null ? (l.source as NeuronNode).id : String(l.source)
      const tgt = typeof l.target === "object" && l.target !== null ? (l.target as NeuronNode).id : String(l.target)
      const linkId = l.id || `${src}-${tgt}`

      if (directNeighbors.has(src) && tgt !== active.id && !directNeighbors.has(tgt)) {
        secondNeighbors.add(tgt)
        highlightedLinks.add(linkId)
      } else if (directNeighbors.has(tgt) && src !== active.id && !directNeighbors.has(src)) {
        secondNeighbors.add(src)
        highlightedLinks.add(linkId)
      }
    })

    return {
      activeId: active.id,
      direct: directNeighbors,
      second: secondNeighbors,
      links: highlightedLinks,
    }
  }, [hoveredNode, selectedNode, filteredData.links])

  // Apply Obsidian Physics to simulation
  const applyPhysics = useCallback(() => {
    const fg = fgRef.current as any
    if (!fg) return
    try {
      if (fg.d3Force) {
        const charge = fg.d3Force("charge")
        if (charge && typeof charge.strength === "function") {
          charge.strength(physics.repelForce)
        }
        const link = fg.d3Force("link")
        if (link && typeof link.distance === "function") {
          link.distance(physics.linkDistance)
        }
        const center = fg.d3Force("center")
        if (center && typeof center.strength === "function") {
          center.strength(physics.centerGravity)
        }
      }
      if (typeof fg.d3ReheatSimulation === "function") {
        fg.d3ReheatSimulation()
      }
    } catch {
      // Ignore force errors during transition
    }
  }, [physics])

  useEffect(() => {
    applyPhysics()
  }, [applyPhysics])

  // 3D Auto-Rotation
  useEffect(() => {
    if (!isRotating || viewMode !== "3d") return
    let animId: number
    const distance = 380

    const rotate = () => {
      const fg = fgRef.current as any
      if (fg && isRotating && fg.cameraPosition) {
        rotationAngleRef.current += 0.0016
        const angle = rotationAngleRef.current
        fg.cameraPosition({
          x: distance * Math.sin(angle),
          z: distance * Math.cos(angle),
        })
      }
      animId = requestAnimationFrame(rotate)
    }

    animId = requestAnimationFrame(rotate)
    return () => cancelAnimationFrame(animId)
  }, [isRotating, viewMode])

  // Center camera / viewport
  const handleRecenter = useCallback(() => {
    const fg = fgRef.current as any
    if (!fg) return
    setIsRotating(false)
    if (viewMode === "2d" && fg.centerAt && fg.zoom) {
      fg.centerAt(0, 0, 800)
      fg.zoom(1.2, 800)
    } else if (viewMode === "3d" && fg.cameraPosition) {
      fg.cameraPosition({ x: 0, y: 0, z: 360 }, { x: 0, y: 0, z: 0 }, 1000)
    }
  }, [viewMode])

  // Node selection & camera fly-to
  const handleNodeClick = useCallback(
    (node: NeuronNode) => {
      setSelectedNode(node)
      setIsRotating(false)
      const fg = fgRef.current as any
      if (!fg) return

      if (viewMode === "2d" && fg.centerAt && fg.zoom) {
        if (typeof node.x === "number" && typeof node.y === "number") {
          fg.centerAt(node.x, node.y, 700)
          fg.zoom(1.8, 700)
        }
      } else if (viewMode === "3d" && fg.cameraPosition && typeof node.x === "number") {
        const hyp = Math.hypot(node.x || 0, node.y || 0, (node as any).z || 0) || 1
        const distRatio = 1 + 90 / hyp
        fg.cameraPosition(
          {
            x: (node.x || 0) * distRatio,
            y: (node.y || 0) * distRatio + 15,
            z: ((node as any).z || 0) * distRatio,
          },
          node,
          1200
        )
      }
    },
    [viewMode]
  )

  // 2D Canvas Custom Node Renderer with Obsidian Aesthetic
  const drawNode2D = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isSelected = selectedNode?.id === node.id
      const isHovered = hoveredNode?.id === node.id

      let alpha = 1.0
      let isDimmed = false

      if (spotlightSets) {
        if (node.id === spotlightSets.activeId) {
          alpha = 1.0
        } else if (spotlightSets.direct.has(node.id)) {
          alpha = 0.95
        } else if (spotlightSets.second.has(node.id)) {
          alpha = 0.65
        } else {
          alpha = 0.08
          isDimmed = true
        }
      }

      const baseRadius = Math.max(
        3.5,
        (node.size ? node.size / 2.5 : 5) * physics.nodeSizeScale
      )
      const r = isSelected ? baseRadius * 1.35 : isHovered ? baseRadius * 1.2 : baseRadius

      ctx.save()
      ctx.globalAlpha = alpha

      const color = node.color || "#818cf8"
      const isInvalid = node.status === "invalid"

      // Outer Halo / Synaptic Glow
      if (!isDimmed) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r * 1.8, 0, 2 * Math.PI, false)
        const glowGrad = ctx.createRadialGradient(node.x, node.y, r * 0.7, node.x, node.y, r * 2.2)
        glowGrad.addColorStop(0, color + (isSelected ? "66" : "26"))
        glowGrad.addColorStop(1, "transparent")
        ctx.fillStyle = glowGrad
        ctx.fill()
      }

      // Main Node Body
      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false)
      ctx.fillStyle = color
      ctx.shadowColor = isDimmed ? "transparent" : color
      ctx.shadowBlur = isSelected ? 16 : isHovered ? 12 : 6
      ctx.fill()

      // Synaptic Ring Border
      ctx.shadowBlur = 0
      ctx.beginPath()
      ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI, false)

      if (isInvalid) {
        // Obsidian broken ring for invalidated facts
        ctx.setLineDash([3, 3])
        ctx.strokeStyle = "#f43f5e"
        ctx.lineWidth = 1.8
      } else if (isSelected) {
        ctx.setLineDash([])
        ctx.strokeStyle = "#ffffff"
        ctx.lineWidth = 2.2
      } else {
        ctx.setLineDash([])
        ctx.strokeStyle = "rgba(255, 255, 255, 0.4)"
        ctx.lineWidth = 1.0
      }
      ctx.stroke()

      // Node Label (adaptive LOD by zoom scale)
      const shouldDrawLabel =
        !isDimmed &&
        (isSelected ||
          isHovered ||
          node.type === "category" ||
          node.type === "subagent" ||
          globalScale >= 1.4)

      if (shouldDrawLabel) {
        const fontSize = Math.max(10 / globalScale, 3)
        ctx.font = `${isSelected ? "600" : "500"} ${fontSize}px ui-monospace, SFMono-Regular, monospace`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"

        const labelText = node.label || node.id
        const textY = node.y + r + fontSize * 0.9

        // Text background badge for clarity
        const textMetrics = ctx.measureText(labelText)
        const bWidth = textMetrics.width + 6 / globalScale
        const bHeight = fontSize + 4 / globalScale

        ctx.fillStyle = "rgba(9, 9, 11, 0.85)"
        ctx.fillRect(
          node.x - bWidth / 2,
          textY - bHeight / 2,
          bWidth,
          bHeight
        )

        ctx.fillStyle = isSelected ? "#ffffff" : isHovered ? "#e0e7ff" : "rgba(244, 244, 245, 0.9)"
        ctx.fillText(labelText, node.x, textY)
      }

      ctx.restore()
    },
    [selectedNode, hoveredNode, spotlightSets, physics.nodeSizeScale]
  )

  // 2D Link Color & Opacity with Spotlight
  const getLinkColor2D = useCallback(
    (link: any) => {
      const src = typeof link.source === "object" ? link.source.id : link.source
      const tgt = typeof link.target === "object" ? link.target.id : link.target
      const linkId = link.id || `${src}-${tgt}`

      if (!spotlightSets) {
        return link.color || "rgba(113, 113, 122, 0.35)"
      }

      if (spotlightSets.links.has(linkId)) {
        if (src === spotlightSets.activeId || tgt === spotlightSets.activeId) {
          return link.color || "#818cf8"
        }
        return "rgba(129, 140, 248, 0.6)"
      }

      // Dim unrelated links
      return "rgba(63, 63, 70, 0.08)"
    },
    [spotlightSets]
  )

  // Number of particles per link
  const getLinkParticles = useCallback(
    (link: any) => {
      if (physics.particleDensity === 0) return 0
      const src = typeof link.source === "object" ? link.source.id : link.source
      const tgt = typeof link.target === "object" ? link.target.id : link.target
      const linkId = link.id || `${src}-${tgt}`

      if (spotlightSets) {
        return spotlightSets.links.has(linkId) ? physics.particleDensity * 2 : 0
      }
      return physics.particleDensity
    },
    [physics.particleDensity, spotlightSets]
  )

  // Rich HTML tooltip for 3D Viewport
  const getNodeTooltip = useCallback((node: any) => {
    const color = node.color || "#818cf8"
    const group = node.group || node.pod || "General"
    const isInvalid = node.status === "invalid"
    return `
      <div style="background: rgba(9, 9, 11, 0.96); border: 1px solid #27272a; padding: 8px 12px; border-radius: 8px; font-family: ui-monospace, monospace; color: #fafafa; box-shadow: 0 16px 36px rgba(0,0,0,0.7); pointer-events: none;">
        <div style="font-weight: 700; font-size: 13px; color: #fff; display: flex; align-items: center; gap: 6px;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};"></span>
          ${node.label}
        </div>
        <div style="font-size: 10px; color: ${color}; margin-top: 3px; font-weight: 600;">
          ${node.type.toUpperCase()} &bull; ${group} ${isInvalid ? ' &bull; <span style="color:#f43f5e">INVALIDATED</span>' : ""}
        </div>
        ${node.description ? `<div style="font-size: 10px; color:#a1a1aa; margin-top: 4px; max-width: 230px; line-height: 1.3;">${node.description}</div>` : ""}
      </div>
    `
  }, [])

  // Copy Cypher query snippet to clipboard
  const handleCopyCypher = (nodeId: string) => {
    const query = `MATCH (n {id: "${nodeId}"})-[r]-(m)\nRETURN n, r, m\nLIMIT 25;`
    navigator.clipboard.writeText(query)
    setCopiedCypher(true)
    setTimeout(() => setCopiedCypher(false), 2000)
  }

  // Find incoming & outgoing edges for selected node
  const nodeSynapses = useMemo(() => {
    if (!selectedNode) return { incoming: [], outgoing: [] }
    const incoming: NeuronLink[] = []
    const outgoing: NeuronLink[] = []

    filteredData.links.forEach((l) => {
      const srcId = typeof l.source === "object" && l.source !== null ? (l.source as NeuronNode).id : String(l.source)
      const tgtId = typeof l.target === "object" && l.target !== null ? (l.target as NeuronNode).id : String(l.target)

      if (srcId === selectedNode.id) {
        outgoing.push(l)
      } else if (tgtId === selectedNode.id) {
        incoming.push(l)
      }
    })

    return { incoming, outgoing }
  }, [selectedNode, filteredData.links])

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full min-h-[640px] bg-[#09090b] overflow-hidden rounded-xl border border-zinc-800 shadow-2xl flex flex-col select-none"
    >
      {/* TOP HEADER CONTROLS */}
      <div className="absolute top-3 left-3 right-3 z-20 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Left Toolbar */}
        <div className="flex flex-wrap items-center gap-2 pointer-events-auto">
          {/* Mode Switcher: 2D Canvas vs 3D WebGL */}
          <div className="flex items-center bg-zinc-900/90 p-1 border border-zinc-800 rounded-lg backdrop-blur-md shadow-lg">
            <button
              onClick={() => {
                setViewMode("2d")
                setIsRotating(false)
              }}
              className={`px-2.5 py-1 text-xs font-mono font-semibold rounded-md transition flex items-center gap-1.5 ${
                viewMode === "2d"
                  ? "bg-indigo-600 text-white shadow"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
              title="Obsidian 2D Canvas View (High performance & precision)"
            >
              <Radio className="w-3.5 h-3.5" />
              <span>2D Obsidian</span>
            </button>
            <button
              onClick={() => setViewMode("3d")}
              className={`px-2.5 py-1 text-xs font-mono font-semibold rounded-md transition flex items-center gap-1.5 ${
                viewMode === "3d"
                  ? "bg-indigo-600 text-white shadow"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
              title="3D WebGL Neural Mesh View"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-300" />
              <span>3D Neural</span>
            </button>
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder="Search neuron label, role..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-xs bg-zinc-900/90 focus:bg-zinc-900 border border-zinc-800 focus:border-indigo-500/60 rounded-lg text-zinc-200 placeholder-zinc-500 focus:outline-none font-mono w-44 sm:w-56 transition backdrop-blur-md shadow"
            />
          </div>

          {/* Category Filter Pills */}
          <div className="hidden sm:flex items-center gap-1 bg-zinc-900/90 p-1 border border-zinc-800 rounded-lg backdrop-blur-md shadow">
            {(
              [
                { id: "all", label: "All", dot: undefined },
                { id: "subagent", label: "Agents", dot: "#818cf8" },
                { id: "category", label: "Hubs", dot: "#38bdf8" },
                { id: "fact_entity", label: "Facts", dot: "#10b981" },
                { id: "invalid", label: "Invalidated", dot: "#f43f5e" },
              ] as const
            ).map((filter) => (
              <button
                key={filter.id}
                onClick={() => setSelectedFilter(filter.id)}
                className={`px-2 py-1 text-[11px] font-mono rounded-md transition flex items-center gap-1.5 ${
                  selectedFilter === filter.id
                    ? "bg-zinc-800 text-zinc-100 font-semibold border border-zinc-700 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {filter.dot && (
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: filter.dot }}
                  />
                )}
                <span>{filter.label}</span>
              </button>
            ))}
          </div>

          {/* Physics Forces Popover Button */}
          <button
            onClick={() => setShowPhysicsPanel((prev) => !prev)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono border transition backdrop-blur-md shadow ${
              showPhysicsPanel
                ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                : "bg-zinc-900/90 text-zinc-300 border-zinc-800 hover:text-zinc-100 hover:bg-zinc-800"
            }`}
            title="Obsidian Physics & Forces Slider"
          >
            <Sliders className="w-3.5 h-3.5 text-indigo-400" />
            <span className="hidden md:inline">Physics</span>
          </button>

          {/* 3D Orbit toggle (only if 3D) */}
          {viewMode === "3d" && (
            <button
              onClick={() => setIsRotating((prev) => !prev)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono border transition backdrop-blur-md ${
                isRotating
                  ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                  : "bg-zinc-900/90 text-zinc-400 border-zinc-800 hover:text-zinc-200"
              }`}
            >
              <RotateCw className={`w-3.5 h-3.5 ${isRotating ? "animate-spin" : ""}`} />
              <span>{isRotating ? "Orbiting" : "Static"}</span>
            </button>
          )}

          {/* Recenter */}
          <button
            onClick={handleRecenter}
            className="p-1.5 rounded-lg text-xs font-mono bg-zinc-900/90 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition backdrop-blur-md shadow"
            title="Recenter Camera View"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>

          {/* Reload data */}
          <button
            onClick={fetchGraph}
            className="p-1.5 rounded-lg text-xs font-mono bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 transition backdrop-blur-md shadow"
            title="Reload from Graphiti API"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Right Status Badge */}
        <div className="flex items-center gap-2 pointer-events-auto">
          <div
            className={`px-2.5 py-1 rounded-lg text-[10px] font-mono flex items-center gap-1.5 border backdrop-blur-md shadow ${
              isLiveApi
                ? "bg-emerald-950/60 border-emerald-500/30 text-emerald-300"
                : "bg-amber-950/50 border-amber-500/30 text-amber-300"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isLiveApi ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
              }`}
            />
            <span>{isLiveApi ? "Live Graphiti DB" : "Demo Fallback Mode"}</span>
          </div>
        </div>
      </div>

      {/* OBSIDIAN FORCES / PHYSICS FLOATING PANEL */}
      {showPhysicsPanel && (
        <div className="absolute top-16 left-3 z-30 w-72 bg-zinc-900/95 backdrop-blur-xl border border-zinc-800 rounded-xl p-4 shadow-2xl text-xs font-mono text-zinc-300 animate-in fade-in duration-200">
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-zinc-800">
            <span className="font-semibold text-zinc-100 flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-indigo-400" />
              Obsidian Physics Sliders
            </span>
            <button
              onClick={() => setPhysics(DEFAULT_PHYSICS)}
              className="text-[10px] text-zinc-500 hover:text-zinc-300 underline"
            >
              Reset
            </button>
          </div>

          <div className="space-y-3">
            {/* Repel Force (Charge) */}
            <div>
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-zinc-400">Repel Force (Charge)</span>
                <span className="text-indigo-400">{physics.repelForce}</span>
              </div>
              <input
                type="range"
                min="-600"
                max="-50"
                step="10"
                value={physics.repelForce}
                onChange={(e) =>
                  setPhysics((p) => ({ ...p, repelForce: Number(e.target.value) }))
                }
                className="w-full accent-indigo-500 bg-zinc-800 h-1.5 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* Link Distance */}
            <div>
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-zinc-400">Link Distance</span>
                <span className="text-indigo-400">{physics.linkDistance}px</span>
              </div>
              <input
                type="range"
                min="30"
                max="180"
                step="5"
                value={physics.linkDistance}
                onChange={(e) =>
                  setPhysics((p) => ({ ...p, linkDistance: Number(e.target.value) }))
                }
                className="w-full accent-indigo-500 bg-zinc-800 h-1.5 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* Center Gravity */}
            <div>
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-zinc-400">Center Gravity</span>
                <span className="text-indigo-400">{physics.centerGravity.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0.01"
                max="0.4"
                step="0.01"
                value={physics.centerGravity}
                onChange={(e) =>
                  setPhysics((p) => ({ ...p, centerGravity: Number(e.target.value) }))
                }
                className="w-full accent-indigo-500 bg-zinc-800 h-1.5 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* Particle Speed */}
            <div>
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-zinc-400">Synaptic Flow Speed</span>
                <span className="text-indigo-400">{physics.particleSpeed.toFixed(3)}</span>
              </div>
              <input
                type="range"
                min="0.001"
                max="0.015"
                step="0.001"
                value={physics.particleSpeed}
                onChange={(e) =>
                  setPhysics((p) => ({ ...p, particleSpeed: Number(e.target.value) }))
                }
                className="w-full accent-indigo-500 bg-zinc-800 h-1.5 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* Node Size Scale */}
            <div>
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-zinc-400">Node Sizing Scale</span>
                <span className="text-indigo-400">{physics.nodeSizeScale.toFixed(1)}x</span>
              </div>
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.1"
                value={physics.nodeSizeScale}
                onChange={(e) =>
                  setPhysics((p) => ({ ...p, nodeSizeScale: Number(e.target.value) }))
                }
                className="w-full accent-indigo-500 bg-zinc-800 h-1.5 rounded-lg appearance-none cursor-pointer"
              />
            </div>
          </div>
        </div>
      )}

      {/* ERROR BANNER */}
      {error && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm">
          <div className="bg-rose-500/10 border border-rose-500/30 p-5 rounded-xl text-center max-w-md shadow-2xl">
            <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto mb-2" />
            <p className="text-rose-300 text-xs font-mono mb-3">{error}</p>
            <button
              onClick={fetchGraph}
              className="text-xs px-3.5 py-1.5 bg-rose-500/20 text-rose-300 rounded-lg border border-rose-500/40 hover:bg-rose-500/30 transition font-mono"
            >
              Muat Ulang
            </button>
          </div>
        </div>
      )}

      {/* GRAPH CANVAS / WEBGL RENDERER */}
      <div className="flex-1 w-full h-full relative">
        {dimensions.width > 0 && dimensions.height > 0 && (
          <>
            {viewMode === "2d" ? (
              <ForceGraph2D
                ref={fgRef as any}
                width={dimensions.width}
                height={dimensions.height}
                graphData={filteredData}
                backgroundColor="#09090b"
                nodeCanvasObject={drawNode2D}
                nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                  const r = Math.max(5, (node.size ? node.size / 2.5 : 5) * physics.nodeSizeScale + 4)
                  ctx.beginPath()
                  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false)
                  ctx.fillStyle = color
                  ctx.fill()
                }}
                linkColor={getLinkColor2D}
                linkWidth={(link: any) => {
                  const src = typeof link.source === "object" ? link.source.id : link.source
                  const tgt = typeof link.target === "object" ? link.target.id : link.target
                  const isHighlighted = spotlightSets?.links.has(link.id || `${src}-${tgt}`)
                  return isHighlighted ? 2.2 : 1.1
                }}
                linkDirectionalParticles={getLinkParticles}
                linkDirectionalParticleSpeed={physics.particleSpeed}
                linkDirectionalParticleWidth={2.4}
                linkDirectionalParticleColor={(link: any) => link.color || "#818cf8"}
                onNodeHover={(node: any) => setHoveredNode(node as NeuronNode | null)}
                onNodeClick={(node: any) => handleNodeClick(node as NeuronNode)}
                onBackgroundClick={() => {
                  setSelectedNode(null)
                  setHoveredNode(null)
                }}
                cooldownTicks={100}
                d3AlphaDecay={0.02}
                d3VelocityDecay={0.3}
              />
            ) : (
              <ForceGraph3D
                ref={fgRef as any}
                width={dimensions.width}
                height={dimensions.height}
                graphData={filteredData}
                nodeLabel={getNodeTooltip}
                nodeColor={(node: any) => node.color || "#818cf8"}
                nodeRelSize={4.5}
                nodeVal={(node: any) => Math.max((node.size || 12) / 3 * physics.nodeSizeScale, 2.5)}
                nodeResolution={24}
                nodeOpacity={0.92}
                linkWidth={1.2}
                linkColor={(link: any) => link.color || "rgba(100, 116, 139, 0.4)"}
                linkDirectionalParticles={physics.particleDensity}
                linkDirectionalParticleSpeed={physics.particleSpeed}
                linkDirectionalParticleWidth={2.0}
                linkDirectionalParticleColor={(link: any) => link.color || "#818cf8"}
                backgroundColor="#09090b"
                showNavInfo={false}
                onNodeClick={(node: any) => handleNodeClick(node as NeuronNode)}
                cooldownTicks={100}
              />
            )}
          </>
        )}
      </div>

      {/* BI-TEMPORAL TIMELINE SLIDER (Bottom) */}
      <div className="absolute bottom-12 left-3 right-3 z-20 bg-zinc-900/90 border border-zinc-800/80 rounded-xl p-2.5 backdrop-blur-md shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] font-mono text-zinc-400 mb-1.5">
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-zinc-200 font-semibold">Bi-Temporal Knowledge Horizon</span>
            <span className="text-[10px] text-zinc-500">
              (valid_at vs invalid_at scrubber)
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-indigo-300 font-semibold">
              {new Date(timelineTime).toLocaleDateString("id-ID", {
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>

            {/* Play / Pause timeline button */}
            <button
              onClick={() => setIsPlayingTimeline((prev) => !prev)}
              className="p-1 px-2 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition flex items-center gap-1 text-[10px]"
              title="Play/Pause Timeline Progression"
            >
              {isPlayingTimeline ? (
                <>
                  <Pause className="w-3 h-3 text-amber-400" /> Jeda
                </>
              ) : (
                <>
                  <Play className="w-3 h-3 text-emerald-400" /> Putar
                </>
              )}
            </button>

            {/* Jump to Present */}
            <button
              onClick={() => {
                setIsPlayingTimeline(false)
                setTimelineTime(timeBounds.max)
              }}
              className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 transition"
            >
              Terkini (Live)
            </button>
          </div>
        </div>

        {/* Timeline Slider */}
        <div className="relative flex items-center">
          <input
            type="range"
            min={timeBounds.min}
            max={timeBounds.max}
            step={(timeBounds.max - timeBounds.min) / 100}
            value={timelineTime}
            onChange={(e) => {
              setIsPlayingTimeline(false)
              setTimelineTime(Number(e.target.value))
            }}
            className="w-full accent-indigo-500 bg-zinc-800 h-2 rounded-lg appearance-none cursor-pointer"
          />
        </div>
      </div>

      {/* BOTTOM LEGEND & METRICS BAR */}
      <div className="absolute bottom-2 left-3 right-3 z-20 flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 rounded-lg bg-zinc-950/80 border border-zinc-900 backdrop-blur-md text-[10px] font-mono text-zinc-400">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 text-zinc-300">
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            <span>Nodes: {filteredData.nodes.length}</span>
          </span>
          <span className="flex items-center gap-1.5 text-zinc-300">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Synapses: {filteredData.links.length}</span>
          </span>
          <span className="hidden sm:flex items-center gap-1 text-emerald-400">
            <Activity className="w-3 h-3 animate-pulse" />
            <span>60 FPS Dynamic Force Simulation</span>
          </span>
        </div>

        {/* Category Color Legend */}
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-[#818cf8]" /> Subagent (Indigo)
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-[#38bdf8]" /> Hub (Sky)
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-[#10b981]" /> Active Fact (Emerald)
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full border border-dashed border-[#f43f5e] bg-[#f43f5e]" />{" "}
            Invalidated (Rose)
          </span>
        </div>
      </div>

      {/* SIDE INSPECTION DRAWER */}
      {selectedNode && (
        <div className="absolute top-3 right-3 bottom-14 z-40 w-84 sm:w-96 bg-zinc-900/98 backdrop-blur-2xl border border-zinc-800 rounded-xl shadow-2xl flex flex-col animate-in slide-in-from-right duration-300 overflow-hidden">
          {/* Drawer Header */}
          <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/60">
            <div className="flex items-center gap-2.5 truncate">
              <div
                className="w-4 h-4 rounded-full flex-shrink-0 shadow-lg border border-white/20"
                style={{ backgroundColor: selectedNode.color }}
              />
              <div className="truncate">
                <h3 className="text-xs font-semibold text-zinc-100 truncate">
                  {selectedNode.label}
                </h3>
                <div className="flex items-center gap-1.5 text-[10px] font-mono">
                  <span className="text-indigo-400 font-medium">
                    {selectedNode.type.toUpperCase()}
                  </span>
                  <span className="text-zinc-600">&bull;</span>
                  <span className="text-zinc-400">
                    {selectedNode.group || selectedNode.pod || "General"}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="p-1 hover:bg-zinc-800 rounded-lg text-zinc-500 hover:text-zinc-200 transition"
              title="Close Drawer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="p-4 overflow-y-auto space-y-4 flex-1 text-xs">
            {/* Bi-Temporal Status Banner */}
            <div
              className={`p-3 rounded-lg border flex items-start gap-2.5 ${
                selectedNode.status === "invalid"
                  ? "bg-rose-500/10 border-rose-500/30 text-rose-300"
                  : "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
              }`}
            >
              {selectedNode.status === "invalid" ? (
                <History className="w-4 h-4 text-rose-400 mt-0.5 flex-shrink-0" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
              )}
              <div className="text-[11px] font-mono">
                <div className="font-semibold">
                  {selectedNode.status === "invalid"
                    ? "Status: INVALIDATED / REPLACED"
                    : "Status: ACTIVE MEMORY FACT"}
                </div>
                <div className="text-[10px] opacity-80 mt-1">
                  Valid:{" "}
                  {selectedNode.valid_at
                    ? new Date(selectedNode.valid_at).toLocaleDateString("id-ID")
                    : "Inception"}
                  {selectedNode.invalid_at && (
                    <>
                      {" "}
                      &bull; Invalidated:{" "}
                      {new Date(selectedNode.invalid_at).toLocaleDateString("id-ID")}
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Centrality & Graph Metrics */}
            <div className="grid grid-cols-3 gap-2">
              <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800 text-center">
                <div className="text-[10px] text-zinc-500 font-mono">Degree</div>
                <div className="text-sm font-semibold text-indigo-400 font-mono mt-0.5">
                  {selectedNode.degree || 0}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800 text-center">
                <div className="text-[10px] text-zinc-500 font-mono">In-Synapses</div>
                <div className="text-sm font-semibold text-emerald-400 font-mono mt-0.5">
                  {nodeSynapses.incoming.length}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800 text-center">
                <div className="text-[10px] text-zinc-500 font-mono">Out-Synapses</div>
                <div className="text-sm font-semibold text-sky-400 font-mono mt-0.5">
                  {nodeSynapses.outgoing.length}
                </div>
              </div>
            </div>

            {/* Metadata Fields */}
            <div className="space-y-2.5 p-3 rounded-lg bg-zinc-950/60 border border-zinc-800">
              <DrawerRow icon={Info} label="Type" value={selectedNode.type} />
              {selectedNode.role && <DrawerRow icon={Cpu} label="Role" value={selectedNode.role} />}
              {selectedNode.trust_level && (
                <DrawerRow icon={Shield} label="Trust Level" value={selectedNode.trust_level} />
              )}
              {selectedNode.pod && <DrawerRow icon={Database} label="Pod" value={selectedNode.pod} />}
              {selectedNode.model_policy && (
                <DrawerRow icon={Layers} label="Model Policy" value={selectedNode.model_policy} />
              )}
              {selectedNode.episode_run_id && (
                <DrawerRow
                  icon={History}
                  label="Episode Source"
                  value={selectedNode.episode_run_id}
                />
              )}
            </div>

            {/* Description */}
            {selectedNode.description && (
              <div className="p-3 bg-zinc-950/60 rounded-lg border border-zinc-800">
                <p className="text-[10px] text-zinc-500 uppercase font-semibold mb-1 font-mono">
                  Deskripsi / Memory Triplet
                </p>
                <p className="text-xs text-zinc-300 leading-relaxed italic">
                  &ldquo;{selectedNode.description}&rdquo;
                </p>
              </div>
            )}

            {/* Capabilities */}
            {selectedNode.capabilities && selectedNode.capabilities.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] text-zinc-500 uppercase font-semibold font-mono">
                  Capabilities ({selectedNode.capabilities.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {selectedNode.capabilities.map((cap, i) => (
                    <span
                      key={i}
                      className="text-[9px] px-2 py-0.5 rounded-md bg-zinc-800 text-zinc-300 border border-zinc-700 font-mono"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Connected Synapses List */}
            <div className="space-y-2">
              <p className="text-[10px] text-zinc-500 uppercase font-semibold font-mono flex items-center justify-between">
                <span>Connected Synapses ({nodeSynapses.incoming.length + nodeSynapses.outgoing.length})</span>
                <span className="text-[9px] text-zinc-600">Klik untuk navigasi</span>
              </p>
              <div className="max-h-36 overflow-y-auto space-y-1 pr-1 font-mono text-[10px]">
                {nodeSynapses.outgoing.map((link, idx) => {
                  const tgtId =
                    typeof link.target === "object" && link.target !== null
                      ? (link.target as NeuronNode).id
                      : String(link.target)
                  const tgtNode = rawData.nodes.find((n) => n.id === tgtId)
                  return (
                    <button
                      key={`out-${idx}`}
                      onClick={() => tgtNode && handleNodeClick(tgtNode)}
                      className="w-full p-1.5 rounded bg-zinc-950/70 hover:bg-zinc-800/80 border border-zinc-800 flex items-center justify-between text-left transition"
                    >
                      <div className="truncate flex items-center gap-1.5">
                        <ChevronRight className="w-3 h-3 text-indigo-400" />
                        <span className="text-zinc-400 font-medium">{link.relation}</span>
                        <span className="text-zinc-600">&rarr;</span>
                        <span className="text-zinc-200">{tgtNode?.label || tgtId}</span>
                      </div>
                    </button>
                  )
                })}
                {nodeSynapses.incoming.map((link, idx) => {
                  const srcId =
                    typeof link.source === "object" && link.source !== null
                      ? (link.source as NeuronNode).id
                      : String(link.source)
                  const srcNode = rawData.nodes.find((n) => n.id === srcId)
                  return (
                    <button
                      key={`in-${idx}`}
                      onClick={() => srcNode && handleNodeClick(srcNode)}
                      className="w-full p-1.5 rounded bg-zinc-950/70 hover:bg-zinc-800/80 border border-zinc-800 flex items-center justify-between text-left transition"
                    >
                      <div className="truncate flex items-center gap-1.5">
                        <ChevronRight className="w-3 h-3 text-emerald-400 rotate-180" />
                        <span className="text-zinc-200">{srcNode?.label || srcId}</span>
                        <span className="text-zinc-600">&rarr;</span>
                        <span className="text-zinc-400 font-medium">{link.relation}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* FalkorDB / Graphiti Cypher Query Preview */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400">
                <span className="flex items-center gap-1">
                  <Code2 className="w-3 h-3 text-indigo-400" />
                  Cypher Query (Graphiti Engine)
                </span>
                <button
                  onClick={() => handleCopyCypher(selectedNode.id)}
                  className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300"
                >
                  {copiedCypher ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-400" /> Disalin
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" /> Salin
                    </>
                  )}
                </button>
              </div>
              <pre className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800 text-[10px] font-mono text-indigo-300/90 overflow-x-auto leading-relaxed">
{`MATCH (n {id: "${selectedNode.id}"})-[r]-(m)
RETURN n, r, m
LIMIT 25;`}
              </pre>
            </div>

            {/* Focus Viewport Action Button */}
            <button
              onClick={() => handleNodeClick(selectedNode)}
              className="w-full py-2 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-mono font-medium flex items-center justify-center gap-2 transition shadow-md"
            >
              <Eye className="w-3.5 h-3.5" />
              Sorot & Fokuskan Viewport
            </button>
          </div>

          {/* Drawer Footer */}
          <div className="p-3 border-t border-zinc-800 bg-zinc-950/60 flex items-center justify-between text-[10px] font-mono text-zinc-500">
            <span className="truncate max-w-[190px]">ID: {selectedNode.id}</span>
            <span className="text-zinc-400">FalkorDB v2.0</span>
          </div>
        </div>
      )}
    </div>
  )
}

function DrawerRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value?: string
}) {
  if (!value) return null
  return (
    <div className="flex items-center justify-between gap-2 font-mono">
      <div className="flex items-center gap-1.5 text-zinc-500">
        <Icon className="w-3 h-3 text-zinc-400" />
        <span className="text-[10px]">{label}</span>
      </div>
      <span className="text-xs text-zinc-200 font-mono truncate max-w-[170px]">{value}</span>
    </div>
  )
}
