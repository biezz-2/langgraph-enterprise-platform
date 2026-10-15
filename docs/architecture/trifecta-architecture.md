# Technical Specification: The Unified Trifecta Architecture

**Sistem:** Enterprise LangGraph Platform (LGP v2.0)  
**Komponen:** LangGraph Supervisor + Graphiti-Core (FalkorDB) + Obsidian Neuron Graph (Next.js)  
**Versi:** 2.0.0  
**Status:** Canonical Architecture Specification  

---

## 1. Arsitektur Tingkat Tinggi (The Unified Trifecta)

Enterprise LangGraph Platform (LGP v2.0) dirancang menggunakan pola **Trifecta Architecture**, menggabungkan tiga pilar utama:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   INGESTION & INTERACTION LAYER                        │
│     FastMCP Clients (Port 8787) │ REST API / WebSockets │ CLI          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             PILAR 1: ORCHESTRATION & SUPERVISION LAYER                 │
│                      (LangGraph StateGraph Engine)                     │
│  - Atlas Orchestrator-Supervisor (Dynamic Task Router)                 │
│  - 10 Flagship Subagents (4 Pods: Koordinasi, Riset, Ops, Tata Kelola)  │
│  - State Machine & ContextPacket Dispatcher                            │
│  - Hierarchical Budget Inheritance & Circuit Breaker Guardrails        │
│  - Tamper-Evident SHA-256 Audit Trail & State Loop Detector            │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌────────────────────────────────────┐ ┌─────────────────────────────────┐
│     PILAR 2: TEMPORAL MEMORY       │ │    PILAR 3: OBSERVABILITY &     │
│   (Graphiti-Core + FalkorDB)       │ │     OBSIDIAN NEURON GRAPH       │
│ - Bi-Temporal Model (T_v vs T_k)   │ │  - 3D/2D Spiking Neuron Canvas  │
│ - FalkorDB C-Engine (<100MB RAM)   │ │  - Obsidian Control Deck        │
│ - Invalidation & Contradiction Res │ │  - Next.js 15 Unified Dashboard │
│ - 9Router Embeddings & LLM Gateway │ │  - Real-Time WebSocket Streaming│
└────────────────────────────────────┘ └─────────────────────────────────┘
```

---

## 2. Pilar 1: LangGraph Supervisor Pattern & Subagent Contracts

### 2.1 Pola Supervisor-via-Tools
Orkestrasi multi-agent menggunakan pola *Supervisor-via-Tools*, di mana node supervisor (`Atlas`) bertindak sebagai single-entrypoint yang mengarahkan subagent melalui pemanggilan alat terstruktur (structured tool dispatch).

- **Supervisor Node (`Atlas`)**:
  - Menganalisis kebutuhan instruksi pengguna dan memecah masalah menjadi rencana eksekusi terstruktur.
  - Membungkus konteks dan batasan eksekusi ke dalam format standar `ContextPacket`.
  - Menerima sintesis hasil eksekusi dari subagent, mengevaluasi kualitas, dan menyusun jawaban akhir.

### 2.2 Kontrak State: `ContextPacket`
Setiap delegasi tugas dari supervisor ke subagent dikawal oleh skema kontrak data ketat:

```python
class ContextPacket(BaseModel):
    task_id: str
    initiator_agent: str
    target_subagent: str
    instruction: str
    context_data: Dict[str, Any]
    budget_allocated: float          # Maksimum biaya USD yang diizinkan
    step_timeout_sec: int = 60
    state_history_hash: str
    security_clearance: str          # PUBLIC, INTERNAL, RESTRICTED
```

### 2.3 Pembagian 10 Flagship Subagents (4 Pods)
1. **Pod Koordinasi**:
   - `atlas`: Supervisor utama, pemecah tugas, agregasi hasil, dan penjaga anggaran global.
2. **Pod Riset & Rekayasa**:
   - `clio`: Deep Researcher (outbound read-only, akses web/dokumen, isolasi ketat dari modul destruktif).
   - `vulcan`: Software Engineer (eksekusi sandbox, modifikasi kode, pembuatan DAG).
   - `athena`: Critic & Reviewer (evaluasi adversarial terhadap output Vulcan, verifikasi acceptance criteria).
3. **Pod Platform Ops**:
   - `hermes`: SRE & Ops Specialist (monitoring kesehatan layanan, pemulihan insiden, auto-remediation).
   - `mnemosyne`: Memory Curator (ingesti bi-temporal, redaksi PII, kurasi ontologi).
   - `janus`: Integration & FastMCP Hub (konektor tool eksternal, validasi anotasi risiko).
4. **Pod Tata Kelola**:
   - `themis`: Security & Compliance Officer (verifikasi hash chain audit, deteksi token kebocoran secret).
   - `metron`: Evaluation & Benchmark (LLM-as-judge, evaluasi metrik NPMI korelasi).
   - `iris`: Documentation & Reporter (penulisan ADR, PRD, dan laporan eksekutif).

### 2.4 Safety Guardrails & Resilience
- **Inherited Budget Hierarchy**: Subagent tidak dapat mengalokasikan anggaran melebihi budget yang diberikan oleh supervisor. Hard stop harian dipatok pada batas $15.00 USD.
- **Circuit Breaker**: Jika subagent mengalami kegagalan 3 kali berturut-turut, status subagent dialihkan ke `CIRCUIT_OPEN` dan eksekusi dialihkan ke Human-in-the-Loop (HITL).
- **State Loop Detector**: Sistem mencatat hash representasi state; pengulangan state berturut-turut $\ge 3$ memicu interupsi darurat ke antarmuka operator.

---

## 3. Pilar 2: Model Memori Bi-Temporal (Graphiti-Core + FalkorDB)

### 3.1 Teori Memori Bi-Temporal
Memori agen enterprise memisahkan dua dimensi waktu independen untuk setiap fakta:
1. **Valid Time ($T_v$)**: Waktu ketika sebuah fakta dianggap benar di dunia nyata (`valid_at` hingga `invalid_at`).
2. **Transaction Time ($T_k$)**: Waktu ketika fakta tersebut dicatat oleh sistem LGP ke dalam basis data (`created_at`).

Dengan model ini, sistem dapat:
- Melakukan rekonstruksi konteks masa lalu (*time-travel query*).
- Menangani fakta kontradiktif tanpa menghapus data historis (cukup mengisi `invalid_at = now`).
- Melacak evolusi pengetahuan dan keputusan agen.

### 3.2 FalkorDB sebagai Graph Storage Engine
FalkorDB dipilih sebagai backend graph native untuk Graphiti-Core berdasarkan karakteristik performa:
- **Low Footprint (<100MB RAM)**: FalkorDB diimplementasikan sebagai modul Redis Graph dalam bahasa C murni, meniadakan JVM overhead seperti pada Neo4j enterprise.
- **Cypher Query Compatibility**: Mendukung kueri openCypher penuh untuk pencarian relasi berderajat jamak.
- **Isolasi Port**: Berjalan pada port host `6382:6379` untuk mencegah tabrakan port dengan service Redis lain.

### 3.3 Skema Node & Edge Graphiti
```cypher
// Node Entitas Pengetahuan
(:Entity {
  id: STRING,
  name: STRING,
  type: STRING,          // "subagent", "category", "concept", "project"
  group: STRING,
  summary: STRING,
  created_at: TIMESTAMP
})

// Edge Relasi Bi-Temporal
(:Entity)-[:RELATION {
  predicate: STRING,
  valid_at: TIMESTAMP,
  invalid_at: TIMESTAMP,  // NULL jika masih berlaku
  episode_run_id: STRING,
  confidence: FLOAT,
  source_agent: STRING
}]->(:Entity)
```

### 3.4 9Router Gateway & Embedding
Ekstraksi entitas dan pencarian semantik ditenagai oleh gateway 9Router:
- **Embedding Model**: `nvidia/nvidia/nv-embedqa-e5-v5` (fallback: `openrouter/openai/text-embedding-3-small`).
- **Inference LLM**: Menghasilkan tripel ontologi (Subject - Predicate - Object) dan deteksi entitas kontradiktif.

---

## 4. Pilar 3: Obsidian Neuron Graph & Next.js Control Plane

### 4.1 Desain Visual Neuron Graph
Visualisasi graf mengadopsi estetika **Obsidian Graph View** yang dipadukan dengan dinamika *spiking neuron*:
- **Dark Obsidian Canvas**: Background `#09090b` dengan grid halus dan particle flows.
- **Dynamic Node Sizing**: Ukuran radius node proporsional terhadap *degree centrality* ($k_i = \sum A_{ij}$).
- **Synaptic Glow**: Node aktif berpendar dengan warna grup ontologi; fakta yang telah usang (`invalid_at != null`) ditandai warna merah Crimson (`#f43f5e`) bergaris putus-putus.
- **Particle Transmission Edges**: Garis lengkung interkoneksi memancarkan pulsa partikel searah aliran informasi handoff.

### 4.2 Obsidian Control Deck & Interaktivitas
- **Neighbor Spotlighting**: Hover pada sebuah node menyorot tetangga derajat 1 & 2 serta meredupkan node lain.
- **Physics Sliders**: Pengaturan dinamis gaya tolak (charge), jarak link, dan sentralitas gravitasi kanvas.
- **Time-Travel Slider**: Memungkinkan operator menelusuri status graf pada waktu $t$, merekonstruksi fakta yang aktif pada titik waktu tersebut.
- **Inspection Drawer**: Panel samping menampilkan properti detail fakta, run ID terkait, serta tombol kueri Cypher interaktif.

### 4.3 Arsitektur Next.js 15
Dashboard Next.js (`apps/dashboard-nextjs`) menyatukan seluruh subsistem kontrol:
- `/`: Overview, status health layanan, ringkasan KPI, dan live WebSocket stream.
- `/neuron-graph`: Eksplorasi 2D/3D Obsidian Neuron Graph.
- `/subagents`: Profil 10 subagent, trust level, kuota budget, dan circuit breaker.
- `/runs`: LangGraph DAG run inspector dan checkpoint time-travel.
- `/hitl`: Human-in-the-Loop approval inbox.
- `/memory`: Tabel kurasi bi-temporal dan pencarian semantik.
- `/matrix`: Heatmap inter-neuron NPMI dan analisis co-activation.
- `/kanban`: Board siklus hidup kartu sesuai protokol `AGENTS.md`.
- `/guardrails`: Monitoring keamanan dan mitigasi OWASP LLM Top 10.
- `/api-docs`: OpenAPI explorer dan FastMCP client testing interface.

---

## 5. Ringkasan Protokol Keamanan & Governance

1. **Least-Privilege Execution**: Subagent beroperasi dalam lingkungan terisolasi dengan akses alat yang dideklarasikan secara eksplisit.
2. **Tamper-Evident Hash Chain**: Setiap transaksi dan transisi state diproteksi oleh rantai hash SHA-256 append-only.
3. **Redaksi PII Otomatis**: NIK, nomor telepon, dan email dipindai dan disamarkan sebelum diabadikan ke memori temporal.
4. **FastMCP Annotation**: Seluruh alat MCP mengekspos metadata risiko (`readOnlyHint`, `destructiveHint`, `idempotentHint`).
