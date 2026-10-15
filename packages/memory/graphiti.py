import os
import time
import socket
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

# Matikan telemetry/PostHog agar latency minimal dan tidak blocking
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from packages.core.db import get_db_connection

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("lgp.memory.graphiti")

def resolve_router_base_url() -> str:
    """Deteksi local IPv4 reverse proxy (20128) atau fallback ke domain HTTPS publik."""
    env_url = os.environ.get("ROUTER_BASE_URL") or os.environ.get("NINE_ROUTER_BASE_URL")
    if env_url:
        return env_url
    try:
        with socket.create_connection(("127.0.0.1", 20128), timeout=0.3):
            return "http://127.0.0.1:20128/v1"
    except Exception:
        return "https://9router.biezz.my.id/v1"

# Check availability of graphiti-core & falkordb
try:
    from falkordb import FalkorDB
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    GRAPHITI_AVAILABLE = True
except ImportError as e:
    GRAPHITI_AVAILABLE = False
    FalkorDB = None
    Graphiti = None
    FalkorDriver = None
    OpenAIGenericClient = None
    LLMConfig = None
    OpenAIEmbedder = object
    OpenAIEmbedderConfig = None
    CrossEncoderClient = object
    logger.warning("graphiti-core or falkordb not installed; will use SQLite fallback: %s", e)


class MemoryTaxonomy:
    """Ontologi dan taksonomi memori subagent LGP v2.0."""
    CATEGORIES = [
        "episodic",    # Log kejadian, run_id, percakapan, jejak runtime
        "semantic",    # Fakta bisnis, kebijakan platform, referensi entitas
        "procedural",  # SOP subagent, prompt chains, tool bindings
        "working",     # State aktif di checkpoint (scratchpad, draft)
        "meta"         # Audit log, konsensus, evaluasi performa, metrik
    ]

    CATEGORY_COLORS = {
        "episodic": "#3b82f6",    # Blue
        "semantic": "#10b981",    # Emerald
        "procedural": "#f59e0b",  # Amber
        "working": "#8b5cf6",     # Violet
        "meta": "#64748b"         # Slate
    }


class BiTemporalEdge(BaseModel):
    """Representasi edge bi-temporal pada knowledge graph memori."""
    source_id: str
    target_id: str
    relation: str
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphitiNeuronNode(BaseModel):
    """Representasi node neuron memori untuk visualisasi kanvas MiroFish."""
    id: str
    label: str
    neuron_type: str = "entity"  # 'category' | 'subagent' | 'entity' | 'episode'
    charge: float = 1.0
    category: str = "semantic"
    status: str = "active"       # 'active' | 'invalid' | 'decaying'
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


if GRAPHITI_AVAILABLE:
    class SimpleCrossEncoder(CrossEncoderClient):
        """Cross-encoder passthrough berbobot konstan untuk konsumsi memori minimal."""
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            return [(p, 1.0) for p in passages]

    class FallbackOpenAIEmbedder(OpenAIEmbedder):
        """Embedder dengan fallback otomatis dari nv-embedqa-e5-v5 ke text-embedding-3-small."""
        def __init__(self, primary_config: OpenAIEmbedderConfig, fallback_config: OpenAIEmbedderConfig):
            super().__init__(primary_config)
            self.fallback_config = fallback_config
            self._using_fallback = False
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=primary_config.api_key, base_url=primary_config.base_url, timeout=12.0, max_retries=1)
            self.fallback_client = AsyncOpenAI(api_key=fallback_config.api_key, base_url=fallback_config.base_url, timeout=12.0, max_retries=1)

        def _activate_fallback(self, reason: Any):
            if not self._using_fallback:
                logger.warning(
                    "Primary embedder '%s' gagal (%s). Beralih ke fallback '%s'",
                    self.config.embedding_model, reason, self.fallback_config.embedding_model
                )
                self._using_fallback = True
                self.config = self.fallback_config
                self.client = self.fallback_client

        async def create(self, input_data: Union[str, list[str]]) -> list[float]:
            if not self._using_fallback:
                try:
                    result = await self.client.embeddings.create(
                        input=input_data, model=self.config.embedding_model
                    )
                    return result.data[0].embedding[: self.config.embedding_dim]
                except Exception as e:
                    self._activate_fallback(e)
            result = await self.fallback_client.embeddings.create(
                input=input_data, model=self.fallback_config.embedding_model
            )
            return result.data[0].embedding[: self.fallback_config.embedding_dim]

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            if not self._using_fallback:
                try:
                    result = await self.client.embeddings.create(
                        input=input_data_list, model=self.config.embedding_model
                    )
                    return [emb.embedding[: self.config.embedding_dim] for emb in result.data]
                except Exception as e:
                    self._activate_fallback(e)
            result = await self.fallback_client.embeddings.create(
                input=input_data_list, model=self.fallback_config.embedding_model
            )
            return [emb.embedding[: self.fallback_config.embedding_dim] for emb in result.data]


class GraphitiMemoryEngine:
    """
    Engine integrasi memori temporal Graphiti & FalkorDB.
    Mendukung ingest episode secara dinamis, ekstraksi entitas temporal,
    dan query Cypher graph neuron dengan fallback aman ke database relasional (SQLite/Supabase).
    """

    FALKORDB_HOST = os.environ.get("FALKORDB_HOST", "localhost")
    FALKORDB_PORT = int(os.environ.get("FALKORDB_PORT", "6382"))
    FALKORDB_DB = os.environ.get("FALKORDB_DB", "langgraph")

    ROUTER_BASE_URL = resolve_router_base_url()
    ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", os.environ.get("NINE_ROUTER_API_KEY", ""))
    ROUTER_LLM_MODEL = os.environ.get("ROUTER_LLM_MODEL", "hermes")
    ROUTER_EMBED_PRIMARY = os.environ.get("ROUTER_EMBED_PRIMARY", "nvidia/nvidia/nv-embedqa-e5-v5")
    ROUTER_EMBED_FALLBACK = os.environ.get("ROUTER_EMBED_FALLBACK", "openrouter/openai/text-embedding-3-small")
    EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))

    _driver: Optional[Any] = None
    _driver_loop: Optional[asyncio.AbstractEventLoop] = None
    _graphiti: Optional[Any] = None
    _graphiti_loop: Optional[asyncio.AbstractEventLoop] = None
    _falkor_available: bool = True

    @classmethod
    async def get_driver(cls) -> Optional[Any]:
        """Lazy initialization FalkorDriver singleton dengan health check singkat dan loop safety."""
        if not GRAPHITI_AVAILABLE:
            return None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if cls._driver is not None and cls._driver_loop is current_loop:
            return cls._driver

        try:
            driver = FalkorDriver(
                host=cls.FALKORDB_HOST,
                port=cls.FALKORDB_PORT,
                database=cls.FALKORDB_DB
            )
            # Quick health check
            await driver.execute_query("RETURN 1 AS ping")
            cls._driver = driver
            cls._driver_loop = current_loop
            cls._falkor_available = True
            logger.info("FalkorDriver terhubung ke %s:%s (DB: %s)", cls.FALKORDB_HOST, cls.FALKORDB_PORT, cls.FALKORDB_DB)
            return cls._driver
        except Exception as e:
            cls._falkor_available = False
            logger.warning("FalkorDB tidak dapat dihubungi (%s). Menggunakan fallback.", e)
            return None

    @classmethod
    async def get_graphiti(cls) -> Optional[Any]:
        """Lazy initialization Graphiti instance dengan 9Router LLM dan Embedder."""
        if not GRAPHITI_AVAILABLE:
            return None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if cls._graphiti is not None and cls._graphiti_loop is current_loop:
            return cls._graphiti

        driver = await cls.get_driver()
        if driver is None:
            return None

        try:
            llm_cfg = LLMConfig(
                api_key=cls.ROUTER_API_KEY,
                base_url=cls.ROUTER_BASE_URL,
                model=cls.ROUTER_LLM_MODEL,
                temperature=0.0
            )
            llm_client = OpenAIGenericClient(config=llm_cfg, structured_output_mode="json_object")

            embed_primary_cfg = OpenAIEmbedderConfig(
                api_key=cls.ROUTER_API_KEY,
                base_url=cls.ROUTER_BASE_URL,
                embedding_model=cls.ROUTER_EMBED_PRIMARY,
                embedding_dim=cls.EMBEDDING_DIM
            )
            embed_fallback_cfg = OpenAIEmbedderConfig(
                api_key=cls.ROUTER_API_KEY,
                base_url=cls.ROUTER_BASE_URL,
                embedding_model=cls.ROUTER_EMBED_FALLBACK,
                embedding_dim=cls.EMBEDDING_DIM
            )
            embedder = FallbackOpenAIEmbedder(embed_primary_cfg, embed_fallback_cfg)
            cross_encoder = SimpleCrossEncoder()

            # Build indices if needed
            try:
                await driver.build_indices_and_constraints()
            except Exception as idx_err:
                logger.debug("Indices/constraints info: %s", idx_err)

            g = Graphiti(
                graph_driver=driver,
                llm_client=llm_client,
                embedder=embedder,
                cross_encoder=cross_encoder
            )
            cls._graphiti = g
            cls._graphiti_loop = current_loop
            logger.info("Graphiti Memory Engine siap dengan model LLM %s", cls.ROUTER_LLM_MODEL)
            return cls._graphiti
        except Exception as e:
            logger.error("Gagal menginisialisasi Graphiti: %s", e)
            return None

    @classmethod
    async def add_episode(
        cls,
        name: str,
        episode_body: str,
        source_description: str = "LGP API Ingestion",
        reference_time: Optional[datetime] = None,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Ingest episode percakapan/eksekusi ke Graphiti temporal knowledge graph."""
        ref_time = reference_time or datetime.now(timezone.utc)
        g = await cls.get_graphiti()

        if g is not None:
            try:
                res = await g.add_episode(
                    name=name,
                    episode_body=episode_body,
                    source_description=source_description,
                    reference_time=ref_time,
                    group_id=group_id
                )
                return {
                    "status": "success",
                    "engine": "graphiti_falkordb",
                    "episode_uuid": getattr(res.episode, "uuid", None),
                    "name": name,
                    "nodes_extracted": len(getattr(res, "nodes", [])),
                    "edges_extracted": len(getattr(res, "edges", [])),
                    "reference_time": ref_time.isoformat()
                }
            except Exception as e:
                logger.error("Graphiti add_episode gagal: %s. Menyimpan fallback catatan.", e)

        # Fallback recording ke database relasional agar data tidak hilang
        try:
            db = await get_db_connection()
            fact_id = f"fact-ep-{int(time.time() * 1000)}"
            async with db.execute(
                "INSERT INTO temporal_facts (fact_id, subject, predicate, object, valid_at, group_id, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fact_id, name, "EPISODE_RECORD", episode_body[:500], ref_time.isoformat(), group_id or "default", "active")
            ):
                await db.commit()
            await db.close()
            return {
                "status": "fallback_recorded",
                "engine": "relational_fallback",
                "fact_id": fact_id,
                "name": name,
                "nodes_extracted": 1,
                "edges_extracted": 0,
                "reference_time": ref_time.isoformat()
            }
        except Exception as db_err:
            return {
                "status": "error",
                "message": f"Episode ingestion error: {db_err}",
                "name": name
            }

    @classmethod
    async def build_neuron_graph(cls) -> Dict[str, Any]:
        """
        Membangun struktur graph neuron MiroFish.
        Mencoba query Cypher ke FalkorDB secara langsung untuk mengambil node
        dan edge bi-temporal (valid_at, invalid_at). Jika FalkorDB gagal,
        secara otomatis fallback ke query relasional (SQLite/Supabase).
        """
        driver = await cls.get_driver()
        if driver is not None:
            try:
                return await cls._build_neuron_graph_falkordb(driver)
            except Exception as e:
                logger.warning("Query Cypher FalkorDB gagal (%s). Menggunakan fallback relasional.", e)

        return await cls._build_neuron_graph_fallback()

    @classmethod
    async def _build_neuron_graph_falkordb(cls, driver: Any) -> Dict[str, Any]:
        """Ambil node & edge bi-temporal dari FalkorDB dan gabungkan dengan subagents & categories."""
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_map: set = set()

        # 1. Pasang 5 Hub Kategori Utama (Taxonomy)
        for cat in MemoryTaxonomy.CATEGORIES:
            cat_id = f"cat-{cat.lower()}"
            nodes.append({
                "id": cat_id,
                "label": cat.upper(),
                "type": "category",
                "category": cat.lower(),
                "charge": 1.0,
                "status": "active",
                "size": 24,
                "color": MemoryTaxonomy.CATEGORY_COLORS.get(cat.lower(), "#64748b")
            })
            node_map.add(cat_id)

        # 2. Ambil 10 Subagent dari DB relasional
        db = await get_db_connection()
        try:
            async with db.execute(
                "SELECT id, name, role, pod, capabilities, model_policy, budget_config, trust_level FROM subagent_registry"
            ) as cursor:
                subagents = await cursor.fetchall()
                for sa_row in subagents:
                    sa = dict(sa_row)
                    sa_id = f"agent-{sa['id']}"
                    nodes.append({
                        "id": sa_id,
                        "label": sa["name"],
                        "type": "subagent",
                        "category": "procedural",
                        "charge": 0.9,
                        "status": "active",
                        "size": 18,
                        "color": "#0ea5e9",
                        "attributes": {
                            "role": sa["role"],
                            "pod": sa["pod"],
                            "trust_level": sa["trust_level"]
                        }
                    })
                    node_map.add(sa_id)

                    # Link subagent ke category procedural
                    edges.append({
                        "id": f"link-{sa_id}-cat-procedural",
                        "source": sa_id,
                        "target": "cat-procedural",
                        "relation": "HAS_CAPABILITY",
                        "weight": 0.8,
                        "color": "#334155"
                    })

            # 3. Ambil Inter-Neuron Correlation Edges
            async with db.execute(
                "SELECT source_subagent, target_subagent, composite_weight, npmi_coactivation, polarity "
                "FROM correlation_edges WHERE composite_weight > 0"
            ) as cursor:
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
        finally:
            await db.close()

        # 4. Query FalkorDB Cypher untuk Node Entitas & Episode
        nodes_res = await driver.execute_query("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")
        falkor_nodes_raw = nodes_res[0] if nodes_res else []

        falkor_entity_count = 0
        falkor_episode_count = 0

        for row in falkor_nodes_raw:
            labels = row.get("labels", [])
            props = dict(row.get("props", {}))
            uuid = props.get("uuid")
            if not uuid:
                continue

            name = props.get("name", "Unknown")
            is_episodic = "Episodic" in labels

            if is_episodic:
                node_id = f"episode-{uuid}"
                ntype = "episode"
                ncat = "episodic"
                color = "#3b82f6"
                size = 13
                falkor_episode_count += 1
            else:
                node_id = f"entity-{uuid}"
                ntype = "entity"
                ncat = "semantic"
                color = "#a855f7"
                size = 15
                falkor_entity_count += 1

            nodes.append({
                "id": node_id,
                "label": name,
                "type": ntype,
                "category": ncat,
                "charge": 0.85,
                "status": "active",
                "size": size,
                "color": color,
                "valid_at": props.get("valid_at") or props.get("created_at"),
                "invalid_at": props.get("invalid_at"),
                "attributes": {
                    "uuid": uuid,
                    "summary": props.get("summary") or props.get("content") or "",
                    "created_at": props.get("created_at")
                }
            })
            node_map.add(node_id)

            # Link ke category hub
            cat_target = f"cat-{ncat}"
            if cat_target in node_map:
                edges.append({
                    "id": f"link-{node_id}-{cat_target}",
                    "source": node_id,
                    "target": cat_target,
                    "relation": "PART_OF",
                    "weight": 0.6,
                    "color": "#475569"
                })

            # Hubungkan ke subagent jika entitas mereferensikan nama subagent
            for sa_key in ["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"]:
                if sa_key in name.lower():
                    sa_node = f"agent-{sa_key}"
                    if sa_node in node_map:
                        edges.append({
                            "id": f"link-{sa_node}-{node_id}",
                            "source": sa_node,
                            "target": node_id,
                            "relation": "REPRESENTATION",
                            "weight": 1.4,
                            "color": "#38bdf8"
                        })
                    break

        # 5. Query FalkorDB Cypher untuk Edge Bi-Temporal
        edges_res = await driver.execute_query(
            "MATCH (a)-[r]->(b) "
            "RETURN a.uuid AS src_uuid, labels(a) AS src_labels, "
            "       type(r) AS rel_type, properties(r) AS rel_props, "
            "       b.uuid AS tgt_uuid, labels(b) AS tgt_labels"
        )
        falkor_edges_raw = edges_res[0] if edges_res else []

        for row in falkor_edges_raw:
            src_uuid = row.get("src_uuid")
            tgt_uuid = row.get("tgt_uuid")
            if not src_uuid or not tgt_uuid:
                continue

            src_labels = row.get("src_labels") or []
            tgt_labels = row.get("tgt_labels") or []
            src_id = f"episode-{src_uuid}" if "Episodic" in src_labels else f"entity-{src_uuid}"
            tgt_id = f"episode-{tgt_uuid}" if "Episodic" in tgt_labels else f"entity-{tgt_uuid}"

            if src_id in node_map and tgt_id in node_map:
                rel_props = dict(row.get("rel_props") or {})
                rel_type = row.get("rel_type") or "RELATES_TO"
                relation_name = rel_props.get("name") or rel_type
                valid_at = rel_props.get("valid_at")
                invalid_at = rel_props.get("invalid_at")
                is_invalid = bool(invalid_at)

                edge_uuid = rel_props.get("uuid") or f"{src_uuid[:8]}-{tgt_uuid[:8]}_{relation_name}"
                edges.append({
                    "id": f"falkor-{edge_uuid}",
                    "source": src_id,
                    "target": tgt_id,
                    "relation": relation_name,
                    "detail": rel_props.get("fact") or "",
                    "valid_at": valid_at,
                    "invalid_at": invalid_at,
                    "weight": 1.2 if not is_invalid else 0.4,
                    "color": "#f43f5e" if is_invalid else ("#60a5fa" if rel_type == "MENTIONS" else "#10b981"),
                    "bitemporal": True
                })

        return {
            "engine": "Graphiti v0.4 (FalkorDB Temporal Graph)",
            "style": "MiroFish Spiking Neuron Architecture",
            "timestamp": time.time(),
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "falkordb_entities": falkor_entity_count,
                "falkordb_episodes": falkor_episode_count,
                "falkordb_edges": len(falkor_edges_raw),
                "subagents": 10,
                "categories": len(MemoryTaxonomy.CATEGORIES)
            }
        }

    @classmethod
    async def _build_neuron_graph_fallback(cls) -> Dict[str, Any]:
        """Fallback membangun graph neuron dari SQLite/Postgres bila FalkorDB tidak aktif."""
        db = await get_db_connection()
        try:
            nodes: List[Dict[str, Any]] = []
            edges: List[Dict[str, Any]] = []
            node_map: set = set()

            # Hub Kategori
            for cat in MemoryTaxonomy.CATEGORIES:
                cat_id = f"cat-{cat.lower()}"
                nodes.append({
                    "id": cat_id,
                    "label": cat.upper(),
                    "type": "category",
                    "category": cat.lower(),
                    "charge": 1.0,
                    "status": "active",
                    "size": 24,
                    "color": MemoryTaxonomy.CATEGORY_COLORS.get(cat.lower(), "#64748b")
                })
                node_map.add(cat_id)

            # Subagent Registry
            async with db.execute(
                "SELECT id, name, role, pod, capabilities, model_policy, budget_config, trust_level FROM subagent_registry"
            ) as cursor:
                subagents = await cursor.fetchall()
                for sa_row in subagents:
                    sa = dict(sa_row)
                    sa_id = f"agent-{sa['id']}"
                    nodes.append({
                        "id": sa_id,
                        "label": sa["name"],
                        "type": "subagent",
                        "category": "procedural",
                        "charge": 0.9,
                        "status": "active",
                        "size": 18,
                        "color": "#0ea5e9",
                        "attributes": {
                            "role": sa["role"],
                            "pod": sa["pod"],
                            "trust_level": sa["trust_level"]
                        }
                    })
                    node_map.add(sa_id)

                    edges.append({
                        "id": f"link-{sa_id}-cat-procedural",
                        "source": sa_id,
                        "target": "cat-procedural",
                        "relation": "HAS_CAPABILITY",
                        "weight": 0.8,
                        "color": "#334155"
                    })

            # Temporal Facts dari DB
            async with db.execute("SELECT * FROM temporal_facts ORDER BY created_at DESC") as cursor:
                facts = await cursor.fetchall()
                for f_row in facts:
                    fact = dict(f_row)
                    node_id = f"fact-{fact['fact_id']}"
                    is_invalid = fact.get("invalid_at") is not None or fact.get("status") == "invalid"
                    group = fact.get("group_id", "semantic")

                    nodes.append({
                        "id": node_id,
                        "label": f"{fact.get('subject', 'Fact')}:{fact.get('predicate', 'PROP')}",
                        "type": "entity",
                        "category": group.lower() if group.lower() in MemoryTaxonomy.CATEGORIES else "semantic",
                        "charge": 0.5 if is_invalid else 0.85,
                        "status": "invalid" if is_invalid else "active",
                        "size": 12 if is_invalid else 15,
                        "color": "#f43f5e" if is_invalid else "#10b981",
                        "valid_at": fact.get("valid_at"),
                        "invalid_at": fact.get("invalid_at"),
                        "attributes": {
                            "subject": fact.get("subject"),
                            "predicate": fact.get("predicate"),
                            "object": fact.get("object"),
                            "group_id": group
                        }
                    })
                    node_map.add(node_id)

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

            # Correlation Edges
            async with db.execute(
                "SELECT source_subagent, target_subagent, composite_weight, npmi_coactivation, polarity "
                "FROM correlation_edges WHERE composite_weight > 0"
            ) as cursor:
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
                "engine": "Graphiti (SQLite/Relational Fallback)",
                "style": "MiroFish Spiking Neuron Architecture",
                "timestamp": time.time(),
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "active_facts": len([n for n in nodes if n.get("status") == "active"]),
                    "subagents": 10,
                    "categories": len(MemoryTaxonomy.CATEGORIES)
                }
            }
        finally:
            await db.close()
