import json
import time
import hashlib
from typing import Dict, List, Any, Optional
from packages.core.db import get_db_connection, record_audit_log
from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS, CONTRACTS_MAP
from packages.orchestrator.atlas_engine import AtlasOrchestrator
from packages.telemetry.correlation import CorrelationCalculator, SUBAGENT_IDS
from packages.memory.temporal import TemporalMemoryStore
from packages.core.models import CorrelationEdge, TemporalFact

class AdminMCPServer:
    """
    FastMCP / MCPServer compatible Admin Server for Enterprise LangGraph Platform (LGP v2.0).
    Exposes 17 lgp_* tools with explicit risk annotations allowing 100% full management by AI.
    """

    TOOL_DEFINITIONS = [
        {
            "name": "lgp_subagent_list",
            "description": "Menampilkan daftar seluruh subagent terdaftar (10 subagents) beserta pod, kontrak, dan status aktifnya.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "pod": {"type": "string", "description": "Filter opsional berdasarkan nama Pod"}
                }
            }
        },
        {
            "name": "lgp_subagent_get",
            "description": "Mengambil kontrak lengkap suatu subagent berdasarkan ID (misal: atlas, clio, vulcan).",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "ID subagent"}
                },
                "required": ["subagent_id"]
            }
        },
        {
            "name": "lgp_subagent_update_config",
            "description": "Memperbarui konfigurasi budget, trust level, atau status aktif subagent di registry.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "ID subagent"},
                    "max_usd": {"type": "number", "description": "Batas anggaran USD baru"},
                    "max_tokens": {"type": "integer", "description": "Batas token baru"},
                    "trust_level": {"type": "string", "enum": ["Low", "Medium", "High"], "description": "Tingkat kepercayaan baru"},
                    "is_active": {"type": "boolean", "description": "Status aktif/non-aktif subagent"}
                },
                "required": ["subagent_id"]
            }
        },
        {
            "name": "lgp_subagent_topology",
            "description": "Mendapatkan struktur topologi 4 Pod LGP v2.0 dan alur delegasi/handoff.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "lgp_circuit_breaker_reset",
            "description": "Mereset status Circuit Breaker untuk subagent yang dinonaktifkan akibat 3 kegagalan beruntun.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "ID subagent yang ingin di-reset"}
                },
                "required": ["subagent_id"]
            }
        },
        {
            "name": "lgp_run_create",
            "description": "Memicu eksekusi task baru melalui supervisor Atlas dengan alokasi budget dan context packet.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": True
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "Tujuan/tugas yang harus dikerjakan"},
                    "subagents": {"type": "array", "items": {"type": "string"}, "description": "Daftar ID subagent opsional yang ingin dilibatkan"}
                },
                "required": ["objective"]
            }
        },
        {
            "name": "lgp_run_get_state",
            "description": "Mendapatkan status eksekusi run, output delegates, dan ringkasan budget.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "ID dari run"}
                },
                "required": ["run_id"]
            }
        },
        {
            "name": "lgp_run_list",
            "description": "Menampilkan daftar riwayat run yang telah dieksekusi di platform.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Jumlah maksimal run yang diambil (default 20)"},
                    "status": {"type": "string", "description": "Filter status run (completed, interrupted, running, failed)"}
                }
            }
        },
        {
            "name": "lgp_run_resume_hitl",
            "description": "Melanjutkan eksekusi yang diinterupsi oleh gerbang HITL (Human-in-the-Loop).",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "interrupt_id": {"type": "string", "description": "ID interupsi"},
                    "approver": {"type": "string", "description": "Nama/ID approver (DILARANG sama dengan subagent pembuat)"},
                    "decision": {"type": "string", "enum": ["approved", "rejected"], "description": "Keputusan approver"}
                },
                "required": ["interrupt_id", "approver", "decision"]
            }
        },
        {
            "name": "lgp_memory_query",
            "description": "Kueri memori bi-temporal Graphiti L2 (fakta, subject, predicate, valid_at Tv, created_at Tk).",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Filter subjek fakta"},
                    "as_of_valid_time": {"type": "number", "description": "Timestamp Unix Tv (waktu validitas dlm realita)"},
                    "as_of_record_time": {"type": "number", "description": "Timestamp Unix Tk (waktu pencatatan dlm sistem)"}
                }
            }
        },
        {
            "name": "lgp_memory_store_fact",
            "description": "Menyimpan fakta bi-temporal baru ke dalam Long-Term Memory L2 dengan sanitasi PII otomatis.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Entitas subjek fakta (misal: Project_X)"},
                    "predicate": {"type": "string", "description": "Predikat relasi (misal: USES_FRAMEWORK)"},
                    "object": {"type": "string", "description": "Objek fakta (misal: FastAPI & LangGraph)"},
                    "valid_at": {"type": "number", "description": "Timestamp validitas awal (default saat ini)"},
                    "invalid_at": {"type": "number", "description": "Timestamp kadaluarsa fakta opsional"},
                    "episode_run_id": {"type": "string", "description": "ID run sumber fakta"}
                },
                "required": ["subject", "predicate", "object"]
            }
        },
        {
            "name": "lgp_memory_invalidate_fact",
            "description": "Membatalkan/menonaktifkan fakta dalam memori temporal (mengisi invalid_at = timestamp saat ini).",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "ID fakta yang ingin dibatalkan"}
                },
                "required": ["fact_id"]
            }
        },
        {
            "name": "lgp_correlation_matrix",
            "description": "Mendapatkan matriks korelasi 10x10 antar-subagent (NPMI, handoff rate, success lift, composite weight).",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "lgp_correlation_setup",
            "description": "Mengonfigurasi bobot kalkulasi korelasi (alpha NPMI, beta success lift, gamma handoff rate) & threshold n_min.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "alpha": {"type": "number", "description": "Bobot NPMI co-activation (default 0.4)"},
                    "beta": {"type": "number", "description": "Bobot success lift (default 0.4)"},
                    "gamma": {"type": "number", "description": "Bobot handoff rate (default 0.2)"},
                    "n_min": {"type": "integer", "description": "Ambang batas sampel data sedikit (default 50)"}
                }
            }
        },
        {
            "name": "lgp_telemetry_events_query",
            "description": "Membaca raw telemetri events L1 per run atau subagent.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Filter ID run"},
                    "subagent_id": {"type": "string", "description": "Filter ID subagent"},
                    "limit": {"type": "integer", "description": "Jumlah maksimal event (default 50)"}
                }
            }
        },
        {
            "name": "lgp_audit_query",
            "description": "Memeriksa catatan audit log append-only dengan verifikasi rantai hash SHA-256.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Jumlah baris log maksimal (default 50)"}
                }
            }
        },
        {
            "name": "lgp_audit_verify",
            "description": "Memverifikasi integritas kriptografis seluruh rantai hash (hash chain SHA-256) audit log.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        }
    ]

    def __init__(self):
        self.orchestrator = AtlasOrchestrator()

    async def _get_correlation_calc(self) -> CorrelationCalculator:
        db = await get_db_connection()
        try:
            async with db.execute("SELECT alpha, beta, gamma, n_min FROM correlation_settings WHERE workspace_id='default'") as cursor:
                row = await cursor.fetchone()
                if row:
                    calc = CorrelationCalculator(alpha=row["alpha"], beta=row["beta"], gamma=row["gamma"])
                    calc.N_MIN = row["n_min"]
                    return calc
        finally:
            await db.close()
        return CorrelationCalculator()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], actor: str = "AdminMCPClient") -> Dict[str, Any]:
        await record_audit_log(actor, f"mcp.tool_call:{tool_name}", "mcp:admin", arguments, "success")

        if tool_name == "lgp_subagent_list":
            pod_filter = arguments.get("pod")
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM subagent_registry") as cursor:
                    rows = await cursor.fetchall()
                    results = []
                    for r in rows:
                        item = dict(r)
                        item["capabilities"] = json.loads(item["capabilities"])
                        item["input_schema"] = json.loads(item["input_schema"])
                        item["output_schema"] = json.loads(item["output_schema"])
                        item["tool_grants"] = json.loads(item["tool_grants"])
                        item["budget_config"] = json.loads(item["budget_config"])
                        if not pod_filter or item["pod"].lower() == pod_filter.lower():
                            results.append(item)
                    return {"subagents": results, "total": len(results)}
            finally:
                await db.close()

        elif tool_name == "lgp_subagent_get":
            subagent_id = arguments.get("subagent_id", "")
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM subagent_registry WHERE id = ?", (subagent_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return {"error": f"Subagent '{subagent_id}' tidak ditemukan"}
                    item = dict(row)
                    item["capabilities"] = json.loads(item["capabilities"])
                    item["budget_config"] = json.loads(item["budget_config"])
                    item["tool_grants"] = json.loads(item["tool_grants"])
                    return {"contract": item}
            finally:
                await db.close()

        elif tool_name == "lgp_subagent_update_config":
            subagent_id = arguments.get("subagent_id", "")
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM subagent_registry WHERE id = ?", (subagent_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return {"error": f"Subagent '{subagent_id}' tidak ditemukan"}

                    budget_config = json.loads(row["budget_config"])
                    if "max_usd" in arguments and arguments["max_usd"] is not None:
                        budget_config["max_usd"] = float(arguments["max_usd"])
                    if "max_tokens" in arguments and arguments["max_tokens"] is not None:
                        budget_config["max_tokens"] = int(arguments["max_tokens"])

                    trust_level = arguments.get("trust_level", row["trust_level"])
                    is_active = 1 if arguments.get("is_active", row["is_active"] == 1) else 0

                    await db.execute("""
                        UPDATE subagent_registry
                        SET budget_config = ?, trust_level = ?, is_active = ?
                        WHERE id = ?
                    """, (json.dumps(budget_config), trust_level, is_active, subagent_id))
                    await db.commit()
                    return {"status": "success", "subagent_id": subagent_id, "updated_budget": budget_config, "trust_level": trust_level, "is_active": bool(is_active)}
            finally:
                await db.close()

        elif tool_name == "lgp_subagent_topology":
            return {
                "topology": {
                    "supervisor": "atlas",
                    "pods": {
                        "Koordinasi": ["atlas"],
                        "Riset & Rekayasa": ["clio", "vulcan", "athena"],
                        "Platform": ["hermes", "mnemosyne", "janus"],
                        "Tata Kelola": ["themis", "metron", "iris"]
                    },
                    "allowed_handoff_loops": [
                        {"from": "vulcan", "to": "athena", "type": "CRITICIZES"},
                        {"from": "athena", "to": "vulcan", "type": "REVISION"}
                    ]
                }
            }

        elif tool_name == "lgp_circuit_breaker_reset":
            subagent_id = arguments.get("subagent_id", "")
            self.orchestrator.circuit_breaker.reset(subagent_id)
            return {"status": "success", "message": f"Circuit breaker untuk subagent '{subagent_id}' telah di-reset ke CLOSED."}

        elif tool_name == "lgp_run_create":
            objective = arguments.get("objective", "")
            subagents = arguments.get("subagents")
            thread_id = f"th-{time.strftime('%Y%m%d%H%M%S')}"
            result = await self.orchestrator.execute_run(thread_id, objective, subagents)
            return result

        elif tool_name == "lgp_run_get_state":
            run_id = arguments.get("run_id", "")
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return {"error": f"Run '{run_id}' tidak ditemukan"}
                    res = dict(row)
                    res["budget_allocated"] = json.loads(res["budget_allocated_json"]) if res.get("budget_allocated_json") else {}
                    res["budget_spent"] = json.loads(res["budget_spent_json"]) if res.get("budget_spent_json") else {}
                    return res
            finally:
                await db.close()

        elif tool_name == "lgp_run_list":
            limit = arguments.get("limit", 20)
            status_filter = arguments.get("status")
            db = await get_db_connection()
            try:
                if status_filter:
                    query = "SELECT * FROM runs WHERE status = ? ORDER BY created_at DESC LIMIT ?"
                    params = (status_filter, limit)
                else:
                    query = "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?"
                    params = (limit,)

                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return {"runs": [dict(r) for r in rows], "count": len(rows)}
            finally:
                await db.close()

        elif tool_name == "lgp_run_resume_hitl":
            interrupt_id = arguments.get("interrupt_id", "")
            approver = arguments.get("approver", "")
            decision = arguments.get("decision", "rejected")

            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM hitl_inbox WHERE interrupt_id = ?", (interrupt_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return {"error": f"Interrupt '{interrupt_id}' tidak ditemukan"}

                    # Rule: Anti-self-approval
                    if approver == row["subagent_id"]:
                        return {"error": "Pelanggaran Keamanan: AI tidak diizinkan menyetujui aksinya sendiri!"}

                now = time.time()
                await db.execute("""
                    UPDATE hitl_inbox
                    SET status = ?, approver = ?, decision = ?, resolved_at = ?
                    WHERE interrupt_id = ?
                """, (decision, approver, decision, now, interrupt_id))
                await db.commit()
                return {"status": "success", "interrupt_id": interrupt_id, "decision": decision}
            finally:
                await db.close()

        elif tool_name == "lgp_memory_query":
            subject = arguments.get("subject")
            tv = arguments.get("as_of_valid_time")
            tk = arguments.get("as_of_record_time")

            db = await get_db_connection()
            try:
                query = "SELECT * FROM temporal_facts"
                params = []
                if subject:
                    query += " WHERE subject LIKE ?"
                    params.append(f"%{subject}%")
                query += " ORDER BY created_at DESC LIMIT 100"

                async with db.execute(query, tuple(params)) as cursor:
                    rows = await cursor.fetchall()
                    facts = [TemporalFact(**dict(r)) for r in rows]

                filtered = TemporalMemoryStore.filter_bitemporal(facts, as_of_valid_time=tv, as_of_record_time=tk)
                return {"facts": [f.model_dump() for f in filtered], "count": len(filtered)}
            finally:
                await db.close()

        elif tool_name == "lgp_memory_store_fact":
            subject = arguments.get("subject", "")
            predicate = arguments.get("predicate", "")
            obj = arguments.get("object", "")
            valid_at = arguments.get("valid_at")
            invalid_at = arguments.get("invalid_at")
            episode_run_id = arguments.get("episode_run_id")

            fact = TemporalMemoryStore.create_fact(
                subject=subject,
                predicate=predicate,
                obj=obj,
                valid_at=valid_at,
                invalid_at=invalid_at,
                episode_run_id=episode_run_id
            )

            db = await get_db_connection()
            try:
                await db.execute("""
                    INSERT INTO temporal_facts (
                        fact_id, subject, predicate, object, valid_at, invalid_at, created_at, expired_at, episode_run_id, pii_redacted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (fact.fact_id, fact.subject, fact.predicate, fact.object, fact.valid_at, fact.invalid_at, fact.created_at, fact.expired_at, fact.episode_run_id, 1))
                await db.commit()
                return {"status": "success", "fact": fact.model_dump()}
            finally:
                await db.close()

        elif tool_name == "lgp_memory_invalidate_fact":
            fact_id = arguments.get("fact_id", "")
            now = time.time()
            db = await get_db_connection()
            try:
                await db.execute("UPDATE temporal_facts SET invalid_at = ? WHERE fact_id = ?", (now, fact_id))
                await db.commit()
                return {"status": "success", "fact_id": fact_id, "invalid_at": now}
            finally:
                await db.close()

        elif tool_name == "lgp_correlation_matrix":
            calc = await self._get_correlation_calc()
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM correlation_edges") as cursor:
                    rows = await cursor.fetchall()
                    edges = [CorrelationEdge(**dict(r)) for r in rows]
                return calc.generate_10x10_matrix(edges)
            finally:
                await db.close()

        elif tool_name == "lgp_correlation_setup":
            alpha = float(arguments.get("alpha", 0.4))
            beta = float(arguments.get("beta", 0.4))
            gamma = float(arguments.get("gamma", 0.2))
            n_min = int(arguments.get("n_min", 50))
            now = time.time()

            db = await get_db_connection()
            try:
                await db.execute("""
                    INSERT INTO correlation_settings (workspace_id, alpha, beta, gamma, n_min, updated_at)
                    VALUES ('default', ?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id) DO UPDATE SET
                        alpha = excluded.alpha,
                        beta = excluded.beta,
                        gamma = excluded.gamma,
                        n_min = excluded.n_min,
                        updated_at = excluded.updated_at
                """, (alpha, beta, gamma, n_min, now))
                await db.commit()
                return {"status": "success", "correlation_settings": {"alpha": alpha, "beta": beta, "gamma": gamma, "n_min": n_min, "updated_at": now}}
            finally:
                await db.close()

        elif tool_name == "lgp_telemetry_events_query":
            run_id = arguments.get("run_id")
            subagent_id = arguments.get("subagent_id")
            limit = arguments.get("limit", 50)

            db = await get_db_connection()
            try:
                query = "SELECT * FROM telemetry_events"
                params = []
                clauses = []
                if run_id:
                    clauses.append("run_id = ?")
                    params.append(run_id)
                if subagent_id:
                    clauses.append("subagent_id = ?")
                    params.append(subagent_id)
                if clauses:
                    query += " WHERE " + " AND ".join(clauses)
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                async with db.execute(query, tuple(params)) as cursor:
                    rows = await cursor.fetchall()
                    return {"events": [dict(r) for r in rows], "count": len(rows)}
            finally:
                await db.close()

        elif tool_name == "lgp_audit_query":
            limit = arguments.get("limit", 50)
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    return {"audit_log": [dict(r) for r in rows], "count": len(rows)}
            finally:
                await db.close()

        elif tool_name == "lgp_audit_verify":
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM audit_log ORDER BY created_at ASC") as cursor:
                    rows = await cursor.fetchall()
                    logs = [dict(r) for r in rows]

                prev_hash = "0" * 64
                valid = True
                violations = []

                for log in logs:
                    if log["prev_hash"] != prev_hash:
                        valid = False
                        violations.append(f"Hash mismatch at log_id={log['log_id']}: expected prev_hash={prev_hash}, got {log['prev_hash']}")

                    payload_to_hash = f"{log['prev_hash']}:{log['log_id']}:{log['actor']}:{log['action']}:{log['scope']}:{log['args_hash']}:{log['result_status']}:{log['created_at']}"
                    expected_curr = hashlib.sha256(payload_to_hash.encode()).hexdigest()

                    if log["curr_hash"] != expected_curr:
                        valid = False
                        violations.append(f"Tampered content at log_id={log['log_id']}: calculated curr_hash={expected_curr}, recorded={log['curr_hash']}")

                    prev_hash = log["curr_hash"]

                return {
                    "is_valid": valid,
                    "total_entries": len(logs),
                    "violations": violations
                }
            finally:
                await db.close()

        return {"error": f"Tool '{tool_name}' tidak dikenali"}
