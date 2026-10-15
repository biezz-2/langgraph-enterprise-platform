# Database Schema & Hash Integrity (LGP v2.0)

Dokumen ini menjelaskan struktur skema basis data, konfigurasi mode WAL, serta spesifikasi integritas kriptografis audit log pada Enterprise LangGraph Platform (LGP v2.0).

---

# Database Schema & Hash Integrity (LGP v2.0)

Dokumen ini menjelaskan struktur skema basis data, konfigurasi mode WAL, serta spesifikasi integritas kriptografis audit log pada Enterprise LangGraph Platform (LGP v2.0).

---

## 1. Engine & Konfigurasi Persistensi Hybrid

LGP v2.0 mengimplementasikan **Hybrid Persistence Layer** yang memungkinkan transisi mulus antara lingkungan lokal dan produksi enterprise tanpa perubahan logika aplikasi:

- **Primary (Enterprise)**: Supabase (PostgreSQL 16+) dengan skema terisolasi `langgraph`. Menggunakan `asyncpg` untuk performa tinggi dan fitur PostgreSQL native seperti `JSONB` dan `TIMESTAMPTZ`.
- **Fallback (Local/Dev)**: SQLite 3 dengan WAL (Write-Ahead Logging) mode. Digunakan secara otomatis jika konfigurasi Supabase tidak valid atau koneksi gagal.
- **Compatibility Layer**: Menggunakan `PostgresConnectionWrapper` untuk menormalisasi sintaks kueri antara PostgreSQL (`$1, $2`) dan SQLite (`?`).

### Konfigurasi Supabase (Enterprise)
- **Skema**: Terisolasi dalam namespace `langgraph` untuk mencegah kolisi data.
- **RLS (Row Level Security)**: 
  - `service_role`: Akses penuh (bypass RLS) untuk internal system.
  - `anon`: Akses read-only untuk dashboard publik/terbatas.
- **Tipe Data**: Mengoptimalkan `JSONB` untuk payload metadata dan `TIMESTAMPTZ` untuk akurasi bi-temporal.

### Konfigurasi SQLite (Dev Default)
- **File Path**: `data/lgp.db` (kustomisasi via `LGP_DB_PATH`).
- **Pragma Settings**:
  ```sql
  PRAGMA journal_mode = WAL;
  PRAGMA synchronous = NORMAL;
  PRAGMA foreign_keys = ON;
  PRAGMA busy_timeout = 5000;
  ```

---

## 2. Struktur Tabel Utama
(Tetap sesuai spesifikasi sebelumnya, namun tipe data `JSON` kini dipetakan ke `JSONB` pada PostgreSQL)


---

## 2. Struktur Tabel Utama

### 1. `subagent_registry`
Menyimpan kontrak formal, batas anggaran, tool grants, dan tingkat kepercayaan 10 subagent.

| Kolom | Tipe | Deskripsi |
| :--- | :--- | :--- |
| `id` | `VARCHAR(64)` / `TEXT` (PK) | Identifier subagent (misal: `atlas`, `clio`, `vulcan`) |
| `role` | `VARCHAR(64)` / `TEXT` | Peran fungsional (misal: `orchestrator-supervisor`) |
| `name` | `VARCHAR(128)` / `TEXT` | Nama tampilan subagent |
| `pod` | `VARCHAR(64)` / `TEXT` | Pod pemilik (`Koordinasi`, `Riset & Rekayasa`, `Platform`, `Tata Kelola`) |
| `capabilities` | `JSON` / `TEXT` | Daftar kapabilitas yang didukung |
| `input_schema` | `JSON` / `TEXT` | Skema validasi input (JSON Schema) |
| `output_schema`| `JSON` / `TEXT` | Skema validasi output (JSON Schema) |
| `tool_grants`  | `JSON` / `TEXT` | Daftar tool yang diizinkan untuk subagent |
| `model_policy` | `JSON` / `TEXT` | Kebijakan model (misal: `frontier-extended-thinking`) |
| `budget_config`| `JSON` / `TEXT` | Alokasi anggaran (max tokens, max USD, timeout) |
| `memory_scope` | `VARCHAR(128)` | Lingkup akses memori |
| `trust_level`  | `VARCHAR(16)`  | Tingkat kepercayaan: `'low'`, `'medium'`, `'high'` |
| `is_active`    | `BOOLEAN` / `INT` | Status aktif subagent (1 = aktif, 0 = nonaktif) |
| `version`      | `VARCHAR(16)`  | Versi kontrak |

---

### 2. `threads`
Menyimpan sesi percakapan atau alur kerja multi-turn.

| Kolom | Tipe | Deskripsi |
| :--- | :--- | :--- |
| `thread_id` | `VARCHAR(64)` (PK) | ID unik thread |
| `title` | `TEXT` | Judul thread atau deskripsi singkat |
| `metadata` | `JSON` / `TEXT` | Konteks tambahan (user ID, workspace ID) |
| `created_at` | `TIMESTAMP` / `REAL` | Waktu pembuatan thread |
| `updated_at` | `TIMESTAMP` / `REAL` | Waktu modifikasi terakhir |

---

### 3. `runs`
Menyimpan siklus eksekusi tugas yang dipimpin oleh Supervisor (Atlas).

| Kolom | Tipe | Deskripsi |
| :--- | :--- | :--- |
| `run_id` | `VARCHAR(64)` (PK) | ID unik eksekusi tugas |
| `thread_id` | `VARCHAR(64)` (FK) | Relasi ke tabel `threads` |
| `status` | `VARCHAR(32)` | `'pending'`, `'running'`, `'interrupted'`, `'completed'`, `'failed'`, `'cancelled'` |
| `objective` | `TEXT` | Tujuan utama yang ditugaskan pengguna |
| `current_subagent` | `VARCHAR(64)` (FK) | Subagent yang sedang memegang giliran eksekusi |
| `context_packet` | `JSON` / `TEXT` | Paket konteks yang dibagikan antar-subagent |
| `budget_allocated` | `JSON` / `TEXT` | Anggaran total yang dialokasikan |
| `budget_spent` | `JSON` / `TEXT` | Realisasi token dan USD yang telah digunakan |
| `consecutive_failures` | `INTEGER` | Counter kegagalan untuk Circuit Breaker |
| `circuit_open` | `INTEGER` | Flag status sirkuit (0 = tertutup, 1 = terbuka) |
| `created_at` | `TIMESTAMP` / `REAL` | Waktu inisiasi run |
| `updated_at` | `TIMESTAMP` / `REAL` | Waktu pembaruan run |

---

### 4. `checkpoints` & `state_diffs`
Menyimpan riwayat state LangGraph untuk time-travel, inspeksi step, dan recovery.

- **`checkpoints`**:
  - `checkpoint_id` (PK), `run_id` (FK), `step` (INT), `state_hash` (SHA-256), `state_data` (JSON), `created_at`.
- **`state_diffs`**:
  - `diff_id` (PK), `checkpoint_id` (FK), `run_id` (FK), `node_name`, `diff_data` (JSON mutasi delta), `timestamp`.

---

### 5. `telemetry_events` (Telemetry L1)
Mencatat telemetri observabilitas tingkat granular per node dan per subagent.

| Kolom | Tipe | Deskripsi |
| :--- | :--- | :--- |
| `event_id` | `VARCHAR(64)` (PK) | ID unik event telemetri |
| `run_id` | `VARCHAR(64)` (FK) | Relasi ke `runs` |
| `subagent_id` | `VARCHAR(64)` (FK) | Subagent penghasil event |
| `event_type` | `VARCHAR(32)` | `'node.start'`, `'node.end'`, `'tool.call'`, `'delegate'`, `'state.read'`, `'state.write'`, `'interrupt'`, `'error'` |
| `payload` | `JSON` / `TEXT` | Rincian argumen atau respons |
| `tokens_in` / `tokens_out` | `INTEGER` | Jumlah token masukan dan luaran |
| `cost_usd` | `NUMERIC` / `REAL` | Estimasi biaya dalam USD |
| `latency_ms` | `REAL` | Waktu eksekusi dalam milidetik |
| `timestamp` | `TIMESTAMP` / `REAL` | Waktu pencatatan |

---

### 6. `correlation_edges` & `correlation_settings` (Telemetry L2: Matriks 10x10)
Menyimpan matriks korelasi interaksi antar-subagent (10 subagents $\times$ 10 subagents).

- **`correlation_edges`**:
  - `source_subagent` (PK), `target_subagent` (PK), `workspace_id` (PK)
  - `handoff_rate`: Rasio perpindahan tugas langsung dari source ke target.
  - `npmi_coactivation`: Normalized Pointwise Mutual Information co-aktivasi.
  - `success_lift`: Peningkatan probabilitas sukses run saat pasangan agen aktif bersama.
  - `latency_coupling`: Derajat keterkaitan latensi antar kedua agen.
  - `composite_weight`: Bobot komposit gabungan $W_{ij} = \alpha \cdot \text{NPMI} + \beta \cdot \text{Lift} + \gamma \cdot \text{Handoff}$.
  - `polarity`: `'positive'`, `'negative'`, atau `'neutral'`.
  - `sample_count`: Jumlah observasi.
- **`correlation_settings`**:
  - `alpha` (default 0.4), `beta` (default 0.4), `gamma` (default 0.2), `n_min` (default 50).

---

### 7. `temporal_memory_facts` (atau `temporal_facts`)
Penyimpanan fakta memori jangka panjang bi-temporal ($T_v$ dan $T_k$).

| Kolom | Tipe | Deskripsi |
| :--- | :--- | :--- |
| `fact_id` | `VARCHAR(64)` (PK) | ID unik fakta memori |
| `subject` | `VARCHAR(128)` | Subject dengan format `Category:ItemName` |
| `predicate` | `VARCHAR(64)` | Relasi (misal: `USES_MODEL_POLICY`, `RESTRICTS_ACCESS`) |
| `object` | `TEXT` | Nilai fakta (sudah melalui redaksi PII) |
| `valid_at` | `TIMESTAMP` / `REAL` | $T_v$ Awal fakta berlaku di dunia nyata |
| `invalid_at` | `TIMESTAMP` / `REAL` | $T_v$ Waktu fakta menjadi usang (NULL jika masih berlaku) |
| `created_at` | `TIMESTAMP` / `REAL` | $T_k$ Waktu fakta disimpan ke basis data |
| `expired_at` | `TIMESTAMP` / `REAL` | $T_k$ Waktu retensi sistem berakhir |
| `episode_run_id` | `VARCHAR(64)` | ID run atau sesi yang menghasilkan fakta ini |
| `pii_redacted` | `BOOLEAN` / `INT` | Flag konfirmasi redaksi PII telah dilakukan |

---

### 8. `hitl_inbox`
Antrean gerbang persetujuan manusia (Human-in-the-Loop).

| Kolom | Tipe | Deskripsi |
| :--- | :--- | :--- |
| `interrupt_id` | `VARCHAR(64)` (PK) | ID unik interupsi |
| `run_id` | `VARCHAR(64)` (FK) | Relasi ke run yang tertunda |
| `subagent_id` | `VARCHAR(64)` (FK) | Subagent yang memicu interupsi |
| `reason` | `VARCHAR(64)` | Alasan (misal: `dangerous_tool_call`, `budget_threshold`) |
| `state_diff` | `JSON` / `TEXT` | Snapshot mutasi state yang membutuhkan persetujuan |
| `status` | `VARCHAR(32)` | `'pending'`, `'approved'`, `'rejected'`, `'timed_out'`, `'cancelled'` |
| `approver` | `VARCHAR(64)` | Identitas pihak yang menyetujui/menolak |
| `decision` | `TEXT` / `JSON` | Catatan keputusan persetujuan |
| `created_at` / `resolved_at` | `TIMESTAMP` / `REAL` | Waktu interupsi dibuat dan diselesaikan |

**Integritas Anti-Self-Approval**:
```sql
CONSTRAINT ck_hitl_no_self_approval CHECK (approver IS NULL OR approver != subagent_id)
```

---

## 3. Spesifikasi Rantai Hash SHA-256 Audit Log (`audit_log`)

Tabel `audit_log` bersifat **append-only** dan dilindungi oleh rantai hash kriptografis yang menjamin setiap manipulasi atau perubahan data lampau dapat dideteksi seketika.

### Skema Tabel `audit_log`
```sql
CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    scope TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    curr_hash TEXT NOT NULL,
    result_status TEXT NOT NULL,
    created_at REAL NOT NULL
);
```

### Algoritma Hash Chaining
1. **Hashing Argumen**:
   $$\text{args\_hash} = \text{SHA256}(\text{canonical\_args\_json})$$
2. **Genesis Hash**:
   Pada baris log pertama, nilai `prev_hash` adalah 64 karakter nol:
   $$\text{prev\_hash}_0 = \text{"0000000000000000000000000000000000000000000000000000000000000000"}$$
3. **Current Hash**:
   $$\text{payload} = \text{prev\_hash} : \text{log\_id} : \text{actor} : \text{action} : \text{scope} : \text{args\_hash} : \text{result\_status} : \text{timestamp}$$
   $$\text{curr\_hash} = \text{SHA256}(\text{payload})$$
4. **Chaining**:
   Setiap entri berikutnya mengambil `curr_hash` entri sebelumnya sebagai `prev_hash`-nya.

### Algoritma Verifikasi Integritas (`lgp_audit_verify`)
Tool FastMCP `lgp_audit_verify` memeriksa dua kondisi secara berurutan:
1. **Kontinuitas Rantai**: Setiap baris harus memiliki `prev_hash` yang persis sama dengan `curr_hash` baris sebelumnya.
2. **Kesesuaian Konten**: Menghitung ulang SHA-256 payload dari data aktual di baris tersebut dan membandingkannya dengan `curr_hash` yang tersimpan. Jika terdapat perbedaan 1 bit saja, verifikasi menghasilkan `is_valid: false` dengan rincian pelanggaran (tampered content).
