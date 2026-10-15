# Enterprise LangGraph Platform (LGP v2.0) - Wiki Overview

Selamat datang di Dokumentasi Arsitektur & Memori Enterprise LangGraph Platform (LGP v2.0).

## Ringkasan Platform

LGP v2.0 adalah sistem orkestrasi multi-agent enterprise yang dirancang untuk mendukung 10 Subagent Flagship, eksekusi Supervisor-via-Tools dipimpin oleh Atlas, bi-temporal long-term memory (Graphiti L2), telemetri korelasi 10x10, dan 17 FastMCP admin tools.

Platform ini dilengkapi dengan **Next.js Dashboard** sebagai pusat kontrol observabilitas untuk monitoring telemetry real-time, manajemen run via Kanban, dan kalibrasi matriks korelasi subagent.

## Struktur Dokumentasi (Wiki)

- [Konsep Utama](concepts/)
  - [Integrasi DeepAgents Framework](concepts/deepagents-integration.md)
  - [Taxonomy Memori & Klasifikasi](concepts/memory-taxonomy.md)
  - [10 Subagents & Pod Structure](concepts/10-subagents.md)
  - [Guardrails & Keamanan](concepts/guardrails.md)
  - [Lapisan Persistensi Hybrid](concepts/persistence-layer.md)
- [Panduan Penggunaan](guides/)
  - [Panduan Kurasi Memori untuk AI Next Session](guides/memory-curation-guide.md)
  - [Panduan Integrasi FastMCP & Stdio CLI](guides/mcp-integration-guide.md)
  - [Panduan Penggunaan Dashboard Next.js](guides/dashboard-guide.md)
- [Referensi API & Sistem](reference/)
  - [Daftar 17 FastMCP Admin Tools](reference/api-and-mcp-tools.md)
  - [Skema Database & Integritas Hash](reference/database-schema.md)
- [Indeks AI & Agent](llms.txt)
