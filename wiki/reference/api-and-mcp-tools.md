# Reference: 17 FastMCP Admin Tools (LGP v2.0)

Dokumen ini menyediakan spesifikasi lengkap untuk ke-17 FastMCP Admin Tools yang dipublikasikan oleh `AdminMCPServer` (`apps/admin_mcp/mcp_server_cli.py` dan `apps/api/main.py`), lengkap dengan anotasi risiko standar model dan skema parameter.

---

## Ringkasan Anotasi Risiko (Risk Annotations)

Klien AI memanfaatkan 4 flag anotasi berikut untuk mengeksekusi tool secara otonom atau memunculkan prompt konfirmasi ke manusia:
- `readOnlyHint`: Apakah tool murni membaca data tanpa mengubah state sistem.
- `destructiveHint`: Apakah tool berpotensi merusak atau menghapus data permanen.
- `idempotentHint`: Apakah pemanggilan berulang dengan argumen sama menghasilkan hasil yang konsisten.
- `openWorldHint`: Apakah tool mengakses sumber daya dunia luar (web/network).

---

## 1. Manajemen Subagent & Topologi

### 1. `lgp_subagent_list`
- **Deskripsi**: Menampilkan daftar seluruh subagent terdaftar (10 subagents) beserta pod, kontrak, dan status aktifnya.
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `pod` (*string, opsional*): Filter berdasarkan nama Pod (`Koordinasi`, `Riset & Rekayasa`, `Platform`, `Tata Kelola`).

### 2. `lgp_subagent_get`
- **Deskripsi**: Mengambil kontrak lengkap suatu subagent berdasarkan ID (misal: `atlas`, `clio`, `vulcan`).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `subagent_id` (*string, wajib*): ID subagent yang dicari.

### 3. `lgp_subagent_update_config`
- **Deskripsi**: Memperbarui konfigurasi budget, trust level, atau status aktif subagent di registry.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `subagent_id` (*string, wajib*): ID subagent yang diperbarui.
  - `max_usd` (*number, opsional*): Batas anggaran USD baru.
  - `max_tokens` (*integer, opsional*): Batas token baru.
  - `trust_level` (*string enum: "low", "medium", "high", opsional*): Tingkat kepercayaan baru.
  - `is_active` (*boolean, opsional*): Status aktif/non-aktif subagent.

### 4. `lgp_subagent_topology`
- **Deskripsi**: Mendapatkan struktur topologi 4 Pod LGP v2.0 dan alur delegasi/handoff antar-subagent (DAG supervisor dan critic loop `CRITICIZES`).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**: Tidak ada.

### 5. `lgp_circuit_breaker_reset`
- **Deskripsi**: Mereset status Circuit Breaker untuk subagent yang dinonaktifkan akibat 3 kegagalan beruntun.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `subagent_id` (*string, wajib*): ID subagent yang ingin di-reset.

---

## 2. Manajemen Eksekusi Run & Human-in-the-Loop (HITL)

### 6. `lgp_run_create`
- **Deskripsi**: Memicu eksekusi task baru melalui supervisor Atlas dengan alokasi budget dan context packet.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: false`, `openWorldHint: false`
- **Parameter**:
  - `objective` (*string, wajib*): Tujuan utama atau instruksi yang ditugaskan ke Atlas.
  - `subagents` (*array of string, opsional*): Daftar subagent yang diizinkan berpartisipasi.

### 7. `lgp_run_get_state`
- **Deskripsi**: Mendapatkan status eksekusi run, output delegates, riwayat checkpoint, dan ringkasan anggaran.
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `run_id` (*string, wajib*): ID eksekusi run.

### 8. `lgp_run_list`
- **Deskripsi**: Menampilkan daftar riwayat run yang telah dieksekusi di platform.
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `limit` (*integer, opsional, default: 20*): Jumlah entri maksimal.
  - `status` (*string, opsional*): Filter status (`pending`, `running`, `completed`, `failed`).

### 9. `lgp_run_resume_hitl`
- **Deskripsi**: Melanjutkan eksekusi yang diinterupsi oleh gerbang HITL (Human-in-the-Loop). Memeriksa aturan anti-self-approval di database.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `interrupt_id` (*string, wajib*): ID interupsi di antrean HITL.
  - `approver` (*string, wajib*): Identitas reviewer manusia atau agen supervisor (bukan subagent pemohon).
  - `decision` (*string enum: "approved", "rejected", wajib*): Keputusan persetujuan.

---

## 3. Memori Jangka Panjang Bi-Temporal (Graphiti L2)

### 10. `lgp_memory_query`
- **Deskripsi**: Kueri fakta temporal bi-temporal ($T_v$ valid time, $T_k$ record time).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `subject` (*string, opsional*): Filter awalan subject (misal: `Architecture:`, `User_Preference:`).
  - `as_of_valid_time` (*number timestamp, opsional*): Rekonstruksi fakta masa lalu berdasarkan waktu dunia nyata ($T_v$).
  - `as_of_record_time` (*number timestamp, opsional*): Rekonstruksi fakta berdasarkan waktu pencatatan sistem ($T_k$).

### 11. `lgp_memory_store_fact`
- **Deskripsi**: Menyimpan fakta terstruktur `(subject, predicate, object)` dengan redaksi otomatis terhadap data sensitif/PII.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: false`, `openWorldHint: false`
- **Parameter**:
  - `subject` (*string, wajib*): Format `Category:ItemName`.
  - `predicate` (*string, wajib*): Relasi semantik.
  - `object` (*string, wajib*): Nilai fakta yang disimpan.
  - `valid_at` (*number timestamp, opsional*): Waktu mulai berlaku.
  - `invalid_at` (*number timestamp, opsional*): Waktu kedaluwarsa fakta.
  - `episode_run_id` (*string, opsional*): ID run atau thread percakapan terkait.

### 12. `lgp_memory_invalidate_fact`
- **Deskripsi**: Menonaktifkan fakta lama dengan menetapkan `invalid_at = now` tanpa menghapus data secara fisik dari basis data.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `fact_id` (*string, wajib*): ID fakta yang ingin dinonaktifkan.

---

## 4. Telemetri & Analisis Matriks Korelasi 10x10

### 13. `lgp_correlation_matrix`
- **Deskripsi**: Menghasilkan matriks korelasi 10x10 antar seluruh pasangan subagent LGP v2.0 (NPMI, handoff rate, success lift, composite weight $W_{ij}$, dan polaritas interaksi).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**: Tidak ada.

### 14. `lgp_correlation_setup`
- **Deskripsi**: Mengatur bobot formula gabungan ($\alpha \cdot \text{NPMI} + \beta \cdot \text{Lift} + \gamma \cdot \text{Handoff}$) dan ambang batas sampel minimum $N_{min}$.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `alpha` (*number, opsional, default: 0.4*): Bobot NPMI co-activation.
  - `beta` (*number, opsional, default: 0.4*): Bobot success lift.
  - `gamma` (*number, opsional, default: 0.2*): Bobot handoff rate.
  - `n_min` (*integer, opsional, default: 50*): Ambang batas sampel data sedikit.

### 15. `lgp_telemetry_events_query`
- **Deskripsi**: Membaca raw telemetri events L1 per run atau subagent (token, cost, latency, payload event).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `run_id` (*string, opsional*): Filter ID run.
  - `subagent_id` (*string, opsional*): Filter ID subagent.
  - `limit` (*integer, opsional, default: 50*): Jumlah maksimal baris event.

---

## 5. Audit Log Kriptografis (SHA-256 Hash Chain)

### 16. `lgp_audit_query`
- **Deskripsi**: Memeriksa catatan audit log append-only dengan relasi hash berantai SHA-256 (`prev_hash`, `curr_hash`, `args_hash`).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**:
  - `limit` (*integer, opsional, default: 50*): Jumlah baris log maksimal.

### 17. `lgp_audit_verify`
- **Deskripsi**: Memverifikasi integritas kriptografis seluruh rantai hash audit log dari awal hingga akhir untuk mendeteksi indikasi modifikasi liar (tampering).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**: Tidak ada.
- **Output**:
  ```json
  {
    "is_valid": true,
    "total_entries": 142,
    "violations": []
  }
  ```

---

## 6. Tools Ekstensi Platform & Graphiti (Extensions)

Selain 17 tools inti di atas, platform menyediakan 6 tools utilitas pendukung:

### 18. `lgp_platform_health`
- **Deskripsi**: Mendapatkan status kesehatan platform, jumlah subagent aktif, mode storage, dan status supervisor.
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`

### 19. `lgp_hitl_inbox_list`
- **Deskripsi**: Melihat daftar interupsi Human-in-the-Loop (HITL) yang sedang pending atau telah selesai.
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`
- **Parameter**: `status` (*string enum: "pending", "approved", "rejected", "all", default: "pending"*).

### 20. `lgp_memory_organized_summary`
- **Deskripsi**: Mendapatkan ringkasan memori yang telah dikurasi dan disortir berdasarkan taksonomi kategori (`Session`, `Subagent`, `Model`, `Architecture`, `Security`, `User_Preference`, dll).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`

### 21. `lgp_graphiti_neuron_graph`
- **Deskripsi**: Mendapatkan graf neuron MiroFish Graphiti lengkap (node entitas fakta bi-temporal, relasi edge, dan bobot visual).
- **Anotasi**: `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`

### 22. `lgp_memory_seed`
- **Deskripsi**: Memicu proses seeding fakta pengetahuan sistem secara otomatis ke dalam memori bi-temporal.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: false`

### 23. `lgp_api_request`
- **Deskripsi**: Universal API Request: Mengeksekusi endpoint REST API LangGraph internal (GET, POST, PUT, DELETE) seperti `/api/health`, `/api/runs`, `/api/subagents`.
- **Anotasi**: `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: false`, `openWorldHint: true`
- **Parameter**: `method` (*string*), `endpoint` (*string*), `params` (*object, opsional*), `body` (*object, opsional*).
