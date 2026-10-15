# Guardrails & Keamanan (LGP v2.0)

Dokumen ini menjelaskan arsitektur guardrails pertahanan berlapis, pembatasan anggaran hirarkis, detektor loop status tak hingga, dan aturan sanitasi keamanan pada Enterprise LangGraph Platform (LGP v2.0).

---

## 1. Arsitektur Pertahanan Berlapis (Defense-in-Depth)

Sistem LGP v2.0 mengimplementasikan modul keamanan deterministik pada `packages/guardrails/guards.py` sebelum pemanggilan model maupun eksekusi tool diizinkan berjalan.

```
Incoming Request / Task
        │
        ▼
[SecurityToolGuard: Sanitasi Input & Anti-Prompt Injection]
        │
        ▼
[InheritedBudgetManager: Validasi Anggaran Hirarkis & Daily Hard Stop]
        │
        ▼
[CircuitBreaker: Pengecekan Kegagalan Beruntun Subagent]
        │
        ▼
[LoopDetector: Deteksi Hash Status Kanonikal 10-Langkah]
        │
        ▼
[Access Control & Privilege Enforcement: Clio / Vulcan / Themis]
        │
        ▼
Eksekusi Subagent & Tool
```

---

## 2. Hirarki Anggaran (Inherited Budget Hierarchy)

Untuk mencegah pembengkakan biaya (runaway cost) saat delegasi bertingkat antar-subagent, platform memberlakukan hierarki anggaran yang diturunkan:

1. **Daily Workspace Hard Stop**:
   - Batas maksimum harian workspace: **$15.00 USD** (`DAILY_HARD_STOP_USD = 15.0`).
   - Jika akumulasi biaya harian ditambah permintaan baru melebihi $15.00, seluruh eksekusi langsung dihentikan dengan pesan `Daily hard stop reached`.

2. **Inherited Child Envelope**:
   - Supervisor (Atlas) memegang alokasi anggaran induk (`BudgetEnvelope`).
   - Saat mendelegasikan tugas ke subagent anak, budget anak divalidasi dengan formula:
     $$\text{tokens}_{\text{child}} \le \text{remaining\_tokens}_{\text{parent}}$$
     $$\text{usd}_{\text{child}} \le \text{remaining\_usd}_{\text{parent}}$$
   - Subagent anak **tidak pernah bisa** meminta token atau biaya yang melampaui sisa jatah induknya.

3. **Budget Specifications per Subagent**:
   | Subagent | Max Tokens | Max USD | Max Wall Clock | Constraint Khusus |
   | :--- | :--- | :--- | :--- | :--- |
   | `atlas` | 1,500,000 | $10.00 | 2700s | Max depth: 2, Max steps: 60 |
   | `clio` | 300,000 | $1.50 | 900s | Parallel max: 3 |
   | `vulcan` | 400,000 | $2.50 | 1800s | Max iterations: 5 |
   | `athena` | 200,000 | $1.00 | 900s | Max rounds: 3 |
   | `hermes` | 1,500,000 | $0.75 | 600s | Deterministic ops |
   | `mnemosyne` | 250,000 | $1.25 | 1200s | Graphiti L2 & Temporal facts |
   | `janus` | 150,000 | $0.75 | 900s | MCP registry only |
   | `themis` | 150,000 | $0.75 | 900s | Hash chain auditor |
   | `metron` | 200,000 | $1.00 | 1200s | Parallel max: 3 |
   | `iris` | 300,000 | $1.50 | 1500s | PRD / ADR generation |

---

## 3. Circuit Breaker

Mencegah cascade failure ketika subagent atau LLM upstream mengalami crash berulang:

- **Ambang Batas (Threshold)**: 3 kegagalan berurutan (`MAX_CONSECUTIVE_FAILURES = 3`).
- **Mekanisme**:
  - Setiap kegagalan menambah counter kegagalan subagent.
  - Saat mencapai 3 kegagalan, sirkuit **terbuka** (`open_circuits[subagent_id] = True`).
  - Subagent tersebut diblokir dari antrean eksekusi berikutnya.
- **Pemulihan / Reset**:
  - Keberhasilan eksekusi mereset counter kembali ke `0`.
  - Operator AI atau manusia dapat membuka kembali sirkuit menggunakan FastMCP tool `lgp_circuit_breaker_reset`.

---

## 4. Detektor Loop Tak Hingga (Loop Detector)

Mencegah agen terjebak dalam siklus pemanggilan tool berulang dengan argumen yang sama tanpa menghasilkan progres:

1. **Kanonikal Hash SHA-256**:
   Setiap langkah dievaluasi dengan payload kanonikal terurut:
   $$\text{Hash} = \text{SHA256}(\text{subagent\_id} : \text{tool\_name} : \text{canonical\_args} : \text{canonical\_state})$$
2. **Jendela Geser (Sliding Window)**:
   - Menyimpan histori hingga 10 langkah terakhir (`WINDOW_SIZE = 10`).
3. **Pemicu Interupsi**:
   - Jika kombinasi hash yang identik muncul $\ge 3$ kali dalam jendela 10 langkah (`THRESHOLD = 3`), sistem mendeteksi loop tak hingga dan membatalkan atau menginterupsi eksekusi run.

---

## 5. SecurityToolGuard & Aturan Hak Istimewa Minimum (Least Privilege)

Pemberlakuan aturan keamanan ketat berdasarkan profil risiko subagent:

### A. Sanitasi Input & Anti-Prompt Injection (PR-SEC-01)
Semua input teks diperiksa terhadap pola injeksi berbahaya:
- `ignore previous instructions`
- `system prompt override`
- `delete from `
- `drop table `
- `rm -rf /`
- `cat /etc/shadow`
- `export AWS_SECRET_ACCESS_KEY`

Jika pola ditemukan, eksekusi ditolak seketika sebelum diteruskan ke model.

### B. Isolasi Clio dari Admin MCP (PR-SEC-02)
- Subagent `clio` bertugas melakukan riset web terbuka (untrusted external data).
- **Aturan**: Clio dilarang keras memanggil tool berawalan `admin:*` atau FastMCP tools yang memiliki otoritas konfigurasi sistem.

### C. Larangan Self-Promote Vulcan ke Prod (PR-SEC-03)
- Subagent `vulcan` bertugas menulis kode graf dan modifikasi pipeline.
- **Aturan**: Vulcan dilarang memanggil tool promosi ke produksi (`graphs:promote_prod`) secara mandiri. Perubahan produksi wajib melalui review Athena dan gerbang persetujuan manusia (**HITL**).

### D. Hygiene Rahasia Themis (PR-SEC-04)
- Subagent `themis` bertugas mengaudit kepatuhan dan keamanan.
- **Aturan**: Themis **hanya boleh menerima referensi token** berformat `secret://<resource_id>`, bukan nilai rahasia plaintext.
- Jika terdapat parameter mentah (`secret_val` atau password), eksekusi ditolak untuk mencegah kebocoran kredensial ke context window model.

### E. Redaksi Otomatis Informasi Rahasia (Secrets Redaction)
Nilai API key (misal berawalan `sk-`), parameter bertuliskan `secret`, `password`, atau `token` pada struktur kamus maupun daftar data otomatis disensor menjadi `[REDACTED_SECRET]`.

---

## 6. Gerbang Persetujuan Manusia (HITL - Human-in-the-Loop)

- **Tabel Persistence**: `hitl_inbox`.
- **Status Siklus Hidup**: `pending` $\rightarrow$ `approved` / `rejected` / `timed_out` / `cancelled`.
- **Anti-Self-Approval Constraint**:
  Terdapat validasi level database:
  ```sql
  CONSTRAINT ck_hitl_no_self_approval CHECK (approver IS NULL OR approver != subagent_id)
  ```
  Subagent tidak pernah diizinkan menyetujui interupsi yang dipicunya sendiri.
- **Resume Execution**: Dilakukan melalui FastMCP tool `lgp_run_resume_hitl(interrupt_id, approver, decision)`.
