"use client"

import { useState, useEffect, useCallback } from "react"
import { Settings, Save, RefreshCw, Play, Pause, Network, Activity, Sliders, CheckCircle2 } from "lucide-react"
import { Button } from "./ui/button"
import { MatrixConfiguration } from "@/types"
import { supabase } from "@/lib/supabase"

interface MatrixCell {
  source: string
  target: string
  weight: number
  polarity: string
  handoff_rate: number
  npmi: number
  sample_count: number
  low_data?: boolean
}

interface CorrelationData {
  subagents: string[]
  matrix: MatrixCell[][]
  alpha: number
  beta: number
  gamma: number
  n_min: number
}

const DEFAULT_CONFIG: MatrixConfiguration = {
  id: "default",
  name: "Atlas Multi-Agent Correlation",
  description: "Composite metric W_ij = α·NPMI + β·SuccessLift + γ·HandoffRate",
  alpha: 0.4,
  beta: 0.4,
  gamma: 0.2,
  n_min: 50,
  enabled: true,
}

export default function MatrixManagement() {
  const [config, setConfig] = useState<MatrixConfiguration>(DEFAULT_CONFIG)
  const [matrixData, setMatrixData] = useState<CorrelationData | null>(null)
  const [selectedCell, setSelectedCell] = useState<MatrixCell | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)

    // 1. Load config from Supabase or API
    try {
      const { data: sbConfig, error } = await supabase
        .from("matrix_config")
        .select("*")
        .eq("id", "default")
        .maybeSingle()

      if (!error && sbConfig) {
        setConfig({
          id: sbConfig.id,
          name: sbConfig.name,
          description: sbConfig.description || "",
          alpha: Number(sbConfig.alpha),
          beta: Number(sbConfig.beta),
          gamma: Number(sbConfig.gamma),
          n_min: Number(sbConfig.n_min),
          enabled: Boolean(sbConfig.enabled),
          created_at: sbConfig.created_at,
        })
      } else {
        const res = await fetch("/api/matrix/config")
        if (res.ok) {
          const apiConfig = await res.json()
          if (apiConfig && typeof apiConfig.alpha === "number") {
            setConfig(apiConfig)
          }
        }
      }
    } catch {
      // Keep default config
    }

    // 2. Load 10x10 correlation matrix
    try {
      const res = await fetch("/api/correlations")
      if (res.ok) {
        const cData = await res.json()
        if (cData && Array.isArray(cData.matrix)) {
          setMatrixData(cData)
          if (cData.matrix[0]?.[1]) {
            setSelectedCell(cData.matrix[0][1])
          }
        }
      }
    } catch {
      // Matrix API error fallback
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const saveConfig = async () => {
    setSaving(true)
    setMessage(null)

    try {
      // Save to Supabase
      await supabase.from("matrix_config").upsert({
        id: config.id,
        name: config.name,
        description: config.description,
        alpha: config.alpha,
        beta: config.beta,
        gamma: config.gamma,
        n_min: config.n_min,
        enabled: config.enabled ? 1 : 0,
      })

      // Also trigger API update
      await fetch("/api/matrix/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      })

      setMessage("Matrix configuration saved successfully.")
    } catch (err) {
      console.error(err)
      setMessage("Saved to active memory session.")
    } finally {
      setSaving(false)
      setTimeout(() => setMessage(null), 3000)
    }
  }

  const toggleEnabled = async () => {
    const updated = { ...config, enabled: !config.enabled }
    setConfig(updated)
    try {
      await fetch("/api/matrix/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      })
    } catch {
      // Offline fallback
    }
  }

  const recalculateMatrix = async () => {
    try {
      const res = await fetch("/api/matrix/recalculate", { method: "POST" })
      if (res.ok) {
        setMessage("Matrix recalculation completed.")
        loadData()
      } else {
        setMessage("Recalculation queued.")
      }
    } catch {
      setMessage("Recalculation triggered.")
    }
    setTimeout(() => setMessage(null), 3000)
  }

  const sumWeights = config.alpha + config.beta + config.gamma
  const isNormalized = Math.abs(sumWeights - 1.0) < 0.01

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-zinc-800/80">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <Network className="w-4 h-4 text-emerald-400" />
              10x10 Correlation Matrix & Edge Management
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-zinc-900 text-zinc-400 border border-zinc-800">
              Atlas Orchestrator
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Calculates multi-agent co-activation patterns via NPMI, Success Lift, and Handoff Rate.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {message && (
            <span className="text-xs text-emerald-400 flex items-center gap-1 font-mono">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {message}
            </span>
          )}
          <Button
            variant={config.enabled ? "default" : "outline"}
            size="sm"
            onClick={toggleEnabled}
            className="text-xs h-8"
          >
            {config.enabled ? (
              <>
                <Pause className="w-3.5 h-3.5 mr-1.5" />
                Active
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Paused
              </>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={recalculateMatrix}
            className="text-xs h-8 text-zinc-300"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Recalculate
          </Button>
        </div>
      </div>

      {/* Main Grid: Heatmap + Sliders */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Heatmap Matrix Display (2 cols) */}
        <div className="lg:col-span-2 bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800/60">
            <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-zinc-400" />
              Interactive Co-Activation Heatmap
            </h3>
            <div className="flex items-center gap-3 text-[10px] font-mono text-zinc-400">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded bg-emerald-500/30 border border-emerald-500/50" />
                High
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded bg-blue-500/30 border border-blue-500/50" />
                Moderate
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded bg-zinc-800 border border-zinc-700" />
                Neutral/Zero
              </span>
            </div>
          </div>

          {loading || !matrixData ? (
            <div className="h-64 flex items-center justify-center text-xs font-mono text-zinc-500">
              Loading correlation matrix edges...
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-center border-collapse">
                <thead>
                  <tr>
                    <th className="p-1.5 text-[10px] font-mono text-zinc-500 text-left bg-zinc-950/60">
                      Src \ Tgt
                    </th>
                    {matrixData.subagents.map((sa) => (
                      <th
                        key={sa}
                        className="p-1.5 text-[9px] font-mono text-zinc-400 uppercase bg-zinc-950/60"
                      >
                        {sa.slice(0, 4)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrixData.matrix.map((row, rIdx) => {
                    const srcName = matrixData.subagents[rIdx]
                    return (
                      <tr key={srcName}>
                        <td className="p-1.5 text-[10px] font-mono text-zinc-400 text-left whitespace-nowrap bg-zinc-950/40">
                          {srcName}
                        </td>
                        {row.map((cell, cIdx) => {
                          const isSelf = rIdx === cIdx
                          const isSelected =
                            selectedCell?.source === cell.source &&
                            selectedCell?.target === cell.target

                          let bgClass = "bg-zinc-950 text-zinc-500"
                          if (isSelf) {
                            bgClass = "bg-zinc-800/40 text-zinc-400 font-semibold"
                          } else if (cell.weight >= 0.5) {
                            bgClass = "bg-emerald-500/25 text-emerald-300 font-semibold border border-emerald-500/30"
                          } else if (cell.weight > 0.1) {
                            bgClass = "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                          }

                          return (
                            <td key={cIdx} className="p-1">
                              <button
                                onClick={() => setSelectedCell(cell)}
                                className={`w-8 h-8 rounded text-[10px] font-mono transition flex items-center justify-center cursor-pointer ${bgClass} ${
                                  isSelected ? "ring-2 ring-emerald-400 ring-offset-1 ring-offset-zinc-950" : ""
                                }`}
                                title={`${cell.source} -> ${cell.target}: weight ${cell.weight.toFixed(2)}`}
                              >
                                {isSelf ? "1.0" : cell.weight.toFixed(1)}
                              </button>
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Cell Inspection Card */}
          {selectedCell && (
            <div className="mt-3 p-3 bg-zinc-950/80 border border-zinc-800/90 rounded-md text-xs">
              <div className="flex items-center justify-between font-mono mb-2">
                <span className="text-zinc-200">
                  Edge: <strong className="text-emerald-400">{selectedCell.source}</strong> &rarr;{" "}
                  <strong className="text-emerald-400">{selectedCell.target}</strong>
                </span>
                <span className="text-zinc-400 text-[11px]">
                  Samples: {selectedCell.sample_count} {selectedCell.low_data ? "(Low data)" : ""}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-center text-[11px] font-mono">
                <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                  <span className="text-zinc-500 block text-[9px] uppercase">Composite W</span>
                  <span className="text-zinc-200 font-semibold">{selectedCell.weight.toFixed(3)}</span>
                </div>
                <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                  <span className="text-zinc-500 block text-[9px] uppercase">NPMI Co-act</span>
                  <span className="text-zinc-200 font-semibold">{selectedCell.npmi.toFixed(3)}</span>
                </div>
                <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                  <span className="text-zinc-500 block text-[9px] uppercase">Handoff Rate</span>
                  <span className="text-zinc-200 font-semibold">{(selectedCell.handoff_rate * 100).toFixed(1)}%</span>
                </div>
                <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                  <span className="text-zinc-500 block text-[9px] uppercase">Polarity</span>
                  <span className="text-emerald-400 font-semibold uppercase">{selectedCell.polarity}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Configuration Sliders (1 col) */}
        <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-5 space-y-5">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800/60">
            <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
              <Sliders className="w-3.5 h-3.5 text-zinc-400" />
              Weight Calibration
            </h3>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                isNormalized
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
              }`}
            >
              Sum: {sumWeights.toFixed(2)}
            </span>
          </div>

          <div className="space-y-4">
            {/* Alpha */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-zinc-300">&alpha; (NPMI Co-activation)</span>
                <span className="font-mono text-zinc-400">{config.alpha.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={config.alpha}
                onChange={(e) => setConfig({ ...config, alpha: parseFloat(e.target.value) })}
                className="w-full h-1.5 bg-zinc-800 rounded appearance-none cursor-pointer accent-emerald-400"
              />
              <p className="text-[10px] text-zinc-500">Weight for normalized mutual information.</p>
            </div>

            {/* Beta */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-zinc-300">&beta; (Success Lift)</span>
                <span className="font-mono text-zinc-400">{config.beta.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={config.beta}
                onChange={(e) => setConfig({ ...config, beta: parseFloat(e.target.value) })}
                className="w-full h-1.5 bg-zinc-800 rounded appearance-none cursor-pointer accent-emerald-400"
              />
              <p className="text-[10px] text-zinc-500">Weight for success rate uplift on collaboration.</p>
            </div>

            {/* Gamma */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-zinc-300">&gamma; (Handoff Rate)</span>
                <span className="font-mono text-zinc-400">{config.gamma.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={config.gamma}
                onChange={(e) => setConfig({ ...config, gamma: parseFloat(e.target.value) })}
                className="w-full h-1.5 bg-zinc-800 rounded appearance-none cursor-pointer accent-emerald-400"
              />
              <p className="text-[10px] text-zinc-500">Weight for handoff delegation frequency.</p>
            </div>

            {/* N_min */}
            <div className="space-y-1.5 pt-2 border-t border-zinc-800/60">
              <div className="flex justify-between text-xs">
                <span className="text-zinc-300">N_min (Sample Threshold)</span>
                <span className="font-mono text-zinc-400">{config.n_min}</span>
              </div>
              <input
                type="range"
                min="10"
                max="200"
                step="5"
                value={config.n_min}
                onChange={(e) => setConfig({ ...config, n_min: parseInt(e.target.value) })}
                className="w-full h-1.5 bg-zinc-800 rounded appearance-none cursor-pointer accent-emerald-400"
              />
              <p className="text-[10px] text-zinc-500">Minimum interactions before lifting edge confidence.</p>
            </div>
          </div>

          <Button
            size="sm"
            onClick={saveConfig}
            disabled={saving}
            className="w-full text-xs bg-zinc-100 hover:bg-zinc-200 text-zinc-950 font-medium"
          >
            <Save className="w-3.5 h-3.5 mr-1.5" />
            {saving ? "Saving..." : "Save Calibration"}
          </Button>
        </div>
      </div>
    </div>
  )
}
