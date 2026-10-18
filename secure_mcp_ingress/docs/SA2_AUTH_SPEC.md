# Spesifikasi Autentikasi dan Otorisasi (SA2)
## Secure MCP Ingress Architecture

Dokumen ini mendefinisikan spesifikasi arsitektur autentikasi, model otorisasi berbasis scope, siklus hidup token (token lifecycle), dan prosedur kedaruratan (emergency response) untuk Secure MCP Ingress.

---

## 1. Standar dan Protokol

1. **RFC 9728 (OAuth 2.0 Protected Resource Metadata)**:
   - Endpoint discovery: `/.well-known/oauth-protected-resource`
   - File konfigurasi: `auth/protected_resource_metadata.json`
   - Mempublikasikan kapabilitas resource server, authorization servers tepercaya, scope yang didukung, dan metode bearer token.
2. **RFC 8707 (Resource Indicators for OAuth 2.0)**:
   - Identifier resource dilindungi: `https://mcp.domainanda.com/mcp`
   - Mengikat token ke target audience (`aud`). Token yang dikeluarkan untuk audience lain akan ditolak (`audience_mismatch`).
3. **RFC 6750 (OAuth 2.0 Bearer Token Usage)**:
   - Token dikirim via header: `Authorization: Bearer <token>`
   - Format tantangan error: `WWW-Authenticate: Bearer realm="...", error="...", error_description="...", scope="...", resource_metadata="..."`

---

## 2. Arsitektur Token Management Engine

- **Komponen**: `auth/token_manager.py`
- **Penyimpanan**: `auth/tokens_store.json`
- **Keamanan Penyimpanan**:
  - Token plaintext **tidak pernah disimpan** di disk atau database.
  - Hanya nilai hash **SHA-256** dari token (`hashlib.sha256`) yang disimpan di registry.
  - File permission dikunci ke `0600` (hanya owner read/write).
  - Penulisan berkas bersifat atomik (tulis ke file temporer lalu `os.replace` dan `fsync`).
- **Masa Berlaku Default**: 90 hari kalender sejak penerbitan.
- **Grace Period Rotasi**: 24 jam untuk token lama selama transisi ke token baru.

---

## 3. Matriks Hak Akses Klien AI (Client Scope Matrix)

Daftar scope yang didukung:
- `memory:read`: Mengambil memori, riwayat percakapan, graph context, dan fakta tersimpan.
- `memory:write`: Menyimpan checkpoint memori, memperbarui fakta graph, dan mutasi context.
- `tools:execute`: Mengeksekusi tools MCP (terminal, eksekusi kode, scraping, integrasi API).

### Matriks Otorisasi AI Client

| Client ID | Tipe Entitas | Scopes Diizinkan | Audience (`aud`) | Masa Berlaku | Keterangan |
|---|---|---|---|---|---|
| `hermes-agent` | Internal Primary Agent | `memory:read`, `memory:write`, `tools:execute` | `https://mcp.domainanda.com/mcp` | 90 hari | Akses penuh operasional Hermes workspace |
| `claude-client` | Secondary AI Coding Agent | `memory:read`, `memory:write`, `tools:execute` | `https://mcp.domainanda.com/mcp` | 90 hari | Akses Claude Code CLI untuk delegasi implementasi kode |
| `external-auditor` | Read-only Audit / Monitor | `memory:read` | `https://mcp.domainanda.com/mcp` | 30 hari | Klien telemetri / observer tanpa izin eksekusi tool |
| `worker-bot` | Specialized Automation Bot | `tools:execute` | `https://mcp.domainanda.com/mcp` | 60 hari | Worker eksekutor tanpa akses pembacaan/penulisan memori persisten |

---

## 4. Mekanisme Rotasi Token (Zero-Downtime Rotation)

Alur rotasi token via `auth/rotate_tokens.py`:
1. Sistem menghasilkan token baru menggunakan generator CSPRNG (`secrets.token_urlsafe(32)`).
2. Token baru dicatat di `auth/tokens_store.json` dengan status `ACTIVE` dan masa berlaku 90 hari.
3. Token aktif lama diubah statusnya menjadi `GRACE_PERIOD` dengan batas waktu kedaluwarsa transisi (`grace_until`) = `now + 24 jam`.
4. Token lama tetap dapat digunakan selama periode transisi 24 jam untuk mencegah request drop sebelum konfigurasi client di-update.
5. Setelah melewati `grace_until`, verifikasi token lama akan otomatis mengembalikan `expired_token`.

### Perintah Rotasi:
```bash
python3 auth/rotate_tokens.py --rotate --client-id claude-client --grace-hours 24
```

---

## 5. Prosedur Revokasi Darurat (Emergency Revocation Procedures)

Bila terjadi indikasi kebocoran kredensial, token bocor ke log, atau anomali akses:

### Skenario A: Kebocoran Token Spesifik (Tahu Nilai Hash)
Jalankan pencabutan instan satu token tertentu:
```bash
python3 auth/rotate_tokens.py --revoke-hash <SHA256_HASH> --reason "Compromised token leak in public channel"
```

### Skenario B: Seluruh Akses Client Terkompromi (Emergency Mass Revoke)
Cabut seluruh token aktif dan grace period untuk satu `client_id` secara instan:
```bash
python3 auth/rotate_tokens.py --revoke-client claude-client --reason "Host machine security compromise"
```
Hasil: Semua token aktif dan grace period untuk client tersebut langsung diset ke `REVOKED`. Setiap request selanjutnya langsung ditolak dengan status HTTP 401 (`revoked_token`).

### Skenario C: Verifikasi Status Revokasi
Periksa status token di registry:
```bash
python3 auth/rotate_tokens.py --list --client-id claude-client
```

---

## 6. Format Tantangan HTTP (RFC 9728 & RFC 6750)

Ketika request ke MCP ingress gagal verifikasi autentikasi/otorisasi, server mengembalikan respon HTTP 401 Unauthorized dengan header `WWW-Authenticate`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="https://mcp.domainanda.com/mcp", resource_metadata="https://mcp.domainanda.com/.well-known/oauth-protected-resource", error="invalid_token", error_description="The access token provided is expired, revoked, malformed, or invalid."
```

Untuk kasus hak akses tidak mencukupi (HTTP 403 Forbidden):
```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="https://mcp.domainanda.com/mcp", resource_metadata="https://mcp.domainanda.com/.well-known/oauth-protected-resource", error="insufficient_scope", scope="memory:write"
```
