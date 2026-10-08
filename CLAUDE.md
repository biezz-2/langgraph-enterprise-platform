# Enterprise LangGraph Platform (LGP v2.0) - Memory & Execution Rules

## Automatic Memory & Context Retention Rules

1. **Automatic Recall (Awal Percakapan / Memulai Tugas)**:
   - Sebelum mengeksekusi tugas baru, periksa konteks proyek dan preferensi pengguna dari memori jangka panjang.
   - Gunakan `mcp__langgraph-memory` (`memory_recall` / `graph_query`) atau LGP Memory API (`lgp_memory_query` via REST `http://localhost:8000/mcp/admin/call`) untuk mengambil fakta penting dari sesi terdahulu.

2. **Automatic Storage (Setiap Keputusan / Preferensi / Perubahan)**:
   - Apabila terdapat preferensi pengguna baru, aturan arsitektur baru, atau perubahan sistem signifikan:
     - Simpan fakta terstruktur (Subject-Predicate-Object) ke memori temporal (`lgp_memory_store_fact` atau `memory_store`).
     - Sertakan `episode_run_id` atau nama percakapan terkait agar fakta terhubung ke histori terkait.

3. **Matriks Keputusan Penggunaan Tools Memori**:
   - **WAJIB Menggunakan Tool Memori**:
     - Pengguna menanyakan konteks sesi terdahulu, preferensi, atau keputusan arsitektur.
     - Terjadi penambahan/perubahan fitur, skema DB, atau endpoint API baru yang harus diingat di sesi mendatang.
     - Pengguna memberikan feedback / koreksi instruksi khusus.
   - **TIDAK PERLU Tool Memori**:
     - Operasi CLI lokal sederhana (mengecek file, tes unit, membetulkan kesalahan sintaks typo minor).

4. **Bi-Temporal & Invalidation**:
   - Jika preferensi atau konfigurasi lama diganti dengan aturan baru, luncurkan pembaruan dengan menandai fakta lama sebagai usang (`invalid_at = now`) via `lgp_memory_invalidate_fact` atau `memory_forget`.
