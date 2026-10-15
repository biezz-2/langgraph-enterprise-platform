import json
import time
import hashlib
from typing import Dict, List, Any, Optional
import httpx
from packages.core.db import get_db_connection, record_audit_log
from packages.subagents.contracts import TEN_SUBAGENTS_CONTRACTS, CONTRACTS_MAP
from packages.orchestrator.atlas_engine import AtlasOrchestrator
from packages.telemetry.correlation import CorrelationCalculator, SUBAGENT_IDS
from packages.memory.temporal import TemporalMemoryStore
from packages.memory.curator import MemoryCuratorEngine
from packages.memory.graphiti import GraphitiMemoryEngine
from packages.core.models import CorrelationEdge, TemporalFact
from packages.core.event_bus import GlobalEventBus

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
        },
        {
            "name": "lgp_platform_health",
            "description": "Mendapatkan status kesehatan platform, jumlah subagent aktif, mode storage, dan status supervisor.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "lgp_hitl_inbox_list",
            "description": "Melihat daftar interupsi Human-in-the-Loop (HITL) yang sedang pending atau telah selesai.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "approved", "rejected", "all"], "description": "Filter status interupsi (default pending)"}
                }
            }
        },
        {
            "name": "lgp_memory_organized_summary",
            "description": "Mendapatkan ringkasan memori yang telah dikurasi dan disortir berdasarkan taksonomi kategori (Session, Subagent, Model, Architecture, Security, User_Preference, dll).",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "lgp_graphiti_neuron_graph",
            "description": "Mendapatkan graf neuron MiroFish Graphiti lengkap (node entitas fakta bi-temporal, relasi edge, dan bobot).",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "lgp_memory_seed",
            "description": "Memicu proses seeding fakta pengetahuan sistem secara otomatis ke dalam memori bi-temporal.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False
            },
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "lgp_api_request",
            "description": "Universal API Request: Mengeksekusi endpoint REST API LangGraph yang ada (GET, POST, PUT, DELETE) seperti /api/health, /api/runs, /api/subagents, dll.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": True
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "description": "Metode HTTP (GET, POST, dll)"},
                    "endpoint": {"type": "string", "description": "Path endpoint API (contoh: /api/health, /api/runs, /api/subagents)"},
                    "params": {"type": "object", "description": "Query parameters opsional"},
                    "body": {"type": "object", "description": "JSON request body untuk method POST/PUT"}
                },
                "required": ["method", "endpoint"]
            }
        }
    ,
    {
        "name": "lgp_kanban_list_boards",
        "description": "Menampilkan daftar seluruh Kanban board yang tersedia di platform.",
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        },
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "lgp_kanban_get_board",
        "description": "Mengambil detail lengkap Kanban board beserta semua kolom dan cards.",
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        },
        "parameters": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "ID Kanban board"}
            },
            "required": ["board_id"]
        }
    },
    {
        "name": "lgp_kanban_create_board",
        "description": "Membuat Kanban board baru dengan kolom-kolom yang ditentukan.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        },
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nama board"},
                "columns": {"type": "array", "items": {"type": "object"}, "description": "Daftar kolom"}
            },
            "required": ["name", "columns"]
        }
    },
    {
        "name": "lgp_kanban_create_card",
        "description": "Membuat card baru di Kanban board pada kolom tertentu.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        },
        "parameters": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "ID board"},
                "column_name": {"type": "string", "description": "Nama kolom"},
                "title": {"type": "string", "description": "Judul card"},
                "description": {"type": "string", "description": "Deskripsi card"},
                "priority": {"type": "string", "description": "Prioritas (low/medium/high/critical)"},
                "assigned_to": {"type": "string", "description": "Subagent yang ditugaskan"}
            },
            "required": ["board_id", "column_name", "title"]
        }
    },
    {
        "name": "lgp_kanban_move_card",
        "description": "Memindahkan card dari satu kolom ke kolom lain.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        },
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "ID card"},
                "to_column_name": {"type": "string", "description": "Nama kolom tujuan"}
            },
            "required": ["card_id", "to_column_name"]
        }
    },
    {
        "name": "lgp_matrix_get_config",
        "description": "Mengambil konfigurasi matriks korelasi saat ini (alpha, beta, gamma, n_min, enabled status).",
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        },
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "lgp_matrix_update_config",
        "description": "Memperbarui konfigurasi matriks korelasi untuk mengoptimalkan bobot perhitungan korelasi.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        },
        "parameters": {
            "type": "object",
            "properties": {
                "alpha": {"type": "number", "description": "Bobot NPMI (0-1)"},
                "beta": {"type": "number", "description": "Bobot Success Lift (0-1)"},
                "gamma": {"type": "number", "description": "Bobot Handoff Rate (0-1)"},
                "n_min": {"type": "integer", "description": "Threshold sampel minimum"},
                "enabled": {"type": "boolean", "description": "Enable/disable matrix calculation"}
            }
        }
    },
    {
        "name": "lgp_matrix_recalculate",
        "description": "Memicu perhitungan ulang matriks korelasi 10x10 berdasarkan data telemetri terbaru.",
        "annotations": {
            "readOnlyHint": False,
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
                    GlobalEventBus.get_instance().publish_sync("subagent_updated", {"subagent_id": subagent_id})
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
            GlobalEventBus.get_instance().publish_sync("subagent_updated", {"subagent_id": subagent_id, "action": "reset"})
            return {"status": "success", "message": f"Circuit breaker untuk subagent '{subagent_id}' telah di-reset ke CLOSED."}

        elif tool_name == "lgp_run_create":
            objective = arguments.get("objective", "")
            subagents = arguments.get("subagents")
            thread_id = f"th-{time.strftime('%Y%m%d%H%M%S')}"
            result = await self.orchestrator.execute_run(thread_id, objective, subagents)
            GlobalEventBus.get_instance().publish_sync("run_updated", {"run_id": result.get("run_id"), "status": result.get("status")})
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
                GlobalEventBus.get_instance().publish_sync("hitl_updated", {"interrupt_id": interrupt_id, "approver": approver, "decision": decision})
                return {"status": "success", "interrupt_id": interrupt_id, "decision": decision}
            finally:
                await db.close()

        elif tool_name in ["lgp_memory_query", "memory_recall"]:
            subject = arguments.get("subject") or arguments.get("query")
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

        elif tool_name in ["lgp_memory_store_fact", "memory_store"]:
            subject = arguments.get("subject", "")
            if not subject and arguments.get("category"):
                cat = arguments.get("category")
                key = arguments.get("key", "")
                subject = f"{cat}:{key}" if key else cat
            predicate = arguments.get("predicate") or "has_value"
            obj = arguments.get("object") or arguments.get("value", "")
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
                GlobalEventBus.get_instance().publish_sync("memory_updated", {
                    "action": "store",
                    "fact_id": fact.fact_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate
                })
                return {"status": "success", "fact": fact.model_dump()}
            finally:
                await db.close()

        elif tool_name in ["lgp_memory_invalidate_fact", "memory_forget"]:
            fact_id = arguments.get("fact_id", "")
            now = time.time()
            db = await get_db_connection()
            try:
                await db.execute("UPDATE temporal_facts SET invalid_at = ? WHERE fact_id = ?", (now, fact_id))
                await db.commit()
                GlobalEventBus.get_instance().publish_sync("memory_updated", {
                    "action": "invalidate",
                    "fact_id": fact_id,
                    "invalid_at": now
                })
                return {"status": "success", "fact_id": fact_id, "invalid_at": now}
            finally:
                await db.close()

        elif tool_name in ["lgp_correlation_matrix", "graph_stats"]:
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
                GlobalEventBus.get_instance().publish_sync("correlation_updated", {
                    "alpha": alpha, "beta": beta, "gamma": gamma, "n_min": n_min
                })
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

                    raw_ts = log["created_at"]
                    ts_val = round(raw_ts.timestamp(), 3) if hasattr(raw_ts, "timestamp") else round(float(raw_ts), 3)
                    payload_to_hash = f"{log['prev_hash']}:{log['log_id']}:{log['actor']}:{log['action']}:{log['scope']}:{log['args_hash']}:{log['result_status']}:{ts_val}"
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

        elif tool_name == "lgp_platform_health":
            db = await get_db_connection()
            try:
                async with db.execute("SELECT COUNT(*) as cnt FROM subagent_registry WHERE is_active=1") as cursor:
                    row = await cursor.fetchone()
                    active_subagents = row["cnt"] if row else 0
                return {
                    "status": "healthy",
                    "version": "2.0.0",
                    "platform": "Enterprise LangGraph Platform (LGP v2.0)",
                    "subagents_active": active_subagents,
                    "supervisor": "atlas",
                    "storage": "SQLite WAL Mode (Enterprise Ready)",
                    "mcp_admin": "active",
                    "timestamp": time.time()
                }
            finally:
                await db.close()

        elif tool_name == "lgp_hitl_inbox_list":
            status_filter = arguments.get("status", "pending")
            db = await get_db_connection()
            try:
                if status_filter == "all":
                    query = "SELECT * FROM hitl_inbox ORDER BY created_at DESC"
                    params = ()
                else:
                    query = "SELECT * FROM hitl_inbox WHERE status = ? ORDER BY created_at DESC"
                    params = (status_filter,)

                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return {"interrupts": [dict(r) for r in rows], "count": len(rows), "status_filter": status_filter}
            finally:
                await db.close()

        elif tool_name in ["lgp_memory_organized_summary", "memory_list"]:
            return await MemoryCuratorEngine.get_organized_memory_summary()

        elif tool_name in ["lgp_graphiti_neuron_graph", "graph_query"]:
            return await GraphitiMemoryEngine.build_neuron_graph()

        elif tool_name == "lgp_memory_seed":
            res = await MemoryCuratorEngine.seed_system_knowledge()
            GlobalEventBus.get_instance().publish_sync("memory_updated", {"action": "seed", "inserted": res.get("inserted", 0)})
            return res

        elif tool_name == "lgp_api_request":
            method = arguments.get("method", "GET").upper()
            endpoint = arguments.get("endpoint", "/api/health")
            params = arguments.get("params") or {}
            body = arguments.get("body") or {}

            if not endpoint.startswith("/"):
                endpoint = "/" + endpoint
            url = f"http://localhost:8000{endpoint}"

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.request(
                        method=method,
                        url=url,
                        params=params if params else None,
                        json=body if method in ["POST", "PUT", "PATCH"] and body else None
                    )
                    try:
                        data = resp.json()
                    except Exception:
                        data = resp.text

                    if method in ["POST", "PUT", "PATCH", "DELETE"]:
                        GlobalEventBus.get_instance().publish_sync("api_mutation", {
                            "method": method,
                            "endpoint": endpoint,
                            "status_code": resp.status_code
                        })
                        if "memory" in endpoint:
                            GlobalEventBus.get_instance().publish_sync("memory_updated", {"source": "api_request"})
                        elif "runs" in endpoint:
                            GlobalEventBus.get_instance().publish_sync("run_updated", {"source": "api_request"})
                        elif "hitl" in endpoint:
                            GlobalEventBus.get_instance().publish_sync("hitl_updated", {"source": "api_request"})

                    return {
                        "status_code": resp.status_code,
                        "data": data,
                        "endpoint": endpoint
                    }
            except Exception as e:
                return {"error": f"API request error: {str(e)}", "endpoint": endpoint}

        # Kanban Board Management
        elif tool_name == "lgp_kanban_list_boards":
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM kanban_boards ORDER BY created_at DESC") as cursor:
                    rows = await cursor.fetchall()
                    return {"boards": [dict(r) for r in rows], "count": len(rows)}
            finally:
                await db.close()

        elif tool_name == "lgp_kanban_get_board":
            board_id = arguments.get("board_id", "")
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM kanban_boards WHERE id = ?", (board_id,)) as cursor:
                    board_row = await cursor.fetchone()
                    if not board_row:
                        return {"error": f"Board '{board_id}' tidak ditemukan"}
                
                async with db.execute("SELECT * FROM kanban_columns WHERE board_id = ? ORDER BY order_idx ASC", (board_id,)) as cursor:
                    columns = [dict(r) for r in await cursor.fetchall()]
                
                for col in columns:
                    async with db.execute("SELECT * FROM kanban_cards WHERE column_id = ? ORDER BY created_at ASC", (col["id"],)) as cursor:
                        col["cards"] = [dict(r) for r in await cursor.fetchall()]
                
                return {**dict(board_row), "columns": columns}
            finally:
                await db.close()

        elif tool_name == "lgp_kanban_create_board":
            name = arguments.get("name", "")
            columns = arguments.get("columns", [])
            
            db = await get_db_connection()
            try:
                board_id = f"board-{int(time.time() * 1000)}"
                now = time.time()
                await db.execute(
                    "INSERT INTO kanban_boards (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (board_id, name, now, now)
                )
                
                for i, col in enumerate(columns):
                    col_id = f"col-{int(time.time() * 1000)}-{i}"
                    await db.execute(
                        "INSERT INTO kanban_columns (id, board_id, name, order_idx) VALUES (?, ?, ?, ?)",
                        (col_id, board_id, col.get("name", ""), i)
                    )
                
                await db.commit()
                GlobalEventBus.get_instance().publish_sync("kanban_updated", {"board_id": board_id})
                return {"board_id": board_id, "status": "created", "name": name}
            finally:
                await db.close()

        elif tool_name == "lgp_kanban_create_card":
            board_id = arguments.get("board_id", "")
            column_name = arguments.get("column_name", "")
            title = arguments.get("title", "")
            description = arguments.get("description", "")
            priority = arguments.get("priority", "medium")
            assigned_to = arguments.get("assigned_to")
            
            db = await get_db_connection()
            try:
                # Find column by name
                async with db.execute("SELECT id FROM kanban_columns WHERE board_id = ? AND name = ?", (board_id, column_name)) as cursor:
                    col_row = await cursor.fetchone()
                    if not col_row:
                        return {"error": f"Column '{column_name}' tidak ditemukan di board '{board_id}'"}
                    column_id = col_row["id"]
                
                card_id = f"card-{int(time.time() * 1000)}"
                now = time.time()
                await db.execute(
                    "INSERT INTO kanban_cards (id, column_id, title, description, priority, assigned_to, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (card_id, column_id, title, description, priority, assigned_to, now, now)
                )
                await db.commit()
                GlobalEventBus.get_instance().publish_sync("kanban_updated", {"card_id": card_id})
                return {"card_id": card_id, "status": "created", "column_id": column_id}
            finally:
                await db.close()

        elif tool_name == "lgp_kanban_move_card":
            card_id = arguments.get("card_id", "")
            to_column_name = arguments.get("to_column_name", "")
            
            db = await get_db_connection()
            try:
                # Get current card to find board_id
                async with db.execute("SELECT kc.board_id FROM kanban_cards k JOIN kanban_columns kc ON k.column_id = kc.id WHERE k.id = ?", (card_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return {"error": f"Card '{card_id}' tidak ditemukan"}
                    board_id = row["board_id"]
                
                # Find target column
                async with db.execute("SELECT id FROM kanban_columns WHERE board_id = ? AND name = ?", (board_id, to_column_name)) as cursor:
                    col_row = await cursor.fetchone()
                    if not col_row:
                        return {"error": f"Column '{to_column_name}' tidak ditemukan"}
                    to_column_id = col_row["id"]
                
                await db.execute(
                    "UPDATE kanban_cards SET column_id = ?, updated_at = ? WHERE id = ?",
                    (to_column_id, time.time(), card_id)
                )
                await db.commit()
                GlobalEventBus.get_instance().publish_sync("kanban_updated", {"card_id": card_id})
                return {"status": "moved", "card_id": card_id, "to_column": to_column_name}
            finally:
                await db.close()

        # Matrix Configuration Management
        elif tool_name == "lgp_matrix_get_config":
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM matrix_config WHERE id = 'default'") as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
                    return {
                        "id": "default",
                        "name": "Default Configuration",
                        "description": "Default correlation matrix weights",
                        "alpha": 0.4,
                        "beta": 0.4,
                        "gamma": 0.2,
                        "n_min": 50,
                        "enabled": True,
                        "created_at": time.time()
                    }
            finally:
                await db.close()

        elif tool_name == "lgp_matrix_update_config":
            alpha = arguments.get("alpha")
            beta = arguments.get("beta")
            gamma = arguments.get("gamma")
            n_min = arguments.get("n_min")
            enabled = arguments.get("enabled")
            
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM matrix_config WHERE id = 'default'") as cursor:
                    row = await cursor.fetchone()
                
                current = dict(row) if row else {
                    "alpha": 0.4, "beta": 0.4, "gamma": 0.2, "n_min": 50, "enabled": True
                }
                
                if alpha is not None: current["alpha"] = alpha
                if beta is not None: current["beta"] = beta
                if gamma is not None: current["gamma"] = gamma
                if n_min is not None: current["n_min"] = n_min
                if enabled is not None: current["enabled"] = 1 if enabled else 0
                
                await db.execute("""
                    INSERT INTO matrix_config (id, name, description, alpha, beta, gamma, n_min, enabled, created_at)
                    VALUES ('default', 'Default Configuration', 'Default correlation matrix weights', ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET alpha=?, beta=?, gamma=?, n_min=?, enabled=?
                """, (current["alpha"], current["beta"], current["gamma"], current["n_min"], current["enabled"], time.time(),
                      current["alpha"], current["beta"], current["gamma"], current["n_min"], current["enabled"]))
                await db.commit()
                GlobalEventBus.get_instance().publish_sync("matrix_updated", current)
                return {"status": "updated", "config": current}
            finally:
                await db.close()

        elif tool_name == "lgp_matrix_recalculate":
            calc = await self._get_correlation_calc()
            db = await get_db_connection()
            try:
                async with db.execute("SELECT * FROM correlation_edges") as cursor:
                    rows = await cursor.fetchall()
                    edges = [CorrelationEdge(**dict(r)) for r in rows]
                
                matrix = calc.generate_10x10_matrix(edges)
                GlobalEventBus.get_instance().publish_sync("correlation_updated", matrix)
                return {"status": "recalculated", "matrix": matrix, "edges_count": len(edges)}
            finally:
                await db.close()

        return {"error": f"Tool '{tool_name}' tidak dikenali"}
