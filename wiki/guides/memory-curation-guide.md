# Memory Curation Guide for Next AI Sessions

Panduan ini ditujukan bagi AI Agent berikutnya (Claude Code, Cursor, Windsurf, atau subagent Mnemosyne) agar dapat mengurutkan, menyortir, dan memelihara kebersihan memori jangka panjang secara rapi dan otomatis.

## Panduan Langkah-demi-Langkah untuk AI Next Session

### 1. Sebelum Menyimpan Memori Baru
Setiap kali Anda mendeteksi informasi penting (seperti preferensi pengguna, model yang digunakan, keputusan arsitektur, atau konteks percakapan baru):
- **Gunakan Format Prefix**: Gunakan format `Category:ItemName` untuk `subject`. Pilih dari daftar kategori berikut:
  - `Session:` untuk konteks percakapan & ID run.
  - `Subagent:` untuk spesifikasi & kontrak subagent.
  - `Model:` untuk kebijakan model AI yang digunakan.
  - `Architecture:` untuk komponen teknis platform.
  - `Security:` untuk aturan keamanan & sanitasi.
  - `Telemetry:` untuk metrik korelasi & biaya.
  - `User_Preference:` untuk preferensi pengguna & tim.

### 2. Gunakan `MemoryCuratorEngine` atau MCP Tool
- **Melalui Python API Internal**:
  ```python
  from packages.memory.curator import MemoryCuratorEngine, MemoryTaxonomy
  
  # Format subject otomatis
  subject = MemoryCuratorEngine.format_subject("User_Preference", "CodingStyle")
  ```
- **Melalui FastMCP / REST API**:
  ```json
  {
    "tool": "lgp_memory_store_fact",
    "arguments": {
      "subject": "User_Preference:CodingStyle",
      "predicate": "PREFERS_TEST_FRAMEWORK",
      "object": "Pytest Asyncio dengan ASGITransport",
      "episode_run_id": "session-123"
    }
  }
  ```

### 3. Redaksi PII Otomatis
Semua string `object` akan melewati fungsi `TemporalMemoryStore.redact_pii()`. Jangan pernah menyimpan email, nomor telepon, atau NIK secara mentah.

### 4. Menangani Fakta Usang (Invalidation)
Jika pengguna meminta perubahan preferensi (misal: mengganti mode DB dari SQLite ke PostgreSQL):
1. **Jangan Hapus**: Jangan gunakan `DELETE FROM temporal_facts`.
2. **Invalidate**: Panggil `lgp_memory_invalidate_fact` dengan `fact_id` fakta lama. `invalid_at` akan diisi timestamp saat ini.
3. **Store New Fact**: Simpan fakta baru dengan `valid_at = now`.

### 5. Memeriksa Kebersihan & Ringkasan Memori
AI berikutnya dapat menjalankan modul kurator internal untuk memeriksa status kerapihan memori:
```bash
.venv/bin/python -c "import asyncio; from packages.memory.curator import MemoryCuratorEngine; res = asyncio.run(MemoryCuratorEngine.get_organized_memory_summary()); print(res)"
```
