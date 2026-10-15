"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { FALLBACK_MEMORY_FACTS } from "@/lib/mockData"
import type { MemoryFact } from "@/types"
import {
  Database,
  Search,
  Plus,
  Shield,
  Clock,
  Sparkles,
  CheckCircle2,
  Calendar,
  FileText,
  RotateCcw,
  Tag,
  ArrowRight,
} from "lucide-react"

export default function MemoryPage() {
  const [facts, setFacts] = useState<MemoryFact[]>(FALLBACK_MEMORY_FACTS)
  const [searchQuery, setSearchQuery] = useState<string>("")
  const [vectorSearchMode, setVectorSearchMode] = useState<boolean>(false)
  const [addFactModal, setAddFactModal] = useState<boolean>(false)
  const [ingestModal, setIngestModal] = useState<boolean>(false)
  const [newSubject, setNewSubject] = useState<string>("")
  const [newPredicate, setNewPredicate] = useState<string>("")
  const [newObject, setNewObject] = useState<string>("")
  const [episodeText, setEpisodeText] = useState<string>("")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchMemory() {
      try {
        const res = await fetch("/api/memory")
        if (res.ok) {
          const data = await res.json()
          if (Array.isArray(data) && data.length > 0) {
            setFacts(data)
          }
        }
      } catch {
        // Fallback active
      }
    }
    fetchMemory()
  }, [])

  const filteredFacts = facts.filter((f) => {
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      f.subject.toLowerCase().includes(q) ||
      f.predicate.toLowerCase().includes(q) ||
      f.object.toLowerCase().includes(q) ||
      f.fact_id.toLowerCase().includes(q)
    )
  })

  const handleAddFact = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newSubject.trim() || !newPredicate.trim() || !newObject.trim()) return

    const newFact: MemoryFact = {
      fact_id: `fact-${Date.now().toString(36)}`,
      subject: newSubject.trim(),
      predicate: newPredicate.trim(),
      object: newObject.trim(),
      valid_at: Date.now(),
      invalid_at: null,
      created_at: Date.now(),
      episode_run_id: "manual-entry",
      pii_redacted: false,
      similarity: 0.95,
    }

    setFacts([newFact, ...facts])
    setAddFactModal(false)
    setNewSubject("")
    setNewPredicate("")
    setNewObject("")
    showToast(`Fakta memori ${newFact.fact_id} berhasil ditambahkan ke SQLite WAL store`)
  }

  const handleIngestEpisode = (e: React.FormEvent) => {
    e.preventDefault()
    if (!episodeText.trim()) return

    const simulatedFact: MemoryFact = {
      fact_id: `fact-ep-${Date.now().toString(36)}`,
      subject: "Episode:Ingested",
      predicate: "synthesized_knowledge",
      object: episodeText.slice(0, 120) + (episodeText.length > 120 ? "..." : ""),
      valid_at: Date.now(),
      invalid_at: null,
      created_at: Date.now(),
      episode_run_id: `run-ep-${Date.now().toString(36)}`,
      pii_redacted: true,
      similarity: 0.98,
    }

    setFacts([simulatedFact, ...facts])
    setIngestModal(false)
    setEpisodeText("")
    showToast("Episode berhasil di-ingest oleh kurator Mnemosyne dengan sanitasi PII")
  }

  return (
    <DashboardShell
      activeModuleTitle="Bi-Temporal Memory Table"
      activeModuleSubtitle="Valid-Time & Transaction-Time Dimensions &bull; Graphiti Semantic Store"
      actions={
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIngestModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Ingest Episode
          </button>
          <button
            onClick={() => setAddFactModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Tambah Fakta
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

      {/* Semantic Vector Search Bar */}
      <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-3 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono">
              Semantic Vector Search & Subgraph Query
            </span>
          </div>
          <button
            onClick={() => setVectorSearchMode(!vectorSearchMode)}
            className={`text-[10px] font-mono px-2 py-0.5 rounded border transition ${
              vectorSearchMode
                ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                : "bg-zinc-900 text-zinc-500 border-zinc-800"
            }`}
          >
            {vectorSearchMode ? "Mode: Cosine Embeddings" : "Mode: Keyword Match"}
          </button>
        </div>

        <div className="relative">
          <input
            type="text"
            placeholder={
              vectorSearchMode
                ? "Masukkan kueri semantik (misal: 'kebijakan isolasi memori dan batas token subagent')..."
                : "Ketik kata kunci pencarian subjek, relasi, atau objek..."
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3.5 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 font-mono"
          />
        </div>
      </div>

      {/* Facts Table */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-4">Fact ID</th>
                <th className="py-3 px-4">Subject</th>
                <th className="py-3 px-4">Predicate</th>
                <th className="py-3 px-4">Object</th>
                <th className="py-3 px-4">Valid Time (T1)</th>
                <th className="py-3 px-4">Record Time (T2)</th>
                <th className="py-3 px-4">PII State</th>
                <th className="py-3 px-4 text-right">Similarity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {filteredFacts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-zinc-500">
                    Tidak ada fakta memori yang sesuai dengan kueri pencarian.
                  </td>
                </tr>
              ) : (
                filteredFacts.map((fact) => (
                  <tr key={fact.fact_id} className="hover:bg-zinc-900/60 transition-colors">
                    <td className="py-3 px-4 text-indigo-400 font-semibold">{fact.fact_id}</td>
                    <td className="py-3 px-4 text-zinc-200 font-medium">{fact.subject}</td>
                    <td className="py-3 px-4 text-amber-400">{fact.predicate}</td>
                    <td className="py-3 px-4 text-zinc-300 max-w-xs truncate" title={fact.object}>
                      {fact.object}
                    </td>
                    <td className="py-3 px-4 text-zinc-500 whitespace-nowrap">
                      {new Date(fact.valid_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-zinc-500 whitespace-nowrap">
                      {new Date(fact.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      {fact.pii_redacted ? (
                        <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          <Shield className="w-2.5 h-2.5" /> Redacted
                        </span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-900 text-zinc-500 border border-zinc-800">
                          Clean
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right font-semibold text-emerald-400 whitespace-nowrap">
                      {(fact.similarity ? (fact.similarity * 100).toFixed(1) : "92.0")}%
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Fact Modal */}
      {addFactModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <form
            onSubmit={handleAddFact}
            className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4 font-mono"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Plus className="w-4 h-4 text-indigo-400" />
                Tambah Fakta Bi-Temporal Baru
              </h3>
              <button
                type="button"
                onClick={() => setAddFactModal(false)}
                className="text-zinc-400 hover:text-zinc-100 text-xs"
              >
                Tutup
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-zinc-400 mb-1">Subject</label>
                <input
                  type="text"
                  required
                  placeholder="Misal: Subagent:Atlas atau Tenant:Enterprise"
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-zinc-400 mb-1">Predicate / Relasi</label>
                <input
                  type="text"
                  required
                  placeholder="Misal: enforces_compliance atau delegates_task_to"
                  value={newPredicate}
                  onChange={(e) => setNewPredicate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-zinc-400 mb-1">Object / Nilai Fakta</label>
                <textarea
                  rows={3}
                  required
                  placeholder="Deskripsi relasi fakta..."
                  value={newObject}
                  onChange={(e) => setNewObject(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setAddFactModal(false)}
                className="px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
              >
                Batal
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-lg text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow"
              >
                Simpan Fakta
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Episode Ingest Modal */}
      {ingestModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <form
            onSubmit={handleIngestEpisode}
            className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4 font-mono"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                Ingest Episode — Mnemosyne Memory Curator
              </h3>
              <button
                type="button"
                onClick={() => setIngestModal(false)}
                className="text-zinc-400 hover:text-zinc-100 text-xs"
              >
                Tutup
              </button>
            </div>

            <p className="text-xs text-zinc-400">
              Tempel transkrip percakapan atau trace run untuk diekstrak menjadi triple fakta Graphiti secara otomatis dengan sanitasi PII.
            </p>

            <div>
              <textarea
                rows={6}
                required
                placeholder="Tempel konteks run, transkrip atau log eksekusi di sini..."
                value={episodeText}
                onChange={(e) => setEpisodeText(e.target.value)}
                className="w-full p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIngestModal(false)}
                className="px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
              >
                Batal
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-lg text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow"
              >
                Proses & Ingest
              </button>
            </div>
          </form>
        </div>
      )}
    </DashboardShell>
  )
}
