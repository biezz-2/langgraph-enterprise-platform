"use client"

import React, { useState, useEffect } from "react"
import DashboardShell from "@/components/DashboardShell"
import { FALLBACK_FASTMCP_TOOLS } from "@/lib/mockData"
import type { FastMCPTool } from "@/types"
import {
  FileCode2,
  Terminal,
  Play,
  Search,
  CheckCircle2,
  Shield,
  Layers,
  Code,
  ExternalLink,
  ChevronRight,
} from "lucide-react"

export default function ApiDocsPage() {
  const [tools, setTools] = useState<FastMCPTool[]>(FALLBACK_FASTMCP_TOOLS)
  const [searchQuery, setSearchQuery] = useState<string>("")
  const [selectedTool, setSelectedTool] = useState<FastMCPTool>(FALLBACK_FASTMCP_TOOLS[0])
  const [inputParams, setInputParams] = useState<string>("{}")
  const [executionResult, setExecutionResult] = useState<string | null>(null)
  const [isExecuting, setIsExecuting] = useState<boolean>(false)
  const [activeTab, setActiveTab] = useState<"fastmcp" | "openapi">("fastmcp")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  useEffect(() => {
    async function fetchTools() {
      try {
        const res = await fetch("/api/mcp/tools")
        if (res.ok) {
          const data = await res.json()
          if (Array.isArray(data) && data.length > 0) {
            setTools(data)
          }
        }
      } catch {
        // Fallback active
      }
    }
    fetchTools()
  }, [])

  const filteredTools = tools.filter(
    (t) =>
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.description.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleSelectTool = (tool: FastMCPTool) => {
    setSelectedTool(tool)
    // Pre-populate input params template from properties
    const sample: Record<string, any> = {}
    if (tool.parameters && tool.parameters.properties) {
      const props = tool.parameters.properties
      Object.keys(props).forEach((k) => {
        const prop = props[k]
        sample[k] = prop?.enum ? prop.enum[0] : prop?.type === "number" || prop?.type === "integer" ? 0 : "sample_value"
      })
    }
    setInputParams(JSON.stringify(sample, null, 2))
    setExecutionResult(null)
  }

  const handleExecuteTool = () => {
    setIsExecuting(true)
    setTimeout(() => {
      setIsExecuting(false)
      const simulatedResponse = {
        tool: selectedTool.name,
        status: "success",
        timestamp: new Date().toISOString(),
        execution_time_ms: 48,
        data: {
          result: `Dry-run execution for ${selectedTool.name} completed cleanly.`,
          parameters_received: JSON.parse(inputParams || "{}"),
          server_environment: "fastmcp-python-3.11",
        },
      }
      setExecutionResult(JSON.stringify(simulatedResponse, null, 2))
      showToast(`Tool ${selectedTool.name} berhasil dijalankan (Dry Run)`)
    }, 400)
  }

  return (
    <DashboardShell
      activeModuleTitle="API & FastMCP Explorer"
      activeModuleSubtitle="FastMCP Tool Registry &bull; Tool Annotations &bull; OpenAPI Specification"
      actions={
        <div className="flex items-center gap-2">
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition"
          >
            <span>Swagger UI :8000</span>
            <ExternalLink className="w-3 h-3 text-zinc-500" />
          </a>
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

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-zinc-800 pb-3 mb-6">
        <button
          onClick={() => setActiveTab("fastmcp")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
            activeTab === "fastmcp"
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent"
          }`}
        >
          <Terminal className="w-3.5 h-3.5" />
          FastMCP Tool Explorer ({tools.length} Tools)
        </button>

        <button
          onClick={() => setActiveTab("openapi")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
            activeTab === "openapi"
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent"
          }`}
        >
          <FileCode2 className="w-3.5 h-3.5" />
          OpenAPI REST Spec
        </button>
      </div>

      {activeTab === "fastmcp" ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Tool Directory List (Left) */}
          <div className="lg:col-span-5 space-y-4">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-zinc-500" />
              <input
                type="text"
                placeholder="Cari tool FastMCP..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>

            <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
              {filteredTools.map((tool) => {
                const isSelected = selectedTool.name === tool.name
                const isReadOnly = tool.annotations?.readOnlyHint

                return (
                  <div
                    key={tool.name}
                    onClick={() => handleSelectTool(tool)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? "bg-indigo-950/30 border-indigo-500"
                        : "bg-zinc-900/40 border-zinc-800/80 hover:bg-zinc-900/70 hover:border-zinc-700"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-mono font-semibold text-zinc-200 truncate">
                        {tool.name}
                      </span>
                      <span
                        className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${
                          isReadOnly
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        }`}
                      >
                        {isReadOnly ? "read-only" : "state-mutating"}
                      </span>
                    </div>

                    <p className="text-xs text-zinc-400 mt-1 line-clamp-2">{tool.description}</p>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Tool Inspector & Execution Sandbox (Right) */}
          <div className="lg:col-span-7 space-y-4 font-mono text-xs">
            <div className="p-5 rounded-xl bg-zinc-900/40 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-100">{selectedTool.name}</h3>
                  <p className="text-xs text-zinc-400 mt-0.5">{selectedTool.description}</p>
                </div>
              </div>

              {/* Tool Annotations Badges */}
              <div>
                <span className="text-[10px] uppercase text-zinc-500 font-semibold block mb-1.5">
                  FastMCP Annotations
                </span>
                <div className="flex flex-wrap gap-2 text-[10px]">
                  <span
                    className={`px-2 py-0.5 rounded border ${
                      selectedTool.annotations?.readOnlyHint
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : "bg-zinc-900 text-zinc-500 border-zinc-800"
                    }`}
                  >
                    readOnlyHint: {String(selectedTool.annotations?.readOnlyHint)}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded border ${
                      selectedTool.annotations?.destructiveHint
                        ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                        : "bg-zinc-900 text-zinc-500 border-zinc-800"
                    }`}
                  >
                    destructiveHint: {String(selectedTool.annotations?.destructiveHint)}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded border ${
                      selectedTool.annotations?.idempotentHint
                        ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                        : "bg-zinc-900 text-zinc-500 border-zinc-800"
                    }`}
                  >
                    idempotentHint: {String(selectedTool.annotations?.idempotentHint)}
                  </span>
                </div>
              </div>

              {/* Parameter JSON Schema */}
              <div>
                <span className="text-[10px] uppercase text-zinc-500 font-semibold block mb-1.5">
                  Parameters Schema
                </span>
                <pre className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-300 overflow-x-auto max-h-40">
                  {JSON.stringify(selectedTool.parameters || {}, null, 2)}
                </pre>
              </div>

              {/* Interactive Execution Form */}
              <div className="space-y-2 pt-2 border-t border-zinc-800">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase text-zinc-500 font-semibold">
                    Test Payload (JSON Input)
                  </span>
                  <button
                    onClick={handleExecuteTool}
                    disabled={isExecuting}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow transition disabled:opacity-50"
                  >
                    <Play className="w-3 h-3" />
                    {isExecuting ? "Executing..." : "Execute Dry Run"}
                  </button>
                </div>
                <textarea
                  rows={4}
                  value={inputParams}
                  onChange={(e) => setInputParams(e.target.value)}
                  className="w-full p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Result Preview */}
              {executionResult && (
                <div className="space-y-1.5 pt-2">
                  <span className="text-[10px] uppercase text-emerald-400 font-semibold block">
                    Execution Response (200 OK)
                  </span>
                  <pre className="p-3 rounded-lg bg-zinc-950 border border-emerald-500/30 text-emerald-300 text-[11px] overflow-x-auto max-h-48">
                    {executionResult}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* OpenAPI REST View */
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-4 font-mono text-xs">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Enterprise LangGraph REST API</h3>
              <p className="text-xs text-zinc-400">Base URL: http://localhost:8000/api</p>
            </div>
            <span className="px-2 py-0.5 rounded bg-zinc-950 text-indigo-400 border border-indigo-500/30 text-[11px]">
              OpenAPI 3.1.0
            </span>
          </div>

          <div className="space-y-3">
            {[
              { method: "GET", path: "/api/health", desc: "System health check, cluster version & WAL mode status" },
              { method: "GET", path: "/api/subagents", desc: "List all 10 registered subagents & their contract specs" },
              { method: "GET", path: "/api/runs", desc: "List multi-agent execution runs with DAG steps & cost telemetry" },
              { method: "POST", path: "/api/runs", desc: "Trigger new LangGraph execution run with objective string" },
              { method: "GET", path: "/api/hitl", desc: "Fetch pending Human-in-the-Loop approval requests" },
              { method: "POST", path: "/api/hitl/decision", desc: "Submit human approval/rejection decision with payload diff" },
              { method: "GET", path: "/api/memory", desc: "Bi-temporal fact lookup with valid_time & record_time filtering" },
              { method: "POST", path: "/api/memory/fact", desc: "Store new subject-predicate-object fact into Graphiti" },
              { method: "GET", path: "/api/matrix", desc: "10x10 NPMI co-activation & handoff routing weights" },
              { method: "GET", path: "/api/kanban", desc: "AGENTS.md phase-gate lifecycle board columns & cards" },
            ].map((ep, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-zinc-950 border border-zinc-800/80 flex items-center justify-between gap-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      ep.method === "GET"
                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/30"
                        : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                    }`}
                  >
                    {ep.method}
                  </span>
                  <span className="font-semibold text-zinc-200">{ep.path}</span>
                </div>
                <span className="text-zinc-400 text-[11px] truncate">{ep.desc}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
