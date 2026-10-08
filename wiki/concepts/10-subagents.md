# 10 Flagship Subagents (LGP v2.0)

Sistem LGP v2.0 dibagi menjadi 4 Pod fungsional yang menaungi 10 Subagent Flagship.

## 1. Pod Koordinasi
- **`atlas` (Orchestrator-Supervisor)**
  - *Role*: Dekomposisi tugas, distribusi context packet, effort scaling, dan eskalasi HITL.
  - *Model Policy*: `frontier-extended-thinking`
  - *Trust Level*: High

## 2. Pod Riset & Rekayasa
- **`clio` (Deep Researcher)**
  - *Role*: Outbound read-only web research, ekstraksi fakta & sitasi.
  - *Security*: Dilarang keras mengakses Admin MCP.
  - *Model Policy*: `mid-tier-structured` | *Trust Level*: Low
- **`vulcan` (Software Engineer)**
  - *Role*: Menulis kode graf, validasi sandbox execution, submit PR.
  - *Security*: Dilarang self-promote ke prod tanpa persetujuan HITL.
  - *Model Policy*: `code-generation-specialist` | *Trust Level*: Medium
- **`athena` (Critic & Reviewer)**
  - *Role*: Adversarial code review, evaluasi keamanan, & critic loop (`CRITICIZES`) bersama Vulcan.
  - *Model Policy*: `adversarial-low-temp` | *Trust Level*: Medium

## 3. Pod Platform
- **`hermes` (Platform Ops / SRE)**
  - *Role*: Incident triage, health checks, & usulan runbook.
  - *Model Policy*: `deterministic-ops` | *Trust Level*: Medium
- **`mnemosyne` (Memory Curator)**
  - *Role*: Kurasi memori Graphiti L2, redaksi PII, deduplikasi, & sorting ontologi.
  - *Model Policy*: `structured-extraction` | *Trust Level*: Medium
- **`janus` (Integration & MCP Hub)**
  - *Role*: Registrasi server MCP eksternal, validasi tool annotations & health.
  - *Model Policy*: `deterministic-mcp` | *Trust Level*: Low-Medium

## 4. Pod Tata Kelola
- **`themis` (Security & Compliance)**
  - *Role*: Audit SHA-256 hash-chain integrity, verifikasi RBAC, hygiene `secret://`.
  - *Security*: Dilarang membaca nilai rahasia secara mentah.
  - *Model Policy*: `security-auditor-strict` | *Trust Level*: Medium-High
- **`metron` (Evaluation & Data)**
  - *Role*: Benchmark dataset per subagent, promote gate, LLM-as-judge independen.
  - *Model Policy*: `independent-judge-model` | *Trust Level*: Medium
- **`iris` (Documentation & Comms)**
  - *Role*: Penyusunan PRD, ADR, changelog, dan laporan eksekutif.
  - *Model Policy*: `mid-high-writer` | *Trust Level*: Medium
