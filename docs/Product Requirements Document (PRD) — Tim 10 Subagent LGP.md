��# Product Requirements Document (PRD) — Tim 10 Subagent LGP


| Info      | Nilai                                                        |
| --------- | ------------------------------------------------------------ |
| Versi     | 1.0 — 2026-10-08                                             |
| Status    | Draf — menunggu konfirmasi pemilik produk                    |
| Pemilik   | Pemilik platform (pengguna)                                  |
| Audiens   | Pemilik, developer/implementer, AI operator (AgentPrincipal) |
| Referensi | Blueprint LGP v2.0; Makalah 10 Subagent; Rencana PR #0–#18   |
| Bahasa    | Indonesia                                                    |


---

## 1. Ringkasan Produk

Tim **10 subagent** yang berjalan di atas Enterprise LangGraph Platform (LGP): satu supervisor (Atlas) dan sembilan spesialis lintas domain (riset, rekayasa perangkat lunak, operasional platform, memori, keamanan, evaluasi, dokumentasi, integrasi) yang:

- dikelola **100% lewat platform** (registry, budget, grant tool, telemetri, korelasi, HITL),
- dapat dikendalikan **dari dashboard dan dari AI eksternal via Admin MCP** dengan paritas penuh,
- aman secara desain: least privilege, sandbox, approval gate untuk aksi berisiko,
- dan **siap jadi showcase produk/SaaS multi-tenant** tanpa rewrite.

## 2. Masalah &amp; Peluang


| Masalah                                                                             | Dampak hari ini                                              | Peluang                                                     |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------- |
| Tugas lintas-domain (riset→kode→ops) dikerjakan manual oleh satu orang/AI monolitik | Lambat, konteks meluap, biaya tak terkontrol                 | Delegasi paralel dengan subagent spesialis + context packet |
| Tidak ada kontrak eksplisit antar-agen                                              | Duplikasi kerja, celah tanggung jawab, biaya tak terprediksi | Registry + kontrak input/output + budget turun-temurun      |
| Memori agen hilang antar sesi / tidak bertanggal                                    | Keputusan berulang, fakta usang dipakai lagi                 | Memori temporal Graphiti bi-temporal dengan sitasi episode  |
| Tidak ada keterkaitan terukur antar-agen                                            | Tidak tahu tim mana yang efektif                             | Matriks korelasi L1 (telemetri) + heatmap di Neuron Graph   |
| Aksi AI berisiko tanpa gerbang                                                      | RCE, biaya meledak, kebocoran data                           | Sandbox + approval gate + audit log                         |


## 3. Tujuan &amp; Non-Tujuan

**Tujuan (v1.0)**

1. 10 subagent terdaftar dengan kontrak lengkap dan aktif untuk 3 skenario lintas-tim (riset, rekayasa, insiden).
2. Semua aksi berisiko (promote prod, ubah grant, ubah secret) melewati approval manusia.
3. Biaya per run dapat diprediksi: budget turun-temurun aktif + hard stop harian.
4. Topologi dan korelasi tim tampil di dashboard (heatmap + Neuron Graph) dengan sitasi episode.
5. Paritas penuh: setiap aksi tim dapat dilakukan via UI maupun Admin MCP.

**Non-Tujuan (v1.0)**

- Marketplace subagent publik; billing nyata; SSO enterprise (SAML/SCIM); multi-region; sub-subagent (kedalaman &gt; 2); fine-tuning model sendiri; editor visual round-trip.

## 4. Persona &amp; Pengguna


| Persona                                   | Kebutuhan                                                       | Momen pakai                                        |
| ----------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------- |
| **Pemilik platform** (satu orang, fase 0) | Melihat biaya, menyetujui aksi berisiko, memantau kesehatan tim | Promote prod, interrupt HITL, review audit         |
| **AI Operator** (`AgentPrincipal`)        | Mengelola tim via Admin MCP dengan scope minimal                | Register/update subagent, jalankan run, baca state |
| **Developer/implementer**                 | Registry, skema, eval, telemetry yang mudah diuji               | PR #8, #16–#18                                     |
| **Approver** (peran manusia)              | Inbox HITL jelas: konteks, risiko, rekomendasi                  | Approval promote/rollback/grant                    |


## 5. Ruang Lingkup Rilis v1.0

- **10 subagent final** (proposal makalah §5.3): Atlas (supervisor), Clio (riset), Vulcan (koding), Athena (reviewer), Hermes (ops), Mnemosyne (memori), Themis (keamanan), Metron (evaluasi), Iris (dokumentasi), Janus (integrasi/MCP hub).
- **4 pod**: Koordinasi; Riset &amp; Rekayasa; Platform; Tata Kelola.
- **Platform pendukung**: runtime, queue, sandbox, HITL, Admin MCP, outbound MCP hub, telemetri L1, Graphiti L2, dashboard, evals — sesuai blueprint.

## 6. Product Requirements (PR)

Prioritas: **Wajib** (harus ada di v1.0) · **Sebaiknya** (v1.1 bila kapasitas) · **Bisa** (backlog).

### 6.1 Orkestrasi (Atlas)


| ID        | Kebutuhan                                                                                                                                                                                  | Prioritas |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| PR-ORC-01 | Atlas adalah satu-satunya titik masuk tugas; memproduksi rencana, memecah tugas, dan mendistribusikan context packet berisi objektif, batas, format output, grant tool, dan budget tersisa | Wajib     |
| PR-ORC-02 | Effort scaling ditegakkan runtime: 1 subagent (tugas sederhana), 2–4 (perbandingan), &gt;4 meminta konfirmasi manusia, maksimum 10 aktif per run                                           | Wajib     |
| PR-ORC-03 | Atlas menyintesis hasil delegasi menjadi jawaban final dengan sitasi dan laporan biaya per subagent                                                                                        | Wajib     |
| PR-ORC-04 | Handoff swarm hanya diizinkan untuk loop critic (Vulcan↔Athena) dan dicatat sebagai event telemetri                                                                                        | Sebaiknya |


### 6.2 Kontrak &amp; registry


| ID        | Kebutuhan                                                                                                                                                                        | Prioritas |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| PR-REG-01 | Setiap subagent terdaftar dengan kontrak lengkap: id, role, kapabilitas, input/output schema, allowed\_tools, model\_policy, budget, memory\_scope, trust\_level, owner, version | Wajib     |
| PR-REG-02 | Perubahan kontrak subagent berversi; kontrak lama tetap terbaca untuk run historis                                                                                               | Wajib     |
| PR-REG-03 | Validasi skema input/output otomatis di setiap delegasi; pelanggaran → interrupt, bukan lanjut diam-diam                                                                         | Wajib     |


### 6.3 Budget &amp; guardrail


| ID        | Kebutuhan                                                                                                        | Prioritas |
| --------- | ---------------------------------------------------------------------------------------------------------------- | --------- |
| PR-BUD-01 | Budget turun-temurun (token, USD, wall-clock, langkah, kedalaman) ditegakkan runtime: anak ≤ sisa induk          | Wajib     |
| PR-BUD-02 | Hard stop harian per workspace (default: ekuivalen $15/hari untuk tim; dapat dikonfigurasi)                      | Wajib     |
| PR-BUD-03 | Circuit breaker per subagent: 3 kegagalan beruntun → nonaktif untuk run, tercatat, dapat diaktifkan ulang manual | Wajib     |
| PR-BUD-04 | Deteksi loop (hash state berulang ≥ 3) → interrupt HITL dengan konteks                                           | Wajib     |


### 6.4 Keamanan &amp; izin


| ID        | Kebutuhan                                                                                                                              | Prioritas |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| PR-SEC-01 | Subagent hanya melihat tool sesuai grant per-node; pelanggaran ditolak + audit                                                         | Wajib     |
| PR-SEC-02 | **Clio (konteks eksternal tak tepercaya) tidak memiliki akses Admin MCP** — diuji otomatis                                             | Wajib     |
| PR-SEC-03 | Vulcan dapat propose/validate graf tetapi **tidak dapat self-promote**; promote prod = approval manusia; AI tidak bisa approve dirinya | Wajib     |
| PR-SEC-04 | Themis tidak pernah menerima nilai secret (hanya referensi nama)                                                                       | Wajib     |
| PR-SEC-05 | Tool-call guard: validasi argumen, timeout, batas output, redaksi secret, deteksi pola injection pada semua tool outbound              | Wajib     |
| PR-SEC-06 | Semua aksi subagent tercatat di audit log append-only (hash-chain) dengan actor, scope, args\_hash, hasil                              | Wajib     |


### 6.5 Memori &amp; korelasi


| ID        | Kebutuhan                                                                                                                                                                           | Prioritas |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| PR-MEM-01 | Telemetri L1 real-time (delegasi, tool call, state read/write, error, biaya) untuk semua subagent — tanpa LLM                                                                       | Wajib     |
| PR-MEM-02 | Ingest Graphiti L2 async per-run (ringkasan) atau node `memorize=true`; batch + dedup hash + anggaran harian; redaksi PII                                                           | Wajib     |
| PR-MEM-03 | Semua fakta bi-temporal (valid\_at/invalid\_at/created\_at/expired\_at) dan tertelusur ke episode sumber                                                                            | Wajib     |
| PR-MEM-04 | Matriks korelasi 10×10 (handoff\_rate, co-activation NPMI, success\_lift, latency\_coupling, state\_dependency, cost\_share, failure\_propagation) tersedia via API/MCP dan heatmap | Wajib     |
| PR-MEM-05 | Pasangan dengan `n < n_min` diberi label "data sedikit"; polaritas menampilkan sumber (semantik vs outcome)                                                                         | Wajib     |


### 6.6 Antarmuka (Dashboard &amp; MCP)


| ID       | Kebutuhan                                                                                                                                | Prioritas |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| PR-UI-01 | Halaman Subagents: daftar kontrak, topologi, budget tersisa, status circuit breaker, heatmap korelasi                                    | Wajib     |
| PR-UI-02 | Konsol run live menampilkan delegasi antar subagent (SSE) + trace tree + biaya per subagent                                              | Wajib     |
| PR-UI-03 | Neuron Graph 3D: node subagent, edge korelasi bertebal `w_ij` dan berwarna polaritas, pulse live, inspector drawer dengan sitasi episode | Wajib     |
| PR-UI-04 | Paritas penuh UI↔MCP: setiap aksi tersedia di keduanya; diuji otomatis (hasil sama)                                                      | Wajib     |
| PR-UI-05 | Mode "AI sedang bekerja" menampilkan aksi Admin MCP secara live + tombol jeda/batalkan                                                   | Sebaiknya |


### 6.7 Evaluasi &amp; kualitas


| ID        | Kebutuhan                                                                                             | Prioritas |
| --------- | ----------------------------------------------------------------------------------------------------- | --------- |
| PR-EVL-01 | Dataset eval per subagent (≥20 kasus) + 3 skenario lintas-tim (riset, rekayasa, insiden)              | Wajib     |
| PR-EVL-02 | Gate promote: eval regresi gagal ambang → promote tertahan; baseline biaya/latensi/kualitas tersimpan | Wajib     |
| PR-EVL-03 | LLM-as-judge memakai model berbeda dari model yang diuji                                              | Wajib     |
| PR-EVL-04 | Drift biaya ±20% dari baseline memicu alert                                                           | Sebaiknya |


## 7. Kebutuhan Non-Fungsional


| Aspek            | Target                                                                                        |
| ---------------- | --------------------------------------------------------------------------------------------- |
| Latensi delegasi | p95 overhead delegasi (packet → subagent mulai) &lt; 2 dtk                                    |
| Paralelisme      | Clio ≤ 3, Metron ≤ 3 instansi per run; lainnya singleton                                      |
| Keandalan        | Run selamat crash worker (lanjut dari checkpoint); ketersediaan API 99,5%                     |
| Audit            | 100% aksi subagent tercatat; audit log tamper-evident                                         |
| Performa graf    | 60 fps @5k node/20k edge; fallback 2D di atas itu                                             |
| Privasi          | Redaksi PII sebelum ingest; isolasi `group_id` per workspace; patuh UU PDP untuk data pribadi |
| Kompatibilitas   | LangGraph SDK kompatibel; MCP Streamable HTTP + stdio (tanpa session)                         |


## 8. Kriteria Penerimaan Rilis v1.0 (Release Gate)

- [ ] 10 subagent terdaftar dengan kontrak tervalidasi; uji skema lulus.
- [ ] Uji negatif keamanan lulus: Clio tanpa Admin MCP; Vulcan gagal self-promote; Themis tanpa nilai secret.
- [ ] Chaos test: bunuh worker saat delegasi paralel → run lanjut dari checkpoint.
- [ ] 3 skenario lintas-tim (riset, rekayasa, insiden) selesai dengan laporan biaya; budget &amp; loop guard terbukti.
- [ ] Eval gate aktif: promote tertahan bila regresi gagal.
- [ ] Heatmap korelasi + Neuron Graph menampilkan data ≥ 50 run dengan sitasi episode.
- [ ] Uji paritas UI↔MCP lulus; audit overlay menampilkan actor AI vs manusia.

## 9. Metrik Keberhasilan (KPI)


| Metrik                                            | Target v1.0                                            |
| ------------------------------------------------- | ------------------------------------------------------ |
| Waktu penyelesaian tugas riset kompleks vs manual | ≤ 30% dari waktu manual                                |
| Biaya LLM per tugas kompleks                      | ≤ $10 (Atlas budget) pada ≥ 70% run                    |
| Run sukses (tanpa budget\_exceeded/loop)          | ≥ 90%                                                  |
| Ambang korelasi bermakna                          | ≥ 8 pasangan subagent dengan n ≥ n\_min setelah 50 run |
| Insiden keamanan (grant violation yang lolos)     | 0                                                      |


## 10. Roadmap &amp; Dependensi

Mengikuti Rencana PR: Fase 0–1 platform (PR #0–#3) → Fase 2 registry (PR #4, #5, #8; Atlas v0) → Fase 3 telemetri &amp; memori (PR #9, #10) → Fase 4 MCP &amp; HITL (PR #6, #7) → Fase 5 evals (PR #14) → Fase 6 dashboard (PR #11–#13) → Fase 7 hardening + tim final (PR #15–#18). PR #16 adalah rilis integrasi tim 10 subagent.

## 11. Risiko Produk


| Risiko                                            | Dampak             | Mitigasi                                                              |
| ------------------------------------------------- | ------------------ | --------------------------------------------------------------------- |
| 10 subagent terlalu mahal untuk pemakaian pribadi | Adopsi rendah      | Effort scaling (banyak tugas hanya 1–2 subagent); budget hard stop    |
| Proposal 10 subagent tidak cocok visi pemilik     | Rework             | Konfirmasi kontrak §5.3 makalah sebelum PR #16                        |
| Kualitas hasil riset/kode belum terukur           | Kepercayaan rendah | Eval lintas-tim + judge sejak Fase 5; baseline tersimpan              |
| Korelasi menyesatkan saat data sedikit            | Keputusan salah    | Label n &lt; n\_min; dua sumber polaritas; tuning α/β/γ per workspace |


## 12. Keputusan yang Menunggu Pemilik

1. **Konfirmasi 10 subagent &amp; pembagian pod** (proposal makalah §5.3) — blokir PR #16.
2. **Nilai budget default** per subagent dan hard stop harian ($15/hari diusulkan).
3. **Use-case go-live pertama**: disarankan Clio (riset) dan Vulcan+Athena (rekayasa).
4. **Keputusan \[KONFIRMASI\] blueprint**: ADR-001 (runtime), ADR-002 (Supabase vs Postgres polos), ADR-009 (backend LLM-trace), ADR-010 (model gateway), gateway MCP tunggal (ya/tidak).
5. Apakah Atlas juga dioperasikan dari klien eksternal (Claude Code/Desktop via Admin MCP) atau hanya dari dalam platform.

## 13. Glosarium

- **Context packet**: paket terkurasi (objektif, batas, format output, grant, budget) yang dikirim supervisor ke subagent.
- **Budget turun-temurun**: anggaran subagent anak tidak boleh melebihi sisa anggaran induk.
- **L1 / L2**: lapis telemetri deterministik (real-time) / lapis knowledge graph Graphiti (bi-temporal, async).
- **Effort scaling**: aturan jumlah subagent proporsional kompleksitas tugas (1 / 2–4 / ≤10).
- **NPMI**: normalised pointwise mutual information; dasar ko-aktivasi antar subagent.
- **AgentPrincipal**: identitas non-manusia untuk AI; scope eksplisit, tidak dapat menjadi approver.��2�file:///home/biezz/Documents/Project/coding/langgraph/docs/Product%20Requirements%20Document%20%28PRD%29%20%E2%80%94%20Tim%2010%20Subagent%20LGP.md