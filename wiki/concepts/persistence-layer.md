# Persistence Layer: Hybrid SQLite & Supabase (LGP v2.0)

Dokumen ini merinci arsitektur lapisan persistensi Enterprise LangGraph Platform (LGP v2.0) yang mengimplementasikan strategi **"Supabase-First with SQLite Fallback"**.

## 1. Arsitektur Dual-Mode
LGP v2.0 dirancang untuk bekerja di berbagai lingkungan (lokal, staging, produksi) tanpa mengubah logika bisnis di lapisan aplikasi. Hal ini dicapai melalui abstraksi database yang menormalisasi interaksi antara PostgreSQL (via Supabase) dan SQLite.

### Diagram Alur Koneksi
`App Logic` $\rightarrow$ `DBManager` $\rightarrow$ `PostgresConnectionWrapper` $\rightarrow$ `[Supabase (Prod) | SQLite (Local)]`

## 2. Mekanisme Normalisasi Kueri
Perbedaan utama antara SQLite dan PostgreSQL terletak pada penanda parameter (placeholder). LGP v2.0 mengatasi hal ini dengan `PostgresConnectionWrapper`:

- **SQLite**: Menggunakan `?` sebagai placeholder.
- **PostgreSQL**: Menggunakan `$1, $2, ...` sebagai placeholder.

Wrapper ini mendeteksi engine yang aktif dan secara otomatis mengonversi kueri SQL agar kompatibel dengan driver yang digunakan (`psycopg2`/`asyncpg` untuk Postgres, `sqlite3` untuk SQLite).

## 3. Implementasi Supabase (Enterprise Mode)
Saat berjalan dalam mode Enterprise, sistem menggunakan infrastruktur Supabase dengan spesifikasi berikut:

### Isolasi Skema
Data LGP tidak disimpan di skema `public`, melainkan di skema terisolasi bernama `langgraph`.
- **Alasan**: Mencegah kolisi dengan tabel sistem Supabase atau aplikasi lain dalam satu instance database.
- **Konfigurasi**: Membutuhkan penambahan `langgraph` ke dalam `db-schemas` pada konfigurasi PostgREST/Kong.

### Optimasi Tipe Data
| SQLite Type | PostgreSQL Type | Alasan |
| :--- | :--- | :--- |
| `TEXT` (JSON string) | `JSONB` | Memungkinkan kueri indeks pada payload metadata. |
| `REAL` (Unix Epoch) | `TIMESTAMPTZ` | Akurasi zona waktu untuk memori bi-temporal. |
| `INTEGER` (0/1) | `BOOLEAN` | Standarisasi tipe logika. |

### Row Level Security (RLS)
Sistem menerapkan kebijakan akses berbasis role:
- **`service_role`**: Digunakan oleh FastAPI backend. Memiliki akses penuh untuk menulis dan membaca seluruh data.
- **`anon`**: Digunakan oleh Next.js Dashboard. Dibatasi hanya untuk operasi `SELECT` pada tabel observabilitas (telemetri, registri).

## 4. Strategi Fallback
Jika `SUPABASE_URL` atau `SUPABASE_KEY` tidak terdeteksi, atau jika terjadi kegagalan koneksi kritis saat inisiasi, `DBManager` akan:
1. Mencoba melakukan koneksi ulang (retry) sebanyak 3 kali.
2. Mengalihkan operasi ke `data/lgp.db` (SQLite).
3. Memberikan peringatan `[Source: LOCAL]` pada dashboard untuk menandakan mode fallback aktif.
