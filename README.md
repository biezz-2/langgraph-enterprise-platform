# Enterprise LangGraph Platform (LGP v2.0)

Platform orkestrasi multi-agent enterprise dengan **10 Subagent Flagship** yang berjalan dengan pola supervisor-via-tools, guardrail keamanan least-privilege, budget turun-temurun, telemetri korelasi L1, dan memori temporal L2.

## Arsitektur 10 Subagent (4 Pod)

1. **Pod Koordinasi**:
   - `atlas`: Orchestrator-Supervisor (titik masuk tunggal, dekomposisi tugas, context packet distribution, effort scaling, sintesis laporan biaya).
2. **Pod Riset & Rekayasa**:
   - `clio`: Deep Researcher (outbound read-only, isolasi ketat: dilarang akses Admin MCP).
   - `vulcan`: Software Engineer (propose & validate graf, sandbox execution; dilarang self-promote prod).
   - `athena`: Critic & Reviewer (evaluasi adversarial, critic loop Vulcan ↔ Athena via `CRITICIZES`).
3. **Pod Platform**:
   - `hermes`: Platform Ops / SRE (incident triage, health check, runbook proposals).
   - `mnemosyne`: Memory Curator (ingest bi-temporal Graphiti L2, redaksi PII, deduplikasi entitas).
   - `janus`: Integration & MCP Hub (manajemen server MCP eksternal, validasi tool annotations).
4. **Pod Tata Kelola**:
   - `themis`: Security & Compliance (verifikasi tamper-evident audit hash chain, isolasi nilai secret).
   - `metron`: Evaluation & Data (dataset benchmark, regression promote gate, LLM-as-judge).
   - `iris`: Documentation & Comms (PRD, ADR, runbook, dan executive report generator).

## Fitur Utama

- **Supervisor-via-Tools Orchestrator**: Distribusi tugas terstruktur via `ContextPacket` lengkap dengan alokasi budget dan batasan tugas.
- **Inherited Budget Hierarchy**: Budget anak $\le$ sisa budget induk. Dilengkapi hard stop harian ($15.00) dan circuit breaker (3 kegagalan beruntun).
- **Loop Detector**: Deteksi perulangan hash state $\ge 3$ memicu interupsi ke Human-in-the-Loop (HITL) Inbox.
- **Matriks Korelasi 10x10**: Kalkulasi metrik telemetri real-time (NPMI, handoff rate, success lift, bobot komposit $W_{ij}$) dengan indikator "data sedikit" ($n < 50$).
- **Memori Bi-Temporal**: Mendukung pemisahan waktu validitas dunia nyata ($T_v$) dan waktu pencatatan sistem ($T_k$) serta redaksi PII (email, NIK, telepon).
- **FastMCP Admin Server**: Antarmuka kendali standar MCP dengan anotasi risiko eksplisit (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`).
- **Audit Log Tamper-Evident**: Rantai hash kriptografis SHA-256 append-only.
- **Web Dashboard**: UI interaktif berbasis Tailwind CSS untuk memantau subagent, heatmap korelasi, live stream SSE, dan HITL inbox.

## Menjalankan dengan PM2

Platform telah dikonfigurasi menggunakan file ekosistem PM2: `ecosystem.config.cjs`.

### Perintah PM2:
```bash
# Menjalankan service
pm2 start ecosystem.config.cjs

# Memeriksa status
pm2 status

# Melihat log real-time
pm2 logs lgp-api

# Me-restart service
pm2 restart lgp-api

# Menghentikan service
pm2 stop lgp-api
```

## Akses Layanan

- **Web Dashboard**: `http://localhost:8000/`
- **Health Check**: `http://localhost:8000/api/health`
- **Swagger OpenAPI Docs**: `http://localhost:8000/docs`
- **10x10 Correlation Heatmap API**: `http://localhost:8000/api/correlations`
- **FastMCP Tools Spec**: `http://localhost:8000/mcp/admin/tools`

## Pengujian & Verifikasi

Untuk menjalankan seluruh test suite (unit test, guardrail test, property test, dan API integration test):

```bash
.venv/bin/pytest tests/ -v
```
