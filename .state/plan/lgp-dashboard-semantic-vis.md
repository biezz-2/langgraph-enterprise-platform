# LGP v2.0 — Dashboard Contract, Semantic Embed & Neuron Visualisation

**Status:** PROPOSED (menunggu persetujuan)
**Basis:** 3 subagent teammate (contract-audit, embed/graph, dataviz) + verifikasi langsung ke live API :8000, FalkorDB :6382, Supabase `langgraph`.
**Baseline:** `pytest tests/` → **44 passed** (1 warning). `npx tsc --noEmit` → clean. HEAD `c2c32d4`.

---

## 1. Temuan Inti (terverifikasi, bukan asumsi)

| # | Temuan | Bukti langsung |
|---|---|---|
| V1 | **6 endpoint yang dipanggil dashboard tidak ada** | `curl` ke :8000 → `/api/hitl` 404, `/api/memory` 404, `/api/matrix` 404, `/api/guardrails` 404, `/api/mcp/tools` 404. Yang ada: `/api/hitl/inbox`, `/api/memory/temporal`, `/api/correlations`, `/mcp/admin/tools` |
| V2 | **Embedding Atlas tidak pernah menampilkan data asli** | `GET /api/embedding/atlas` → `total_nodes: 5` berisi 5 node demo hardcoded. SQL `SELECT id, text_content, memory_category FROM temporal_facts` → kolom tak ada; error ditelan `except Exception: pass` |
| V3 | **Proyeksi 2D = PCA, bukan UMAP** | `project_embeddings_2d` = mean-center + `np.linalg.svd`. UI label "UMAP Dim 1/2", "(UMAP 2D Projection)" — label berbohong |
| V4 | **Custom projection 422 + hasil (0,0)** | Client POST `{text:...}`, model butuh `input`. Lalu POST 1 vektor → early-return `n_samples==1` → (0,0) |
| V5 | **4 model embed mati + 1 id salah di registry** | Live probe: `gemini/text-embedding-005` 404, `text-embedding-004` 404, `gemini/embedding-001` 404, `nvidia/nvidia/nv-embedqa-e5-v5` 410 EOL, `nvidia/nv-embedqa-e5-v5` 404. Semua jatuh diam-diam ke fallback |
| V6 | **`embedding_space_id` bohong** | `mistral/mistral-embed` `target_dim=2048` → vektor 1024, tapi `space_id=mistral_mistral_embed_2048` |
| V7 | **Prosedur index vektor tidak ada** | `dbms.procedures()` → hanya `db.idx.vector.queryNodes`/`queryRelationships`. `db.idx.vector.createNodeIndex` **tidak terdaftar** → `ensure_vector_indexes` melaporkan palsu (append ke `created` walau gagal) |
| V8 | **Query vektor FalkorDB bisa jalan** (revisi klaim subagent) | `MATCH (e:Entity) WHERE e.name_embedding IS NOT NULL WITH e LIMIT 5 CALL db.idx.vector.queryNodes('Entity','name_embedding',$k,vecf32($qv)) YIELD node,score` → **sukses**, score = jarak (self=5.96e-08) |
| V9 | **Embedding tidak pernah dipersistensi** | FalkorDB: 206 Entity, **2** punya `name_embedding`. Postgres `langgraph`: 27 tabel, **tidak ada** kolom/tabel vektor. `pgvector 0.8.2` **sudah terpasang** |
| V10 | **Nol edge semantik** | 446 edge: HAS_FACT 225, IS_EPISODE 66, EXECUTED 66, MENTIONS 32, RELATES_TO 22, PART_OF 20, HAS_CAPABILITY 10, NPMI 6, REPRESENTATION 3, +2. Semua struktural. NPMI = statistik co-activation, **bukan** similaritas embedding |
| V11 | **Drawer subagent selalu kosong** | Census 324 node: `role`/`pod`/`trust_level`/`capabilities`/`model_policy`/`group`/`icon`/`degree` = **0** node. UI baca top-level (`:1242-1248`), server nest di `attributes` |
| V12 | **Warna server ditimpa client** | Backend subagent `#0ea5e9`; UI rewrite jadi `#818cf8`. Tooltip 3D baca `node.color` **sebelum** normalisasi → palet salah |
| V13 | **Cypher "Copy" tidak match apa pun** | `MATCH (n {id:"..."})` → `[]`. FalkorDB key = `uuid` (`MATCH (n {uuid:"d5225299-..."})` → 1 row) |
| V14 | **Fetch ganda ke `/api/graph/graphiti`** | `NeuronGraph.tsx:142-169` (`loadGraphData`) + `:171-205` (useEffect) → race, last-write-wins |
| V15 | **Error banner mati** | Kedua catch block panggil `setError(null)` → error tidak pernah tampil |
| V16 | **HITL diemulasikan, bukan native LangGraph** | `atlas_engine.py:212-231` tulis `hitl_inbox` + `status='interrupted'`, `route_next` → `END`. **Tidak ada jalur resume.** `lgp_run_resume_hitl` (`admin_server.py:678-704`) hanya UPDATE tabel |
| V17 | **Native interrupt terbukti jalan di LangGraph 1.2.15** | `ainvoke` → `{'__interrupt__':[Interrupt(id='2d00d200af6e0abfa688e6af669f9cf9')]}`; `Command(resume='approved')` → lanjut. `Interrupt.id` bisa dipakai sebagai `hitl_inbox.interrupt_id` |
| V18 | **Blokir migrasi HITL** | `hitl_inbox` **tidak punya** kolom `thread_id`; native resume butuh `thread_id` + `Interrupt.id` |
| V19 | **Join checkpoint→run yang benar** | `langgraph.checkpoints.checkpoint->'channel_values'->>'run_id'` → 14 run_id valid (14/66 run punya state LangGraph asli). Join via `runs.thread_id` **salah** (`test-th-1` → 8 run) |
| V20 | **DAG bisa dibangun dari telemetry** | `telemetry_events`: node.start 80, node.end 123 (ada tokens_in/out, cost_usd, latency_ms), delegate 106, handoff 30. Semua punya `run_id` |
| V21 | **Data guardrails tidak ada** | Tabel `guardrail_events` / `circuit_breaker_events` **tidak ada** di `langgraph`. `CircuitBreaker.record_failure` tak pernah dipanggil dari `atlas_engine` → breaker tidak pernah trip (0 event `circuit.tripped`) |
| V22 | **Normalisasi fabric sudah benar** (revisi klaim subagent) | Live fabric: `gemini-embedding-001` req 1024 → **L2=1.000000**; req 3072 → 1.000000. Raw provider tanpa normalisasi = 0.616, tapi fabric sudah L2-normalize (guard `len(vec) < spec.raw_dim and not spec.supports_mrl` → True karena MRL model). **P0-1 subagent TIDAK berlaku di jalur runtime** |
| V23 | **Tapi `align_vector_dimension` = kode mati dengan aturan berbeda** | `embedding_fabric.py:319-332`; satu-satunya pemanggil = `tests/test_embedding_fabric.py:74`. Runtime tidak pernah memanggilnya. Dua kontrak normalisasi berbeda dalam 1 file |
| V24 | **`/mcp/*` tidak di-rewrite Next.js** | `next.config.ts` hanya rewrite `/api/:path*`, `/docs`, `/openapi.json`. `/mcp/admin/tools` dari browser → Next.js, bukan backend |
| V25 | **Guardrail tidak pernah dipanggil** | `SecurityToolGuard.sanitize_input` nol call site produksi. `validate_subagent_tool_access` dipanggil 1x (`atlas_engine.py:249`) **dengan return value dibuang** |
| V26 | **API key bocor di source** | `embedding_fabric.py:291` literal `***REMOVED-SECRET***...` sebagai default |

---

## 2. Fase，分为 (DAG: backend → contract → embed → visual)

### FASE 1 — Kontrak API (P0, blocker semua dashboard page)
**Prinsip: reuse handler yang sudah ada, jangan tulis ulang logika.**

| File:line | Aksi |
|---|---|
| `apps/api/main.py` (baru, dekat §4) | `GET /api/hitl` → baca `hitl_inbox`, map ke `HITLItem` frontend (`id, interrupt_id, thread_id, run_id, subagent, action_type, description, risk_level, proposed_payload, created_at, status`). `thread_id` diisi dari join `runs` (fallback `""`) |
| `apps/api/main.py` | `GET /api/memory` → **alias** `/api/memory/temporal`, map ke `MemoryFact` (`fact_id, subject, predicate, object, valid_at, invalid_at, created_at, expired_at, episode_run_id, pii_redacted`) |
| `apps/api/main.py` | `GET /api/matrix` → **alias** `/api/correlations` (shape sudah cocok `CorrelationMatrixCell` persis) |
| `apps/api/main.py` | `GET /api/mcp/tools` → return `AdminMCPServer.TOOL_DEFINITIONS` (array, cocok `FastMCPTool` frontend) |
| `apps/api/main.py` | `GET /api/guardrails` → bangun `owasp` / `audit` / `breakers` dari `audit_log` + `telemetry_events` + `runs.consecutive_failures/circuit_open`. Guardrail log **dibangun dari event nyata**, bukan tabel baru (P2-1) |
| `apps/api/main.py:74-92` | `/api/health` + `uptime_s`, `avg_latency_ms` (dari `telemetry_events.latency_ms` AVG) |
| `apps/api/main.py:154` | `/api/runs` + `budget_used` (`runs.budget_spent_json`), `total_tokens`, `total_latency_s`, `steps[]` (dari `telemetry_events` node.start/node.end), `checkpoints[]` (dari `langgraph.checkpoints` via `channel_values.run_id` — V19) |
| `apps/api/main.py:799-813` | **Fix SQL atlas** (V2): `SELECT fact_id, subject, predicate, object FROM temporal_facts WHERE invalid_at IS NULL` → text = `subject + " " + predicate + " " + object`. **Hapus 5 node demo hardcoded + `except: pass`** |
| `apps/api/main.py:712-719` | Backward-compat: `EmbeddingRequest` terima `text` sebagai alias `input` (`model_validator(mode='before')`) — memperbaiki 422 tanpa harus ganti client |
| `apps/api/main.py:841` | Rename `/api/embedding/umap` → `/api/embedding/project` (+ alias lama 1 rilis). Ganti label UI "UMAP" → nama algoritma sebenarnya |
| `apps/dashboard-nextjs/next.config.ts` | Tambah rewrite `/mcp/:path*` → `http://localhost:8000/mcp/:path*` (V24) |

### FASE 2 — HITL native LangGraph (P0, "sesuai esensi LangGraph")
1. Migrasi `hitl_inbox`: tambah kolom `thread_id TEXT`, `interrupt_id` (sudah ada) — V18.
2. `atlas_engine.py`: ganti emulasi (`:212-231`) dengan `from langgraph.types import interrupt, Command`; `raise interrupt({...})` di node. Ambil `Interrupt.id` → tulis ke `hitl_inbox.interrupt_id` + `thread_id`.
3. `route_next` (`:431-451`): hapus cabang `if state.get("interrupted"): return END` — dengan native interrupt, graph berhenti otomatis dan bisa di-resume.
4. `lgp_run_resume_hitl` (`admin_server.py:678-704`): setelah UPDATE, **panggil `graph.ainvoke(Command(resume=decision), config={"configurable":{"thread_id":...}})`** — inilah yang hilang sekarang. Pertahankan anti-self-approval.
5. Verifikasi: `aget_state(cfg)` → `next`, `tasks[0].interrupts[0].id` (terbukti jalan di 1.2.15).

### FASE 3 — Semantic embedding (P0→P1)
| Item | Aksi |
|---|---|
| V26 | **Hapus API key literal** `embedding_fabric.py:291` → wajib env, tanpa default. Rotation key. |
| V5 | Hapus 4 model mati (`text-embedding-005`, `text-embedding-004`, `gemini/embedding-001`, `nv-embedqa-e5-v5`) + id salah. Update default `embed_ensemble` (`embedding_fabric.py:620-624`) & `embed_shard_hash` default (`:541-545`) yang masih pakai id EOL. Tandai nemotron-vl `supports_query=False`. |
| V6 | `embedding_space_id` dari **dimensi aktual** (`len(vectors[0])`), bukan `dim_to_use` yang diminta. Guard `target_dim > raw_dim` untuk model non-MRL → error eksplisit, bukan dipotong diam-diam. |
| V23 | **Hapus `align_vector_dimension`** (kode mati, kontrak normalisasi berbeda) + update test. Runtime jadi satu otoritas normalisasi. |
| — | Fallback harus **menandai** `is_fallback=True` di telemetry (`fallbacks` saat ini selalu 0) + menyertakan `fallback_reason` di respons. |
| V9 | **Persistensi vektor** — `pgvector 0.8.2` sudah ada, tanpa dependency baru:<br>`CREATE TABLE langgraph.embeddings (fact_id, space_id, model_id, dim, content_hash, vector vector(1024), created_at, PRIMARY KEY(fact_id, space_id))` + index HNSW `vector_cosine_ops`. Populate dari `rehydrate_falkordb_from_db` (`graphiti.py:1028`) yang sudah menelusuri setiap `temporal_facts`. |
| V7 | `ensure_vector_indexes`: ganti `db.idx.vector.createNodeIndex` (tidak ada) → `CREATE VECTOR INDEX FOR (e:Entity) ON (e.vec_<space>) OPTIONS {dimension: 1024, similarityFunction: 'cosine'}` (terbukti didukung, V8). **Append ke `created` hanya kalau sukses**; log WARNING bukan DEBUG. |
| V3 | **Label jujur + proyeksi lebih baik.** Opsi A (tanpa dependency): PCA-50 → cosine kNN → spectral embedding 2D (numpy saja, deterministik, preservasi neighborhood). Opsi B: `umap-learn` (dependency baru: scipy+sklearn+numba). Rekomendasi: **A dulu** — rename endpoint & label ke "PCA-50 → kNN-spectral". |
| — | Guard `n_features == 1` (IndexError → 500 saat ini). |
| — | **Cache embedding** (LRU, key = sha256(teks tersanitasi) + model + dim) → atlas p50 1.5 s/request. Cache key pakai teks **setelah** redaksi PII. |
| — | **Proyeksi stabil**: atlas harus fit **satu kali** per korpus, bukan refit per request (V3/P1-3 — saat ini posisi 4 titik berubah total setiap ada titik ke-5). Client kirim vektor existing + vektor baru dalam satu call. |
| V10 | **Edge semantik** `SEMANTICALLY_SIMILAR`: numpy all-pairs cosine pada vektor 1024-d (229² = 52k dot product, sub-milidetik), threshold ~0.82, tulis via MERGE. FalkorDB `queryNodes` dipakai sebagai jalur **query** (retrieval), bukan build. |

### FASE 4 — Visualisasi node & neuron graph (P1)
| Item | Aksi |
|---|---|
| V11 | `graphiti.py:400-411` + fallback `:795-807`: naikkan `role, pod, group, trust_level, capabilities, model_policy, icon` ke **top-level** node (pertahankan `attributes` untuk BC). `capabilities` disimpan sebagai JSON string → parse. |
| V12 | **Palet server-side** jadi sumber kebenaran: subagent `#818cf8`, category `#38bdf8`, fact aktif `#10b981`, invalid `#f43f5e`, episode `#38bdf8`, edge semantik `#a855f7`. **Hapus rewrite warna client** `mockNeuronData.ts:477-486`. |
| — | **Degree dihitung server-side** (1 pass di akhir builder) + `inDegree`/`outDegree`/`degree`; ukuran node berbasis degree. Path client (`:457-475`) jadi fallback untuk mock saja. |
| — | Pisahkan `status` (aktif/invalid) dari `run_status` (status run) — sekarang tumpang tindih. Ganti filter client `n.status === "invalid"` → `temporal_status`. Gunakan `packages/memory/temporal.py:filter_bitemporal` untuk as-of, bukan cek ad-hoc `invalid_at is not None`. |
| — | `invalid_at` `""` → `None` (`graphiti.py:722-730`) — `new Date("")` = NaN di client. |
| V13 | Cypher clipboard: `MATCH (n {uuid: "<attributes.uuid>"})-[r]-(m)` + escape quote. |
| — | Escape HTML di tooltip 3D (`NeuronGraph.tsx:601-618`) — `node.label`/`node.description` masuk ke innerHTML tanpa escape (XSS). |
| V14 | **Hapus fetch ganda**: pertahankan `loadGraphData` saja, hapus useEffect duplikat. |
| V15 | `setError(null)` di catch → `setError("...")` supaya banner error hidup. |
| — | "Center Gravity" slider (0.01–0.4) Plateau: `forceCenter.strength()` = multiplier centering, default 1, **bukan** gravity. Ganti rentang ke 0.1–2.0 (atau beri label "Centering"). Branch 3D tidak pasang `center` sama sekali → tambahkan. |
| — | Label LOD `globalScale >= 1.4` → 309/324 node tak pernah berlabel. Turunkan threshold + label node terpilih/hover selalu tampil. |
| — | `linkWidth` 2D mengabaikan `link.weight`; `linkDirectionalParticles` 3D diisi angka (harusnya fungsi); badge "60 FPS" hardcoded → hitung riil. |
| — | Legend warna harusIKUT palet server (§V12) atau hapus. |
| — | Dedupe `/api/graph/graphiti` (V14) + hardcode fetch. |

### FASE 5 — Guardrails & keamanan (P1, sebagian sudah ada di plan hardening)
| Item | Aksi |
|---|---|
| V21 | Table `guardrail_events` (atau bangun dari `audit_log`+`telemetry_events`). `CircuitBreaker.record_failure/success` **dipanggil** dari `atlas_engine` pada node gagal → `circuit.tripped` benar-benar terjadi, dan `runs.consecutive_failures`/`circuit_open` terisi. |
| V25 | `SecurityToolGuard.sanitize_input` dipanggil di `atlas_engine` sebelum subgoal/objective; **periksa return value** `validate_subagent_tool_access` (`:249`) → tolak + audit kalau denied. |
| — | Half-open probe di `CircuitBreaker` (`guards.py:30`) setelah cooldown — sekarang tidak pernah reset. |
| — | Integrasikan ke plan hardening yang sudah ada (p01 secret hygiene sudah mencakup `ecosystem.config.cjs`; **tambah**: rotasi key router + hapus literal `embedding_fabric.py:291`). |

---

## 3. Urutan Eksekusi & Verifikasi

```
F1 (kontrak API)  → tsc clean + 6 endpoint 200 + halaman dashboard benar
F2 (HITL native)  → interrupt → approve → graph lanjut → run completed
F3 (embed)        → atlas 200 dgn facts asli; vector persisted; edge semantik > 0
F4 (visual)       → drawer subagent terisi; warna cocok legend; fetch tunggal
F5 (guardrail)    → circuit.tripped bisa terjadi; guardrail tab terisi
```

**Wajib ada 1 check runnable per fase** (assert-based, tanpa framework baru).

---

## 4. Keputusan yang Butuh Persetujuan Owner

| # | Keputusan | Rekomendasi |
|---|---|---|
| D1 | UMAP asli (dependency baru) vs spectral numpy | **Spectral numpy** — nol dependency, deterministik, label jujur. Tambah `umap-learn` nanti bila perlu |
| D2 | Persistensi vektor: Postgres pgvector vs FalkorDB property | **Postgres pgvector** (sudah terpasang) + tulis balik ke FalkorDB untuk graph |
| D3 | Fase 2 (HITL native) — invasive ke orchestrator | **Ya**, tapi setelah F1 & F2 sebagai commit terpisah |
| D4 | `/api/embedding/umap` rename → `/api/embedding/project` | Ya + alias lama 1 rilis |
| D5 | Peta warna berubah (subagent sky→indigo, hub multi→sky) | Ya — server jadi sumber kebenaran |
| D6 | Membangun tabel `guardrail_events` vs turunan dari audit+telemetry | **Turunan dulu** (nol migrasi) |
| D7 | Rotasi & hapus key router yang bocor | **Ya, segera** (P0 keamanan) |

---

## 5. Yang Dis-engage (YAGNI)
- Tabel `guardrail_events` & `circuit_breaker_events` baru (D6)
- `umap-learn` / `scipy` / `sklearn` / `faiss` (D1)
- Atlas 3D semantic edges clustering — reframe C2 dari subagent dipakai, 1 filter semantics
- Multi-dimensi embedding store (3072) — pilih 1024 saja
- `interface`/`factory` baru untuk handler — reuse langsung
