# Spesifikasi Arsitektur Ingress & Jaringan Zero-Trust (SA1)

Dokumen ini mendefinisikan arsitektur zero-trust ingress, isolasi jaringan host, konfigurasi Cloudflare Tunnel, systemd sandboxing, dan kebijakan Cloudflare Access Edge untuk Secure MCP Server Gateway.

---

## 1. Topologi Arsitektur Zero-Trust

Dalam arsitektur MCP Ingress ini, server backend tidak membuka port publik apa pun ke internet (*zero open inbound ports*). Semua komunikasi dari klien eksternal (AI Agent, Orchestrator, CLI) dipaksa melalui Cloudflare Edge dan diteruskan secara aman ke server lokal melalui outbound encrypted tunnel.

```
+-----------------------------------------------------------------------------------------+
|                                    INTERNET / WAN                                       |
+-----------------------------------------------------------------------------------------+
       |
       | 1. HTTPS / TLS 1.3 (Headers: CF-Access-Client-Id, CF-Access-Client-Secret)
       v
+-----------------------------------------------------------------------------------------+
|                                  CLOUDFLARE EDGE                                        |
|  - Edge TLS 1.3 Termination (HSTS, TLS_AES_256_GCM_SHA384)                             |
|  - WAF Rules (Method whitelist: GET/POST/OPTIONS, Path Traversal Block)                 |
|  - DDoS Mitigation & Rate Limiting (120 req/min per Client-ID + IP)                     |
|  - Cloudflare Access Policy: Enforce M2M Service Token (Non-Identity)                   |
|  - Injeksi Header: Cf-Access-Jwt-Assertion                                              |
+-----------------------------------------------------------------------------------------+
       |
       | 2. Encrypted Outbound QUIC/UDP Tunnel (no inbound port needed on host)
       v
+-----------------------------------------------------------------------------------------+
|                                  HOST LOCALHOST (127.0.0.1)                             |
|                                                                                         |
|  [cloudflared daemon] (systemd sandboxed: NoNewPrivileges, ProtectSystem=full)          |
|         |                                                                               |
|         | 3. Local HTTP Forwarding (Loopback only)                                      |
|         v                                                                               |
|  [Reverse Proxy Gateway / Auth Middleware] ---> Listen: 127.0.0.1:8088                 |
|         |                                                                               |
|         | 4. Internal Auth-Verified Routing                                             |
|         v                                                                               |
|  [MCP Server Backend]                    ---> Listen: 127.0.0.1:8787                 |
|                                                                                         |
|  FIREWALL (UFW & iptables):                                                             |
|  - Inbound eth0/public to 8088/8787: DROP / DENY                                       |
|  - Loopback (lo) to 127.0.0.1:8088/8787: ACCEPT                                         |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Komponen & Artefak Konfigurasi

| Komponen | File Konfigurasi | Deskripsi & Tujuan |
| :--- | :--- | :--- |
| **Cloudflare Tunnel** | `config/cloudflared_config.yml` | Mendefinisikan routing ingress dari `mcp.domainanda.com` ke loopback `127.0.0.1:8088`, tuning transport (QUIC, keepAliveTimeout 90s, noTLSVerify: false), dan catch-all 404. |
| **Systemd Service** | `config/cloudflared.service` | Hardening daemon `cloudflared` dengan pembatasan hak akses kernel, sandboxing filesystem, non-root user, dan restart otomatis. |
| **Host Firewall** | `config/setup_firewall.sh` | Skrip otomasi UFW & iptables untuk memblokir akses publik ke port 8787 & 8088 dan mengisolasi port ke interface loopback `127.0.0.1`. |
| **Edge Access Policy** | `config/cloudflare_access_policy.json` | Definisi JSON untuk Cloudflare Access Application, WAF Custom Rules, Rate Limiting, dan validasi M2M Service Token. |

---

## 3. Rincian Konfigurasi Cloudflare Tunnel (`config/cloudflared_config.yml`)

### Parameter Utama:
- **`protocol: quic`**: Menggunakan protokol HTTP/3 (QUIC) berbasis UDP untuk koneksi tunnel keluar ke edge Cloudflare. Protokol ini tahan terhadap degradasi jaringan dan packet loss.
- **`originRequest`**:
  - `keepAliveTimeout: 90s`: Mempertahankan koneksi keep-alive ke backend proxy lokal untuk mengurangi latency TLS/TCP handshake berulang.
  - `connectTimeout: 30s` & `tlsTimeout: 10s`: Mencegah connection hanging jika backend mengalami stall.
  - `noTLSVerify: false`: Menolak koneksi TLS jika sertifikat origin tidak valid (jika menggunakan upstream HTTPS).
- **Ingress Rule Mapping**:
  - `mcp.domainanda.com` -> `http://127.0.0.1:8088` (Reverse Proxy / Auth Gateway).
  - Reverse proxy bertugas memvalidasi JWT `Cf-Access-Jwt-Assertion` sebelum meneruskan payload ke MCP Server di port `8787`.
  - Fallback catch-all: `- service: http_status:404` untuk menolak domain/path yang tidak cocok.

### Prosedur Setup & Pairing Tunnel:
1. Otentikasi CLI Cloudflare:
   ```bash
   cloudflared tunnel login
   ```
2. Buat tunnel baru:
   ```bash
   cloudflared tunnel create secure-mcp-tunnel
   ```
   *Salin UUID tunnel yang dihasilkan dan perbarui `tunnel` dan `credentials-file` pada `config/cloudflared_config.yml`.*
3. Petakan DNS CNAME di Cloudflare:
   ```bash
   cloudflared tunnel route dns secure-mcp-tunnel mcp.domainanda.com
   ```
4. Salin file konfigurasi ke direktori sistem:
   ```bash
   sudo cp config/cloudflared_config.yml /etc/cloudflared/config.yml
   ```

---

## 4. Hardening Systemd Daemon (`config/cloudflared.service`)

Daemon `cloudflared` dijalankan sebagai service non-root dengan sandboxing ketat:

- **Hak Akses & User**:
  - `User=cloudflared`, `Group=cloudflared`.
  - `NoNewPrivileges=yes`: Mencegah eskalasi hak akses proses anak melalui SUID/SGID.
  - `RestrictSUIDSGID=true`: Memblokir pembuatan atau eksekusi bit setuid/setgid.
- **Isolasi Filesystem**:
  - `ProtectSystem=full`: Menjadikan direktori `/usr`, `/boot`, dan `/etc` berstatus read-only bagi service.
  - `ProtectHome=true`: Menyembunyikan direktori `/home`, `/root`, dan `/run/user`.
  - `PrivateTmp=true`: Membuat namespace `/tmp` dan `/var/tmp` terisolasi dari proses lain.
  - `ReadOnlyPaths=/etc/cloudflared`: Mengunci direktori konfigurasi dan credential tunnel agar read-only.
- **Proteksi Kernel & Namespace**:
  - `ProtectKernelTunables=true`, `ProtectKernelModules=true`, `ProtectKernelLogs=true`.
  - `MemoryDenyWriteExecute=true`: Mencegah pembuatan alokasi memory yang writable sekaligus executable (mitigasi W^X / buffer overflow exploitation).
  - `SystemCallFilter=@system-service`: Membatasi system call hanya pada API sistem operasi yang diperlukan service standar.
- **Resiliensi**:
  - `Restart=on-failure` & `RestartSec=5s`: Otomatis memulihkan koneksi tunnel jika proses crash atau jaringan sempat terputus.

---

## 5. Isolasi Jaringan Host (`config/setup_firewall.sh`)

Meskipun Cloudflare Tunnel tidak membutuhkan port inbound terbuka, aplikasi backend (Node.js/Python/Go) berpotensi secara tidak sengaja listen pada `0.0.0.0` (all interfaces). Untuk mencegah bypass jaringan dari LAN atau penyerang publik:

1. **UFW (Uncomplicated Firewall)**:
   - Port `8787` (MCP Server) dan `8088` (Proxy) secara eksplisit diizinkan HANYA pada interface loopback (`lo` / `127.0.0.1`).
   - Aturan `ufw deny in to any port 8787` dan `8088` diterapkan untuk semua interface eksternal.
2. **iptables & ip6tables (Defense-in-depth)**:
   - Rule `INPUT 1 & 2`: `-p tcp --dport <PORT> -i lo -j ACCEPT`.
   - Rule `INPUT 3 & 4`: `-p tcp --dport <PORT> ! -i lo -j DROP`.
   - Paket yang mencoba mengakses port target dari interface publik (misalnya `eth0` atau `wlan0`) langsung di-DROP sebelum mencapai socket layer.
3. **Audit Sockets**:
   - Skrip memverifikasi output `ss -tlpn` untuk memperingatkan operator jika terdapat proses backend yang masih mengikat ke `0.0.0.0`.

---

## 6. Kebijakan Cloudflare Access Edge & M2M Service Token

### 6.1 Enforcement Service Token
Akses ke endpoint `mcp.domainanda.com` dikhususkan untuk klien Machine-to-Machine (M2M) seperti autonomous agent dan coding framework. Tidak ada interaksi browser login berbasis email OTP/SAML.

Setiap request dari klien AI **WAJIB** menyertakan dua header HTTP:
```http
CF-Access-Client-Id: <CLIENT_ID_DARI_CLOUDFLARE_ZERO_TRUST>
CF-Access-Client-Secret: <CLIENT_SECRET_DARI_CLOUDFLARE_ZERO_TRUST>
```

Ketika request tiba di Cloudflare Edge:
1. Cloudflare memvalidasi pasangan Client ID & Secret terhadap database Zero Trust Access.
2. Jika valid, Cloudflare membubuhkan header JWT signed:
   ```http
   Cf-Access-Jwt-Assertion: <SIGNED_RS256_JWT>
   ```
3. Request diteruskan melalui Tunnel ke Reverse Proxy (`127.0.0.1:8088`).
4. Reverse Proxy memverifikasi keaslian JWT assertion menggunakan public keys dari Cloudflare:
   `https://<TEAM_NAME>.cloudflareaccess.com/cdn-cgi/access/certs`

### 6.2 Cloudflare Edge WAF & Sanitasi Input
- **WAF Rule 1 (Token Mandat)**:
  `expression: (http.host eq "mcp.domainanda.com" and not (http.request.headers["cf-access-client-id"][0] ne "" and http.request.headers["cf-access-client-secret"][0] ne ""))`
  *Aksi: Block.*
- **WAF Rule 2 (Path Sanitization)**:
  Memblokir request yang mengandung karakter traversal `..`, `/etc/`, atau `/proc/` guna mencegah LFI probing ke MCP server.
- **WAF Rule 3 (HTTP Method Whitelist)**:
  Hanya mengizinkan metode `GET`, `POST`, dan `OPTIONS`. Metode `PUT`, `DELETE`, `TRACE`, `CONNECT` langsung diblokir di Edge.

### 6.3 Rate Limiting & DDoS Mitigation
- **Karakteristik Tracking**: Kombinasi `CF-Access-Client-Id` dan `ip.src`.
- **Threshold**: Maksimum 120 requests per 60 detik.
- **Action**: Respon HTTP `429 Too Many Requests` dalam format JSON selama 60 detik mitigasi.

---

## 7. Runbook Verifikasi & Pengujian

### Uji 1: Verifikasi Proteksi Port Host (Harus Gagal dari Luar)
Dari mesin lain di jaringan lokal / internet:
```bash
# Menghubungi IP host publik langsung pada port 8088 atau 8787
curl -m 5 http://<SERVER_PUBLIC_IP>:8088/health
# Hasil yang diharapkan: Connection refused atau Connection timed out (Firewall DROP)
```

### Uji 2: Verifikasi Akses Loopback Lokal (Harus Sukses)
Di dalam server lokal:
```bash
curl -i http://127.0.0.1:8088/health
# Hasil yang diharapkan: Respon HTTP dari reverse proxy / auth gateway
```

### Uji 3: Uji Edge Access Tanpa Service Token (Harus Ditolak di Edge)
```bash
curl -i https://mcp.domainanda.com/mcp/v1/tools
# Hasil yang diharapkan: HTTP 403 Forbidden atau Halaman Cloudflare Access Denied
```

### Uji 4: Uji Edge Access Dengan Service Token Valid
```bash
curl -i -X POST https://mcp.domainanda.com/mcp/v1/call \
  -H "Content-Type: application/json" \
  -H "CF-Access-Client-Id: $CF_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
# Hasil yang diharapkan: HTTP 200 OK dengan payload JSON-RPC dari MCP Server
```

### Uji 5: Uji Edge WAF Traversal Protection
```bash
curl -i "https://mcp.domainanda.com/mcp/../etc/passwd" \
  -H "CF-Access-Client-Id: $CF_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET"
# Hasil yang diharapkan: HTTP 403 Forbidden langsung oleh Cloudflare Edge WAF
```

---
*Dokumen ini merupakan artefak resmi Subagent 1 (SA1 - Ingress & Jaringan) untuk integrasi dengan SA4 (Reverse Proxy) dan SA5 (Integration Test).*
