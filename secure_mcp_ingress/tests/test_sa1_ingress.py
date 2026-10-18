#!/usr/bin/env python3
"""
Unit and Contract Tests for SA1 (Ingress & Network Architecture) Artifacts.
"""

import json
import os
import unittest
from pathlib import Path

BASE_DIR = Path("/home/biezz/Documents/Project/coding/langgraph/secure_mcp_ingress")

class TestSA1Artifacts(unittest.TestCase):
    def setUp(self):
        self.config_dir = BASE_DIR / "config"
        self.docs_dir = BASE_DIR / "docs"

    def test_cloudflared_config_structure(self):
        cfg_file = self.config_dir / "cloudflared_config.yml"
        self.assertTrue(cfg_file.exists(), "cloudflared_config.yml harus ada")
        content = cfg_file.read_text(encoding="utf-8")

        # Ingress hostname check
        self.assertIn("hostname: mcp.domainanda.com", content)
        # Backend target check
        self.assertTrue(
            "service: http://127.0.0.1:8088" in content or "service: http://127.0.0.1:8787" in content,
            "Target ingress harus mengarah ke loopback 127.0.0.1:8088 atau 127.0.0.1:8787"
        )
        # Catch-all 404
        self.assertIn("service: http_status:404", content)
        # Transport settings
        self.assertIn("keepAliveTimeout: 90s", content)
        self.assertIn("noTLSVerify: false", content)

    def test_systemd_service_hardening(self):
        svc_file = self.config_dir / "cloudflared.service"
        self.assertTrue(svc_file.exists(), "cloudflared.service harus ada")
        content = svc_file.read_text(encoding="utf-8")

        self.assertIn("ExecStart=", content)
        self.assertIn("tunnel run", content)
        self.assertIn("NoNewPrivileges=yes", content)
        self.assertIn("ProtectSystem=full", content)
        self.assertIn("RestrictSUIDSGID=true", content)
        self.assertIn("Restart=on-failure", content)

    def test_firewall_setup_script(self):
        sh_file = self.config_dir / "setup_firewall.sh"
        self.assertTrue(sh_file.exists(), "setup_firewall.sh harus ada")
        self.assertTrue(os.access(sh_file, os.X_OK), "setup_firewall.sh harus executable (+x)")
        
        content = sh_file.read_text(encoding="utf-8")
        self.assertIn("8787", content)
        self.assertIn("8088", content)
        self.assertIn("127.0.0.1", content)
        self.assertTrue("DROP" in content or "deny" in content)

    def test_cloudflare_access_policy_json(self):
        json_file = self.config_dir / "cloudflare_access_policy.json"
        self.assertTrue(json_file.exists(), "cloudflare_access_policy.json harus ada")
        
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        cf_access = data.get("cloudflare_access", {})
        app = cf_access.get("application", {})
        self.assertEqual(app.get("domain"), "mcp.domainanda.com")

        # Service Token header specification
        token_spec = cf_access.get("service_token_specification", {})
        headers = token_spec.get("header_mapping", {})
        self.assertEqual(headers.get("client_id_header"), "CF-Access-Client-Id")
        self.assertEqual(headers.get("client_secret_header"), "CF-Access-Client-Secret")

        # WAF and DDoS rules
        self.assertIn("edge_waf_rules", data)
        self.assertGreater(len(data["edge_waf_rules"]), 0)
        self.assertIn("rate_limiting_and_ddos", data)

    def test_ingress_spec_document(self):
        doc_file = self.docs_dir / "SA1_INGRESS_SPEC.md"
        self.assertTrue(doc_file.exists(), "SA1_INGRESS_SPEC.md harus ada")
        content = doc_file.read_text(encoding="utf-8")
        
        self.assertIn("CF-Access-Client-Id", content)
        self.assertIn("CF-Access-Client-Secret", content)
        self.assertIn("127.0.0.1", content)
        self.assertIn("WAF", content)
        self.assertIn("Rate Limiting", content)

if __name__ == "__main__":
    unittest.main()
