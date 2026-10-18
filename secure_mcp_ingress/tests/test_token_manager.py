"""Unit tests for Token Management Engine (SA2)."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auth.token_manager import (
    DEFAULT_EXPIRY_DAYS,
    DEFAULT_RESOURCE_AUD,
    SUPPORTED_SCOPES,
    TokenManager,
    build_www_authenticate,
    verify_token,
)


class TestTokenManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = Path(self.temp_dir) / "tokens_test.json"
        self.tm = TokenManager(store_path=self.store_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_token_creation_and_hashing(self):
        raw_token, record = self.tm.create_token(
            client_id="claude-test",
            scopes=["memory:read", "tools:execute"],
            aud=DEFAULT_RESOURCE_AUD,
            description="Test client",
        )
        self.assertTrue(raw_token.startswith("mcp_"))
        self.assertEqual(len(raw_token), 47)  # "mcp_" (4) + 43 base64 chars for 32 bytes

        # Ensure plaintext token NOT in store
        with open(self.store_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertNotIn(raw_token, content)

        # Ensure SHA-256 hash is present
        expected_hash = self.tm.hash_token(raw_token)
        self.assertEqual(record["token_hash"], expected_hash)
        store_data = json.loads(content)
        self.assertIn(expected_hash, store_data["tokens"])

        # Check default 90 days expiry
        created_at = datetime.fromisoformat(record["created_at"])
        expires_at = datetime.fromisoformat(record["expires_at"])
        diff_days = (expires_at - created_at).days
        self.assertEqual(diff_days, DEFAULT_EXPIRY_DAYS)

    def test_unsupported_scope_rejected(self):
        with self.assertRaises(ValueError):
            self.tm.create_token(
                client_id="bad-client",
                scopes=["invalid:scope"],
            )

    def test_empty_client_rejected(self):
        with self.assertRaises(ValueError):
            self.tm.create_token(
                client_id="",
                scopes=["memory:read"],
            )

    def test_verify_token_success(self):
        raw_token, _ = self.tm.create_token(
            client_id="claude-verify",
            scopes=["memory:read", "memory:write"],
            aud=DEFAULT_RESOURCE_AUD,
        )
        # Valid with exact aud and scope
        valid, status, rec = self.tm.verify_token(
            token=raw_token,
            required_scope="memory:read",
            requested_aud=DEFAULT_RESOURCE_AUD,
        )
        self.assertTrue(valid)
        self.assertEqual(status, "valid")
        self.assertIsNotNone(rec)

    def test_verify_missing_or_invalid_token(self):
        # Empty
        valid, status, _ = self.tm.verify_token("")
        self.assertFalse(valid)
        self.assertEqual(status, "missing_token")

        # Fake token
        valid, status, _ = self.tm.verify_token("mcp_fake_token_value_that_does_not_exist")
        self.assertFalse(valid)
        self.assertEqual(status, "invalid_token")

    def test_verify_audience_mismatch(self):
        raw_token, _ = self.tm.create_token(
            client_id="claude-aud",
            scopes=["memory:read"],
            aud=DEFAULT_RESOURCE_AUD,
        )
        valid, status, _ = self.tm.verify_token(
            token=raw_token,
            requested_aud="https://other.domain.com/mcp",
        )
        self.assertFalse(valid)
        self.assertEqual(status, "audience_mismatch")

    def test_verify_insufficient_scope(self):
        raw_token, _ = self.tm.create_token(
            client_id="claude-scope",
            scopes=["memory:read"],
            aud=DEFAULT_RESOURCE_AUD,
        )
        valid, status, _ = self.tm.verify_token(
            token=raw_token,
            required_scope="tools:execute",
        )
        self.assertFalse(valid)
        self.assertEqual(status, "insufficient_scope")

    def test_token_expiration(self):
        # Create token expiring in negative days (already expired)
        raw_token, _ = self.tm.create_token(
            client_id="claude-expired",
            scopes=["memory:read"],
            expires_in_days=-1,
        )
        valid, status, _ = self.tm.verify_token(raw_token)
        self.assertFalse(valid)
        self.assertEqual(status, "expired_token")

    def test_token_rotation_and_grace_period(self):
        client = "rot-client"
        old_raw, old_rec = self.tm.create_token(client_id=client, scopes=["memory:read"])

        # Rotate token with 24 hours grace
        new_raw, new_hash, new_rec = self.tm.rotate_token(client_id=client, grace_hours=24)

        self.assertNotEqual(old_raw, new_raw)

        # Both new and old should be valid immediately
        valid_new, status_new, _ = self.tm.verify_token(new_raw)
        self.assertTrue(valid_new)
        self.assertEqual(status_new, "valid")

        valid_old, status_old, old_in_store = self.tm.verify_token(old_raw)
        self.assertTrue(valid_old)
        self.assertEqual(status_old, "valid")
        self.assertEqual(old_in_store["status"], "GRACE_PERIOD")
        self.assertEqual(old_in_store["rotated_to"], new_hash)

        # Simulate expired grace period on old token
        store = self.tm._read_store()
        store["tokens"][old_rec["token_hash"]]["grace_until"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        self.tm._write_store(store)

        valid_expired_grace, status_eg, _ = self.tm.verify_token(old_raw)
        self.assertFalse(valid_expired_grace)
        self.assertEqual(status_eg, "expired_token")

    def test_emergency_revocation(self):
        client = "emergency-client"
        raw1, rec1 = self.tm.create_token(client_id=client, scopes=["memory:read"])
        raw2, rec2 = self.tm.create_token(client_id=client, scopes=["tools:execute"])

        # Revoke single by hash
        self.tm.revoke_token(rec1["token_hash"], reason="Leak detected")
        valid1, status1, _ = self.tm.verify_token(raw1)
        self.assertFalse(valid1)
        self.assertEqual(status1, "revoked_token")

        # Second token still valid
        valid2, _, _ = self.tm.verify_token(raw2)
        self.assertTrue(valid2)

        # Revoke all for client
        count = self.tm.revoke_by_client_id(client, reason="Full breach")
        self.assertEqual(count, 1)

        valid2_after, status2, _ = self.tm.verify_token(raw2)
        self.assertFalse(valid2_after)
        self.assertEqual(status2, "revoked_token")

    def test_store_permissions(self):
        self.tm.create_token(client_id="perm-test", scopes=["memory:read"])
        st = os.stat(self.store_path)
        # Check permission mode (0600: user rw, group/other none)
        mode = oct(st.st_mode & 0o777)
        self.assertEqual(mode, "0o600")

    def test_build_www_authenticate(self):
        header = build_www_authenticate(
            error="invalid_token",
            error_description="The token is expired.",
            scope="memory:read",
        )
        self.assertIn('Bearer realm="https://mcp.domainanda.com/mcp"', header)
        self.assertIn('resource_metadata="https://mcp.domainanda.com/.well-known/oauth-protected-resource"', header)
        self.assertIn('error="invalid_token"', header)
        self.assertIn('error_description="The token is expired."', header)
        self.assertIn('scope="memory:read"', header)


if __name__ == "__main__":
    unittest.main()
