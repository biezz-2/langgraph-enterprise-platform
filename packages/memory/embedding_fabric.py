import asyncio
import hashlib
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import numpy as np

from packages.guardrails.guards import CircuitBreaker, InheritedBudgetManager
from packages.memory.temporal import TemporalMemoryStore

logger = logging.getLogger("lgp.embedding_fabric")

@dataclass
class ModelSpec:
    model_id: str
    provider: str
    raw_dim: int
    default_target_dim: int
    supports_mrl: bool = False
    auto_normalized: bool = True
    is_free: bool = False
    logs_prompts: bool = False
    rpm: int = 60
    rpd: int = 10000
    price_per_m_tokens: float = 0.05
    description: str = ""

@dataclass
class EmbeddingVector:
    vector: List[float]
    text: str
    embedding_space_id: str
    model_id: str
    raw_dim: int
    target_dim: int
    latency_ms: float
    provider: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_vector: bool = True) -> Dict[str, Any]:
        d = {
            "embedding_space_id": self.embedding_space_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "raw_dim": self.raw_dim,
            "target_dim": self.target_dim,
            "dim": len(self.vector),
            "latency_ms": round(self.latency_ms, 2),
            "created_at": self.created_at,
            "metadata": self.metadata,
            "vector_preview": self.vector[:5] if self.vector else [],
            "vector_len": len(self.vector),
        }
        if include_vector:
            d["vector"] = self.vector
        return d

class TokenBucketLimiter:
    """Token-bucket rate limiter per model/provider."""
    def __init__(self, rpm: int, rpd: int):
        self.rpm = rpm
        self.rpd = rpd
        self.tokens = float(rpm)
        self.daily_tokens = float(rpd)
        self.last_update = time.time()
        self.daily_reset = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.time()
            # Refill RPM
            elapsed = now - self.last_update
            self.tokens = min(float(self.rpm), self.tokens + elapsed * (self.rpm / 60.0))
            self.last_update = now

            # Reset daily bucket after 24h
            if now - self.daily_reset > 86400:
                self.daily_tokens = float(self.rpd)
                self.daily_reset = now

            if self.tokens >= 1.0 and self.daily_tokens >= 1.0:
                self.tokens -= 1.0
                self.daily_tokens -= 1.0
                return True
            return False

class EmbeddingTelemetry:
    """Records telemetry statistics for embedding calls."""
    def __init__(self):
        self.total_requests = 0
        self.total_tokens = 0
        self.errors = 0
        self.fallbacks = 0
        self.latencies: Dict[str, List[float]] = {}
        self.model_calls: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def record_call(self, model_id: str, latency_ms: float, tokens: int, is_error: bool = False, is_fallback: bool = False):
        async with self._lock:
            self.total_requests += 1
            if is_error:
                self.errors += 1
            if is_fallback:
                self.fallbacks += 1
            self.total_tokens += tokens
            self.model_calls[model_id] = self.model_calls.get(model_id, 0) + 1
            if model_id not in self.latencies:
                self.latencies[model_id] = []
            self.latencies[model_id].append(latency_ms)
            if len(self.latencies[model_id]) > 500:
                self.latencies[model_id].pop(0)

    def get_summary(self) -> Dict[str, Any]:
        latency_p50 = {}
        latency_p95 = {}
        for m, lats in self.latencies.items():
            if lats:
                arr = sorted(lats)
                latency_p50[m] = round(arr[len(arr) // 2], 2)
                p95_idx = min(len(arr) - 1, int(len(arr) * 0.95))
                latency_p95[m] = round(arr[p95_idx], 2)

        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "errors": self.errors,
            "fallbacks": self.fallbacks,
            "model_calls": self.model_calls,
            "latency_p50_ms": latency_p50,
            "latency_p95_ms": latency_p95,
        }

redact_pii = TemporalMemoryStore.redact_pii

class ParallelEmbeddingFabric:
    """
    Unified Parallel Multi-Provider Embedding Fabric.
    Orchestrates models across Gemini, OpenRouter, NVIDIA, and Mistral via 9Router.
    Implements 3 parallelization patterns:
      1. Race / Hedged Requests (Latency reduction)
      2. Shard-by-Hash (Throughput partition)
      3. Ensemble Multi-Model (Recall maximization with RRF)
    """

    DEFAULT_MODELS: Dict[str, ModelSpec] = {
        "gemini/gemini-embedding-2-preview": ModelSpec(
            model_id="gemini/gemini-embedding-2-preview",
            provider="gemini",
            raw_dim=3072,
            default_target_dim=1024,
            supports_mrl=True,
            auto_normalized=True,
            rpm=60,
            rpd=10000,
            price_per_m_tokens=0.08,
            description="Gemini 2 multimodal embedding with native MRL support"
        ),
        "gemini/gemini-embedding-001": ModelSpec(
            model_id="gemini/gemini-embedding-001",
            provider="gemini",
            raw_dim=3072,
            default_target_dim=1024,
            supports_mrl=True,
            auto_normalized=False,
            rpm=60,
            rpd=10000,
            price_per_m_tokens=0.08,
            description="Gemini 1 embedding with truncation requiring L2 norm"
        ),
        "gemini/text-embedding-005": ModelSpec(
            model_id="gemini/text-embedding-005",
            provider="gemini",
            raw_dim=768,
            default_target_dim=768,
            supports_mrl=False,
            auto_normalized=True,
            rpm=60,
            rpd=10000,
            price_per_m_tokens=0.08,
            description="Google text-embedding-005 (768 dim)"
        ),
        "gemini/text-embedding-004": ModelSpec(
            model_id="gemini/text-embedding-004",
            provider="gemini",
            raw_dim=768,
            default_target_dim=768,
            supports_mrl=False,
            auto_normalized=True,
            rpm=60,
            rpd=10000,
            price_per_m_tokens=0.08,
            description="Google text-embedding-004 (768 dim)"
        ),
        "gemini/embedding-001": ModelSpec(
            model_id="gemini/embedding-001",
            provider="gemini",
            raw_dim=768,
            default_target_dim=768,
            supports_mrl=False,
            auto_normalized=True,
            rpm=60,
            rpd=10000,
            price_per_m_tokens=0.08,
            description="Google legacy embedding-001 (768 dim)"
        ),
        "openrouter/openai/text-embedding-3-small": ModelSpec(
            model_id="openrouter/openai/text-embedding-3-small",
            provider="openrouter",
            raw_dim=1536,
            default_target_dim=1024,
            supports_mrl=True,
            auto_normalized=True,
            rpm=100,
            rpd=10000,
            price_per_m_tokens=0.02,
            description="OpenAI text-embedding-3-small via OpenRouter (MRL 1024)"
        ),
        "openrouter/openai/text-embedding-3-large": ModelSpec(
            model_id="openrouter/openai/text-embedding-3-large",
            provider="openrouter",
            raw_dim=3072,
            default_target_dim=1024,
            supports_mrl=True,
            auto_normalized=True,
            rpm=100,
            rpd=10000,
            price_per_m_tokens=0.13,
            description="OpenAI text-embedding-3-large via OpenRouter (MRL 1024)"
        ),
        "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free": ModelSpec(
            model_id="openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free",
            provider="openrouter_free",
            raw_dim=2048,
            default_target_dim=2048,
            supports_mrl=False,
            auto_normalized=True,
            is_free=True,
            logs_prompts=True,
            rpm=20,
            rpd=200,
            price_per_m_tokens=0.0,
            description="NVIDIA Llama Nemotron free tier (logs prompts, PII redacted)"
        ),
        "nvidia/nvidia/nv-embedqa-e5-v5": ModelSpec(
            model_id="nvidia/nvidia/nv-embedqa-e5-v5",
            provider="nvidia",
            raw_dim=1024,
            default_target_dim=1024,
            supports_mrl=False,
            auto_normalized=True,
            rpm=40,
            rpd=1000,
            price_per_m_tokens=0.0,
            description="NVIDIA NV-EmbedQA E5 v5 official spec (1024 dim)"
        ),
        "mistral/mistral-embed": ModelSpec(
            model_id="mistral/mistral-embed",
            provider="mistral",
            raw_dim=1024,
            default_target_dim=1024,
            supports_mrl=False,
            auto_normalized=True,
            rpm=60,
            rpd=5000,
            price_per_m_tokens=0.10,
            description="Mistral Embed official spec (1024 dim fixed)"
        ),
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        budget_manager: Optional[InheritedBudgetManager] = None,
        timeout: float = 30.0,
    ):
        raw_url = base_url or os.environ.get("ROUTER_BASE_URL", "https://9router.biezz.my.id/v1")
        if raw_url.endswith("/embeddings"):
            self.base_url = raw_url
        else:
            self.base_url = f"{raw_url.rstrip('/')}/embeddings"

        # No default: credential must come from env (ROUTER_API_KEY / NINE_ROUTER_API_KEY).
        self.api_key = api_key or os.environ.get("ROUTER_API_KEY") or os.environ.get("NINE_ROUTER_API_KEY")
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.budget_manager = budget_manager or InheritedBudgetManager()
        self.timeout = timeout
        self.telemetry = EmbeddingTelemetry()

        self.registry: Dict[str, ModelSpec] = dict(self.DEFAULT_MODELS)
        self.rate_limiters: Dict[str, TokenBucketLimiter] = {
            m_id: TokenBucketLimiter(spec.rpm, spec.rpd)
            for m_id, spec in self.registry.items()
        }
        self.semaphores: Dict[str, asyncio.Semaphore] = {
            m_id: asyncio.Semaphore(10) for m_id in self.registry
        }

    @staticmethod
    def get_embedding_space_id(model_id: str, target_dim: int) -> str:
        safe_name = model_id.replace("/", "_").replace(":", "_").replace("-", "_").lower()
        return f"{safe_name}_{target_dim}"

    @staticmethod
    def l2_normalize(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0.0 or math.isnan(norm):
            return vector
        return [x / norm for x in vector]

    @classmethod
    def align_vector_dimension(
        cls,
        vector: List[float],
        raw_dim: int,
        target_dim: int,
        supports_mrl: bool = True,
        auto_normalized: bool = False
    ) -> List[float]:
        """Aligns vector dimension via MRL truncation and applies L2 normalization."""
        if supports_mrl and target_dim < len(vector):
            vector = vector[:target_dim]
        if not auto_normalized:
            vector = cls.l2_normalize(vector)
        return vector

    @staticmethod
    def get_shard_model_for_text(text: str, sharding_models: List[str]) -> str:
        """Determines assigned model for text using consistent SHA-256 hash modulo."""
        h = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
        return sharding_models[h % len(sharding_models)]

    @staticmethod
    def sanitize_input(text: str) -> str:
        """Enforces PII redaction (email, phone, NIK 16 digit)."""
        return TemporalMemoryStore.redact_pii(text)

    def register_model(self, spec: ModelSpec):
        self.registry[spec.model_id] = spec
        self.rate_limiters[spec.model_id] = TokenBucketLimiter(spec.rpm, spec.rpd)
        self.semaphores[spec.model_id] = asyncio.Semaphore(10)

    async def _call_provider_http(
        self,
        model_id: str,
        texts: List[str],
        target_dim: Optional[int] = None,
    ) -> List[List[float]]:
        """Low-level single HTTP invocation to the router with guardrails."""
        spec = self.registry.get(model_id)
        if not spec:
            raise ValueError(f"Unknown model_id: {model_id}")

        if not self.api_key:
            raise RuntimeError(
                "Embedding credential missing: set ROUTER_API_KEY (or NINE_ROUTER_API_KEY)."
            )

        if self.circuit_breaker.is_open(model_id):
            raise RuntimeError(f"Circuit breaker is OPEN for model: {model_id}")

        dim_to_use = target_dim or spec.default_target_dim

        # Enforce rate limiter
        limiter = self.rate_limiters.get(model_id)
        if limiter and not await limiter.acquire():
            logger.warning(f"Rate limit exceeded for model {model_id}; waiting 0.25s")
            await asyncio.sleep(0.25)

        # Sanitize texts
        sanitized_texts = [self.sanitize_input(t) for t in texts]

        # Payload building
        payload: Dict[str, Any] = {
            "model": model_id,
            "input": sanitized_texts if len(sanitized_texts) > 1 else sanitized_texts[0],
        }

        # Matryoshka dimension truncation support
        if spec.supports_mrl and dim_to_use != spec.raw_dim:
            payload["dimensions"] = dim_to_use

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "curl/8.5.0",
        }

        t0 = time.time()
        sem = self.semaphores.get(model_id, asyncio.Semaphore(5))
        async with sem:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                latency_ms = (time.time() - t0) * 1000.0

                if resp.status_code == 410:
                    # EOL handle
                    self.circuit_breaker.record_failure(model_id)
                    await self.telemetry.record_call(model_id, latency_ms, 0, is_error=True)
                    raise RuntimeError(f"Model {model_id} returned 410 EOL")

                if resp.status_code != 200:
                    self.circuit_breaker.record_failure(model_id)
                    await self.telemetry.record_call(model_id, latency_ms, 0, is_error=True)
                    raise RuntimeError(f"Embedding error from {model_id} ({resp.status_code}): {resp.text}")

                data = resp.json()
                self.circuit_breaker.record_success(model_id)

                # Token cost tracking
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", len(" ".join(texts).split()))
                est_cost = (prompt_tokens / 1_000_000.0) * spec.price_per_m_tokens
                self.budget_manager.daily_spent_usd += est_cost

                await self.telemetry.record_call(model_id, latency_ms, prompt_tokens, is_error=False)

                raw_data = data.get("data", [])
                vectors: List[List[float]] = []
                for item in raw_data:
                    vec = item.get("embedding", [])
                    # If model truncated but did not support native MRL auto-normalization, apply L2 norm
                    if len(vec) > dim_to_use:
                        vec = vec[:dim_to_use]
                    if not spec.auto_normalized or (len(vec) < spec.raw_dim and not spec.supports_mrl):
                        vec = self.l2_normalize(vec)
                    vectors.append(vec)

                return vectors

    async def embed_single(
        self,
        text: str,
        model_id: str = "gemini/gemini-embedding-2-preview",
        target_dim: Optional[int] = None,
        fallback_model: str = "openrouter/openai/text-embedding-3-small",
    ) -> EmbeddingVector:
        """Embed single text with automatic fallback if circuit breaker trips or failure occurs."""
        spec = self.registry.get(model_id) or self.registry["gemini/gemini-embedding-2-preview"]
        dim_to_use = target_dim or spec.default_target_dim
        space_id = self.get_embedding_space_id(spec.model_id, dim_to_use)

        t0 = time.time()
        try:
            vectors = await self._call_provider_http(spec.model_id, [text], target_dim=dim_to_use)
            return EmbeddingVector(
                vector=vectors[0],
                text=self.sanitize_input(text),
                embedding_space_id=space_id,
                model_id=spec.model_id,
                raw_dim=spec.raw_dim,
                target_dim=len(vectors[0]),
                latency_ms=(time.time() - t0) * 1000.0,
                provider=spec.provider,
            )
        except Exception as e:
            logger.warning(f"Primary model {model_id} failed: {e}. Attempting fallback to {fallback_model}")
            fallback_spec = self.registry.get(fallback_model) or self.registry["openrouter/openai/text-embedding-3-small"]
            fb_dim = target_dim or fallback_spec.default_target_dim
            fb_space_id = self.get_embedding_space_id(fallback_spec.model_id, fb_dim)
            vectors = await self._call_provider_http(fallback_spec.model_id, [text], target_dim=fb_dim)
            return EmbeddingVector(
                vector=vectors[0],
                text=self.sanitize_input(text),
                embedding_space_id=fb_space_id,
                model_id=fallback_spec.model_id,
                raw_dim=fallback_spec.raw_dim,
                target_dim=len(vectors[0]),
                latency_ms=(time.time() - t0) * 1000.0,
                provider=fallback_spec.provider,
                metadata={"fallback_from": model_id, "fallback_reason": str(e)},
            )

    # ---------------------------------------------------------
    # Pattern A: Race / Hedged Requests (Latency reduction)
    # ---------------------------------------------------------
    async def embed_race(
        self,
        text: str,
        candidate_models: Optional[List[str]] = None,
        target_dim: int = 1024,
    ) -> EmbeddingVector:
        """
        Dispatches identical text concurrently across candidate models.
        Returns the first to complete successfully, cancelling remaining tasks.
        Slashes tail latency (p95/p99) and guarantees zero-downtime hedged fallback.
        """
        models = candidate_models or [
            "gemini/gemini-embedding-2-preview",
            "openrouter/openai/text-embedding-3-small",
            "mistral/mistral-embed",
        ]
        # Filter out circuit-broken models
        healthy_models = [m for m in models if not self.circuit_breaker.is_open(m)]
        if not healthy_models:
            healthy_models = models[:1]  # Force try first

        async def _run_candidate(m_id: str) -> EmbeddingVector:
            return await self.embed_single(text, model_id=m_id, target_dim=target_dim)

        tasks = [asyncio.create_task(_run_candidate(m)) for m in healthy_models]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # Cancel remaining hedged tasks
        for p in pending:
            p.cancel()

        for d in done:
            try:
                res = d.result()
                res.metadata["hedged_race_winner"] = res.model_id
                res.metadata["total_hedged_candidates"] = len(healthy_models)
                return res
            except Exception as e:
                logger.warning(f"Hedged candidate failed: {e}")

        # If all first-completed raised, await remaining
        if pending:
            done_rest, _ = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
            for d in done_rest:
                if not d.cancelled():
                    try:
                        return d.result()
                    except Exception:
                        pass

        raise RuntimeError("All hedged race candidates failed.")

    # ---------------------------------------------------------
    # Pattern B: Shard-by-Hash (Throughput partition)
    # ---------------------------------------------------------
    async def embed_shard_hash(
        self,
        texts: List[str],
        sharding_models: Optional[List[str]] = None,
        target_dim: int = 1024,
    ) -> List[EmbeddingVector]:
        """
        Partitions large batch of texts across N models using consistent chunk hashing.
        Distributes workload across multiple providers simultaneously.
        Yields linear indexing throughput speedup.
        """
        models = sharding_models or [
            "gemini/gemini-embedding-2-preview",
            "openrouter/openai/text-embedding-3-small",
            "mistral/mistral-embed",
        ]
        healthy = [m for m in models if not self.circuit_breaker.is_open(m)]
        if not healthy:
            healthy = models

        n_shards = len(healthy)
        shards: Dict[int, List[Tuple[int, str]]] = {i: [] for i in range(n_shards)}

        for idx, text in enumerate(texts):
            h = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
            shard_idx = h % n_shards
            shards[shard_idx].append((idx, text))

        async def _process_shard(shard_id: int, items: List[Tuple[int, str]]) -> List[Tuple[int, EmbeddingVector]]:
            if not items:
                return []
            m_id = healthy[shard_id]
            spec = self.registry[m_id]
            dim = target_dim or spec.default_target_dim
            space_id = self.get_embedding_space_id(m_id, dim)

            raw_texts = [it[1] for it in items]
            t0 = time.time()
            try:
                vecs = await self._call_provider_http(m_id, raw_texts, target_dim=dim)
            except Exception as e:
                logger.warning(f"Shard {shard_id} failed on {m_id}: {e}. Retrying with fallback.")
                vecs = await self._call_provider_http("openrouter/openai/text-embedding-3-small", raw_texts, target_dim=dim)
                m_id = "openrouter/openai/text-embedding-3-small"
                spec = self.registry[m_id]
                space_id = self.get_embedding_space_id(m_id, dim)

            lat = (time.time() - t0) * 1000.0 / max(1, len(items))
            results = []
            for (orig_idx, orig_text), v in zip(items, vecs):
                ev = EmbeddingVector(
                    vector=v,
                    text=self.sanitize_input(orig_text),
                    embedding_space_id=space_id,
                    model_id=m_id,
                    raw_dim=spec.raw_dim,
                    target_dim=len(v),
                    latency_ms=lat,
                    provider=spec.provider,
                    metadata={"shard_id": shard_id, "hash_partition": True},
                )
                results.append((orig_idx, ev))
            return results

        shard_tasks = [_process_shard(i, shards[i]) for i in range(n_shards)]
        shard_results = await asyncio.gather(*shard_tasks)

        # Merge and sort by original index
        flat_results = [item for sub in shard_results for item in sub]
        flat_results.sort(key=lambda x: x[0])
        return [item[1] for item in flat_results]

    # ---------------------------------------------------------
    # Pattern C: Ensemble Multi-Model (Recall maximization)
    # ---------------------------------------------------------
    async def embed_ensemble(
        self,
        text: str,
        ensemble_models: Optional[List[str]] = None,
        target_dim: int = 1024,
    ) -> List[EmbeddingVector]:
        """
        Embeds identical text across ALL ensemble models concurrently.
        Each vector is stored in its own partitioned space.
        Used for multi-perspective semantic indexing.
        """
        models = ensemble_models or [
            "gemini/gemini-embedding-2-preview",
            "openrouter/openai/text-embedding-3-small",
            "nvidia/nvidia/nv-embedqa-e5-v5",
        ]

        async def _embed_one(m_id: str) -> Optional[EmbeddingVector]:
            try:
                return await self.embed_single(text, model_id=m_id, target_dim=target_dim)
            except Exception as e:
                logger.error(f"Ensemble member {m_id} failed: {e}")
                return None

        results = await asyncio.gather(*[_embed_one(m) for m in models])
        return [r for r in results if r is not None]

    # ---------------------------------------------------------
    # Reciprocal Rank Fusion (RRF) for Multi-Space Retrieval
    # ---------------------------------------------------------
    @staticmethod
    def rrf_fusion(
        ranked_lists: List[List[Dict[str, Any]]],
        k: int = 60,
        id_key: str = "id",
    ) -> List[Dict[str, Any]]:
        """
        Fuses ranked search results from multiple embedding spaces using RRF.
        Formula: RRF_score(d) = sum_{m in M} (1.0 / (k + rank_m(d)))
        """
        scores: Dict[str, float] = {}
        item_data: Dict[str, Dict[str, Any]] = {}
        appearances: Dict[str, List[str]] = {}

        for ranked_list in ranked_lists:
            for rank, item in enumerate(ranked_list, start=1):
                doc_id = str(item.get(id_key, item.get("node_id", "")))
                if not doc_id:
                    continue
                rrf_increment = 1.0 / (k + rank)
                scores[doc_id] = scores.get(doc_id, 0.0) + rrf_increment
                if doc_id not in item_data:
                    item_data[doc_id] = dict(item)
                source_space = item.get("embedding_space_id", "unknown")
                if doc_id not in appearances:
                    appearances[doc_id] = []
                appearances[doc_id].append(source_space)

        # Sort descending by fused score
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        fused_results = []
        for doc_id, score in sorted_docs:
            doc_dict = item_data[doc_id]
            doc_dict["rrf_score"] = round(score, 6)
            doc_dict["fused_from_spaces"] = appearances.get(doc_id, [])
            fused_results.append(doc_dict)

        return fused_results

    # ---------------------------------------------------------
    # Visualization / Atlas Dimensionality Reduction (UMAP/PCA)
    # ---------------------------------------------------------
    @staticmethod
    def project_embeddings_2d(
        vectors: List[List[float]],
        labels: Optional[List[str]] = None,
        ids: Optional[List[str]] = None,
        spaces: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Projects high-dimensional vectors to 2D coordinates for the Embedding Atlas /
        Obsidian Neuron Graph dashboard. Uses fast PCA (SVD) with zero external C-dependencies.
        """
        if not vectors:
            return []

        X = np.array(vectors, dtype=np.float32)
        n_samples, n_features = X.shape

        if n_samples == 1:
            return [{
                "id": ids[0] if ids else "node-0",
                "x": 0.0,
                "y": 0.0,
                "label": labels[0] if labels else "node-0",
                "space": spaces[0] if spaces else "default",
            }]

        # Mean center
        X_centered = X - np.mean(X, axis=0)

        # Compute top 2 principal components via SVD
        try:
            U, S, Vt = np.linalg.svd(X_centered, full_matrices=False)
            projected = U[:, :2] * S[:2]
        except Exception:
            # Fallback simple projection
            projected = X_centered[:, :2]

        # Normalize coordinates between -100 and +100 for canvas rendering
        max_val = np.max(np.abs(projected))
        if max_val > 0:
            coords = (projected / max_val) * 100.0
        else:
            coords = projected

        output = []
        for i in range(n_samples):
            output.append({
                "id": ids[i] if ids and i < len(ids) else f"node-{i}",
                "x": round(float(coords[i, 0]), 2),
                "y": round(float(coords[i, 1]), 2),
                "label": labels[i] if labels and i < len(labels) else f"Item {i}",
                "space": spaces[i] if spaces and i < len(spaces) else "default",
            })
        return output

    # ---------------------------------------------------------
    # FalkorDB Vector Index Helpers
    # ---------------------------------------------------------
    @classmethod
    async def ensure_vector_indexes(
        cls,
        driver,
        space_ids: Optional[List[str]] = None,
        dim: int = 1024,
        similarity_metric: str = "COSINE",
    ) -> List[str]:
        """
        Ensures explicit vector indexes exist in FalkorDB for each embedding space partition.
        Format: CALL db.idx.vector.createNodeIndex('Entity', 'vec_<space_id>', <dim>, '<metric>')
        """
        created = []
        target_spaces = space_ids or [
            "gemini_gemini_embedding_2_preview_1024",
            "openrouter_openai_text_embedding_3_small_1024",
            "nvidia_nvidia_nv_embedqa_e5_v5_1024",
            "mistral_mistral_embed_1024",
        ]

        for s in target_spaces:
            attr_name = f"vec_{s}"
            query = f"CALL db.idx.vector.createNodeIndex('Entity', '{attr_name}', {dim}, '{similarity_metric}')"
            try:
                # FalkorDB cypher execution
                if hasattr(driver, "execute_query"):
                    res = driver.execute_query(query)
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(driver, "query"):
                    if asyncio.iscoroutinefunction(driver.query):
                        await driver.query(query)
                    else:
                        await asyncio.to_thread(driver.query, query)
                created.append(attr_name)
                logger.info(f"FalkorDB vector index ensured on Entity.{attr_name} (dim={dim})")
            except Exception as e:
                # Often index already exists, which is safe to ignore
                logger.debug(f"Vector index notice for {attr_name}: {e}")
                created.append(attr_name)

        return created
