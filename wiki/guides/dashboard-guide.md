# Panduan Penggunaan Dashboard Next.js (LGP v2.0)

Dokumen ini adalah panduan pengguna untuk Dashboard Enterprise LangGraph Platform (LGP v2.0), pusat kontrol observabilitas untuk monitoring sistem multi-agent.

## 1. Akses Dashboard
Dashboard berjalan sebagai aplikasi Next.js yang terhubung ke FastAPI backend melalui proxy `/api/*`.
- **URL Default**: `http://localhost:3000`
- **Data Source**: Terdeteksi secara otomatis sebagai `SUPABASE` (Enterprise) atau `LOCAL` (SQLite fallback).

## 2. Fitur Utama (Tab Navigasi)

### A. Overview (Sistem Health)
Menampilkan status kesehatan platform secara real-time:
- **Uptime & Version**: Versi current LGP dan status server.
- **Active Runs**: Jumlah eksekusi tugas yang sedang berjalan.
- **Resource Usage**: Metrik konsumsi token dan USD secara agregat.
- **System Logs**: Stream log terbaru dari backend.

### B. Kanban (Run Management)
Visualisasi alur kerja `runs` dan `threads` menggunakan board Kanban:
- **Kolom**: `Pending` $\rightarrow$ `Running` $\rightarrow$ `Completed` / `Failed`.
- **Interaksi**: Klik pada card untuk melihat detail `context_packet`, history subagent, dan state diffs.
- **Action**: Memungkinkan interupsi atau penghentian run secara manual.

### C. Correlation Matrix (Subagent Calibration)
Heatmap 10x10 yang memvisualisasikan ko-aktivasi antar 10 subagent:
- **Warna**: Intensitas warna menunjukkan kekuatan bobot komposit $W_{ij}$.
- **Kalibrasi**: User dapat menyesuaikan bobot $\alpha$ (NPMI), $\beta$ (Lift), dan $\gamma$ (Handoff) melalui slider untuk mengoptimalkan routing supervisor.
- **Insight**: Mengidentifikasi pasangan agen yang terlalu sering berinteraksi (redundansi) atau pasangan yang seharusnya berkolaborasi namun jarang aktif.

### D. Subagent Registry
Daftar kontrak formal seluruh subagent:
- **Detail**: Menampilkan role, pod, budget config, dan tool grants.
- **Status**: Indikator visual agen yang aktif/nonaktif.

### E. Memory & Audit Log
Pusat verifikasi integritas data:
- **Temporal Facts**: Daftar fakta memori jangka panjang dengan filter subject/predicate.
- **Audit Chain**: Tampilan list `audit_log` dengan status verifikasi hash.
- **Verifikasi**: Tombol untuk memicu `lgp_audit_verify` guna memastikan tidak ada data yang dimanipulasi.

## 3. Troubleshooting & Tips
- **Label "Source: LOCAL"**: Artinya dashboard sedang menggunakan SQLite fallback. Pastikan konfigurasi Supabase di `.env` benar.
- **Data Tidak Update**: Cek koneksi proxy di `next.config.ts` dan pastikan FastAPI server berjalan di port 8000.
- **Matrix Not Loading**: Pastikan tabel `correlation_edges` telah terisi melalui eksekusi beberapa run simulasi.
