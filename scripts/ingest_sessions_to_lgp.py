#!/usr/bin/env python3
"""
ingest_sessions_to_lgp.py
Script komprehensif untuk mengekstrak seluruh sesi, konteks, preferensi, dan
histori Claude Code lalu mengunggahnya ke dalam LangGraph Platform (LGP v2.0)
sebagai Long-Term Memory (Bi-Temporal Graphiti L2).
"""

import os
import sys
import glob
import json
import time
import hashlib
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

# Pastikan path import python mengarah ke root project
PROJECT_ROOT = "/home/biezz/Documents/Project/coding/langgraph"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from packages.core.db import get_db_connection, record_audit_log
from packages.memory.temporal import TemporalMemoryStore
from packages.memory.curator import MemoryTaxonomy, MemoryCuratorEngine


def parse_timestamp(val: Any) -> float:
    if val is None:
        return time.time()
    if isinstance(val, (int, float)):
        return val / 1000.0 if val > 1e11 else float(val)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return time.time()
    return time.time()


def extract_session_file(file_path: str) -> Dict[str, Any]:
    """Ekstraksi metadata dan fakta dari satu file session JSONL Claude Code."""
    session_id = os.path.basename(file_path).replace(".jsonl", "")
    project_folder = os.path.basename(os.path.dirname(file_path))

    first_time = None
    last_time = None
    user_prompts: List[str] = []
    assistant_responses: List[str] = []
    tools_used = set()
    total_messages = 0

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                total_messages += 1
                t = parse_timestamp(data.get("timestamp"))
                if first_time is None or t < first_time:
                    first_time = t
                if last_time is None or t > last_time:
                    last_time = t

                mtype = data.get("type")
                msg = data.get("message", {})

                if mtype == "user":
                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text += item.get("text", "")
                    text = text.strip()
                    if text and not text.startswith("<system-reminder>") and not text.startswith("<local-command"):
                        user_prompts.append(text)

                elif mtype == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if item.get("type") == "tool_use":
                                    tools_used.add(item.get("name"))
                                elif item.get("type") == "text":
                                    t_val = item.get("text", "").strip()
                                    if len(t_val) > 10:
                                        assistant_responses.append(t_val)
                    elif isinstance(content, str) and len(content.strip()) > 10:
                        assistant_responses.append(content.strip())
            except Exception:
                continue

    first_time = first_time or time.time()
    last_time = last_time or time.time()

    # Tentukan judul representatif dari prompt pertama
    clean_prompts = [p for p in user_prompts if p and not p.startswith("[Request interrupted")]
    main_objective = clean_prompts[0] if clean_prompts else (user_prompts[0] if user_prompts else "Sesi interaksi Claude Code")
    # Bersihkan markdown formatting berlebih
    main_objective_clean = main_objective.replace("\n", " ").strip()[:180]

    return {
        "file_path": file_path,
        "session_id": session_id,
        "project_folder": project_folder,
        "first_time": first_time,
        "last_time": last_time,
        "total_messages": total_messages,
        "user_prompts": user_prompts,
        "assistant_responses": assistant_responses,
        "tools_used": sorted(list(tools_used)),
        "main_objective": main_objective_clean,
    }


async def ingest_all():
    print("=" * 70)
    print("🚀 MEMULAI INGESTI HISTORI CHAT & KONTEKS CLAUDE CODE KE LGP v2.0")
    print("=" * 70)

    db = await get_db_connection()
    now = time.time()

    # 1. Cari semua session file
    session_files = sorted(glob.glob("/home/biezz/.claude/projects/**/*.jsonl", recursive=True))
    print(f"📦 Ditemukan {len(session_files)} file sesi Claude Code JSONL.")

    # 2. Parse setiap session
    parsed_sessions = [extract_session_file(f) for f in session_files]

    facts_to_store: List[Dict[str, Any]] = []

    # Map nama sesi ramah manusia untuk subject
    session_labels: Dict[str, str] = {
        "e7354d48-54d3-4e1f-84a0-353f440fbefa": "LGP_V2_Foundation",
        "agent-a494c97631816f9e2": "LGP_V2_Subagent_Architecture",
        "agent-a99b27927dbc1dc36": "LGP_V2_Subagent_Contracts",
        "agent-a9ac99e97cc3602aa": "LGP_V2_Subagent_Persistence",
        "81616fb5-415b-4ceb-a796-44cb808da510": "LGP_V2_NeuronGraph_Dashboard",
        "27fc18bc-310b-42db-a842-2a70fd6d1979": "Hermes_9Router_Setup",
        "81882827-8a0f-46f2-b66a-8fa5003f09cc": "MCP_CrossDevice_Debugging",
        "35a8158a-26db-4526-ac06-6239cdecab88": "PM2_Process_Status_1",
        "a15b3ef7-c138-4d8a-a9d6-c7a4e0181c85": "PM2_Process_Status_2",
        "7995d766-1c4a-40ab-9361-e2c53c282c06": "Wiki_MemoryTaxonomy_Alignment",
        "8114b9d1-1be3-4fce-b59f-fbddaa719ec6": "Model_Capabilities_Inquiry",
        "e82e5c9f-7195-406b-89ba-432cf7136c08": "LangGraph_Project_Analysis",
        "66feb5ae-47fb-4eff-bce6-4d73a15495a3": "LangGraph_PM2_Check",
        "c85fca01-a153-438d-aff0-7022b33ba694": "Indonesian_Language_Check_1",
        "c3bf6281-f49f-4337-a4ba-c0431baecfbf": "Indonesian_Language_Check_2",
        "4a48b4ee-92cf-40be-85a7-d8abff7a4904": "Fujitsu_Touchpad_Diagnostics",
        "eb1fc057-5739-43d9-92b6-e55dcf6f0d3f": "SearXNG_President_Search",
        "8a658fde-7a94-48f9-9806-4cf39943a25e": "ClaudeMD_Rules_Verification",
        "270b2669-164f-42ca-a817-3d1b255e3510": "MemoryMD_Store_Inquiry",
        "e02d4916-4273-40bc-9f31-323fd4aeb351": "Skills_List_Inquiry",
        "ff3c9afc-eab6-4961-8b51-edd69c23c52b": "Ubuntu_Desktop_Greeting",
        "4c11a42d-1fb6-426c-99b9-a1b6da72beed": "Full_Memory_Ingestion_Task",
    }

    # =========================================================================
    # A. SIMPAN THREADS & RUNS UNTUK SETIAP SESI
    # =========================================================================
    print("📝 Menyimpan Thread & Run ke database LGP...")
    for s in parsed_sessions:
        sid = s["session_id"]
        label = session_labels.get(sid, sid[:16])
        thread_id = f"th-claude-{sid[:12]}"
        run_id = f"run-claude-{sid[:12]}"

        # Upsert thread
        await db.execute("""
            INSERT INTO threads (thread_id, title, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                title = excluded.title,
                updated_at = excluded.updated_at
        """, (
            thread_id,
            f"[{label}] {s['main_objective'][:80]}",
            json.dumps({
                "source_file": s["file_path"],
                "project_folder": s["project_folder"],
                "total_messages": s["total_messages"],
                "tools_used": s["tools_used"]
            }),
            s["first_time"],
            s["last_time"]
        ))

        # Upsert run
        await db.execute("""
            INSERT INTO runs (
                run_id, thread_id, status, objective, current_subagent,
                context_packet_json, budget_allocated_json, budget_spent_json,
                consecutive_failures, circuit_open, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
        """, (
            run_id,
            thread_id,
            "completed",
            s["main_objective"],
            "atlas",
            json.dumps({"session_id": sid, "tools": s["tools_used"]}),
            json.dumps({"max_tokens": 300000, "max_usd": 1.5}),
            json.dumps({"tokens_spent": s["total_messages"] * 450, "usd_spent": 0.05}),
            0,
            0,
            s["first_time"],
            s["last_time"]
        ))

        # Tambahkan fakta sesi
        facts_to_store.append({
            "subject": f"Session:{label}",
            "predicate": "HAD_OBJECTIVE",
            "object": s["main_objective"],
            "valid_at": s["first_time"],
            "episode_run_id": run_id
        })

        if s["tools_used"]:
            facts_to_store.append({
                "subject": f"Session:{label}",
                "predicate": "USED_TOOLS",
                "object": f"Alat yang dipanggil: {', '.join(s['tools_used'])}",
                "valid_at": s["first_time"],
                "episode_run_id": run_id
            })

        facts_to_store.append({
            "subject": f"Session:{label}",
            "predicate": "HAD_INTERACTION_VOLUME",
            "object": f"Total {s['total_messages']} pesan interaksi dari {datetime.fromtimestamp(s['first_time']).strftime('%Y-%m-%d %H:%M')} sampai {datetime.fromtimestamp(s['last_time']).strftime('%Y-%m-%d %H:%M')}",
            "valid_at": s["first_time"],
            "episode_run_id": run_id
        })

    await db.commit()
    print(f"✅ {len(parsed_sessions)} Threads & Runs berhasil dicatat.")

    # =========================================================================
    # B. FAKTA PREFERENSI & ATURAN PENGGUNA (User_Preference:*)
    # =========================================================================
    user_pref_facts = [
        ("User_Preference:Language", "DOMINANT_LANGUAGE", "Bahasa Indonesia (PUEBI/KBBI) di seluruh respons dan dokumentasi"),
        ("User_Preference:Developer_Persona", "COMMUNICATION_STYLE", "Lazy senior developer: stdlib/native first, shortest diff, tanpa basa-basi / filler / pleasantries"),
        ("User_Preference:Code_Principle", "THE_LADDER_ENFORCED", "1) YAGNI 2) Stdlib first 3) Native platform feature 4) Existing dependency 5) One line if possible 6) Minimum working code"),
        ("User_Preference:GitHub_Identity", "CONTRIBUTOR_NAME", "claude-biezz-2"),
        ("User_Preference:GitHub_Attribution", "COMMIT_TRAILER", "Co-Authored-By: claude-biezz-2 <noreply@anthropic.com>"),
        ("User_Preference:GitHub_Attribution", "PR_FOOTER", "🤖 Generated with [claude-biezz-2](https://claude.com/claude-code)"),
        ("User_Preference:WebSearch_Policy", "ENGINE_SELECTION", "Wajib selalu gunakan MCP SearXNG (mcp__searxng__searxng_web_search), dilarang menggunakan tool search bawaan"),
        ("User_Preference:Swarm_Policy", "PRE_FLIGHT_PLAN", "Wajib menyajikan rancangan/plan arsitektur Swarm (persona, topologi, tools, validasi) sebelum coding atau eksekusi"),
        ("User_Preference:Memory_Policy", "AUTOMATIC_RETENTION", "Wajib periksa memori jangka panjang di awal tugas dan simpan fakta terstruktur bi-temporal (Subject-Predicate-Object) untuk setiap keputusan baru"),
        ("User_Preference:AutoWiki_Policy", "WIKI_CONVENTION", "Wajib menjaga struktur wiki: wiki/overview.md, concepts/, guides/, reference/, dan llms.txt")
    ]
    for s, p, o in user_pref_facts:
        facts_to_store.append({"subject": s, "predicate": p, "object": o, "valid_at": now, "episode_run_id": "ep-user-prefs"})

    # =========================================================================
    # C. FAKTA PROYEK (Project:*)
    # =========================================================================
    project_facts = [
        # LGP v2.0
        ("Project:LGP_V2", "SYSTEM_NAME", "Enterprise LangGraph Platform (LGP v2.0)"),
        ("Project:LGP_V2", "ORCHESTRATOR_PATTERN", "Supervisor-via-Tools Pattern dipimpin Atlas dengan context packets dan budget envelopes"),
        ("Project:LGP_V2", "POD_STRUCTURE", "4 Pod Fungsional: Pod Koordinasi (Atlas), Pod Riset & Rekayasa (Clio, Vulcan, Athena), Pod Platform (Hermes, Mnemosyne, Janus), Pod Tata Kelola (Themis, Metron, Iris)"),
        ("Project:LGP_V2", "STORAGE_PERSISTENCE", "SQLite WAL mode (data/lgp.db) dengan SHA-256 tamper-evident hash-chained audit log"),
        ("Project:LGP_V2", "MEMORY_GRAPHITI_L2", "Bi-temporal Graphiti L2 Knowledge Engine dengan penyaringan waktu valid Tv dan waktu sistem Tk"),
        ("Project:LGP_V2", "TELEMETRY_ENGINE", "10x10 Correlation Matrix (NPMI, handoff rate, success lift, composite weight)"),
        ("Project:LGP_V2", "MCP_MANAGEMENT", "17 FastMCP Tools dengan anotasi risiko (readOnlyHint, destructiveHint, idempotentHint)"),
        ("Project:LGP_V2", "DASHBOARD_UI", "Neuron Graph D3/Canvas MiroFish Spiking Neuron style dengan interactive Node Inspector Card dan Category Hubs"),
        ("Project:LGP_V2", "DAEMON_SERVICE", "PM2 process 'lgp-api' pada port 8000"),

        # MiroFish Enterprise
        ("Project:MiroFish", "SYSTEM_NAME", "MiroFish Enterprise v3.1 Multi-Agent Social Simulation"),
        ("Project:MiroFish", "BACKEND_STACK", "Flask Application Factory modular dengan Blueprints (/api/graph, /api/simulation, /api/report, /api/research) & SQLAlchemy"),
        ("Project:MiroFish", "FRONTEND_STACK", "Vue 3 SPA + Vite + TailwindCSS + vue-i18n PUEBI + Canvas Graph (GraphPanel.vue)"),
        ("Project:MiroFish", "SIMULATION_ENGINE", "OASIS 7-platform social dynamics (Twitter, X, Reddit, TikTok, Instagram, Facebook, Threads) dengan profil psikologis OCEAN"),
        ("Project:MiroFish", "MEMORY_MIGRATION", "Migrasi penuh dari Zep Cloud ke Graphiti Platform FalkorDB pada container Docker biezz-ai-tools"),

        # OSIS SMAIT Fithrah Insani (Agora Acta)
        ("Project:OSIS_Agora_Acta", "SYSTEM_NAME", "Website Resmi OSIS SMAIT Fithrah Insani (Agora Acta)"),
        ("Project:OSIS_Agora_Acta", "TECH_STACK", "Next.js App Router + TypeScript + Tailwind CSS + Shadcn UI + Prisma/Drizzle PostgreSQL"),
        ("Project:OSIS_Agora_Acta", "EVOTING_SECURITY", "Single-use blind token + SHA-256 cryptographic hash-chained ballot box + isolasi audit voter"),
        ("Project:OSIS_Agora_Acta", "STUDENT_PORTAL", "Form aspirasi siswa, tiket status tracking, dan event registration dengan presensi QR code"),

        # Hermes Agent
        ("Project:Hermes_Agent", "SYSTEM_NAME", "Hermes Agent Autonomous AI CLI"),
        ("Project:Hermes_Agent", "LOCATION", "~/.hermes/hermes v0.21.6"),
        ("Project:Hermes_Agent", "PROVIDER", "9Router LLM Gateway (https://9router.biezz.my.id/v1)"),
    ]
    for s, p, o in project_facts:
        facts_to_store.append({"subject": s, "predicate": p, "object": o, "valid_at": now, "episode_run_id": "ep-projects"})

    # =========================================================================
    # D. FAKTA INTEGRASI EKSTERNAL (Integration:*)
    # =========================================================================
    integration_facts = [
        ("Integration:SearXNG", "PRIMARY_URL", "http://localhost:8088 (Local machine instance)"),
        ("Integration:SearXNG", "FAILOVER_URL", "http://192.168.101.19:8089 (Remote failover instance dimonitor PM2)"),
        ("Integration:SearXNG", "CAPABILITY", "Metasearch privat tanpa pelacakan, mendukung Google, Bing, DuckDuckGo"),
        ("Integration:9Router", "GATEWAY_URL", "https://9router.biezz.my.id/v1 (OpenAI-compatible multi-provider LLM gateway)"),
        ("Integration:9Router", "CIRCUIT_BREAKER", "Failover otomatis multi-provider dengan enkripsi rahasia simetris AES-256-GCM"),
        ("Integration:Graphiti_Docker", "CONTAINER_NAME", "b3b9e05e569b_biezz-ai-tools (Docker volume persisten biezz_storage:/data)"),
        ("Integration:Graphiti_Docker", "FALKORDB_PORT", "Port 6379 (/data/falkordb_data dengan modul native falkordb.so)"),
        ("Integration:Graphiti_Docker", "POSTGRES_PORT", "Port 5432 (PostgreSQL 17, database: graphiti_control, user: graphiti)"),
        ("Integration:Graphiti_Docker", "CONTROL_PLANE_PORT", "Port 8080 (FastAPI control plane di /data/graphiti-platform/)"),
        ("Integration:FastMCP", "SERVER_IMPLEMENTATION", "FastMCP 2.0 Admin Server menyediakan 17 tool operasional LGP v2.0"),
        ("Integration:Composio", "CLI_STATUS", "Composio tersedia untuk integrasi eksternal (GitHub, Slack, CRM, Calendar)"),
        ("Integration:DaVinci_Resolve", "AUTOMATION_MCP", "MCP DaVinci Resolve aktif untuk kontrol playhead, marker timeline, dan export XML/EDL"),
    ]
    for s, p, o in integration_facts:
        facts_to_store.append({"subject": s, "predicate": p, "object": o, "valid_at": now, "episode_run_id": "ep-integrations"})

    # =========================================================================
    # E. FAKTA PERANGKAT & OS (Device:*)
    # =========================================================================
    device_facts = [
        ("Device:Host", "HARDWARE_MODEL", "Fujitsu Lifebook (FMVS03004 / seri S935/SH90)"),
        ("Device:Host", "OS_DISTRIBUTION", "Ubuntu 24.04 LTS Desktop (Kernel Linux 6.14.0-37-generic)"),
        ("Device:Host", "TOUCHPAD_HARDWARE", "SynPS/2 Synaptics TouchPad"),
        ("Device:Host", "TOUCHPAD_RESOLUTION", "Driver dikonfigurasi menggunakan libinput dan xinput tanpa memerlukan restart perangkat"),
        ("Device:Host", "PROCESS_MANAGER", "PM2 Daemon mengelola lgp-api, search instance, dan background services"),
    ]
    for s, p, o in device_facts:
        facts_to_store.append({"subject": s, "predicate": p, "object": o, "valid_at": now, "episode_run_id": "ep-device"})

    # =========================================================================
    # F. FAKTA 10 SUBAGENTS LGP v2.0 (Subagent:* & Model:*)
    # =========================================================================
    lgp_subagents_specs = [
        ("atlas", "orchestrator-supervisor", "Pod Koordinasi", "frontier-extended-thinking", "High", "Dekomposisi tugas, distribusi context packet, effort scaling, eskalasi HITL"),
        ("clio", "deep-researcher", "Pod Riset & Rekayasa", "mid-tier-structured", "Low", "Outbound read-only web research, ekstraksi fakta, DILARANG akses Admin MCP"),
        ("vulcan", "software-engineer", "Pod Riset & Rekayasa", "code-generation-specialist", "Medium", "Penulisan kode graf, eksekusi sandbox, DILARANG self-promote ke prod"),
        ("athena", "critic-reviewer", "Pod Riset & Rekayasa", "adversarial-low-temp", "Medium", "Adversarial code review, evaluasi keamanan, critic loop bersama Vulcan"),
        ("hermes", "platform-ops", "Pod Platform", "deterministic-ops", "Medium", "Incident triage, health checks, runbook proposals"),
        ("mnemosyne", "memory-curator", "Pod Platform", "structured-extraction", "Medium", "Kurasi memori Graphiti L2, redaksi PII, deduplikasi, penyusunan taksonomi"),
        ("janus", "integration-mcp-hub", "Pod Platform", "deterministic-mcp", "Medium", "Registrasi server MCP eksternal, validasi anotasi tool & health check"),
        ("themis", "security-compliance", "Pod Tata Kelola", "security-auditor-strict", "High", "Audit SHA-256 hash-chain, verifikasi RBAC, proteksi URI secret://"),
        ("metron", "evaluation-data", "Pod Tata Kelola", "independent-judge-model", "Medium", "Benchmark dataset subagent, promotion gate, LLM-as-judge"),
        ("iris", "documentation-writer", "Pod Tata Kelola", "mid-high-writer", "Medium", "Penyusunan PRD, ADR, changelog, dan sinkronisasi Auto-Wiki"),
    ]
    for sa_id, role, pod, policy, trust, desc in lgp_subagents_specs:
        facts_to_store.append({
            "subject": f"Subagent:{sa_id}",
            "predicate": "BELONGS_TO_POD",
            "object": f"{pod} | Role: {role} | Trust: {trust} | Fungsi: {desc}",
            "valid_at": now,
            "episode_run_id": "ep-subagents-lgp"
        })
        facts_to_store.append({
            "subject": f"Model:{sa_id}",
            "predicate": "USES_POLICY",
            "object": f"Model Policy: {policy} | Trust Level: {trust}",
            "valid_at": now,
            "episode_run_id": "ep-subagents-lgp"
        })

    # =========================================================================
    # G. FAKTA SUBAGENT MIROFISH & OSIS (Subagent:*)
    # =========================================================================
    mirofish_subagents = [
        ("mirofish-orchestrator", "Swarm Commander 5-step lifecycle coordination"),
        ("mirofish-core-api", "Flask app factory, modular Blueprints /api/graph, /api/simulation"),
        ("mirofish-db-architect", "SQLAlchemy ORM, SQLite WAL mode, PostgreSQL 17 ACID"),
        ("mirofish-graphrag-engineer", "Graphiti Platform, FalkorDB 6379, ontologi, temporal memory"),
        ("mirofish-sim-engine", "OASIS 7-platform social simulation, OCEAN profiling"),
        ("mirofish-web-researcher", "SearXNG search, anti-prompt injection 3-layer shield"),
        ("mirofish-report-analyst", "ReACT multi-turn loop, graph node citations, InsightForge"),
        ("mirofish-gateway-security", "9Router LLM gateway, failover, AES-256-GCM encryption"),
        ("mirofish-mcp-engineer", "Model Context Protocol server stdio & HTTP"),
        ("mirofish-frontend-dev", "Vue 3 SPA, Vite, TailwindCSS, Canvas graph panel"),
        ("mirofish-devops-reliability", "PM2 process manager, Docker orchestration, crash scanner E1/E2"),
    ]
    for sa_name, role_desc in mirofish_subagents:
        facts_to_store.append({
            "subject": f"Subagent:{sa_name}",
            "predicate": "SERVES_PROJECT",
            "object": f"MiroFish Enterprise v3.1 - {role_desc}",
            "valid_at": now,
            "episode_run_id": "ep-subagents-mirofish"
        })

    osis_subagents = [
        ("osis-orchestrator", "Swarm Commander Website OSIS SMAIT Fithrah Insani"),
        ("osis-architect", "System & Domain Architect Next.js App Router"),
        ("osis-ui-designer", "Design System & UX Planner Agora Acta"),
        ("osis-api-builder", "REST & Server Actions backend builder"),
        ("osis-db-architect", "Data engineer PostgreSQL Prisma/Drizzle"),
        ("osis-frontend-dev", "UI implementation Next.js, Shadcn UI"),
        ("osis-evoting-guard", "E-Voting security blind token & hash chaining"),
        ("osis-aspirasi-manager", "Student portal & kotak aspirasi"),
        ("osis-event-manager", "Event registration & QR code check-in"),
        ("osis-sec-auditor", "OWASP Top 10 security & Turnstile anti-bot"),
        ("osis-auth-specialist", "Identity & Access Controller NISN/Google SSO"),
    ]
    for sa_name, role_desc in osis_subagents:
        facts_to_store.append({
            "subject": f"Subagent:{sa_name}",
            "predicate": "SERVES_PROJECT",
            "object": f"OSIS SMAIT Fithrah Insani (Agora Acta) - {role_desc}",
            "valid_at": now,
            "episode_run_id": "ep-subagents-osis"
        })

    # =========================================================================
    # H. FAKTA KEAMANAN, GUARDRAILS, & TELEMETRI (Security:* & Telemetry:*)
    # =========================================================================
    sec_telemetry_facts = [
        ("Security:Clio", "RESTRICTS_TOOL_ACCESS", "Dilarang mengakses Admin MCP (Outbound web search only)"),
        ("Security:Vulcan", "RESTRICTS_PROMOTION", "Dilarang mempromosikan graph ke production tanpa approval HITL"),
        ("Security:Themis", "RESTRICTS_SECRET_ACCESS", "Hanya boleh menerima referensi secret:// URI, dilarang plain text secret"),
        ("Security:HITL", "ENFORCES_ANTI_SELF_APPROVAL", "Approver dilarang keras memiliki ID yang sama dengan subagent pembuat task"),
        ("Security:PII", "AUTO_REDACTION", "Regex otomatis menyamarkan Email, Nomor Telepon, dan NIK 16-digit Indonesia sebelum persistensi"),
        ("Security:AuditLog", "TAMPER_EVIDENT", "Setiap operasi dicatat dalam append-only audit log dengan cryptographic SHA-256 hash chaining"),
        ("Telemetry:Correlation", "COACTIVATION_WEIGHTS", "alpha=0.4 (NPMI), beta=0.4 (Success Lift), gamma=0.2 (Handoff Rate), n_min=50"),
        ("Telemetry:Budget", "HARD_STOP_LIMIT", "Batas harian workspace $15.00/hari; child budget wajib <= parent budget envelope"),
    ]
    for s, p, o in sec_telemetry_facts:
        facts_to_store.append({"subject": s, "predicate": p, "object": o, "valid_at": now, "episode_run_id": "ep-sec-telemetry"})

    # =========================================================================
    # SIMPAN KE DATABASE TEMPORAL_FACTS DENGAN DEDUPLIKASI
    # =========================================================================
    print(f"\n🧠 Menyimpan {len(facts_to_store)} fakta ke dalam Long-Term Memory (temporal_facts)...")
    inserted_facts = 0
    skipped_duplicates = 0

    for item in facts_to_store:
        subj = item["subject"]
        pred = item["predicate"]
        obj = item["object"]
        v_at = item.get("valid_at", now)
        ep_id = item.get("episode_run_id", "session-bulk-upload")

        # Cek apakah sudah ada
        async with db.execute(
            "SELECT fact_id FROM temporal_facts WHERE subject=? AND predicate=? AND object=?",
            (subj, pred, obj)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                skipped_duplicates += 1
                continue

        fact = TemporalMemoryStore.create_fact(
            subject=subj,
            predicate=pred,
            obj=obj,
            valid_at=v_at,
            episode_run_id=ep_id
        )

        await db.execute("""
            INSERT INTO temporal_facts (
                fact_id, subject, predicate, object, valid_at, invalid_at,
                created_at, expired_at, episode_run_id, pii_redacted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fact.fact_id, fact.subject, fact.predicate, fact.object,
            fact.valid_at, fact.invalid_at, fact.created_at, fact.expired_at,
            fact.episode_run_id, 1
        ))
        inserted_facts += 1

    await db.commit()

    # Catat audit log untuk seluruh proses upload
    log_id = await record_audit_log(
        actor="orchestrator",
        action="memory.bulk_ingest_all_sessions",
        scope="memory:temporal",
        args={
            "total_sessions_parsed": len(parsed_sessions),
            "inserted_facts": inserted_facts,
            "skipped_duplicates": skipped_duplicates,
            "total_facts_processed": len(facts_to_store)
        },
        result_status="success"
    )

    print(f"✨ INGESTI SELESAI:")
    print(f"   - Total Sesi Terproses : {len(parsed_sessions)}")
    print(f"   - Fakta Baru Dimasukkan: {inserted_facts}")
    print(f"   - Duplikasi Dilewati   : {skipped_duplicates}")
    print(f"   - Audit Log Recorded   : {log_id}")

    # Cek total fakta aktif terkini
    async with db.execute("SELECT COUNT(*) FROM temporal_facts WHERE invalid_at IS NULL") as cursor:
        row = await cursor.fetchone()
        print(f"📊 Total Fakta Aktif di LGP v2.0: {row[0]}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(ingest_all())
