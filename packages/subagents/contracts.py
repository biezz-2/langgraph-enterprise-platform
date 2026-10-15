from typing import List, Dict, Any, Optional
from packages.core.models import SubagentContract

TEN_SUBAGENTS_CONTRACTS: List[SubagentContract] = [
    # 1. Atlas (Pod Koordinasi)
    SubagentContract(
        id="atlas",
        role="orchestrator-supervisor",
        name="Atlas — Supervisor",
        pod="Koordinasi",
        capabilities=[
            "Dekomposisi tugas",
            "Effort scaling",
            "Distribusi context packet",
            "Sintesis hasil multi-agent",
            "Eskalasi HITL"
        ],
        input_schema={"objective": "string", "constraints": "object", "context_refs": "array"},
        output_schema={"final_answer": "string", "citations": "array", "delegates_report": "array", "cost_summary": "object"},
        tool_grants=["runs:execute", "graphs:read", "state:read", "memory:read", "subagents:read"],
        model_policy="frontier-extended-thinking",
        budget_config={"max_tokens": 1500000, "max_usd": 10.0, "max_wall_clock_s": 2700, "max_depth": 2, "max_steps": 60},
        memory_scope="tenant:workspace:user",
        trust_level="High",
        version="2.0.0"
    ),

    # 2. Clio (Pod Riset & Rekayasa) - Outbound only, NO Admin MCP
    SubagentContract(
        id="clio",
        role="deep-researcher",
        name="Clio — Riset & Sintesis",
        pod="Riset & Rekayasa",
        capabilities=[
            "Web search outbound",
            "Cross-check multi-sumber",
            "Ekstraksi fakta & sitasi",
            "Deteksi konflik informasi"
        ],
        input_schema={"query": "string", "depth": "string", "max_sources": "integer"},
        output_schema={"findings": "array", "sources": "array", "confidence_score": "number"},
        tool_grants=["web_search", "news_search", "open_url"],  # Strictly outbound only, NO admin:*
        model_policy="mid-tier-structured",
        budget_config={"max_tokens": 300000, "max_usd": 1.5, "max_wall_clock_s": 900, "parallel_max": 3},
        memory_scope="read-all, write-via-atlas",
        trust_level="Low",  # Untrusted external web content
        version="2.0.0"
    ),

    # 3. Vulcan (Pod Riset & Rekayasa) - Sandboxed, Cannot self-promote
    SubagentContract(
        id="vulcan",
        role="software-engineer",
        name="Vulcan — Rekayasa Perangkat Lunak",
        pod="Riset & Rekayasa",
        capabilities=[
            "Menulis kode graf/node",
            "lgp_graph_propose",
            "lgp_graph_validate",
            "Eksekusi sandbox unit test"
        ],
        input_schema={"task": "string", "target_files": "array", "constraints": "array"},
        output_schema={"code_diff": "string", "test_results": "object", "requires_approval": "boolean"},
        tool_grants=["graphs:propose", "graphs:validate", "sandbox:run", "github:read_pr_create"],  # NO self-promote
        model_policy="code-generation-specialist",
        budget_config={"max_tokens": 400000, "max_usd": 2.5, "max_wall_clock_s": 1800, "max_iterations": 5},
        memory_scope="project:artifacts",
        trust_level="Medium",
        version="2.0.0"
    ),

    # 4. Athena (Pod Riset & Rekayasa) - Critic & Reviewer
    SubagentContract(
        id="athena",
        role="critic-reviewer",
        name="Athena — Reviewer & Critic",
        pod="Riset & Rekayasa",
        capabilities=[
            "Adversarial code review",
            "Graph diff inspection",
            "Prompt-injection testing",
            "Kritik swarm handoff"
        ],
        input_schema={"code_diff": "string", "context": "object", "iteration": "integer"},
        output_schema={"verdict": "string", "vulnerabilities": "array", "critique": "string", "passed": "boolean"},
        tool_grants=["graphs:diff", "graphs:get_dag", "audit:query", "checkpoint:diff"],
        model_policy="adversarial-low-temp",
        budget_config={"max_tokens": 200000, "max_usd": 1.0, "max_wall_clock_s": 900, "max_rounds": 3},
        memory_scope="read-all, write-criticizes-edge",
        trust_level="Medium",
        version="2.0.0"
    ),

    # 5. Hermes (Pod Platform) - SRE & Ops
    SubagentContract(
        id="hermes",
        role="platform-ops",
        name="Hermes — Platform Ops/SRE",
        pod="Platform",
        capabilities=[
            "Triage insiden",
            "Metrik platform & health check",
            "Usulan runbook remediasi",
            "Verifikasi backup"
        ],
        input_schema={"incident_id": "string", "severity": "string", "telemetry_snapshot": "object"},
        output_schema={"triage_report": "object", "remediation_proposal": "string", "sla_status": "string"},
        tool_grants=["health:read", "metrics:read", "schedule:create_dry_run"],
        model_policy="deterministic-ops",
        budget_config={"max_tokens": 1500000, "max_usd": 0.75, "max_wall_clock_s": 600},
        memory_scope="system:incidents, decisions",
        trust_level="Medium",
        version="2.0.0"
    ),

    # 6. Mnemosyne (Pod Platform) - Memory Curator
    SubagentContract(
        id="mnemosyne",
        role="memory-curator",
        name="Mnemosyne — Kurator Memori",
        pod="Platform",
        capabilities=[
            "Kurasi episode run Graphiti",
            "Redaksi PII otomatis",
            "Deduplikasi hash & penataan ontologi",
            "Penjelasan korelasi multi-agent"
        ],
        input_schema={"episode_data": "object", "run_id": "string", "redact_pii": "boolean"},
        output_schema={"facts_ingested": "integer", "entities_updated": "array", "dedup_count": "integer"},
        tool_grants=["memory:read", "memory:write", "memory:ingest", "correlation:explain"],
        model_policy="structured-extraction",
        budget_config={"max_tokens": 250000, "max_usd": 1.25, "max_wall_clock_s": 1200},
        memory_scope="graphiti:group_id:full",
        trust_level="Medium",
        version="2.0.0"
    ),

    # 7. Janus (Pod Platform) - Integration & MCP Hub
    SubagentContract(
        id="janus",
        role="integration-mcp-hub",
        name="Janus — Integrasi & MCP Hub",
        pod="Platform",
        capabilities=[
            "Registrasi server MCP eksternal",
            "Validasi tool annotations & health",
            "Evaluasi grant per-node",
            "Webhook & trigger adapter"
        ],
        input_schema={"mcp_server_url": "string", "server_name": "string", "action": "string"},
        output_schema={"tools_discovered": "array", "annotations_valid": "boolean", "grant_recommendation": "array"},
        tool_grants=["mcp:manage", "mcp:ping", "tools:inspect"],
        model_policy="deterministic-mcp",
        budget_config={"max_tokens": 150000, "max_usd": 0.75, "max_wall_clock_s": 900},
        memory_scope="tool:registry",
        trust_level="Low-Medium",
        version="2.0.0"
    ),

    # 8. Themis (Pod Tata Kelola) - Security & Compliance, NO RAW SECRETS
    SubagentContract(
        id="themis",
        role="security-compliance",
        name="Themis — Keamanan & Kepatuhan",
        pod="Tata Kelola",
        capabilities=[
            "Verifikasi hash-chain tamper-evident",
            "Audit RBAC & tool-call grants",
            "Hygiene secret reference (secret://)",
            "Checklist kepatuhan UU PDP"
        ],
        input_schema={"audit_window_s": "integer", "target_subagents": "array"},
        output_schema={"integrity_verified": "boolean", "violations": "array", "compliance_report": "object"},
        tool_grants=["audit:query", "secret_ref:list", "security:read"],  # Strictly secret_ref:list, NEVER secret values
        model_policy="security-auditor-strict",
        budget_config={"max_tokens": 150000, "max_usd": 0.75, "max_wall_clock_s": 900},
        memory_scope="system:decidents, incidents",
        trust_level="Medium-High",
        version="2.0.0"
    ),

    # 9. Metron (Pod Tata Kelola) - Evaluation & Data
    SubagentContract(
        id="metron",
        role="evaluation-data",
        name="Metron — Evaluasi & Data",
        pod="Tata Kelola",
        capabilities=[
            "Benchmark dataset per subagent",
            "Regresi gating promote otomatis",
            "LLM-as-judge independen",
            "Deteksi drift biaya & latensi (+-20%)"
        ],
        input_schema={"eval_suite": "string", "subagent_id": "string", "runs_count": "integer"},
        output_schema={"score": "number", "baseline_drift": "number", "gate_passed": "boolean"},
        tool_grants=["runs:execute_eval", "usage:report", "evals:read_write"],
        model_policy="independent-judge-model",
        budget_config={"max_tokens": 200000, "max_usd": 1.0, "max_wall_clock_s": 1200, "parallel_max": 3},
        memory_scope="evals:benchmarks",
        trust_level="Medium",
        version="2.0.0"
    ),

    # 10. Iris (Pod Tata Kelola) - Documentation & Comms
    SubagentContract(
        id="iris",
        role="documentation-writer",
        name="Iris — Dokumentasi & Komunikasi",
        pod="Tata Kelola",
        capabilities=[
            "Penyusunan PRD, Makalah, Runbook",
            "Changelog versi & dokumentasi API",
            "Status laporan eksekutif",
            "Ringkasan keputusan arsitektur (ADR)"
        ],
        input_schema={"topic": "string", "doc_type": "string", "source_artifacts": "array"},
        output_schema={"content_markdown": "string", "table_of_contents": "array", "version": "string"},
        tool_grants=["graphs:read", "runs:read", "memory:read", "docs:write_workspace"],
        model_policy="mid-high-writer",
        budget_config={"max_tokens": 300000, "max_usd": 1.5, "max_wall_clock_s": 1500},
        memory_scope="documents:artifacts",
        trust_level="Medium",
        version="2.0.0"
    ),
]

CONTRACTS_MAP: Dict[str, SubagentContract] = {sc.id: sc for sc in TEN_SUBAGENTS_CONTRACTS}


# ==========================================
# DEEPAGENTS INTEGRATION HELPERS
# ==========================================

try:
    from deepagents.middleware.subagents import SubAgent
    from deepagents.middleware.filesystem import FilesystemPermission
    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False
    SubAgent = dict  # type: ignore
    FilesystemPermission = dict  # type: ignore


def to_deepagents_subagent(
    contract: SubagentContract,
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None
) -> "SubAgent":
    """Mengonversi SubagentContract LGP v2.0 ke format SubAgent DeepAgents."""
    permissions: List[Any] = []
    
    # Sandboxing policy untuk subagent tertentu
    if DEEPAGENTS_AVAILABLE:
        if contract.id == "vulcan":
            permissions = [
                FilesystemPermission(operations=["read", "write"], paths=["/workspace"], mode="allow"),
                FilesystemPermission(operations=["write"], paths=["/etc", "/admin", "/root"], mode="deny"),
            ]
        elif contract.id == "clio":
            permissions = [
                FilesystemPermission(operations=["read"], paths=["/workspace"], mode="allow"),
                FilesystemPermission(operations=["write"], paths=["/"], mode="deny"),
            ]

    system_prompt = (
        f"Kamu adalah subagen {contract.name} (Role: {contract.role}, Pod: {contract.pod}).\n"
        f"Kemampuan: {', '.join(contract.capabilities)}.\n"
        f"Trust Level: {contract.trust_level}. Scope Memori: {contract.memory_scope}."
    )

    subagent_kwargs: Dict[str, Any] = {
        "name": contract.id,
        "description": f"{contract.name} ({contract.pod}) — {', '.join(contract.capabilities[:2])}",
        "system_prompt": system_prompt,
    }

    if permissions:
        subagent_kwargs["permissions"] = permissions
    if model is not None:
        subagent_kwargs["model"] = model
    if tools is not None:
        subagent_kwargs["tools"] = tools

    return SubAgent(**subagent_kwargs) if DEEPAGENTS_AVAILABLE else subagent_kwargs  # type: ignore


def get_deepagents_subagents(
    model: Optional[Any] = None,
    tools_map: Optional[Dict[str, List[Any]]] = None,
    exclude_ids: Optional[List[str]] = None
) -> List["SubAgent"]:
    """Mengembalikan daftar 10 SubAgent DeepAgents (default excluding root atlas)."""
    exclude = set(exclude_ids or ["atlas"])
    tools_map = tools_map or {}
    
    result = []
    for c in TEN_SUBAGENTS_CONTRACTS:
        if c.id in exclude:
            continue
        sub_tools = tools_map.get(c.id)
        result.append(to_deepagents_subagent(c, model=model, tools=sub_tools))
    return result

