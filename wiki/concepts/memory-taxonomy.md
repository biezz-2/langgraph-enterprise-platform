# Memory Taxonomy & Labeling Standards (LGP v2.0)

Dokumen ini menjelaskan konvensi penamaan, kategorisasi, dan penyusunan memori jangka panjang untuk memastikan semua agent, IDE (Claude Code, Cursor, Windsurf), dan anggota tim dapat membaca serta mengelola memori dengan rapi.

## Format Standar Subject

Setiap memori disimpan sebagai tuple tuple `(subject, predicate, object)` di mana `subject` harus menggunakan prefix kategori:

```
Category:ItemName
```

### Kategori Resmi:

1. **`Session`**: Informasi percakapan, ID sesi, prompt pengguna, dan riwayat interaksi.
   - Contoh Subject: `Session:ClaudeCode`, `Session:run-2026-10-09`
   - Predicate Contoh: `IDENTIFIER`, `PROMPT_OBJECTIVE`, `STATUS`

2. **`Subagent`**: Spesifikasi 10 subagent LGP v2.0, kontrak, dan tugasnya.
   - Contoh Subject: `Subagent:atlas`, `Subagent:clio`, `Subagent:mnemosyne`
   - Predicate Contoh: `BELONGS_TO_POD`, `HAS_ROLE`, `HAS_BUDGET_CONFIG`

3. **`Model`**: Kebijakan dan jenis model AI yang dipetakan ke subagent tertentu.
   - Contoh Subject: `Model:atlas`, `Model:vulcan`
   - Predicate Contoh: `USES_MODEL_POLICY`, `TRUST_LEVEL`

4. **`Architecture`**: Komponen dasar platform LGP v2.0.
   - Contoh Subject: `Architecture:Database`, `Architecture:FastMCP`, `Architecture:Daemon`
   - Predicate Contoh: `USES_PATTERN`, `EXPOSES_TOOLS`, `MANAGED_BY`

5. **`Security`**: Aturan keamanan, batasan hak akses (least privilege), dan sanitasi.
   - Contoh Subject: `Security:Clio`, `Security:Vulcan`, `Security:PII`
   - Predicate Contoh: `RESTRICTS_ACCESS`, `AUTO_REDACTS`, `ENFORCES_HARD_STOP`

6. **`Telemetry`**: Metrik performa, matriks korelasi 10x10, dan penggunaan anggaran.
   - Contoh Subject: `Telemetry:Correlation`, `Telemetry:WorkspaceBudget`
   - Predicate Contoh: `CALCULATES_CORRELATION`, `SPENT_TODAY`

7. **`User_Preference`**: Preferensi pengguna dan instruksi khusus.
   - Contoh Subject: `User_Preference:CodingStyle`, `User_Preference:Language`
   - Predicate Contoh: `PREFERS_STYLE`, `LANG_INDONESIAN`

## Penyaringan Bi-Temporal ($T_v$ & $T_k$)

- **$T_v$ (Valid Time)**: `valid_at` & `invalid_at` menunjukkan rentang waktu fakta berlaku di dunia nyata.
- **$T_k$ (Record Time)**: `created_at` & `expired_at` menunjukkan pencatatan sistem.

Saat fakta diperbarui, fakta lama **TIDAK DIHAPUS**, melainkan di-set `invalid_at = timestamp_sekarang`.
