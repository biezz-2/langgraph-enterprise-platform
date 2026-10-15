# Enterprise LangGraph Platform (LGP v2.0) — The Unified Trifecta

[![LangGraph](https://img.shields.io/badge/Orchestrator-LangGraph%20v2.0-blue?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![FalkorDB](https://img.shields.io/badge/Graph%20Engine-FalkorDB%20C--Engine-red?style=flat-square)](https://www.falkordb.com/)
[![Graphiti](https://img.shields.io/badge/Temporal%20Memory-Graphiti--Core-emerald?style=flat-square)](https://github.com/getzep/graphiti)
[![9Router](https://img.shields.io/badge/LLM%20Gateway-9Router-purple?style=flat-square)](https://9router.biezz.my.id)
[![Next.js](https://img.shields.io/badge/Dashboard-Next.js%2015%20Obsidian-black?style=flat-square)](https://nextjs.org/)

Platform orkestrasi multi-agent enterprise dengan **10 Subagent Flagship**, memori pengetahuan bi-temporal berbasis **Graphiti-Core & FalkorDB**, gateway inferensi cerdas **9Router**, serta visualisasi interaktif **Obsidian Neuron Graph** berbasis Next.js.

---

## 1. Arsitektur Komprehensif (The Unified Trifecta)

Sistem LGP v2.0 dibangun di atas arsitektur Trifecta yang memadukan komputasi agen, memori jangka panjang bi-temporal, dan visualisasi interkoneksi saraf:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   INGESTION & INTERACTION LAYER                        │
│   FastMCP Clients (Port 8787) │ REST API │ WebSockets │ CLI Admin      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│            PILAR 1: ORCHESTRATION & SUPERVISION LAYER                  │
│                      (LangGraph StateGraph Engine)                     │
│  - Atlas Orchestrator-Supervisor (Pola Supervisor-via-Tools)           │
│  - 10 Subagent Flagship (4 Pod: Koordinasi, Riset, Ops, Tata Kelola)   │
│  - ContextPacket Dispatcher & State Transition Engine                  │
│  - Hierarchical Budget Inheritance ($15.00/day hard stop)              │
│  - Circuit Breakers & SHA-256 Tamper-Evident Audit Trail               │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌────────────────────────────────────┐ ┌─────────────────────────────────┐
│     PILAR 2: TEMPORAL MEMORY       │ │    PILAR 3: OBSERVABILITY &     │
│   (Graphiti-Core + FalkorDB)       │ │     OBSIDIAN NEURON GRAPH       │
│ - Model Bi-Temporal (T_v vs T_k)   │ │  - 3D/2D Spiking Neuron Canvas  │
│ - Engine C FalkorDB (<100MB RAM)   │ │  - Obsidian Control Deck        │
│ - Port Terisolasi 6382:6379        │ │  - Time-Travel History Slider   │
│ - 9Router Embedding & Extraction   │ │  - Next.js 15 Unified Dashboard │
│ - Resolusi Kontradiksi Otomatis    │ │  - WebSocket Live Stream Feed   │
└────────────────────────────────────┘ └─────────────────────────────────┘
```

Untuk rincian teknis lengkap, lihat [Technical Specification: The Unified Trifecta Architecture](docs/architecture/trifecta-architecture.md).

---

## 2. Struktur 10 Subagent Flagship (4 Pods)

Platform ini mengoperasikan 10 subagent mandiri dengan peran dan batasan least-privilege yang ketat:

| Pod | Subagent | Peran Utama | Kebijakan & Batasan |
|---|---|---|---|
| **Pod 1: Koordinasi** | `atlas` | Orchestrator-Supervisor | Titik masuk tunggal, dekomposisi tugas, distribusi `ContextPacket`, sintesis hasil dan budget capping. |
| **Pod 2: Riset & Rekayasa** | `clio` | Deep Researcher | Akses web outbound read-only; dilarang mengakses alat mutasi atau Admin MCP. |
| | `vulcan` | Software Engineer | Pembuatan dan validasi graf eksekusi kode di sandbox; dilarang self-promote ke production. |
| | `athena` | Critic & Reviewer | Evaluasi adversarial independen atas output Vulcan; verifikasi acceptance criteria. |
| **Pod 3: Platform Ops** | `hermes` | Platform Ops / SRE | Incident triage, automated health remediation, pemantauan performa layanan. |
| | `mnemosyne` | Memory Curator | Ingesti memori bi-temporal Graphiti L2, redaksi PII otomatis, deduplikasi entitas. |
| | `janus` | Integration & MCP Hub | Manajemen koneksi FastMCP eksternal, validasi anotasi risiko (`destructiveHint`, dll). |
| **Pod 4: Tata Kelola** | `themis` | Security & Compliance | Verifikasi rantai hash kriptografis SHA-256, audit least privilege, token leaks guard. |
| | `metron` | Evaluation & Data | LLM-as-judge benchmark, perhitungan matriks korelasi 10x10 NPMI. |
| | `iris` | Documentation & Comms | Generator PRD, ADR, changelog, dan laporan eksekutif berkala. |

---

## 3. Obsidian Neuron Graph (Visualisasi Memori Saraf)

Visualisasi pengetahuan dan interaksi subagent disajikan dalam antarmuka terinspirasi **Obsidian Graph View** yang dipadukan dengan dinamika *spiking neuron*:

- **Dark Obsidian Aesthetics**: Kanvas bertema gelap pekat (`#09090b`), kontras tinggi, dan tata letak force-directed yang mulus.
- **Dynamic Node Sizing**: Ukuran node merefleksikan *degree centrality* (jumlah koneksi relasi aktif). Hub kategori dan subagent berukuran lebih dominan daripada fakta individual.
- **Synaptic Pulse & Halo Glow**: Node aktif memancarkan pendar warna pod masing-masing. Relasi yang sudah usang (`invalid_at != null`) ditandai merah crimson (`#f43f5e`) bergaris putus-putus.
- **Obsidian Control Deck**: Slider interaktif untuk *repel force (charge)*, *link distance*, dan gravitasi pusat kanvas.
- **Bi-Temporal Time-Travel Slider**: Menjelajahi evolusi memori pada titik waktu masa lalu ($T_v$), menampilkan status validitas fakta historis.
- **Neighbor Spotlighting**: Arahkan kursor pada sebuah node untuk menyorot koneksi derajat 1 dan 2, serta meredupkan node lain.

---

## 4. Panduan Instalasi & Menjalankan Sistem

### 4.1 Prasyarat
- **Linux / macOS / WSL2** (Direkomendasikan Linux x86_64)
- **Python 3.11+**
- **Node.js 18+ & npm / pnpm**
- **Docker Engine** (untuk FalkorDB)
- **PM2** (opsional, untuk orchestrasi daemon produksi)

### 4.2 Menjalankan FalkorDB via Docker
FalkorDB adalah modul graph berbasis bahasa C yang sangat efisien (<100MB RAM). Karena port 6379 sering digunakan oleh instance Redis lain, petakan FalkorDB ke port **6382**:

```bash
docker run -d \
  --name lgp-falkordb \
  --restart unless-stopped \
  -p 6382:6379 \
  -v lgp_falkordb_data:/var/lib/falkordb/data \
  falkordb/falkordb-server:latest
```

Verifikasi container berjalan:
```bash
docker ps --filter "name=lgp-falkordb"
```

### 4.3 Menyiapkan Backend Python (LangGraph + FastMCP)
1. Buat dan aktifkan virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependensi platform:
   ```bash
   pip install --upgrade pip
   pip install -e .
   pip install "graphiti-core[falkordb]" falkordb
   ```
3. Salin file template lingkungan:
   ```bash
   cp .env.example .env
   # Sesuaikan kredensial di file .env
   ```

### 4.4 Menyiapkan Frontend Dashboard Next.js
1. Masuk ke direktori dashboard:
   ```bash
   cd apps/dashboard-nextjs
   npm install
   ```
2. Jalankan server pengembangan Next.js:
   ```bash
   npm run dev
   # Dashboard dapat diakses di http://localhost:3000
   ```

### 4.5 Menjalankan Produksi dengan PM2
Platform dilengkapi konfigurasi PM2 siap pakai (`ecosystem.config.cjs`):

```bash
# Menjalankan seluruh layanan LGP
pm2 start ecosystem.config.cjs

# Memeriksa status proses
pm2 status

# Melihat log streaming
pm2 logs lgp-api

# Me-restart layanan
pm2 restart lgp-api

# Menghentikan layanan
pm2 stop lgp-api
```

---

## 5. Konfigurasi Environment Variables

Konfigurasi sistem diatur melalui file `.env`. Gunakan `.env.example` sebagai acuan:

```ini
# ---- Backend Database -----------------------------------------------------
# Set USE_SUPABASE=true jika menggunakan Supabase terisolasi, atau false untuk SQLite lokal
USE_SUPABASE=false
LGP_DB_PATH=./data/lgp.db

# ---- Supabase Configuration (Jika USE_SUPABASE=true) ----------------------
SUPABASE_URL=https://your-supabase.domain.com
SUPABASE_SCHEMA=langgraph
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# ---- FalkorDB Storage -----------------------------------------------------
FALKORDB_HOST=127.0.0.1
FALKORDB_PORT=6382
FALKORDB_DB=lgp_graphiti

# ---- 9Router AI Gateway ---------------------------------------------------
9ROUTER_BASE_URL=https://9router.biezz.my.id/v1
9ROUTER_API_KEY=your_9router_key
EMBEDDING_MODEL=nvidia/nvidia/nv-embedqa-e5-v5
DEFAULT_INFERENCE_MODEL=anthropic/claude-3-5-sonnet

# ---- FastMCP Admin Server -------------------------------------------------
MCP_HOST=127.0.0.1
MCP_PORT=8787
```

---

## 6. Akses Layanan & API Endpoints

| Endpoint / Layanan | Port / URL | Keterangan |
|---|---|---|
| **Web Dashboard** | `http://localhost:3000` | Antarmuka grafis Next.js Obsidian Neuron Graph |
| **API Health Check** | `GET http://localhost:8000/api/health` | Pengecekan status backend, DB, dan MCP |
| **Swagger OpenAPI Docs** | `http://localhost:8000/docs` | Dokumentasi interaktif REST API |
| **Neuron Graph Payload** | `GET http://localhost:8000/api/graph/graphiti` | Ekstraksi node & edge untuk visualisasi kanvas |
| **Correlation Heatmap** | `GET http://localhost:8000/api/correlations` | Matriks telemetri 10x10 NPMI antar subagent |
| **FastMCP Tools Spec** | `GET http://localhost:8000/mcp/admin/tools` | Spesifikasi perkakas FastMCP terdaftar |
| **FastMCP Tool Execution** | `POST http://localhost:8000/mcp/admin/call` | Eksekusi RPC perkakas administrasi |

---

## 7. Pengujian & Verifikasi Kualitas

Jalankan test suite lengkap yang mencakup unit test, guardrail test, integrasi FastMCP, dan property-based test:

```bash
# Menjalankan seluruh pengujian dengan output verbose
.venv/bin/pytest tests/ -v
```

---

## 8. Protokol Kontribusi Multi-Agent

Repositori ini dikelola secara kolaboratif oleh agen otonom (Claude Code CLI, Nous Hermes Agent, OpenAI Codex, dan LangGraph Subagents). Setiap kontributor agen **wajib** mematuhi:

- **[AGENTS.md](AGENTS.md)**: Protokol operasional master, aturan phase-gate validation (V1–V8), dan siklus hidup kanban board.
- **[CLAUDE.md](CLAUDE.md)**: Panduan kerja khusus Claude Code CLI dan mekanisme ingesti/recall memori temporal.
- **Prinsip Utama**: *"IMPLEMENTED ≠ DONE"*. Setiap perubahan harus melalui fase validasi dan verifikasi sebelum dinyatakan selesai.
