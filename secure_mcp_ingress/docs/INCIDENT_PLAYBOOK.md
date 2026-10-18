# Incident Response Playbook — Secure MCP Ingress

Dokumen ini adalah panduan operasional kedaruratan (*Emergency Incident Response Playbook*) untuk sistem Ingress Model Context Protocol (MCP) LangGraph yang aman. Seluruh staf operasional, administrator sistem, dan teknisi SRE wajib mematuhi standar operasi ini saat mendeteksi indikasi anomali, serangan siber, atau kebocoran kredensial.

---

## 1. Matriks Klasifikasi Insiden & Eskalasi

| Tingkat Keparahan | Kriteria Insiden | Contoh Kasus | Waktu Respons Target (MTTR) | Tindakan Utama |
|---|---|---|---|---|
| **P1 - CRITICAL** | Kompromi kredensial, Remote Code Execution (RCE), kebocoran token aktif, intrusi host. | Token `tools:execute` bocor ke publik, aktivitas shell tidak sah, kegagalan isolasi. | < 15 menit | Eksekusi **Kill Switch Darurat**, isolasi host, rotasi total token. |
| **P2 - HIGH** | Serangan injeksi persisten tertolak, brute-force / DoS skala menengah, anomali lonjakan 401/403. | Penyerang mencoba bypass sanitizer ribuan kali/menit, flood request dari IP terdistribusi. | < 30 menit | Blokir IP di Cloudflare WAF, sesuaikan rate limiter Nginx, audit log sanitasi. |
| **P3 - MEDIUM** | Kegagalan rotasi otomatis, peningkatan latency tunneling, request payload malformed sporadis. | Cloudflare tunnel flapping, disk usage log meningkat, handshake timeouts. | < 2 jam | Periksa status tunnel daemon, bersihkan log lama, uji konektivitas origin. |
| **P4 - LOW** | Deprecated scope request, peringatan sertifikat TLS kedaluwarsa dalam 30 hari. | Client lama meminta scope usang, sertifikat origin internal mendekati masa perpanjangan. | < 24 jam | Pembaruan konfigurasi rutin, notifikasi pemilik klien AI. |

---

## 2. Prosedur 1: Isolasi Darurat (Emergency Kill Switch)

Jika terjadi insiden keamanan **P1 (Critical)** di mana integritas server MCP diragukan, atau terdapat indikasi penyerang berhasil menembus tunnel:

### Langkah 2.1: Nonaktifkan Cloudflare Tunnel (Edge Cut-Off)
Mematikan koneksi keluar tunnel seketika memutus akses publik dari Cloudflare Edge ke origin server:

```bash
# Hentikan daemon cloudflared secara instan
sudo systemctl stop cloudflared.service

# Nonaktifkan autostart agar tidak menyala kembali saat reboot darurat
sudo systemctl disable cloudflared.service

# Verifikasi proses telah sepenuhnya mati
ps aux | grep "[c]loudflared" || echo "Status: Cloudflare Tunnel terisolasi (OFFLINE)"
```

### Langkah 2.2: Isolasi Jaringan Host (Host Network Quarantine)
Jika diperlukan isolasi host total untuk mencegah eksfiltrasi data ke luar server:

```bash
# Blokir seluruh trafik jaringan masuk dan keluar kecuali loopback lokal
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT DROP
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A OUTPUT -o lo -j ACCEPT

# Pastikan port internal MCP (8088 dan 8787) tidak dapat diakses dari interface fisik
sudo iptables -L -n -v
```

### Langkah 2.3: Hentikan Reverse Proxy & MCP Backend
```bash
# Matikan Nginx proxy lokal
sudo systemctl stop nginx

# Hentikan proses MCP server / LangGraph ingress daemon
pkill -f "secure_mcp_ingress" || true
```

---

## 3. Prosedur 2: Rotasi & Revokasi Darurat Token (Emergency Credential Rotation)

Jika salah satu atau seluruh token API MCP mengalami kebocoran (misal: terunggah ke repo publik atau log bocor):

### Skenario A: Revokasi Segera Token Tertentu (Targeted Revocation)
Gunakan modul `auth/token_manager.py` untuk mencabut izin token yang terkompromi secara instan:

```bash
# Pindah ke direktori proyek
cd /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress

# Revokasi token bocor berdasarkan string token mentah
python3 -c "
from auth.token_manager import TokenManager
mgr = TokenManager()
compromised_token = '[REDACTED_COMPROMISED_TOKEN]'
revoked = mgr.revoke_token(compromised_token, reason='Security Incident P1: Compromised credential')
print('Status Pencabutan:', 'BERHASIL' if revoked else 'GAGAL/TIDAK DITEMUKAN')
"
```

### Skenario B: Rotasi Masal & Penerbitan Ulang (Full Fleet Token Rotation)
Jalankan script rotasi otomatis untuk menerbitkan token baru bagi seluruh klien tepercaya (`hermes-agent`, `claude-client`, `external-auditor`):

```bash
cd /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress

# Eksekusi rotasi darurat (menerbitkan token baru & menandai token lama kedaluwarsa)
python3 auth/rotate_tokens.py

# Verifikasi integritas store token
python3 -c "
from auth.token_manager import TokenManager
mgr = TokenManager()
tokens = mgr.list_active_tokens()
print(f'Total token aktif setelah rotasi: {len(tokens)}')
for t in tokens:
    print(f\"Client: {t['client_id']} | Scopes: {t['scopes']} | Created: {t['created_at']}\")
"
```

### Skenario C: Purge Total Token Store (Nuclear Reset)
Jika `tokens_store.json` rusak atau master key bocor:
```bash
# Backup store lama untuk keperluan forensik
cp /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress/auth/tokens_store.json \
   /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress/auth/tokens_store.json.forensic.$(date +%s)

# Inisialisasi ulang store kosong
echo '{"tokens": {}, "revoked": {}}' > /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress/auth/tokens_store.json
chmod 0600 /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress/auth/tokens_store.json

# Terbitkan ulang token untuk primary agents
python3 -c "
from auth.token_manager import TokenManager
mgr = TokenManager()
t_hermes, _ = mgr.create_token('hermes-agent', ['tools:execute', 'memory:read', 'memory:write'], description='Emergency re-issue')
t_claude, _ = mgr.create_token('claude-client', ['tools:execute', 'memory:read', 'memory:write'], description='Emergency re-issue')
print('Token baru berhasil diterbitkan. Distribusikan ke environment agent secara aman.')
"
```

---

## 4. Prosedur 3: Analisis Log, Triage, & Deteksi Ancaman

Log tersimpan dalam format terstruktur JSON di Nginx dan event log di syslog/daemon.

### 4.1. Lokasi Berkas Log
- **Nginx JSON Ingress Log**: `/var/log/nginx/mcp_access_json.log` (atau `/tmp/mcp_access_json.log`)
- **Nginx Error Log**: `/var/log/nginx/mcp_error.log`
- **Cloudflare Tunnel Log**: `journalctl -u cloudflared.service`
- **Application Auth & Sanitizer Log**: stdout/stderr systemd service `secure-mcp-ingress`

### 4.2. Perintah Analisis Cepat (Fast Triage Commands)

#### A. Deteksi Upaya Injeksi / Serangan OWASP (HTTP 400 dari Input Sanitizer):
```bash
# Filter request yang diblokir oleh Input Sanitizer
cat /var/log/nginx/mcp_access_json.log | jq -r 'select(.status == 400) | "\(.time) | IP: \(.client_ip) | URI: \(.uri) | Error: \(.body_bytes_sent)"'
```

#### B. Deteksi Upaya Akses Tanpa Token / Forged Token (HTTP 401 Unauthorized):
```bash
# Hitung distribusi IP sumber yang memicu error 401
cat /var/log/nginx/mcp_access_json.log | jq -r 'select(.status == 401) | .client_ip' | sort | uniq -c | sort -nr | head -n 20
```

#### C. Deteksi Pelanggaran Otorisasi / Privilege Escalation (HTTP 403 Forbidden):
```bash
# Identifikasi token valid yang mencoba mengakses resource di luar scopanya
cat /var/log/nginx/mcp_access_json.log | jq -r 'select(.status == 403) | "\(.time) | Client: \(.client_id // "unknown") | URI: \(.uri)"'
```

#### D. Deteksi Serangan Flooding / DoS (HTTP 429 Too Many Requests):
```bash
# Pantau frekuensi trigger rate limiter per menit
cat /var/log/nginx/mcp_access_json.log | jq -r 'select(.status == 429) | "\(.time[0:16]) \(.client_ip)"' | sort | uniq -c
```

---

## 5. Prosedur 4: Pemulihan Layanan (Post-Incident Recovery & Verification)

Setelah ancaman dinetralkan dan akar masalah terisolasi:

1. **Verifikasi Integritas File & Kode**:
   ```bash
   cd /home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress
   git status
   git diff
   ```

2. **Jalankan Test Suite Keamanan End-to-End**:
   ```bash
   python3 tests/test_e2e_security.py
   ```
   *Seluruh 6 pengujian keamanan wajib berstatus `OK`.*

3. **Aktifkan Kembali Layanan Ingress**:
   ```bash
   # Nyalakan Nginx proxy
   sudo systemctl start nginx

   # Nyalakan Cloudflare tunnel
   sudo systemctl enable cloudflared.service
   sudo systemctl start cloudflared.service

   # Verifikasi status tunnel
   cloudflared tunnel info [REDACTED_TUNNEL_NAME]
   ```

4. **Kirim Notifikasi Pasca-Insiden**:
   Gunakan `scripts/notify_hub.py` untuk menginformasikan tim di Slack dan Discord bahwa insiden telah terselesaikan dan layanan telah beroperasi normal.

---

## 6. Kontak Darurat & Eskalasi

- **Security Lead / SRE On-Call**:biezz (Workspace Owner)
- **Discord Incident Hub**: Thread `1560336746653294692`
- **Slack Security Alerts**: Channel `#ops-alerts` (`C0BV1LWFVB5`)
- **Cloudflare Support**: https://dash.cloudflare.com
