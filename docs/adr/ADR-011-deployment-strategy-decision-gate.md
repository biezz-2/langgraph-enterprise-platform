# ADR-011: Strategi Deployment LangGraph Enterprise (Decision Gate: Strategi A vs Strategi B)

- **Status**: Diterima (Accepted)
- **Tanggal**: 2026-10-12
- **Penulis**: claude-biezz-2
- **Cakupan**: Platform Architecture, Deployment Lifecycle, Licensing & Runtime Parity

---

## 1. Konteks dan Masalah

Proyek LGP v2.0 (`~/Documents/Project/coding/langgraph`) dirancang sebagai platform orkestrasi agentic enterprise. Pada evaluasi arsitektur Oktober 2026, teridentifikasi kontradiksi struktural antara dua pendekatan deployment:
1. **Fase 2 (Rencana Awal)**: Mengembangkan API adapter kustom di atas FastAPI dengan endpoint `/threads`, `/runs`, `/stream`.
2. **Fase 5 (Rencana Awal)**: Menuntut pembuatan manifest `langgraph.json` dan deployment berbasis image Docker resmi LangGraph CLI.

Kedua pendekatan tersebut mewakili paradigma arsitektural yang berbeda secara lisensi, runtime, dan infrastruktur:
- **Strategi A (Official Agent Server)**: Menggunakan binary container resmi `langgraph-api`.
- **Strategi B (Custom FastAPI Adapter)**: Memanfaatkan engine inti `langgraph` (lisensi MIT) dibungkus FastAPI kustom.

---

## 2. Perbandingan Parameter Kunci

| Parameter | Strategi A: Official Agent Server | Strategi B: FastAPI + LangGraph MIT |
| :--- | :--- | :--- |
| **Lisensi** | `Elastic License 2.0` (Bukan Apache 2.0/MIT). Memerlukan `LANGGRAPH_CLOUD_LICENSE_KEY` & validasi LangSmith di produksi. | `MIT License` penuh. Bebas royalti dan tanpa ketergantungan lisensi eksternal. |
| **Paritas SDK** | 100% natif out-of-the-box (`langgraph-sdk`, LangGraph Studio). | Harus dibangun dan dipelihara secara manual (~15 endpoint kritis). |
| **Task Queue** | Native Postgres-backed worker dengan scaling terdistribusi. | Dibangun via Postgres Queue (`SELECT ... FOR UPDATE SKIP LOCKED`). |
| **Database Pool** | Menggunakan psycopg 3 pool internal Agent Server. | Menggunakan asyncpg (tabel kustom) + psycopg 3 (`AsyncPostgresSaver`). |
| **Batas Supabase** | Memerlukan isolasi pool agar tidak melebihi 20 koneksi client. | Alokasi pool terkontrol eksplisit: max 5 asyncpg + max 5 psycopg. |

---

## 3. Keputusan (Decision)

Mengadopsi **Hybrid Phased Approach (Strategi Bertahap)**:

1. **Fondasi Graf Bersama (Fase 1)**: Seluruh arsitektur agen (10 subagent LGP) dimigrasikan murni menggunakan `langgraph.graph.StateGraph` (v1.2+) dan checkpointer `AsyncPostgresSaver` (psycopg 3). Kode graf wajib 100% agnostik terhadap server pembungkusnya.
2. **Pengembangan Lokal / Staging (Fase 1-2)**: Memanfaatkan `langgraph dev` (port 2024) yang tersedia gratis tanpa lisensi enterprise untuk validasi visual di LangGraph Studio dan smoke test `langgraph-sdk`.
3. **Decision Gate Akhir Fase 2**:
   - Jika kredensial LangSmith Enterprise tersedia: Terbitkan manifest `langgraph.json` dan bangun image kontainer via `langgraph build` (Strategi A).
   - Jika deployment mandiri/air-gapped tanpa lisensi LangSmith: Aktifkan runtime router FastAPI `apps/api/routers/langgraph_server.py` yang kompatibel dengan kontrak `langgraph_sdk.get_client()` menggunakan task queue PostgreSQL natif (Strategi B).

---

## 4. Konsekuensi dan Mitigasi

- **Batas Koneksi Supavisor (Max 20 clients)**:
  - Driver `asyncpg` untuk tabel aplikasi dibatasi `max_size=5`.
  - Driver `psycopg 3` untuk `AsyncPostgresSaver` dibatasi `max_size=5`.
  - Fixture testing wajib memanfaatkan pooling lifecycle teardown eksplisit untuk mencegah error `EMAXCONNSESSION`.
- **Integritas Audit Log**:
  - Timestamp diformat presisi milidetik kanonik (`round(ts, 3)`) di seluruh layer penyimpanan dan verifikasi untuk mencegah desinkronisasi hash akibat truncating microsecond PostgreSQL `TIMESTAMPTZ`.
- **Idempotensi Side-Effect**:
  - Seluruh operasi mutasi database (seperti alokasi budget dan insert thread) wajib idempoten (`ON CONFLICT DO NOTHING` / upsert) guna mengantisipasi eksekusi ulang node saat HITL `interrupt()` di-resume via `Command(resume=...)`.
