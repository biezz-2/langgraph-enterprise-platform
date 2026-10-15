# Panduan Integrasi FastMCP & Stdio CLI (LGP v2.0)

Panduan ini ditujukan bagi pengembang dan agen AI untuk mengintegrasikan Enterprise LangGraph Platform (LGP v2.0) ke berbagai IDE dan client AI eksternal seperti **Claude Code**, **Claude Desktop**, **Cursor**, dan **Windsurf**.

---

## 1. Arsitektur Kontrol FastMCP

LGP v2.0 menyediakan dua jalur antarmuka manajemen:

1. **Stdio Protocol Mode** (`apps/admin_mcp/mcp_server_cli.py`):
   - Menggunakan pustaka resmi MCP SDK (`mcp.server.mcpserver.MCPServer`).
   - Berjalan sebagai subprocess via standard input/output (stdio).
   - Ideal untuk integrasi lokal langsung pada IDE (Claude Desktop, Cursor, Windsurf, Claude Code).

2. **REST API Gateway Mode** (`apps/api/main.py`):
   - Berjalan pada service PM2 `lgp-api` di port `8000`.
   - Menyediakan endpoint:
     - `GET http://localhost:8000/mcp/admin/tools`: Daftar 17 tools berserta parameter dan risk annotations.
     - `POST http://localhost:8000/mcp/admin/call`: Menjalankan tool secara terisolasi dengan payload JSON.
   - Ideal untuk integrasi web dashboard, automation worker, dan pemanggilan berbasis HTTP/curl.

---

## 2. Risk Annotations pada Tools LGP

Semua 17 tools FastMCP LGP v2.0 dilengkapi anotasi risiko standar model MCP:

- `readOnlyHint` (`true`/`false`): Menunjukkan tool hanya membaca data tanpa mengubah state sistem.
- `destructiveHint` (`true`/`false`): Menunjukkan apakah tool berpotensi menghapus atau merombak state permanen.
- `idempotentHint` (`true`/`false`): Menunjukkan eksekusi berulang dengan parameter sama menghasilkan state identik.
- `openWorldHint` (`true`/`false`): Menunjukkan interaksi dengan dunia eksternal di luar boundaries lokal.

Klien AI memanfaatkan anotasi ini untuk menentukan apakah suatu tool aman dieksekusi secara otonom atau memerlukan konfirmasi pengguna (HITL prompt).

---

## 3. Konfigurasi Client AI

### A. Claude Code (CLI)

Konfigurasikan pada file global atau project `.claude/settings.json` atau jalankan via CLI:

```bash
claude mcp add lgp-admin /home/biezz/Documents/Project/coding/langgraph/.venv/bin/python \
  /home/biezz/Documents/Project/coding/langgraph/apps/admin_mcp/mcp_server_cli.py
```

Atau tambahkan ke konfigurasi JSON:
```json
{
  "mcpServers": {
    "lgp-admin": {
      "command": "/home/biezz/Documents/Project/coding/langgraph/.venv/bin/python",
      "args": [
        "/home/biezz/Documents/Project/coding/langgraph/apps/admin_mcp/mcp_server_cli.py"
      ],
      "env": {
        "PYTHONPATH": "/home/biezz/Documents/Project/coding/langgraph",
        "LGP_DB_PATH": "/home/biezz/Documents/Project/coding/langgraph/data/lgp.db"
      }
    }
  }
}
```

---

### B. Claude Desktop

Buka file konfigurasi Claude Desktop:
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Tambahkan blok berikut di dalam `"mcpServers"`:

```json
{
  "mcpServers": {
    "lgp-admin-fastmcp": {
      "command": "/home/biezz/Documents/Project/coding/langgraph/.venv/bin/python",
      "args": [
        "/home/biezz/Documents/Project/coding/langgraph/apps/admin_mcp/mcp_server_cli.py"
      ],
      "env": {
        "PYTHONPATH": "/home/biezz/Documents/Project/coding/langgraph",
        "LGP_DB_PATH": "/home/biezz/Documents/Project/coding/langgraph/data/lgp.db"
      }
    }
  }
}
```

---

### C. Cursor IDE

Tambahkan ke `.cursor/mcp.json` di root workspace atau konfigurasi Cursor Settings > Features > MCP:

```json
{
  "mcpServers": {
    "lgp-admin": {
      "command": "/home/biezz/Documents/Project/coding/langgraph/.venv/bin/python",
      "args": [
        "/home/biezz/Documents/Project/coding/langgraph/apps/admin_mcp/mcp_server_cli.py"
      ],
      "env": {
        "PYTHONPATH": "/home/biezz/Documents/Project/coding/langgraph",
        "LGP_DB_PATH": "/home/biezz/Documents/Project/coding/langgraph/data/lgp.db"
      }
    }
  }
}
```

---

### D. Windsurf (Codeium)

Buka `~/.codeium/windsurf/mcp_config.json` dan tambahkan server:

```json
{
  "mcpServers": {
    "lgp-admin": {
      "command": "/home/biezz/Documents/Project/coding/langgraph/.venv/bin/python",
      "args": [
        "/home/biezz/Documents/Project/coding/langgraph/apps/admin_mcp/mcp_server_cli.py"
      ],
      "env": {
        "PYTHONPATH": "/home/biezz/Documents/Project/coding/langgraph",
        "LGP_DB_PATH": "/home/biezz/Documents/Project/coding/langgraph/data/lgp.db"
      }
    }
  }
}
```

---

## 4. Pengujian & Verifikasi Koneksi

### A. Uji Coba Mode Stdio (CLI)
Jalankan perintah berikut di terminal untuk memastikan tidak ada import error:

```bash
/home/biezz/Documents/Project/coding/langgraph/.venv/bin/python \
  /home/biezz/Documents/Project/coding/langgraph/apps/admin_mcp/mcp_server_cli.py
```
*(Server akan menunggu pesan JSON-RPC melalui STDIN)*

### B. Uji Coba Mode REST HTTP Gateway
Lakukan pemanggilan tool via `curl`:

1. **Daftar Seluruh Subagent**:
   ```bash
   curl -s -X POST http://localhost:8000/mcp/admin/call \
     -H "Content-Type: application/json" \
     -d '{"tool": "lgp_subagent_list", "arguments": {}, "actor": "TestCLI"}'
   ```

2. **Kueri Memori Jangka Panjang**:
   ```bash
   curl -s -X POST http://localhost:8000/mcp/admin/call \
     -H "Content-Type: application/json" \
     -d '{"tool": "lgp_memory_query", "arguments": {"subject": "Architecture"}, "actor": "TestCLI"}'
   ```

3. **Verifikasi Hash Chain Audit Log**:
   ```bash
   curl -s -X POST http://localhost:8000/mcp/admin/call \
     -H "Content-Type: application/json" \
     -d '{"tool": "lgp_audit_verify", "arguments": {}, "actor": "ThemisAuditor"}'
   ```

---

## 5. Audit Trail Otomatis

Setiap pemanggilan tool FastMCP, baik lewat Stdio maupun REST API, **otomatis dicatat ke tabel `audit_log`** dengan hash chaining kriptografis SHA-256 (`record_audit_log`). 

Untuk memantau aktivitas tool MCP:
- Periksa via FastMCP tool: `lgp_audit_query(limit=20)`
- Verifikasi integritas: `lgp_audit_verify()`
