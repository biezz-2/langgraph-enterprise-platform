#!/usr/bin/env bash
# ==============================================================================
# Setup Firewall Host - Loopback Isolation for Secure MCP Ingress (SA1)
# ==============================================================================
# Enforces ports 8787 (MCP Server) and 8088 (Reverse Proxy Gateway) to accept
# traffic ONLY via local loopback interface (127.0.0.1).
# Direct public inbound access from external network interfaces is strictly blocked.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

MCP_PORT=8787
PROXY_PORT=8088
SSH_PORT=22

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Script ini harus dijalankan sebagai root atau menggunakan sudo."
        exit 1
    fi
}

check_dependencies() {
    log_info "Memeriksa ketersediaan tool firewall..."
    if command -v ufw >/dev/null 2>&1; then
        FIREWALL_BACKEND="ufw"
        log_info "Backend terdeteksi: UFW (Uncomplicated Firewall)"
    elif command -v iptables >/dev/null 2>&1; then
        FIREWALL_BACKEND="iptables"
        log_info "Backend terdeteksi: iptables"
    else
        log_error "Tidak ditemukan ufw maupun iptables pada sistem!"
        exit 1
    fi
}

verify_socket_bindings() {
    log_info "Memeriksa socket binding port $MCP_PORT dan $PROXY_PORT..."
    if command -v ss >/dev/null 2>&1; then
        local exposed_bindings
        exposed_bindings=$(ss -tlpn 2>/dev/null | grep -E ":($MCP_PORT|$PROXY_PORT)\b" | grep -v "127.0.0.1\|\[::1\]" || true)
        if [[ -n "$exposed_bindings" ]]; then
            log_warn "PERINGATAN: Ditemukan proses listen pada alamat publik/0.0.0.0:"
            echo "$exposed_bindings"
            log_warn "Pastikan konfigurasi aplikasi juga mengikat (bind) ke 127.0.0.1!"
        else
            log_success "Socket check: Tidak ada port $MCP_PORT / $PROXY_PORT yang terekspos langsung di 0.0.0.0."
        fi
    fi
}

configure_ufw() {
    log_info "Mengonfigurasi aturan UFW..."

    # Pastikan SSH tidak terblokir
    ufw allow ${SSH_PORT}/tcp comment 'SSH Management Port' >/dev/null 2>&1 || true

    # Izinkan akses loopback lokal ke port target
    ufw allow in on lo to 127.0.0.1 port "$MCP_PORT" proto tcp comment 'Allow MCP server on loopback only'
    ufw allow in on lo to 127.0.0.1 port "$PROXY_PORT" proto tcp comment 'Allow Reverse Proxy on loopback only'

    # Tolak semua akses publik / eksternal ke port 8787 dan 8088
    ufw deny in to any port "$MCP_PORT" proto tcp comment 'Block direct public ingress to MCP server'
    ufw deny in to any port "$PROXY_PORT" proto tcp comment 'Block direct public ingress to Reverse Proxy'

    # Pastikan loopback interface diizinkan secara umum
    ufw allow in on lo comment 'Allow all loopback traffic' >/dev/null 2>&1 || true

    log_success "Aturan UFW berhasil ditambahkan."
}

configure_iptables() {
    log_info "Mengonfigurasi aturan iptables (defense-in-depth)..."

    # Hapus rule lama jika sudah pernah dibuat agar tidak duplikat
    iptables -D INPUT -p tcp --dport "$MCP_PORT" -i lo -j ACCEPT 2>/dev/null || true
    iptables -D INPUT -p tcp --dport "$PROXY_PORT" -i lo -j ACCEPT 2>/dev/null || true
    iptables -D INPUT -p tcp --dport "$MCP_PORT" ! -i lo -j DROP 2>/dev/null || true
    iptables -D INPUT -p tcp --dport "$PROXY_PORT" ! -i lo -j DROP 2>/dev/null || true

    # Tambah rule iptables spesifik:
    # 1. Terima paket ke 8787 dan 8088 HANYA dari loopback (lo)
    iptables -I INPUT 1 -p tcp --dport "$MCP_PORT" -i lo -j ACCEPT -m comment --comment "MCP-SA1: loopback only"
    iptables -I INPUT 2 -p tcp --dport "$PROXY_PORT" -i lo -j ACCEPT -m comment --comment "PROXY-SA1: loopback only"

    # 2. Drop paket ke 8787 dan 8088 jika datang BUKAN dari lo
    iptables -I INPUT 3 -p tcp --dport "$MCP_PORT" ! -i lo -j DROP -m comment --comment "MCP-SA1: block public inbound"
    iptables -I INPUT 4 -p tcp --dport "$PROXY_PORT" ! -i lo -j DROP -m comment --comment "PROXY-SA1: block public inbound"

    # Terapkan juga untuk IPv6 jika ip6tables tersedia
    if command -v ip6tables >/dev/null 2>&1; then
        ip6tables -D INPUT -p tcp --dport "$MCP_PORT" -i lo -j ACCEPT 2>/dev/null || true
        ip6tables -D INPUT -p tcp --dport "$PROXY_PORT" -i lo -j ACCEPT 2>/dev/null || true
        ip6tables -D INPUT -p tcp --dport "$MCP_PORT" ! -i lo -j DROP 2>/dev/null || true
        ip6tables -D INPUT -p tcp --dport "$PROXY_PORT" ! -i lo -j DROP 2>/dev/null || true

        ip6tables -I INPUT 1 -p tcp --dport "$MCP_PORT" -i lo -j ACCEPT -m comment --comment "MCP-SA1: loopback only v6"
        ip6tables -I INPUT 2 -p tcp --dport "$PROXY_PORT" -i lo -j ACCEPT -m comment --comment "PROXY-SA1: loopback only v6"
        ip6tables -I INPUT 3 -p tcp --dport "$MCP_PORT" ! -i lo -j DROP -m comment --comment "MCP-SA1: block public inbound v6"
        ip6tables -I INPUT 4 -p tcp --dport "$PROXY_PORT" ! -i lo -j DROP -m comment --comment "PROXY-SA1: block public inbound v6"
    fi

    log_success "Aturan iptables & ip6tables berhasil diterapkan."
}

print_status() {
    echo ""
    log_info "Status Konfigurasi Firewall:"
    if [[ "$FIREWALL_BACKEND" == "ufw" ]]; then
        ufw status verbose | grep -E "($MCP_PORT|$PROXY_PORT|Status:)" || true
    fi
    echo ""
    log_info "Verifikasi iptables INPUT chain untuk port $MCP_PORT dan $PROXY_PORT:"
    iptables -L INPUT -v -n --line-numbers | grep -E "($MCP_PORT|$PROXY_PORT)" || true
    echo ""
    log_success "Hardening firewall selesai. Port $MCP_PORT dan $PROXY_PORT hanya dapat diakses melalui 127.0.0.1."
}

# --- Main Execution Flow ---
main() {
    echo "=========================================================="
    echo "  Zero-Trust Firewall Setup: Secure MCP Ingress (SA1)     "
    echo "=========================================================="
    
    check_root
    check_dependencies
    
    if [[ "$FIREWALL_BACKEND" == "ufw" ]]; then
        configure_ufw
    fi
    
    # Always enforce iptables rules as defense-in-depth layer
    configure_iptables
    
    verify_socket_bindings
    print_status
}

main "$@"
