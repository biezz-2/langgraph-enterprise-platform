import time
import json
from typing import List, Dict, Any, Optional
from packages.core.db import get_db_connection
from packages.memory.curator import MemoryCuratorEngine, MemoryTaxonomy

class GraphitiMemoryEngine:
    """Engine Graphiti Temporal Knowledge Graph untuk LGP v2.0.
    Mengonversi temporal facts, registri subagent, dan korelasi menjadi struktur
    Neuron Graph MiroFish dengan klusterikasi bi-temporal.
    """

    POD_COLORS = {
        "Supervision": "#f4f4f5",     # Zinc 100 (Atlas Supervisor)
        "Riset & Sintesis": "#34d399", # Emerald 400 (Clio, Iris)
        "Koding & Eksekusi": "#818cf8",# Indigo 400 (Vulcan, Athena)
        "Platform Ops": "#fbbf24",    # Amber 400 (Hermes, Mnemosyne)
        "Tata Kelola": "#f472b6",     # Pink 400 (Janus, Themis, Metron)
        "Category": "#38bdf8",        # Sky 400 (Hub Categories)
        "User_Preference": "#c084fc", # Purple 400
        "Project": "#0ea5e9",         # Sky 500
        "Integration": "#f59e0b",     # Amber 500
        "Device": "#10b981",          # Emerald 500
        "Session": "#94a3b8",         # Slate 400
        "Subagent": "#818cf8",        # Indigo 400
        "Model": "#e879f9",           # Fuchsia 400
        "Architecture": "#2dd4bf",    # Teal 400
        "Security": "#f43f5e",        # Rose 500
        "Telemetry": "#3b82f6",       # Blue 500
        "System": "#a1a1aa"           # Zinc 400
    }

    @classmethod
    async def build_neuron_graph(cls) -> Dict[str, Any]:
        """Membuat payload Neuron Graph MiroFish lengkap berbasis Graphiti Engine."""
        db = await get_db_connection()
        nodes = []
        edges = []
        node_map = {}

        try:
            # 1. Fetch Taxonomy & Categories as central hub nodes
            for cat, desc in MemoryTaxonomy.CATEGORIES.items():
                cat_id = f"cat-{cat.lower()}"
                node = {
                    "id": cat_id,
                    "label": cat,
                    "type": "category",
                    "group": cat,
                    "color": cls.POD_COLORS.get(cat, cls.POD_COLORS["Category"]),
                    "size": 28,
                    "description": desc,
                    "status": "active",
                    "icon": "HUB"
                }
                nodes.append(node)
                node_map[cat_id] = node

            # 2. Fetch Subagents & add as agent nodes
            async with db.execute("SELECT id, name, role, pod, capabilities, model_policy, budget_config, trust_level FROM subagent_registry") as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    sa = dict(r)
                    sa_id = f"agent-{sa['id']}"
                    pod_color = cls.POD_COLORS.get(sa["pod"], "#818cf8")

                    try:
                        caps = json.loads(sa["capabilities"]) if isinstance(sa["capabilities"], str) else sa["capabilities"]
                    except Exception:
                        caps = []

                    try:
                        budget = json.loads(sa["budget_config"]) if isinstance(sa["budget_config"], str) else sa["budget_config"]
                    except Exception:
                        budget = {}

                    node = {
                        "id": sa_id,
                        "label": sa["name"],
                        "type": "subagent",
                        "group": sa["pod"],
                        "color": pod_color,
                        "size": 22,
                        "role": sa["role"],
                        "pod": sa["pod"],
                        "trust_level": sa["trust_level"],
                        "model_policy": sa["model_policy"],
                        "budget": budget,
                        "capabilities": caps,
                        "description": f"Subagent {sa['name']} ({sa['role']}) dalam Pod {sa['pod']}. Policy: {sa['model_policy']}.",
                        "status": "active",
                        "icon": sa['id'][:2].upper()
                    }
                    nodes.append(node)
                    node_map[sa_id] = node

                    # Connect subagent to Subagent category node
                    edges.append({
                        "id": f"edge-{sa_id}-cat",
                        "source": sa_id,
                        "target": "cat-subagent",
                        "relation": "REGISTERED_IN",
                        "weight": 1.5,
                        "color": "#38bdf8"
                    })

            # 3. Fetch Temporal Facts & convert into entity nodes & edges
            async with db.execute("SELECT * FROM temporal_facts ORDER BY created_at DESC") as cursor:
                fact_rows = await cursor.fetchall()
                for idx, r in enumerate(fact_rows):
                    fact = dict(r)
                    subj = fact["subject"]
                    pred = fact["predicate"]
                    obj = fact["object"]
                    is_invalid = fact["invalid_at"] is not None

                    # Parse subject entity node
                    subj_clean = subj.replace(":", "_").lower()
                    node_id = f"fact-{subj_clean}"

                    if node_id not in node_map:
                        # Extract category prefix if exists
                        group = "System"
                        for cat_name in MemoryTaxonomy.CATEGORIES.keys():
                            if subj.startswith(f"{cat_name}:"):
                                group = cat_name
                                break

                        node_color = "#f43f5e" if is_invalid else cls.POD_COLORS.get(group, "#34d399")

                        node = {
                            "id": node_id,
                            "label": subj,
                            "type": "fact_entity",
                            "group": group,
                            "color": node_color,
                            "size": 14,
                            "subject": subj,
                            "predicate": pred,
                            "object": obj,
                            "valid_at": fact["valid_at"],
                            "invalid_at": fact["invalid_at"],
                            "episode_run_id": fact.get("episode_run_id"),
                            "description": f"Bi-temporal Fact: [{subj}] {pred} → {obj}",
                            "status": "invalid" if is_invalid else "active",
                            "icon": "F"
                        }
                        nodes.append(node)
                        node_map[node_id] = node

                        # Link to category node
                        cat_key = group.lower()
                        cat_node_id = f"cat-{cat_key}"
                        if cat_node_id in node_map:
                            edges.append({
                                "id": f"link-{node_id}-{cat_node_id}",
                                "source": node_id,
                                "target": cat_node_id,
                                "relation": "HAS_FACT",
                                "weight": 1.0,
                                "color": "#475569"
                            })

                    # If object looks like another subagent/entity, link edge
                    target_id = None
                    if "Pod " in obj or "Role: " in obj:
                        for sa_key in ["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"]:
                            if sa_key in subj.lower() or sa_key in obj.lower():
                                target_id = f"agent-{sa_key}"
                                break

                    if target_id and target_id in node_map:
                        edges.append({
                            "id": f"fact-edge-{fact['fact_id']}",
                            "source": node_id,
                            "target": target_id,
                            "relation": pred,
                            "detail": obj,
                            "weight": 1.2,
                            "color": "#f43f5e" if is_invalid else "#10b981"
                        })

            # 4. Fetch Correlation Edges (Inter-Neuron Handoffs)
            async with db.execute("SELECT source_subagent, target_subagent, composite_weight, npmi_coactivation, polarity FROM correlation_edges WHERE composite_weight > 0") as cursor:
                corr_rows = await cursor.fetchall()
                for r in corr_rows:
                    corr = dict(r)
                    src = f"agent-{corr['source_subagent']}"
                    tgt = f"agent-{corr['target_subagent']}"
                    if src in node_map and tgt in node_map:
                        edge_color = "#34d399" if corr["polarity"] == "positive" else ("#f43f5e" if corr["polarity"] == "negative" else "#64748b")
                        edges.append({
                            "id": f"corr-{corr['source_subagent']}-{corr['target_subagent']}",
                            "source": src,
                            "target": tgt,
                            "relation": f"NPMI: {corr['npmi_coactivation']:.2f}",
                            "weight": max(0.5, corr["composite_weight"] * 2),
                            "color": edge_color,
                            "animated": True
                        })

            return {
                "engine": "Graphiti v0.4 (Bi-Temporal Knowledge Graph)",
                "style": "MiroFish Spiking Neuron Architecture",
                "timestamp": time.time(),
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "active_facts": len([n for n in nodes if n.get("status") == "active"]),
                    "categories": len(MemoryTaxonomy.CATEGORIES)
                }
            }
        finally:
            await db.close()
