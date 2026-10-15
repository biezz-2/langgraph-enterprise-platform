"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { generateFallbackCorrelationMatrix } from "@/lib/mockData"
import type { CorrelationMatrixCell } from "@/types"
import {
  Network,
  RotateCcw,
  Sliders,
  CheckCircle2,
  TrendingUp,
  Layers,
  ArrowRight,
  Info,
} from "lucide-react"

export default function MatrixPage() {
  const [data, setData] = useState(generateFallbackCorrelationMatrix())
  const [selectedCell, setSelectedCell] = useState<CorrelationMatrixCell | null>(null)
  const [alpha, setAlpha] = useState<number>(0.4)
  const [beta, setBeta] = useState<number>(0.4)
  const [gamma, setGamma] = useState<number>(0.2)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchMatrix() {
      try {
        const res = await fetch("/api/matrix")
        if (res.ok) {
          const resData = await res.json()
          if (resData && resData.matrix) {
            setData(resData)
          }
        }
      } catch {
        // Fallback active
      }
    }
    fetchMatrix()
  }, [])

  const handleRecalculate = () => {
    // Recompute weights dynamically based on current sliders
    const updated = {
      ...data,
      matrix: data.matrix.map((row) =>
        row.map((cell) => {
          if (cell.source === cell.target) return cell
          const newWeight = Number((alpha * cell.npmi + beta * 0.75 + gamma * cell.handoff_rate).toFixed(3))
          return {
            ...cell,
            weight: newWeight,
            polarity: newWeight >= 0.7 ? "high" : newWeight >= 0.5 ? "medium" : "low",
          }
        })
      ),
      alpha,
      beta,
      gamma,
    }
    setData(updated)
    showToast(`Matriks korelasi 10x10 berhasil di-rekalkulasi dengan α=${alpha}, β=${beta}, γ=${gamma}`)
  }

  const getHeatmapColor = (weight: number, isSelf: boolean) => {
    if (isSelf) return "bg-zinc-800 text-zinc-400 font-bold border-zinc-700"
    if (weight >= 0.85) return "bg-indigo-600 text-white font-bold border-indigo-500"
    if (weight >= 0.7) return "bg-indigo-700/80 text-indigo-100 font-semibold border-indigo-600"
    if (weight >= 0.55) return "bg-indigo-900/60 text-indigo-200 border-indigo-800"
    if (weight >= 0.4) return "bg-zinc-900 text-zinc-300 border-zinc-800"
    return "bg-zinc-950 text-zinc-500 border-zinc-900"
  }

  return (
    <DashboardShell
      activeModuleTitle="Subagent Correlation Matrix"
      activeModuleSubtitle="10x10 NPMI Co-Activation Heatmap &bull; Swarm Handoff Routing Weights"
      actions={
        <button
          onClick={handleRecalculate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow transition"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Rekalkulasi Matriks
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

      {/* Main Grid: Heatmap + Inspector / Sliders */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Heatmap Area */}
        <div className="lg:col-span-8 space-y-4">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 sm:p-5 overflow-hidden">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono flex items-center gap-2">
                <Network className="w-4 h-4 text-indigo-400" />
                10x10 Subagent Co-Activation & Handoff Matrix
              </h2>
              <span className="text-[10px] font-mono text-zinc-500">
                W(i, j) = α·NPMI + β·Affinity + γ·Handoff
              </span>
            </div>

            {/* Matrix Table */}
            <div className="overflow-x-auto pb-2">
              <table className="border-collapse font-mono text-center text-xs">
                <thead>
                  <tr>
                    <th className="p-2 text-[10px] text-zinc-500 font-normal">Src \ Tgt</th>
                    {data.subagents.map((name) => (
                      <th
                        key={name}
                        className="p-2 text-[10px] text-zinc-300 uppercase font-semibold capitalize min-w-[52px]"
                      >
                        {name.slice(0, 3)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.matrix.map((row, rIdx) => {
                    const srcAgent = data.subagents[rIdx]
                    return (
                      <tr key={srcAgent}>
                        <td className="p-2 text-[10px] text-left text-zinc-300 uppercase font-semibold capitalize whitespace-nowrap">
                          {srcAgent}
                        </td>
                        {row.map((cell, cIdx) => {
                          const isSelf = rIdx === cIdx
                          const isSelected =
                            selectedCell?.source === cell.source && selectedCell?.target === cell.target

                          return (
                            <td key={cIdx} className="p-1">
                              <button
                                onClick={() => setSelectedCell(cell)}
                                className={`w-12 h-10 rounded border flex flex-col items-center justify-center transition-all ${
                                  isSelected ? "ring-2 ring-white scale-105 z-10" : ""
                                } ${getHeatmapColor(cell.weight, isSelf)}`}
                              >
                                <span className="text-[11px] leading-tight">
                                  {isSelf ? "1.00" : cell.weight.toFixed(2)}
                                </span>
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

            {/* Legend */}
            <div className="mt-4 pt-3 border-t border-zinc-800/80 flex flex-wrap items-center justify-between text-[10px] font-mono text-zinc-400 gap-2">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-indigo-600 border border-indigo-500" />
                  High Co-activation (&ge; 0.85)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-indigo-700/80 border border-indigo-600" />
                  Moderate (&ge; 0.70)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-indigo-900/60 border border-indigo-800" />
                  Low (&ge; 0.55)
                </span>
              </div>
              <span className="text-zinc-500">Klik sembarang sel untuk inspeksi</span>
            </div>
          </div>
        </div>

        {/* Sidebar: Selected Cell Inspector & Hyperparameter Tuning */}
        <div className="lg:col-span-4 space-y-4">
          {/* Cell Inspector */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3 font-mono">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              Cell Metrics Inspector
            </h3>

            {selectedCell ? (
              <div className="space-y-3 text-xs">
                <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 flex items-center justify-between">
                  <div className="capitalize font-semibold text-zinc-200">
                    {selectedCell.source}
                  </div>
                  <ArrowRight className="w-4 h-4 text-indigo-400" />
                  <div className="capitalize font-semibold text-zinc-200">
                    {selectedCell.target}
                  </div>
                </div>

                <div className="space-y-2 bg-zinc-950 p-3 rounded-lg border border-zinc-800/80 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Combined Weight:</span>
                    <span className="text-emerald-400 font-bold">{selectedCell.weight.toFixed(3)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">NPMI Value:</span>
                    <span className="text-indigo-300 font-semibold">{selectedCell.npmi.toFixed(3)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Handoff Success Rate:</span>
                    <span className="text-zinc-300 font-semibold">
                      {(selectedCell.handoff_rate * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Co-Occurrence Samples:</span>
                    <span className="text-zinc-300">{selectedCell.sample_count} runs</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Routing Polarity:</span>
                    <span className="uppercase text-amber-400 font-semibold">{selectedCell.polarity}</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-xs text-zinc-500 py-4 text-center">
                Pilih sel matriks di sebelah kiri untuk melihat rincian kalkulasi korelasi.
              </p>
            )}
          </div>

          {/* Hyperparameter Sliders */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-4 font-mono text-xs">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-indigo-400" />
              Routing Equation Tuning
            </h3>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-zinc-400 mb-1">
                  <span>α (NPMI Weight)</span>
                  <span className="text-indigo-400">{alpha.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  value={alpha}
                  onChange={(e) => setAlpha(parseFloat(e.target.value))}
                  className="w-full accent-indigo-500"
                />
              </div>

              <div>
                <div className="flex justify-between text-zinc-400 mb-1">
                  <span>β (Affinity Weight)</span>
                  <span className="text-indigo-400">{beta.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  value={beta}
                  onChange={(e) => setBeta(parseFloat(e.target.value))}
                  className="w-full accent-indigo-500"
                />
              </div>

              <div>
                <div className="flex justify-between text-zinc-400 mb-1">
                  <span>γ (Handoff Rate)</span>
                  <span className="text-indigo-400">{gamma.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  value={gamma}
                  onChange={(e) => setGamma(parseFloat(e.target.value))}
                  className="w-full accent-indigo-500"
                />
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800/80 text-[10px] text-zinc-500 flex items-start gap-2">
              <Info className="w-3.5 h-3.5 text-zinc-400 flex-shrink-0 mt-0.5" />
              <span>
                Bobot kombinasi digunakan oleh Atlas supervisor untuk menentukan subagent penerima delegasi berikutnya secara optimal.
              </span>
            </div>
          </div>
        </div>
      </div>
    </DashboardShell>
  )
}
