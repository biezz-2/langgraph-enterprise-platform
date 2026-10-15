"use client"

import React, { useState } from "react"
import DashboardShell from "@/components/DashboardShell"
import NeuronGraph from "@/components/NeuronGraph"
import { Sparkles, Maximize2, Minimize2 } from "lucide-react"

export default function NeuronGraphPage() {
  const [isFullscreen, setIsFullscreen] = useState(false)

  return (
    <DashboardShell
      activeModuleTitle="Neuron Topology Graph"
      activeModuleSubtitle="Obsidian-Style Interactive Force-Directed Graph &bull; Bi-Temporal Knowledge Engine"
      actions={
        <button
          onClick={() => setIsFullscreen(!isFullscreen)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition"
        >
          {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          <span>{isFullscreen ? "Keluar Fullscreen" : "Layar Penuh"}</span>
        </button>
      }
    >
      <div
        className={`w-full transition-all ${
          isFullscreen
            ? "fixed inset-0 z-50 bg-zinc-950 p-4 flex flex-col"
            : "h-[calc(100vh-14rem)] min-h-[640px] rounded-xl border border-zinc-800/80 overflow-hidden relative"
        }`}
      >
        {isFullscreen && (
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800">
            <span className="text-xs font-mono text-zinc-400">
              Obsidian Neuron Graph — Fullscreen Explorer
            </span>
            <button
              onClick={() => setIsFullscreen(false)}
              className="px-3 py-1 rounded bg-zinc-900 text-xs font-mono text-zinc-300 hover:bg-zinc-800 border border-zinc-700"
            >
              Tutup Fullscreen
            </button>
          </div>
        )}
        <div className="flex-1 w-full h-full relative">
          <NeuronGraph />
        </div>
      </div>
    </DashboardShell>
  )
}
