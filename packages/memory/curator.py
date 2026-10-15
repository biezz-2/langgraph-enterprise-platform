import time
import json
from typing import List, Dict, Any, Optional
from packages.core.models import TemporalFact
from packages.memory.temporal import TemporalMemoryStore
from packages.core.db import get_db_connection
from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS

class MemoryTaxonomy:
    CATEGORIES = {
        "Session": "Konteks sesi eksekusi, prompt pengguna, dan histori percakapan",
        "User_Preference": "Preferensi pengguna, instruksi khusus, dan aturan gaya komunikasi",
        "Project": "Konteks proyek terdaftar (LGP v2.0, MiroFish Enterprise, OSIS Agora Acta, dll)",
        "Integration": "Integrasi pihak ketiga & eksternal (SearXNG, 9Router, FastMCP, GitHub, Graphiti Platform)",
        "Device": "Karakteristik perangkat host (Fujitsu Lifebook, Ubuntu Desktop, kernel, input driver)",
        "Subagent": "Spesifikasi kontrak 10 subagent, role, dan pod",
        "Model": "Model AI yang digunakan per subagent (policy & provider)",
        "Architecture": "Komponen utama LGP v2.0 (Supervisor, CircuitBreaker, FastMCP, WAL DB)",
        "Security": "Guardrail least-privilege, sanitasi PII, isolasi secret, & verification hash",
        "Telemetry": "Matriks korelasi 10x10, NPMI, handoff rate, & budget ceiling"
    }

class MemoryCuratorEngine:
    """Engine kurasi memori untuk Mnemosyne (Pod Platform).
    Mengatur klasifikasi terstruktur, deduplikasi, dan seeding pengetahuan sistem.
    """

    @classmethod
    def format_subject(cls, category: str, item_name: str) -> str:
        """Format standar subject memori: Category:ItemName (contoh: Subagent:atlas, Model:frontier)"""
        cat_clean = category.strip()
        item_clean = item_name.strip()
        return f"{cat_clean}:{item_clean}"

    @classmethod
    async def seed_system_knowledge(cls) -> Dict[str, Any]:
        """Ingest seluruh konteks sistem, 10 subagent, model policy, & arsitektur ke SQLite temporal_facts."""
        db = await get_db_connection()
        facts_to_insert = []
        now = time.time()
        session_id = "session-lgp-v2-init"

        # 1. Subagent & Model Policy Context
        for contract in TEN_SUBAGENTS_CONTRACTS:
            # Subagent Spec
            sub_fact = TemporalMemoryStore.create_fact(
                subject=cls.format_subject("Subagent", contract.id),
                predicate="BELONGS_TO_POD",
                obj=f"Pod {contract.pod} - Role: {contract.role} - Name: {contract.name}",
                episode_run_id=session_id
            )
            facts_to_insert.append(sub_fact)

            # Model Policy Spec
            model_fact = TemporalMemoryStore.create_fact(
                subject=cls.format_subject("Model", contract.id),
                predicate="USES_MODEL_POLICY",
                obj=f"Model Policy: {contract.model_policy} | Trust Level: {contract.trust_level}",
                episode_run_id=session_id
            )
            facts_to_insert.append(model_fact)

            # Budget Allocation Spec
            budget_str = json.dumps(contract.budget_config)
            budget_fact = TemporalMemoryStore.create_fact(
                subject=cls.format_subject("Subagent", contract.id),
                predicate="HAS_BUDGET_CONFIG",
                obj=f"Budget Specs: {budget_str}",
                episode_run_id=session_id
            )
            facts_to_insert.append(budget_fact)

        # 2. Architecture & Runtime Context
        arch_facts = [
            ("Architecture:LGP_Core", "USES_PATTERN", "Supervisor-via-Tools Pattern dipimpin Atlas"),
            ("Architecture:Database", "USES_PERSISTENCE", "SQLite WAL mode + SHA-256 Hash Chaining Audit Log"),
            ("Architecture:FastMCP", "EXPOSES_TOOLS", "17 FastMCP Tools dengan anotasi risiko (readOnlyHint, destructiveHint)"),
            ("Architecture:Telemetry", "CALCULATES_CORRELATION", "10x10 Correlation Matrix (NPMI, Handoff Rate, Success Lift, Composite Weight)"),
            ("Architecture:Daemon", "MANAGED_BY", "PM2 Daemon Process 'lgp-api' pada port 8000"),
        ]
        for subj, pred, val in arch_facts:
            facts_to_insert.append(TemporalMemoryStore.create_fact(
                subject=subj, predicate=pred, obj=val, episode_run_id=session_id
            ))

        # 3. Security & Compliance Guardrails
        sec_facts = [
            ("Security:Clio", "RESTRICTS_ACCESS", "Dilarang mengakses Admin MCP (Outbound web search only)"),
            ("Security:Vulcan", "RESTRICTS_PROMOTION", "Dilarang self-promote graph ke prod tanpa persetujuan HITL"),
            ("Security:Themis", "RESTRICTS_SECRETS", "Hanya boleh menerima referensi secret:// (bukan plain value)"),
            ("Security:Budget", "ENFORCES_HARD_STOP", "Workspace limit $15.00/day hard stop & inherited child budget <= parent budget"),
            ("Security:PII", "AUTO_REDACTS", "Pembersihan otomatis Regex untuk Email, Telepon, dan NIK Indonesia"),
        ]
        for subj, pred, val in sec_facts:
            facts_to_insert.append(TemporalMemoryStore.create_fact(
                subject=subj, predicate=pred, obj=val, episode_run_id=session_id
            ))

        # 4. Session & IDE Knowledge Context
        session_facts = [
            ("Session:ClaudeCode", "IDENTIFIER", "claude-biezz-2 | Model: Gemini 3.6 Flash / Claude Code Client"),
            ("Session:Storage_Rule", "MEMORY_TAXONOMY", "Category:Session, Category:Subagent, Category:Model, Category:Architecture, Category:Security, Category:Telemetry"),
            ("Session:IDE_Integration", "SUPPORTED_CLIENTS", "Claude Code, Cursor, Windsurf, Claude Desktop via Stdio & REST API"),
        ]
        for subj, pred, val in session_facts:
            facts_to_insert.append(TemporalMemoryStore.create_fact(
                subject=subj, predicate=pred, obj=val, episode_run_id=session_id
            ))

        # Insert to DB with deduplication check
        inserted_count = 0
        try:
            for f in facts_to_insert:
                # Check if exact subject + predicate + object already exists
                async with db.execute(
                    "SELECT fact_id FROM temporal_facts WHERE subject=? AND predicate=? AND object=?",
                    (f.subject, f.predicate, f.object)
                ) as cursor:
                    existing = await cursor.fetchone()
                    if not existing:
                        await db.execute("""
                            INSERT INTO temporal_facts (
                                fact_id, subject, predicate, object, valid_at, invalid_at, created_at, expired_at, episode_run_id, pii_redacted
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (f.fact_id, f.subject, f.predicate, f.object, f.valid_at, f.invalid_at, f.created_at, f.expired_at, f.episode_run_id, 1))
                        inserted_count += 1
            await db.commit()
            return {"status": "success", "inserted": inserted_count, "total_processed": len(facts_to_insert)}
        finally:
            await db.close()

    @classmethod
    async def get_organized_memory_summary(cls) -> Dict[str, Any]:
        """Mengambil seluruh fakta memori yang tersusun rapi berdasarkan kategori."""
        db = await get_db_connection()
        categorized = {cat: [] for cat in MemoryTaxonomy.CATEGORIES.keys()}
        categorized["Other"] = []

        try:
            async with db.execute("SELECT * FROM temporal_facts WHERE invalid_at IS NULL ORDER BY subject ASC") as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    fact = dict(r)
                    subj = fact["subject"]
                    matched = False
                    for cat in MemoryTaxonomy.CATEGORIES.keys():
                        if subj.startswith(f"{cat}:"):
                            categorized[cat].append({
                                "fact_id": fact["fact_id"],
                                "subject": fact["subject"],
                                "predicate": fact["predicate"],
                                "object": fact["object"],
                                "episode_run_id": fact["episode_run_id"],
                                "created_at": fact["created_at"]
                            })
                            matched = True
                            break
                    if not matched:
                        categorized["Other"].append(fact)

            return {
                "taxonomy": MemoryTaxonomy.CATEGORIES,
                "categorized_facts": categorized,
                "total_active_facts": sum(len(v) for v in categorized.values())
            }
        finally:
            await db.close()
