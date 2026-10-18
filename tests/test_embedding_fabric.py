import pytest
import math
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from packages.memory.embedding_fabric import (
    ParallelEmbeddingFabric,
    ModelSpec,
    EmbeddingVector,
    redact_pii
)

def test_fabric_registry_all_ten_models():
    """Memverifikasi registri fabric memuat tepat 10 model dengan metadata dan spesifikasi valid."""
    fabric = ParallelEmbeddingFabric()
    assert len(fabric.registry) == 10
    
    # Check 10 models explicitly
    expected_models = [
        "gemini/gemini-embedding-2-preview",
        "gemini/gemini-embedding-001",
        "gemini/text-embedding-005",
        "gemini/text-embedding-004",
        "gemini/embedding-001",
        "nvidia/nvidia/nv-embedqa-e5-v5",
        "openrouter/openai/text-embedding-3-small",
        "openrouter/openai/text-embedding-3-large",
        "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free",
        "mistral/mistral-embed"
    ]
    for model_id in expected_models:
        assert model_id in fabric.registry, f"Model {model_id} harus terdaftar di fabric"

    # Verifikasi koreksi kritis K-1: nv-embedqa-e5-v5 berdimensi 1024
    nv_spec = fabric.registry["nvidia/nvidia/nv-embedqa-e5-v5"]
    assert nv_spec.raw_dim == 1024
    assert nv_spec.default_target_dim == 1024
    assert nv_spec.supports_mrl is False

    # Verifikasi mistral-embed fixed 1024
    mistral_spec = fabric.registry["mistral/mistral-embed"]
    assert mistral_spec.raw_dim == 1024
    assert mistral_spec.default_target_dim == 1024

    # Verifikasi Gemini Embedding 2 Preview mendukung MRL dan default 1024
    gemini_spec = fabric.registry["gemini/gemini-embedding-2-preview"]
    assert gemini_spec.raw_dim == 3072
    assert gemini_spec.default_target_dim == 1024
    assert gemini_spec.supports_mrl is True

    # Verifikasi tier gratis OpenRouter ditandai logs_prompts (K-4)
    free_spec = fabric.registry["openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free"]
    assert free_spec.is_free is True
    assert free_spec.logs_prompts is True

def test_redact_pii_security_sanitization():
    """Memverifikasi gate sanitasi PII (email, telepon, NIK 16 digit, credit card) sebelum fan-out."""
    raw_text = (
        "User Rahasia memiliki email kontak@biezz.my.id dan nomor telepon 081234567890. "
        "Nomor Induk Kependudukan (NIK) adalah 3201011205900001 untuk verifikasi."
    )
    sanitized = redact_pii(raw_text)
    assert "kontak@biezz.my.id" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "081234567890" not in sanitized
    assert "[REDACTED_PHONE]" in sanitized
    assert "3201011205900001" not in sanitized
    assert "[REDACTED_NIK]" in sanitized

def test_mrl_truncation_and_l2_normalization():
    """Memverifikasi pemotongan dimensi Matryoshka dan normalisasi L2 berjarak unit (norm = 1.0)."""
    fabric = ParallelEmbeddingFabric()
    # Mock vector berdimensi 2048
    fake_vec = [float(i + 1) for i in range(2048)]
    aligned = fabric.align_vector_dimension(
        fake_vec,
        raw_dim=2048,
        target_dim=1024,
        supports_mrl=True,
        auto_normalized=False
    )
    assert len(aligned) == 1024
    # Hitung norma L2
    norm = math.sqrt(sum(x * x for x in aligned))
    assert abs(norm - 1.0) < 1e-4

def test_shard_by_hash_deterministic():
    """Memverifikasi partisi teks berbasis hash terdistribusi deterministik ke model."""
    fabric = ParallelEmbeddingFabric()
    shards = ["gemini/gemini-embedding-2-preview", "nvidia/nvidia/nv-embedqa-e5-v5", "mistral/mistral-embed"]
    assigned_1 = fabric.get_shard_model_for_text("Chunk text alpha", shards)
    assigned_2 = fabric.get_shard_model_for_text("Chunk text alpha", shards)
    assert assigned_1 == assigned_2
    assert assigned_1 in shards

def test_rrf_fusion_calculation():
    """Memverifikasi fusi peringkat multi-model menggunakan algoritma Reciprocal Rank Fusion (RRF)."""
    fabric = ParallelEmbeddingFabric()
    # 2 list peringkat kandidat dokumen
    list_a = [
        {"id": "doc-1", "title": "First doc"},
        {"id": "doc-2", "title": "Second doc"},
        {"id": "doc-3", "title": "Third doc"}
    ]
    list_b = [
        {"id": "doc-2", "title": "Second doc"},
        {"id": "doc-1", "title": "First doc"},
        {"id": "doc-4", "title": "Fourth doc"}
    ]
    fused = fabric.rrf_fusion([list_a, list_b], k=60, id_key="id")
    assert len(fused) == 4
    # doc-1 dan doc-2 harus memiliki skor tertinggi karena muncul di kedua model
    top_ids = [item["id"] for item in fused[:2]]
    assert "doc-1" in top_ids
    assert "doc-2" in top_ids
    assert fused[0]["rrf_score"] > fused[-1]["rrf_score"]

def test_project_embeddings_2d():
    """Memverifikasi proyeksi UMAP 2D untuk visualisasi visual Embedding Atlas."""
    fabric = ParallelEmbeddingFabric()
    # Buat 5 vektor 1024-dim
    vectors = [[0.01 * (i + j) for j in range(1024)] for i in range(5)]
    labels = ["cat_a", "cat_b", "cat_a", "cat_c", "cat_b"]
    ids = [f"node-{i}" for i in range(5)]
    spaces = ["gemini/gemini-embedding-2-preview:1024"] * 5
    
    nodes = fabric.project_embeddings_2d(vectors, labels=labels, ids=ids, spaces=spaces)
    assert len(nodes) == 5
    for n in nodes:
        assert "x" in n
        assert "y" in n
        assert "id" in n
        assert "label" in n
        assert "space" in n

@pytest.mark.asyncio
async def test_api_embedding_models_endpoint():
    """Memverifikasi endpoint REST GET /api/embedding/models."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/embedding/models")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["total"] == 10
        model_ids = [m["model_id"] for m in data["models"]]
        assert "gemini/gemini-embedding-2-preview" in model_ids
        assert "nvidia/nvidia/nv-embedqa-e5-v5" in model_ids

@pytest.mark.asyncio
async def test_api_embedding_telemetry_endpoint():
    """Memverifikasi endpoint REST GET /api/embedding/telemetry."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/embedding/telemetry")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "telemetry" in data
        assert "total_requests" in data["telemetry"]

@pytest.mark.asyncio
async def test_api_embedding_fuse_endpoint():
    """Memverifikasi endpoint REST POST /api/embedding/fuse."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "ranked_lists": [
                [{"id": "doc-a", "score": 0.9}, {"id": "doc-b", "score": 0.8}],
                [{"id": "doc-b", "score": 0.95}, {"id": "doc-c", "score": 0.7}]
            ],
            "k": 60,
            "id_key": "id"
        }
        res = await ac.post("/api/embedding/fuse", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["fused_results"]) == 3
        assert data["fused_results"][0]["id"] == "doc-b"

@pytest.mark.asyncio
async def test_api_embedding_embed_live_call():
    """Memverifikasi panggilan live embedding via 9Router dengan target dimension 1024."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "input": "Orkestrasi multi-agent LangGraph dengan memory bi-temporal FalkorDB.",
            "pattern": "single",
            "model": "gemini/gemini-embedding-2-preview",
            "target_dim": 1024
        }
        res = await ac.post("/api/embedding/embed", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["data"]) == 1
        emb_obj = data["data"][0]
        assert emb_obj["model_id"] == "gemini/gemini-embedding-2-preview"
        assert emb_obj["dim"] == 1024
        assert len(emb_obj["vector"]) == 1024

@pytest.mark.asyncio
async def test_api_cors_security_whitelist():
    """Memverifikasi remediasi keamanan F-001: Whitelist CORS dinamis mencegah CWE-942."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Origin terdaftar di whitelist: localhost:3002
        headers_allowed = {"Origin": "http://localhost:3002"}
        res_allowed = await ac.options("/api/health", headers=headers_allowed)
        assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:3002"

        # Origin jahat/tidak terdaftar: evil-attacker.com
        headers_blocked = {"Origin": "https://evil-attacker.com"}
        res_blocked = await ac.options("/api/health", headers=headers_blocked)
        # Origin tidak boleh direfleksikan
        assert res_blocked.headers.get("access-control-allow-origin") != "https://evil-attacker.com"
