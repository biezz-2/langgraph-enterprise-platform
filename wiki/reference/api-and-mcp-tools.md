# Reference: 17 FastMCP Admin Tools (LGP v2.0)

Berikut adalah daftar 17 FastMCP Admin Tools yang dipublikasikan oleh `AdminMCPServer` (`apps/admin_mcp/mcp_server_cli.py` dan `apps/api/main.py`):

1. `lgp_subagent_list`: Menampilkan daftar subagent & pod.
2. `lgp_subagent_get`: Detail kontrak & kapabilitas subagent.
3. `lgp_subagent_update_config`: Mengubah alokasi anggaran, model policy, atau status aktif.
4. `lgp_subagent_topology`: Mendapatkan DAG supervisor & alur critic loop (`CRITICIZES`).
5. `lgp_circuit_breaker_reset`: Mereset status circuit breaker subagent yang terbuka.
6. `lgp_run_create`: Memicu eksekusi task via Atlas Supervisor.
7. `lgp_run_get_state`: Memeriksa checkpoint, output delegates, & biaya run.
8. `lgp_run_list`: Riwayat eksekusi run.
9. `lgp_run_resume_hitl`: Approve/reject interupsi HITL (dengan aturan anti-self-approval).
10. `lgp_memory_query`: Kueri fakta temporal bi-temporal ($T_v, T_k$).
11. `lgp_memory_store_fact`: Menyimpan fakta terstruktur dengan redaksi PII otomatis.
12. `lgp_memory_invalidate_fact`: Menonaktifkan fakta lama (`invalid_at = now`).
13. `lgp_correlation_matrix`: Matriks korelasi 10x10 (NPMI, handoff rate, success lift, composite weight $W_{ij}$).
14. `lgp_correlation_setup`: Pengaturan bobot formula ($\alpha, \beta, \gamma$) & threshold sample $N_{min}$.
15. `lgp_telemetry_events_query`: Kueri raw telemetri events L1.
16. `lgp_audit_query`: Memeriksa catatan audit log append-only.
17. `lgp_audit_verify`: Verifikasi integritas kriptografis rantai hash SHA-256.
