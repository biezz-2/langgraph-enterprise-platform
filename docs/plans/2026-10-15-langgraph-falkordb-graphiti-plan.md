# Pelan Komprehensif Arsitektur & Implementasi: LangGraph + Graphiti (FalkorDB) + Obsidian Neuron Graph Dashboard

**Versi Dokumen:** 1.0.0  
**Tanggal:** 15 Oktober 2026  
**Status:** PROPOSED & REGISTERED (Board ID: `board-1792059973647`)  
**Penanggung Jawab:** PRIMARY_AI & HERMES (Dual Operatives)  
**Tujuan Utama:** Mengintegrasikan Graphiti asli berbasis FalkorDB (Opsi 1: Low RAM, <100MB), menyajikan data bi-temporal lengkap ke visualisasi Neuron Graph bergaya Obsidian, menyatukan seluruh halaman kontrol LangGraph ke dalam Next.js Dashboard, dan mempublikasikan repositori GitHub untuk kolaborasi multi-agent.

---

## 1. Executive Summary & Analisis Kebutuhan

Berdasarkan analisis infrastruktur host Linux (`/home/biezz`):
- **Sisa RAM:** ~2.2 GiB (dari 9.1 GiB total), **Swap:** 0 Byte.
- **Keputusan Backend (Opsi 1):** Menggunakan **FalkorDB** (`falkordb/falkordb-server:latest`). FalkorDB ditulis dalam bahasa C (modul Redis Graph), mengonsumsi RAM sangat rendah (<100 MB), mendukung Cypher query secara penuh, dan zero JVM overhead (meniadakan risiko Linux OOM Killer yang mematikan Hermes/Supabase).
- **Mapping Port:** Karena port 6379 sudah digunakan oleh `waha-redis` dan 6380 oleh `cap-redis-dev`, FalkorDB dipetakan ke **port 6382:6379**.
- **Model LLM & Embeddings:** Memanfaatkan gateway lokal 9Router (`https://9router.biezz.my.id/v1` atau proxy `http://127.0.0.1:20128/v1`) dengan model embedding `nvidia/nvidia/nv-embedqa-e5-v5` (fallback `openrouter/openai/text-embedding-3-small`) serta model inferensi ekstraksi via `OpenAIGenericClient`.

---

## 2. Arsitektur Komprehensif (The Unified Trifecta)

```
┌────────────────────────────────────────────────────────────────────────┐
│                   USER INTERFACE & INGESTION LAYER                     │
│  Discord / WAHA WhatsApp / Slack / CLI / FastMCP Client (Port 8787)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              ORCHESTRATION LAYER: LangGraph Platform (Port 8000)       │
│  - Atlas Supervisor Graph (Dynamic Routing & State Machine)            │
│  - Subagents: Clio, Vulcan, Athena, Mnemosyne, Janus, Themis, Metron   │
│  - State Persistence: SQLite / PostgreSQL Checkpointer & Store         │
│  - Event Bus (WebSocket Live Broadcasting to Dashboard)                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│         AGENT MEMORY & REASONING LAYER: Graphiti Core Engine           │
│  - Episodic Ingestion & Bi-temporal Fact Extraction (valid_at / invalid)│
│  - Dynamic Contradiction Resolution & Memory Invalidation              │
│  - LLM & Embedder: 9Router OpenAIGenericClient + nv-embedqa-e5-v5       │
│  - Graphiti-Core Native Driver: FalkorDriver (Port 6382)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│           GRAPH STORAGE LAYER: FalkorDB Docker Container               │
│  - Image: falkordb/falkordb-server:latest (C-based Redis Graph Module) │
│  - Storage: Labeled Property Graph (Nodes, Edges, Properties, Cypher)  │
│  - Volume: lgp_falkordb_data:/var/lib/falkordb/data                    │
│  - Memory footprint: ~50-80 MB RAM (Aman untuk host 2.2GB RAM)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│      DASHBOARD & VISUALIZATION LAYER: Next.js Platform (Port 3000)     │
│  - Obsidian-style 3D/2D Neuron Graph (Three.js / Force-Directed / D3)  │
│  - Unified Dashboard Suite (8+ Halaman): Overview, Runs, HITL, Memory, │
│    Subagents, Matrix, Kanban, Telemetry, API/MCP Explorer             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detail Desain Neuron Graph (Obsidian-Style)

Visualisasi dibuat menyerupai **Graph View Obsidian** dengan sentuhan interkoneksi biologis/sinaptik (MiroFish Spiking Neuron):

### 3.1 Estetika Visual (Obsidian Aesthetic)
1. **Dark Obsidian Canvas:** Background gelap pekat (`#09090b` / `#020617`) dengan subtle grid / starfield yang tidak mendistraksi.
2. **Dynamic Node Sizing:** Ukuran node proporsional terhadap *degree centrality* (jumlah relasi/koneksi aktif). Hub utama dan Subagent berukuran lebih besar (24-32px), entitas spesifik berukuran kompak (12-16px).
3. **Synaptic Glow & Rings:** Node bercahaya dengan glow halo semitransparan. Node aktif memancarkan aura warna kelompoknya; node yang sudah invalid (`invalid_at != null`) berwarna merah padam (`#f43f5e`) dengan border putus-putus.
4. **Curved & Particle Edges:** Garis koneksi halus dengan particle pulses yang mengalir searah transmisi relasi (meniru *action potential* sinapsis).

### 3.2 Kontrol Interaktif (Obsidian Control Deck)
1. **Interactive Search & Highlights:** Input search box dengan auto-complete. Mengetik query langsung memfokuskan kamera ke node terkait.
2. **Neighbor Spotlighting:** Hover pada sebuah node akan menerangi (highlight) tetangga derajat 1 & 2 dan meredupkan (dim) node yang tidak terhubung (persis seperti Obsidian).
3. **Color Groups & Tags:** Pemetaan warna otomatis berdasarkan kategori ontologi:
   - `Supervision / Atlas`: Zinc / Pearl White (`#f4f4f5`)
   - `Riset / Clio / Iris`: Emerald (`#10b981`)
   - `Koding / Vulcan / Athena`: Indigo (`#6366f1`)
   - `Platform / Hermes / Mnemosyne`: Amber (`#f59e0b`)
   - `Tata Kelola / Themis / Janus`: Fuchsia (`#d946ef`)
   - `Temporal Facts`: Cyan (`#06b6d4`)
   - `Invalidated Facts`: Rose Crimson (`#f43f5e`)
4. **Physics & Force Sliders:**
   - *Repel Force (Charge)*: Mengatur daya tolak antar-node.
   - *Link Distance & Strength*: Mengatur kerapatan kluster.
   - *Center Gravity*: Mengatur tarikan ke tengah kanvas.
5. **Bi-Temporal Time-Travel Slider:**
   - Slider garis waktu (timestamp). Menggeser slider ke masa lalu akan memperlihatkan fakta mana yang saat itu aktif dan menyembunyikan fakta masa depan atau menampilkan evolusi invalidasi fakta.
6. **Side Inspection Drawer:**
   - Mengklik node membuka panel samping detail: Subject, Predicate, Object, Valid At, Invalid At, Episode Run ID, derajat relasi, dan tombol untuk menjalankan kueri Cypher terkait.

---

## 4. Struktur Lengkap Dashboard LangGraph Enterprise

Dashboard Next.js (`apps/dashboard-nextjs`) dikonsolidasikan agar memuat seluruh modul operasional:

1. **Overview & Control Plane (`/` / Tab Overview):**
   - KPI Ringkasan: Total Runs, Aktif Subagents, Hit Rate Memori, Latency Rata-rata.
   - Health Monitor: Status Uvicorn, FastMCP, FalkorDB, Supabase, WAHA.
   - Live Event Stream: WebSocket realtime feed aktivitas agen.
2. **3D/2D Obsidian Neuron Graph (`/neuron-graph`):**
   - Fullscreen / expanded graph explorer dengan deck kontrol Obsidian.
   - Switcher mode 3D (ThreeJS WebGL) dan 2D (HTML5 Canvas ultra-ringan).
3. **Subagent Registry & Pods (`/subagents`):**
   - Kartu profil tiap agen (Atlas, Clio, Vulcan, Athena, Hermes, Mnemosyne, Janus, Themis, Metron, Iris).
   - Indikator Trust Level, Model Policy (9Router), Kapabilitas, Alokasi Token Budget, dan Circuit Breaker status.
4. **LangGraph Thread & Run Inspector (`/runs`):**
   - Riwayat eksekusi thread LangGraph.
   - Visualisasi visual DAG eksekusi langkah (state graph execution flow).
   - Checkpoint inspect: State input/output di setiap langkah, node latency, token cost.
5. **Human-in-the-Loop (HITL) Inbox (`/hitl`):**
   - Antarmuka persetujuan (approval) tindakan berisiko tinggi.
   - Pause, Resume, Reject eksekusi agent.
6. **Bi-Temporal Memory & Curation Table (`/memory`):**
   - Tabel seluruh fakta memori jangka panjang (subject, predicate, object, bi-temporal interval).
   - Fitur pencarian semantik (menggunakan 9Router vector embeddings).
   - Form penambahan manual fakta & tombol trigger Ingest Episode baru.
7. **Inter-Neuron Correlation Matrix (`/matrix`):**
   - Heatmap NPMI (Normalized Pointwise Mutual Information) antar subagent.
   - Analisis co-activation dan bobot handoff antar subagent.
8. **Kanban Platform Board (`/kanban`):**
   - Implementasi siklus hidup kartu AGENTS.md: `BACKLOG` → `IN PROGRESS` → `IMPLEMENTED` → `IN VALIDATION` → `VALIDATED` / `REWORK`.
9. **Security, Telemetry & Guardrails (`/guardrails`):**
   - Monitor circuit breaker dan OWASP LLM Top 10 mitigation logs.
   - Audit trail transaksi dan mutasi state.
10. **FastMCP & API Explorer (`/api-docs`):**
    - Dokumentasi interaktif OpenAPI / Swagger dan FastMCP Tool playground.

---

## 5. Rencana Fase Implementasi & Validasi (Sesuai AGENTS.md)

### Fase 1: FalkorDB Infrastructure & Dependency Setup
- **Tindakan:**
  1. Jalankan container Docker:
     ```bash
     docker run -d --name lgp-falkordb \
       --restart unless-stopped \
       -p 6382:6379 \
       -v lgp_falkordb_data:/var/lib/falkordb/data \
       falkordb/falkordb-server:latest
     ```
  2. Install paket ke `.venv`:
     ```bash
     uv pip install "graphiti-core[falkordb]" falkordb
     ```
  3. Konfigurasi kredensial di `.env`: `FALKORDB_PORT=6382`, `FALKORDB_HOST=localhost`, `FALKORDB_DB=lgp_graphiti`.
- **Validasi Gate (V1-V5):**
  - Tes koneksi Redis/Cypher via `redis-cli -p 6382 ping` dan kueri `GRAPH.QUERY lgp_graphiti "RETURN 1"`.
  - Verifikasi penggunaan RAM container (<100MB) via `docker stats --no-stream lgp-falkordb`.

### Fase 2: Graphiti Memory Engine & FalkorDB Driver Integration
- **Tindakan:**
  1. Refaktor `packages/memory/graphiti.py` untuk menginisialisasi `FalkorDriver` dan `Graphiti` asli.
  2. Sambungkan ke LLM & Embedding 9Router via `OpenAIGenericClient` dan `OpenAIEmbedder`.
  3. Bangun fungsi `build_neuron_graph()` yang mengeksekusi Cypher query terhadap FalkorDB:
     - Mengambil node entitas, subagent, kategori, dan episode.
     - Mengambil edges beserta metadata temporal (`valid_at`, `invalid_at`).
     - Menghitung degree node dan bobot koneksi.
  4. Expose endpoint di FastAPI: `GET /api/graph/graphiti` dan `POST /api/memory/episodes`.
- **Validasi Gate (V1-V7):**
  - Unit test `test_graphiti_falkordb.py`: Ingest 1 episode, pastikan entitas dan relasi tersimpan di FalkorDB dan terbaca via Cypher.
  - Test skenario invalidasi fakta: Tambahkan fakta baru yang kontradiktif, pastikan fakta lama berstatus `invalid_at != null`.

### Fase 3: Komponen Obsidian-Style Neuron Graph di Frontend
- **Tindakan:**
  1. Tingkatkan `apps/dashboard-nextjs/src/components/NeuronGraph.tsx`:
     - Tambahkan kontrol gaya Obsidian (slider daya tolak, jarak link, gravitasi).
     - Tambahkan filter node types & bi-temporal slider.
     - Tambahkan neighbor spotlighting (hover 1st & 2nd degree).
     - Tambahkan drawer detail inspeksi node di sisi kanan.
  2. Pastikan responsif dan performa tinggi (60 FPS) dengan level of detail (LOD).
- **Validasi Gate:**
  - Rendering test di browser dengan >100 nodes tanpa lag memori.

### Fase 4: Konsolidasi Multi-Page Dashboard LangGraph
- **Tindakan:**
  1. Perbarui navigasi dan rute Next.js untuk mencakup 10 modul lengkap.
  2. Sediakan mock/live fallback jika beberapa backend offline sehingga UI tetap resilient.
  3. Pastikan layout konsisten dengan tema Dark MiroFish/Obsidian (Zinc 900/950, Indigo accent).
- **Validasi Gate:**
  - Build test Next.js (`npm run build`) bebas error TypeScript & linting.

### Fase 5: GitHub Repository Setup & Multi-Agent Collaboration
- **Tindakan:**
  1. Buat repository baru di GitHub melalui MCP: `biezz/langgraph-enterprise-platform`.
  2. Buat file `AGENTS.md`, `README.md`, `CLAUDE.md`, dan lisensi.
  3. Hubungkan git remote lokal ke GitHub via SSH/HTTPS dan lakukan push pertama.
  4. Dokumentasikan arsitektur dan panduan kontribusi untuk agent lain (Claude Code, Hermes, Codex).
- **Validasi Gate:**
  - Verifikasi repo aktif di `https://github.com/biezz/langgraph-enterprise-platform` dan commit terverifikasi.

### Fase 6: Phase-Gate Validation & Automated Monitoring
- **Tindakan:**
  1. Jalankan full review V1-V8 sesuai protokol `AGENTS.md`.
  2. Daftarkan cron health-audit di Hermes / system scheduler untuk memantau performa FalkorDB dan sinkronisasi graf tiap 24 jam.

---

## 6. Risk Register & Mitigasi

| Risiko | Keparahan | Mitigasi |
|---|---|---|
| Konflik port 6379 dengan WAHA Redis | TINGGI | Map FalkorDB ke port `6382:6379`. |
| Kapasitas RAM menipis jika banyak episode di-ingest | SEDANG | FalkorDB dikonfigurasi dengan batas memori `maxmemory 512mb` dan LRU policy; embedding disimpan terkompresi. |
| Latency embedding 9Router saat graphiti ekstraksi entitas | RENDAH | Gunakan asynchronous episode processing dengan batching dan queue internal. |
| Browser lag saat merender ribuan node 3D | SEDANG | Gunakan Web Worker layout atau opsi toggle 2D Canvas view untuk graf berukuran besar. |

---

*Dokumen ini tersimpan secara persisten dan menjadi panduan baku bagi seluruh agent dalam eksekusi proyek.*
