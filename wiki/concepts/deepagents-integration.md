# Integrasi DeepAgents Framework (LGP v2.0)

Dokumentasi integrasi resmi antara Enterprise LangGraph Platform (LGP v2.0) dan framework `deepagents`.

## Arsitektur Integrasi

Integrasi `deepagents` memodernisasi eksekusi supervisor Atlas dan 9 subagen terspesialisasi menggunakan paradigma:
1. **Tool-driven Subagent Invocation**: Subagen didefinisikan sebagai `SubAgent` typed dictionary yang dipanggil melalui tool `task`.
2. **Dynamic Context & File Sharing**: Memori jangka panjang bi-temporal LGP (`temporal_facts`) diserialisasikan ke format Markdown `/memory/AGENTS.md` dan disuntikkan ke runtime via `MemoryMiddleware` / `FilesystemBackend` / `StateBackend`.
3. **Filesystem Sandboxing & Policy Enforcement**: Subagent memiliki batas akses filesystem ketat via `FilesystemPermission`:
   - `Clio` (Researcher): Read-only pada `/workspace`, deny write ke root `/`.
   - `Vulcan` (Software Engineer): Read/Write pada `/workspace`, deny write ke path sistem kritis (`/etc`, `/admin`, `/root`).

## Konversi Kontrak Subagent (`packages/subagents/contracts.py`)

Fungsi `to_deepagents_subagent(contract: SubagentContract)` dan `get_deepagents_subagents()` mengonversi kontrak deklaratif LGP v2.0 ke format `SubAgent` DeepAgents:

```python
from deepagents import create_deep_agent
from packages.subagents.contracts import get_deepagents_subagents

subagents = get_deepagents_subagents(model=llm)
agent = create_deep_agent(
    model=llm,
    subagents=subagents,
    memory=["/memory/AGENTS.md"]
)
```

## Serialisasi Bi-Temporal Memory ke Markdown

Method `TemporalMemoryStore.to_agents_markdown(facts)` menyusun representasi tabel Markdown dari fakta aktif bi-temporal LGP:

```markdown
# AGENTS MEMORY (Bi-Temporal Facts)

| Subject | Predicate | Object | Valid Since | Run ID |
|---|---|---|---|---|
| User_Config | PREFERS | Dark_Mode | 2026-10-14 12:00:00 | run-123 |
```

Markdown ini dibaca oleh `MemoryMiddleware` saat agen mulai mengeksekusi giliran, memastikan kesadaran konteks yang akurat dan terverifikasi secara temporal.

## Eksekusi via Atlas Engine & REST API

Atlas Orchestrator mendukung opsi `use_deepagents=True`:
- **API Request**: `POST /api/runs` dengan payload `{"objective": "...", "use_deepagents": true}`.
- **Python Engine**: `orchestrator.execute_run(..., use_deepagents=True)`.
