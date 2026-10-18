#!/usr/bin/env python3
"""
Test Suite for Nginx MCP Reverse Proxy & SSE Streaming (SA4)
Validates:
1. Static configuration syntax and mandatory directives (buffering off, keepalive, 3600s timeouts, limit_req_zone).
2. RFC 9728 OAuth 2.0 Protected Resource Metadata schema and static serving.
3. Live SSE stream latency (verifying zero-buffering / immediate chunk delivery).
4. Long-lived keepalive connection handling.
5. Structured JSON access logging and zero token leakage (Bearer redaction).
6. Internal healthcheck endpoint.
"""

import http.client
import http.server
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_DIR, "config")
AUTH_DIR = os.path.join(PROJECT_DIR, "auth")

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

class MockSSEHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def send_chunk(self, data: bytes):
        chunk_header = f"{len(data):X}\r\n".encode("utf-8")
        self.wfile.write(chunk_header + data + b"\r\n")
        self.wfile.flush()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/sse/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # Emit 5 events with 100ms interval
            for i in range(5):
                payload = f"id: {i}\nevent: message\ndata: {{\"step\": {i}, \"ts\": {time.time():.4f}}}\n\n".encode("utf-8")
                self.send_chunk(payload)
                time.sleep(0.1)

            # End of chunked stream
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

        elif parsed.path == "/sse/keepalive":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            # Emit keepalive comments over 600ms
            for i in range(3):
                comment = f": keepalive ping {i}\n\n".encode("utf-8")
                self.send_chunk(comment)
                time.sleep(0.2)

            self.send_chunk(b"event: close\ndata: complete\n\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

        elif parsed.path == "/test/auth":
            body = b'{"status":"authenticated"}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            body = b"Not Found"
            self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

def test_config_directives():
    print("[TEST 1/5] Checking Nginx configuration directives...")
    mcp_conf_path = os.path.join(CONFIG_DIR, "nginx_mcp.conf")
    json_conf_path = os.path.join(CONFIG_DIR, "nginx_json_logging.conf")

    with open(mcp_conf_path, "r") as f:
        mcp_conf = f.read()

    with open(json_conf_path, "r") as f:
        json_conf = f.read()

    # Mandatory SSE directives
    assert "proxy_buffering off;" in mcp_conf, "Missing 'proxy_buffering off;'"
    assert "proxy_cache off;" in mcp_conf, "Missing 'proxy_cache off;'"
    assert "proxy_read_timeout 3600s;" in mcp_conf, "Missing 'proxy_read_timeout 3600s;'"
    assert "proxy_send_timeout 3600s;" in mcp_conf, "Missing 'proxy_send_timeout 3600s;'"
    assert "proxy_http_version 1.1;" in mcp_conf, "Missing 'proxy_http_version 1.1;'"
    assert 'proxy_set_header Connection "";' in mcp_conf, 'Missing Connection "" header'
    assert "proxy_set_header Host $host;" in mcp_conf, "Missing Host header"
    assert "proxy_set_header X-Real-IP $remote_addr;" in mcp_conf, "Missing X-Real-IP header"
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in mcp_conf, "Missing X-Forwarded-For"

    # Rate limiting zone
    assert "limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=30r/s;" in mcp_conf, "Missing rate limit zone"

    # Endpoints
    assert "location = /.well-known/oauth-protected-resource" in mcp_conf, "Missing RFC 9728 endpoint"
    assert "location = /health" in mcp_conf, "Missing /health endpoint"

    # JSON logging directives
    assert "log_format mcp_json" in json_conf, "Missing log_format mcp_json"
    assert '"timestamp":' in json_conf, "Missing timestamp in json log"
    assert '"remote_addr":' in json_conf, "Missing remote_addr in json log"
    assert '"client_id":' in json_conf, "Missing client_id in json log"
    assert '"status":' in json_conf, "Missing status in json log"
    assert '"request_time":' in json_conf, "Missing request_time in json log"
    assert '"request_uri":' in json_conf, "Missing request_uri in json log"

    # Token Redaction verification: ensure raw $http_authorization is NOT logged
    assert "$http_authorization" not in json_conf.split("log_format")[1], \
        "SECURITY LEAK: $http_authorization must not be present in log_format"

    print("  -> PASSED: All Nginx & JSON logging directives verified.")

def test_rfc9728_metadata_schema():
    print("[TEST 2/5] Checking RFC 9728 OAuth Protected Resource Metadata schema...")
    meta_path = os.path.join(AUTH_DIR, "protected_resource_metadata.json")
    assert os.path.exists(meta_path), f"File not found: {meta_path}"

    with open(meta_path, "r") as f:
        meta = json.load(f)

    assert "resource" in meta, "Missing 'resource' in RFC 9728 metadata"
    assert "authorization_servers" in meta and isinstance(meta["authorization_servers"], list), \
        "Missing or invalid 'authorization_servers'"
    assert "bearer_methods_supported" in meta and "header" in meta["bearer_methods_supported"], \
        "Missing 'bearer_methods_supported' containing 'header'"

    print("  -> PASSED: RFC 9728 JSON schema matches specifications.")

def run_live_tests():
    print("[TEST 3/5, 4/5, 5/5] Executing Live Streaming, Keepalive, and Observability Tests...")
    upstream_port = get_free_port()
    proxy_port = get_free_port()

    # Start mock SSE server
    server = socketserver.TCPServer(("127.0.0.1", upstream_port), MockSSEHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    container_name = f"test-mcp-proxy-{proxy_port}"

    # Generate temporary Nginx configuration pointing to mock upstream port
    test_conf_dir = os.path.join(CONFIG_DIR, ".test_runtime")
    os.makedirs(test_conf_dir, exist_ok=True)
    test_mcp_conf_path = os.path.join(test_conf_dir, "nginx_mcp.conf")

    with open(os.path.join(CONFIG_DIR, "nginx_mcp.conf"), "r") as f:
        conf_content = f.read()

    # Replace upstream port and listening port for isolation
    conf_content = conf_content.replace("server 127.0.0.1:8787;", f"server 127.0.0.1:{upstream_port};")
    conf_content = conf_content.replace("listen 8088 default_server;", f"listen {proxy_port} default_server;")
    conf_content = conf_content.replace("listen [::]:8088 default_server;", f"listen [::]:{proxy_port} default_server;")

    with open(test_mcp_conf_path, "w") as f:
        f.write(conf_content)

    # Start test Nginx container
    docker_cmd = [
        "docker", "run", "-d", "--rm",
        "--name", container_name,
        "--network", "host",
        "-v", f"{os.path.join(CONFIG_DIR, 'nginx_json_logging.conf')}:/etc/nginx/conf.d/00_nginx_json_logging.conf:ro",
        "-v", f"{test_mcp_conf_path}:/etc/nginx/conf.d/nginx_mcp.conf:ro",
        "-v", f"{os.path.join(AUTH_DIR, 'protected_resource_metadata.json')}:/etc/nginx/auth/protected_resource_metadata.json:ro",
        "secure-mcp-nginx-proxy:latest"
    ]

    subprocess.run(docker_cmd, check=True, capture_output=True)

    # Wait for container readiness
    ready = False
    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", proxy_port), timeout=0.5):
                ready = True
                break
        except (socket.error, ConnectionRefusedError):
            time.sleep(0.1)

    assert ready, f"Nginx test container failed to listen on port {proxy_port}"

    try:
        # TEST 3: Healthcheck & RFC 9728 Static Serving
        print("  -> Testing /health endpoint...")
        conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        assert resp.status == 200, f"/health returned status {resp.status}"
        health_data = json.loads(resp.read().decode())
        assert health_data.get("status") == "ok", f"Unexpected health response: {health_data}"
        conn.close()

        print("  -> Testing /.well-known/oauth-protected-resource...")
        conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=5)
        conn.request("GET", "/.well-known/oauth-protected-resource")
        resp = conn.getresponse()
        assert resp.status == 200, f"Metadata returned status {resp.status}"
        assert resp.getheader("Access-Control-Allow-Origin") == "*", "Missing CORS header"
        meta_data = json.loads(resp.read().decode())
        assert "resource" in meta_data, "Metadata missing 'resource'"
        conn.close()

        # TEST 4: SSE Stream Latency & Zero-Buffering
        print("  -> Testing SSE stream latency & zero-buffering...")
        conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=10)
        conn.request("GET", "/sse/stream", headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        assert resp.status == 200, f"SSE stream returned {resp.status}"
        assert "text/event-stream" in resp.getheader("Content-Type", "")

        events_received = 0
        arrival_times = []
        start_time = time.time()

        while events_received < 5 and (time.time() - start_time) < 5:
            line = resp.readline()
            if not line:
                break
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data:"):
                arrival_times.append(time.time())
                events_received += 1

        conn.close()

        assert events_received == 5, f"Expected 5 events, received {events_received}"

        # Calculate inter-arrival intervals
        intervals = [arrival_times[i] - arrival_times[i-1] for i in range(1, len(arrival_times))]
        for idx, interval in enumerate(intervals):
            assert 0.05 <= interval <= 0.25, \
                f"Buffering detected on event {idx+1}: interval was {interval:.3f}s (expected ~0.10s)"

        print(f"  -> PASSED: Zero buffering verified! Intervals: {[round(i, 3) for i in intervals]}")

        # TEST 5: Keepalive Stream Handling
        print("  -> Testing SSE keepalive ping reception...")
        conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=10)
        conn.request("GET", "/sse/keepalive", headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        assert resp.status == 200

        keepalive_comments = 0
        stream_closed = False
        t_start = time.time()
        while (time.time() - t_start) < 4:
            line = resp.readline()
            if not line:
                break
            line_str = line.decode("utf-8").strip()
            if line_str.startswith(": keepalive ping"):
                keepalive_comments += 1
            elif line_str == "data: complete":
                stream_closed = True
                break

        conn.close()
        assert keepalive_comments == 3, f"Expected 3 keepalive pings, got {keepalive_comments}"
        assert stream_closed, "Stream did not complete as expected"
        print("  -> PASSED: Keepalive stream delivered pings without connection drops.")

        # TEST 6: Structured JSON Logging & Token Leakage Prevention
        print("  -> Testing structured JSON logging and token redaction...")
        conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=10)
        secret_token = "secret-token-xyz-never-leak-999"
        client_tag = "sa4-test-client-agent"

        conn.request(
            "GET",
            "/test/auth",
            headers={
                "Authorization": f"Bearer {secret_token}",
                "X-Client-Id": client_tag
            }
        )
        resp = conn.getresponse()
        assert resp.status == 200
        resp.read()
        conn.close()

        # Check Docker container logs
        time.sleep(0.5)
        log_proc = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
        container_logs = log_proc.stdout + log_proc.stderr

        # Security assertion: Token must NOT be in logs
        assert secret_token not in container_logs, \
            "SECURITY BREACH: Bearer token found in Nginx access logs!"

        # Structured JSON assertion: client_id and required fields
        found_target_log = False
        for line in container_logs.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                log_entry = json.loads(line)
                if log_entry.get("client_id") == client_tag and log_entry.get("request_uri") == "/test/auth":
                    found_target_log = True
                    assert "timestamp" in log_entry, "Missing 'timestamp' in JSON log"
                    assert "remote_addr" in log_entry, "Missing 'remote_addr' in JSON log"
                    assert "status" in log_entry, "Missing 'status' in JSON log"
                    assert "request_time" in log_entry, "Missing 'request_time' in JSON log"
                    assert log_entry["status"] == 200, f"Expected status 200, got {log_entry['status']}"
                    break
            except json.JSONDecodeError:
                continue

        assert found_target_log, "Target JSON access log entry with client_id not found in Nginx output"
        print("  -> PASSED: Structured JSON access logging verified (zero token leakage).")

    finally:
        # Cleanup container and mock server
        subprocess.run(["docker", "stop", container_name], capture_output=True)
        server.shutdown()
        # Clean temporary test configuration
        if os.path.exists(test_mcp_conf_path):
            os.remove(test_mcp_conf_path)
        if os.path.exists(test_conf_dir):
            os.rmdir(test_conf_dir)

if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING MCP REVERSE PROXY & SSE STREAMING TEST SUITE")
    print("=" * 70)
    try:
        test_config_directives()
        test_rfc9728_metadata_schema()
        run_live_tests()
        print("=" * 70)
        print("ALL TESTS PASSED SUCCESSFULLY (5/5)")
        print("=" * 70)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[FAILURE] Assertion failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Test suite raised unexpected exception: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
