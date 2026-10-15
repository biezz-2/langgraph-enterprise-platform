import { NeuronGraphData, NeuronNode, NeuronLink } from "@/types/neuron";

export const MOCK_GRAPHITI_DATA: () => NeuronGraphData = () => {
  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;

  const nodes: NeuronNode[] = [
    // 1. Central Taxonomy Hubs (Sky / Cyan)
    {
      id: "cat-subagent",
      label: "Subagent Taxonomy",
      type: "category",
      group: "Taxonomy",
      color: "#38bdf8",
      size: 26,
      description: "Pusat orkestrasi & registri subagent 10-node LGP v2.0.",
      status: "active",
      icon: "HUB",
    },
    {
      id: "cat-model",
      label: "Model Policy Hub",
      type: "category",
      group: "Policy",
      color: "#38bdf8",
      size: 24,
      description: "Routing model inferensi (Claude 3.5 Sonnet, GPT-4o, Hermes-3).",
      status: "active",
      icon: "HUB",
    },
    {
      id: "cat-architecture",
      label: "Architecture & State",
      type: "category",
      group: "Platform",
      color: "#38bdf8",
      size: 25,
      description: "State graph, checkpointer, and correlation matrix synchronization.",
      status: "active",
      icon: "HUB",
    },
    {
      id: "cat-security",
      label: "Security & Guardrails",
      type: "category",
      group: "Security",
      color: "#38bdf8",
      size: 24,
      description: "Circuit breakers, trust boundaries, OWASP LLM mitigation, & HITL.",
      status: "active",
      icon: "HUB",
    },
    {
      id: "cat-telemetry",
      label: "Telemetry & Logs",
      type: "category",
      group: "Telemetry",
      color: "#38bdf8",
      size: 22,
      description: "Real-time metrics, token burn rate, and audit trailing.",
      status: "active",
      icon: "HUB",
    },

    // 2. Subagents (Indigo)
    {
      id: "agent-atlas",
      label: "Atlas (Orchestrator)",
      type: "subagent",
      group: "Koordinasi",
      color: "#818cf8",
      size: 22,
      role: "Lead Orchestrator",
      pod: "Koordinasi",
      trust_level: "High",
      model_policy: "claude-3-5-sonnet",
      capabilities: ["plan_decomposition", "subagent_dispatch", "state_merge"],
      description: "Primary orchestrator and master planner for multi-agent workflows.",
      status: "active",
      icon: "AT",
    },
    {
      id: "agent-clio",
      label: "Clio (Historiographer)",
      type: "subagent",
      group: "Koordinasi",
      color: "#818cf8",
      size: 20,
      role: "Session Historian",
      pod: "Koordinasi",
      trust_level: "High",
      model_policy: "gpt-4o",
      capabilities: ["session_logging", "audit_record", "changelog_generate"],
      description: "Maintains immutable historical logs and session timelines.",
      status: "active",
      icon: "CL",
    },
    {
      id: "agent-vulcan",
      label: "Vulcan (Code Crafter)",
      type: "subagent",
      group: "Riset & Rekayasa",
      color: "#818cf8",
      size: 21,
      role: "Senior Synthesizer",
      pod: "Riset & Rekayasa",
      trust_level: "Medium-High",
      model_policy: "claude-3-5-sonnet",
      capabilities: ["tool_synthesis", "refactor_engine", "test_runner"],
      description: "Code generation, tool synthesis, and unit testing runner.",
      status: "active",
      icon: "VU",
    },
    {
      id: "agent-athena",
      label: "Athena (Deep Research)",
      type: "subagent",
      group: "Riset & Rekayasa",
      color: "#818cf8",
      size: 20,
      role: "Research Specialist",
      pod: "Riset & Rekayasa",
      trust_level: "High",
      model_policy: "gpt-4o",
      capabilities: ["web_research", "arxiv_ingest", "doc_validation"],
      description: "Literature review, web intelligence, and standards verification.",
      status: "active",
      icon: "ATH",
    },
    {
      id: "agent-hermes",
      label: "Hermes (Comm & Relay)",
      type: "subagent",
      group: "Koordinasi",
      color: "#818cf8",
      size: 21,
      role: "External Messenger",
      pod: "Koordinasi",
      trust_level: "High",
      model_policy: "hermes-3",
      capabilities: ["slack_dispatch", "discord_webhook", "handoff_protocol"],
      description: "Facilitates seamless inter-agent messages and user alerts.",
      status: "active",
      icon: "HE",
    },
    {
      id: "agent-mnemosyne",
      label: "Mnemosyne (Memory KG)",
      type: "subagent",
      group: "Riset & Rekayasa",
      color: "#818cf8",
      size: 21,
      role: "Knowledge Curator",
      pod: "Riset & Rekayasa",
      trust_level: "High",
      model_policy: "text-embedding-3-large",
      capabilities: ["falkordb_sync", "temporal_facts", "cypher_query"],
      description: "Curation of bi-temporal facts, knowledge graph, and Graphiti engine.",
      status: "active",
      icon: "MN",
    },
    {
      id: "agent-janus",
      label: "Janus (Gateway Adapter)",
      type: "subagent",
      group: "Platform",
      color: "#818cf8",
      size: 19,
      role: "Protocol Adapter",
      pod: "Platform",
      trust_level: "Medium-High",
      model_policy: "gpt-4o-mini",
      capabilities: ["rest_api", "mcp_server", "event_stream"],
      description: "Translates external requests into internal LangGraph events.",
      status: "active",
      icon: "JA",
    },
    {
      id: "agent-themis",
      label: "Themis (Security Sentinel)",
      type: "subagent",
      group: "Tata Kelola",
      color: "#818cf8",
      size: 20,
      role: "Governance Auditor",
      pod: "Tata Kelola",
      trust_level: "High",
      model_policy: "gpt-4o",
      capabilities: ["circuit_breaker", "owasp_guard", "pii_redaction"],
      description: "Monitors tool executions and enforces security guardrails.",
      status: "active",
      icon: "TH",
    },
    {
      id: "agent-metron",
      label: "Metron (Telemetry)",
      type: "subagent",
      group: "Platform",
      color: "#818cf8",
      size: 19,
      role: "Metrics Collector",
      pod: "Platform",
      trust_level: "Medium",
      model_policy: "gpt-4o-mini",
      capabilities: ["latency_tracking", "token_counter", "cost_projection"],
      description: "Real-time metrics aggregator and SLA compliance observer.",
      status: "active",
      icon: "ME",
    },
    {
      id: "agent-iris",
      label: "Iris (HITL Dispatcher)",
      type: "subagent",
      group: "Tata Kelola",
      color: "#818cf8",
      size: 19,
      role: "Human-in-the-Loop",
      pod: "Tata Kelola",
      trust_level: "Medium",
      model_policy: "gpt-4o-mini",
      capabilities: ["approval_request", "channel_notifier", "resume_signal"],
      description: "Pauses execution for human approvals during high-risk actions.",
      status: "active",
      icon: "IR",
    },

    // 3. Bi-Temporal Facts (Emerald/Cyan for active, Rose for invalidated)
    {
      id: "fact-sqlite_buffer",
      label: "Memory:LegacyBuffer",
      type: "fact_entity",
      group: "Architecture",
      color: "#f43f5e",
      size: 14,
      subject: "Memory:Buffer",
      predicate: "USES_ENGINE",
      object: "SQLite In-Memory Driver",
      valid_at: new Date(now - 14 * day).toISOString(),
      invalid_at: new Date(now - 7 * day).toISOString(),
      episode_run_id: "ep_run_01j7x001_legacy",
      description: "Fakta lampau: Memory LGP awalnya menggunakan SQLite buffer in-memory.",
      status: "invalid",
      icon: "F",
    },
    {
      id: "fact-graphiti_falkordb",
      label: "Memory:GraphitiEngine",
      type: "fact_entity",
      group: "Architecture",
      color: "#10b981",
      size: 16,
      subject: "Memory:Graphiti",
      predicate: "POWERED_BY",
      object: "FalkorDB Graph Engine (port 6382)",
      valid_at: new Date(now - 7 * day).toISOString(),
      invalid_at: null,
      episode_run_id: "ep_run_01j8k902_graphiti",
      description: "Fakta aktif: Graphiti Memory Engine diaktifkan di FalkorDB port 6382.",
      status: "active",
      icon: "F",
    },
    {
      id: "fact-budget_cap_legacy",
      label: "Policy:BudgetCap_v1",
      type: "fact_entity",
      group: "Security",
      color: "#f43f5e",
      size: 13,
      subject: "Policy:Budget",
      predicate: "MAX_DAILY_COST",
      object: "$50.00 / day hard limit",
      valid_at: new Date(now - 12 * day).toISOString(),
      invalid_at: new Date(now - 3 * day).toISOString(),
      episode_run_id: "ep_run_01j7z441_budget",
      description: "Fakta lampau: Batas harian lama dipatok $50 sebelum skalabilitas v2.0.",
      status: "invalid",
      icon: "F",
    },
    {
      id: "fact-budget_cap_v2",
      label: "Policy:BudgetCap_v2",
      type: "fact_entity",
      group: "Security",
      color: "#10b981",
      size: 15,
      subject: "Policy:Budget",
      predicate: "SCALED_DAILY_COST",
      object: "$150.00 / day with dynamic elasticity",
      valid_at: new Date(now - 3 * day).toISOString(),
      invalid_at: null,
      episode_run_id: "ep_run_01j9a311_elastic",
      description: "Fakta aktif: Anggaran dinamis LGP v2.0 ditingkatkan ke $150/hari.",
      status: "active",
      icon: "F",
    },
    {
      id: "fact-circuit_breaker",
      label: "Security:CircuitThreshold",
      type: "fact_entity",
      group: "Security",
      color: "#10b981",
      size: 15,
      subject: "Security:CircuitBreaker",
      predicate: "TRIP_CONDITION",
      object: "5 consecutive tool errors triggers 60s cooldown",
      valid_at: new Date(now - 10 * day).toISOString(),
      invalid_at: null,
      episode_run_id: "ep_run_01j8a202_guardrail",
      description: "Fakta aktif: Circuit breaker menghentikan loop tool jika 5 kali gagal berturut-turut.",
      status: "active",
      icon: "F",
    },
    {
      id: "fact-embedding_model",
      label: "Model:EmbeddingDimension",
      type: "fact_entity",
      group: "Policy",
      color: "#10b981",
      size: 15,
      subject: "Model:Embedding",
      predicate: "VECTOR_DIMENSIONS",
      object: "1536-dim text-embedding-3-large",
      valid_at: new Date(now - 9 * day).toISOString(),
      invalid_at: null,
      episode_run_id: "ep_run_01j8c772_embed",
      description: "Fakta aktif: Standarisasi representasi semantik memori pada 1536 dimensi.",
      status: "active",
      icon: "F",
    },
    {
      id: "fact-hitl_protocol",
      label: "Governance:HITLRules",
      type: "fact_entity",
      group: "Security",
      color: "#10b981",
      size: 15,
      subject: "Governance:HITL",
      predicate: "INTERRUPT_LEVEL",
      object: "High-risk tools (DB Drop, Secret Patch) require Human Signoff",
      valid_at: new Date(now - 6 * day).toISOString(),
      invalid_at: null,
      episode_run_id: "ep_run_01j9b119_hitl",
      description: "Fakta aktif: Eksekusi berisiko tinggi wajib menunggu token persetujuan operator.",
      status: "active",
      icon: "F",
    },
    {
      id: "fact-postgres_checkpointer",
      label: "State:PostgresCheckpointer",
      type: "fact_entity",
      group: "Architecture",
      color: "#10b981",
      size: 16,
      subject: "State:Checkpointer",
      predicate: "PERSISTENCE_LAYER",
      object: "Postgres 17 Async Connection Pool (5432)",
      valid_at: new Date(now - 11 * day).toISOString(),
      invalid_at: null,
      episode_run_id: "ep_run_01j8e503_postgres",
      description: "Fakta aktif: LangGraph checkpointer terhubung ke PostgreSQL 17 untuk persistensi thread.",
      status: "active",
      icon: "F",
    },
  ];

  const links: NeuronLink[] = [
    // Subagents -> Central Hubs
    { source: "agent-atlas", target: "cat-subagent", relation: "ORCHESTRATES", color: "rgba(129, 140, 248, 0.6)", weight: 2 },
    { source: "agent-clio", target: "cat-subagent", relation: "CHRONICLES", color: "rgba(129, 140, 248, 0.6)", weight: 1.5 },
    { source: "agent-vulcan", target: "cat-subagent", relation: "IMPLEMENTS", color: "rgba(129, 140, 248, 0.6)", weight: 1.8 },
    { source: "agent-athena", target: "cat-subagent", relation: "INVESTIGATES", color: "rgba(129, 140, 248, 0.6)", weight: 1.6 },
    { source: "agent-hermes", target: "cat-subagent", relation: "COMMUNICATES", color: "rgba(129, 140, 248, 0.6)", weight: 1.7 },
    { source: "agent-mnemosyne", target: "cat-architecture", relation: "SYNCS_MEMORY", color: "rgba(56, 189, 248, 0.6)", weight: 2 },
    { source: "agent-janus", target: "cat-architecture", relation: "BRIDGES_MCP", color: "rgba(56, 189, 248, 0.6)", weight: 1.8 },
    { source: "agent-themis", target: "cat-security", relation: "ENFORCES_POLICY", color: "rgba(244, 63, 94, 0.6)", weight: 2 },
    { source: "agent-metron", target: "cat-telemetry", relation: "OBSERVES_METRICS", color: "rgba(56, 189, 248, 0.6)", weight: 1.8 },
    { source: "agent-iris", target: "cat-security", relation: "DISPATCHES_HITL", color: "rgba(245, 158, 11, 0.6)", weight: 1.6 },

    // Subagent to Subagent (NPMI Co-Activation Synapses)
    { source: "agent-atlas", target: "agent-vulcan", relation: "NPMI: +0.88", color: "#34d399", weight: 2.2, animated: true },
    { source: "agent-atlas", target: "agent-athena", relation: "NPMI: +0.76", color: "#34d399", weight: 1.9, animated: true },
    { source: "agent-atlas", target: "agent-hermes", relation: "NPMI: +0.91", color: "#34d399", weight: 2.4, animated: true },
    { source: "agent-vulcan", target: "agent-themis", relation: "NPMI: +0.65", color: "#34d399", weight: 1.6, animated: true },
    { source: "agent-mnemosyne", target: "agent-athena", relation: "NPMI: +0.82", color: "#34d399", weight: 2.0, animated: true },
    { source: "agent-janus", target: "agent-atlas", relation: "NPMI: +0.71", color: "#34d399", weight: 1.8, animated: true },
    { source: "agent-themis", target: "agent-iris", relation: "NPMI: +0.84", color: "#34d399", weight: 2.1, animated: true },
    { source: "agent-metron", target: "agent-clio", relation: "NPMI: +0.59", color: "#34d399", weight: 1.5, animated: true },

    // Hub to Hub cross links
    { source: "cat-subagent", target: "cat-architecture", relation: "LGP_TOPOLOGY", color: "rgba(100, 116, 139, 0.4)", weight: 1.2 },
    { source: "cat-architecture", target: "cat-security", relation: "SECURITY_BOUNDARY", color: "rgba(100, 116, 139, 0.4)", weight: 1.2 },
    { source: "cat-telemetry", target: "cat-architecture", relation: "TELEMETRY_PIPELINE", color: "rgba(100, 116, 139, 0.4)", weight: 1.2 },
    { source: "cat-model", target: "cat-subagent", relation: "POLICY_BINDING", color: "rgba(100, 116, 139, 0.4)", weight: 1.2 },

    // Facts to Hubs & Subagents
    { source: "fact-sqlite_buffer", target: "cat-architecture", relation: "HISTORICAL_FACT", color: "rgba(244, 63, 94, 0.5)", weight: 1 },
    { source: "fact-graphiti_falkordb", target: "cat-architecture", relation: "ACTIVE_FACT", color: "rgba(16, 185, 129, 0.6)", weight: 1.5 },
    { source: "fact-graphiti_falkordb", target: "agent-mnemosyne", relation: "MANAGED_BY", color: "rgba(16, 185, 129, 0.7)", weight: 1.7 },
    { source: "fact-budget_cap_legacy", target: "cat-security", relation: "HISTORICAL_FACT", color: "rgba(244, 63, 94, 0.5)", weight: 1 },
    { source: "fact-budget_cap_v2", target: "cat-security", relation: "ACTIVE_FACT", color: "rgba(16, 185, 129, 0.6)", weight: 1.5 },
    { source: "fact-circuit_breaker", target: "agent-themis", relation: "ENFORCED_BY", color: "rgba(16, 185, 129, 0.7)", weight: 1.8 },
    { source: "fact-embedding_model", target: "cat-model", relation: "STANDARDIZED_ON", color: "rgba(16, 185, 129, 0.6)", weight: 1.4 },
    { source: "fact-hitl_protocol", target: "agent-iris", relation: "ROUTED_THROUGH", color: "rgba(16, 185, 129, 0.7)", weight: 1.6 },
    { source: "fact-postgres_checkpointer", target: "cat-architecture", relation: "CHECKPOINT_CORE", color: "rgba(16, 185, 129, 0.7)", weight: 1.8 },
  ];

  return {
    engine: "Graphiti v0.4 (FalkorDB Bi-Temporal KG) [Mock Fallback]",
    style: "Obsidian Spiking Neuron Aesthetic",
    timestamp: now,
    nodes,
    links,
    stats: {
      total_nodes: nodes.length,
      total_edges: links.length,
      active_facts: nodes.filter((n) => n.status === "active" && n.type === "fact_entity").length,
      categories: nodes.filter((n) => n.type === "category").length,
    },
  };
};

/**
 * Normalizes graph data, computes degree centrality (inDegree, outDegree, total degree)
 * and assigns dynamic sizing based on Obsidian degree scaling.
 */
export function processNeuronGraphData(raw: { nodes?: NeuronNode[]; edges?: NeuronLink[]; links?: NeuronLink[] }): NeuronGraphData {
  const nodes: NeuronNode[] = (raw.nodes || []).map((n) => ({ ...n }));
  const rawLinks = raw.links || raw.edges || [];

  const inDegreeMap: Record<string, number> = {};
  const outDegreeMap: Record<string, number> = {};

  nodes.forEach((n) => {
    inDegreeMap[n.id] = 0;
    outDegreeMap[n.id] = 0;
  });

  const links: NeuronLink[] = rawLinks.map((l, i) => {
    const srcId = typeof l.source === "object" && l.source !== null ? (l.source as NeuronNode).id : String(l.source);
    const tgtId = typeof l.target === "object" && l.target !== null ? (l.target as NeuronNode).id : String(l.target);

    if (srcId in outDegreeMap) outDegreeMap[srcId] = (outDegreeMap[srcId] || 0) + 1;
    if (tgtId in inDegreeMap) inDegreeMap[tgtId] = (inDegreeMap[tgtId] || 0) + 1;

    return {
      id: l.id || `link-${srcId}-${tgtId}-${i}`,
      source: srcId,
      target: tgtId,
      relation: l.relation || l.predicate || "CONNECTED_TO",
      weight: typeof l.weight === "number" ? l.weight : 1.0,
      color: l.color || "rgba(100, 116, 139, 0.4)",
      animated: l.animated ?? true,
      detail: l.detail,
    };
  });

  // Calculate dynamic degree-based sizing
  nodes.forEach((n) => {
    const inDeg = inDegreeMap[n.id] || 0;
    const outDeg = outDegreeMap[n.id] || 0;
    const deg = inDeg + outDeg;
    n.inDegree = inDeg;
    n.outDegree = outDeg;
    n.degree = deg;

    // Base sizing on node type and degree centrality
    if (!n.size || n.size <= 0) {
      if (n.type === "category" || n.type === "hub") {
        n.size = 24 + Math.sqrt(deg) * 3;
      } else if (n.type === "subagent") {
        n.size = 18 + Math.sqrt(deg) * 2.5;
      } else {
        n.size = 10 + Math.sqrt(deg) * 1.8;
      }
    }

    // Color group tagging
    if (n.status === "invalid" || (n.invalid_at && new Date(n.invalid_at).getTime() <= Date.now())) {
      n.color = "#f43f5e"; // Rose 500 for invalidated
    } else if (n.type === "subagent") {
      n.color = "#818cf8"; // Indigo 400
    } else if (n.type === "category" || n.type === "hub") {
      n.color = "#38bdf8"; // Sky 400
    } else if (n.type === "fact_entity" || n.type === "fact") {
      n.color = "#10b981"; // Emerald 500
    }
  });

  return {
    nodes,
    links,
    stats: {
      total_nodes: nodes.length,
      total_edges: links.length,
      active_facts: nodes.filter((n) => n.status !== "invalid" && (n.type === "fact_entity" || n.type === "fact")).length,
      categories: nodes.filter((n) => n.type === "category" || n.type === "hub").length,
    },
  };
}
