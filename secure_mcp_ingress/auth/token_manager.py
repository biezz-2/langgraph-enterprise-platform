"""Token Management Engine for Secure MCP Ingress.

Implements token generation, SHA-256 storage, audience and scope verification,
grace period expiration, and RFC 9728/6750 challenge builder.
"""

from __future__ import annotations

import hashlib
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, Optional

DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "tokens_store.json"
DEFAULT_RESOURCE_AUD = "https://mcp.domainanda.com/mcp"
DEFAULT_EXPIRY_DAYS = 90
DEFAULT_GRACE_HOURS = 24
SUPPORTED_SCOPES = {"memory:read", "memory:write", "tools:execute"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(iso_str: str) -> datetime:
    # Handles trailing 'Z' if present
    clean_str = iso_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean_str)


class TokenManager:
    """Manages secure access tokens for MCP Protected Resources."""

    def __init__(self, store_path: Optional[str | Path] = None) -> None:
        self.store_path = Path(store_path) if store_path else DEFAULT_STORE_PATH
        self._ensure_store_file()

    def _ensure_store_file(self) -> None:
        if not self.store_path.exists():
            initial_data = {
                "version": "1.0",
                "updated_at": _format_iso(_utc_now()),
                "tokens": {},
            }
            self._write_store(initial_data)

    def _read_store(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"version": "1.0", "updated_at": _format_iso(_utc_now()), "tokens": {}}
        with open(self.store_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_store(self, data: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _format_iso(_utc_now())

        # Atomic write via temporary file
        temp_path = self.store_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Restrict permissions (owner read/write only: 0600)
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass

        temp_path.replace(self.store_path)
        try:
            os.chmod(self.store_path, 0o600)
        except OSError:
            pass

    async def async_sync_token_to_supabase(self, record: dict[str, Any]) -> None:
        """Asynchronously upsert token to Supabase langgraph.ingress_tokens."""
        try:
            from packages.core.db import get_db_connection
            conn = await get_db_connection()
            upsert_sql = """
            INSERT INTO langgraph.ingress_tokens (
                token_hash, client_id, description, scopes, aud, status,
                created_at, expires_at, grace_until, rotated_to, revoked_at, revocation_reason, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
            ON CONFLICT (token_hash) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                description = EXCLUDED.description,
                scopes = EXCLUDED.scopes,
                aud = EXCLUDED.aud,
                status = EXCLUDED.status,
                expires_at = EXCLUDED.expires_at,
                grace_until = EXCLUDED.grace_until,
                rotated_to = EXCLUDED.rotated_to,
                revoked_at = EXCLUDED.revoked_at,
                revocation_reason = EXCLUDED.revocation_reason,
                updated_at = NOW();
            """
            scopes_json = json.dumps(record.get("scopes", []))
            created_at = datetime.fromisoformat(record["created_at"]) if record.get("created_at") else datetime.now(timezone.utc)
            expires_at = datetime.fromisoformat(record["expires_at"]) if record.get("expires_at") else datetime.now(timezone.utc)
            grace_until = datetime.fromisoformat(record["grace_until"]) if record.get("grace_until") else None
            revoked_at = datetime.fromisoformat(record["revoked_at"]) if record.get("revoked_at") else None

            async with conn.execute(
                upsert_sql,
                (
                    record["token_hash"],
                    record.get("client_id", ""),
                    record.get("description", ""),
                    scopes_json,
                    record.get("aud", ""),
                    record.get("status", "ACTIVE"),
                    created_at,
                    expires_at,
                    grace_until,
                    record.get("rotated_to"),
                    revoked_at,
                    record.get("revocation_reason"),
                )
            ):
                pass
            await conn.close()
        except Exception:
            pass

    def _sync_token_to_supabase(self, record: dict[str, Any]) -> None:
        """Best-effort upsert to Supabase langgraph.ingress_tokens."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.async_sync_token_to_supabase(record))
                return
        except RuntimeError:
            pass

        try:
            asyncio.run(self.async_sync_token_to_supabase(record))
        except Exception:
            pass

    def get_token(self, token_hash: str) -> Optional[dict[str, Any]]:
        """Retrieve token record by token_hash."""
        store = self._read_store()
        return store.get("tokens", {}).get(token_hash)

    @staticmethod
    def hash_token(token: str) -> str:
        """Computes SHA-256 digest of raw token string."""
        return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()

    def create_token(
        self,
        client_id: str,
        scopes: list[str],
        aud: str = DEFAULT_RESOURCE_AUD,
        description: str = "",
        expires_in_days: int = DEFAULT_EXPIRY_DAYS,
    ) -> tuple[str, dict[str, Any]]:
        """Generate a cryptographically secure token and store its SHA-256 hash."""
        if not client_id or not client_id.strip():
            raise ValueError("client_id cannot be empty")

        invalid_scopes = [s for s in scopes if s not in SUPPORTED_SCOPES]
        if invalid_scopes:
            raise ValueError(f"Unsupported scopes: {invalid_scopes}. Supported: {sorted(SUPPORTED_SCOPES)}")

        raw_token = f"mcp_{token_urlsafe(32)}"
        token_hash = self.hash_token(raw_token)
        now = _utc_now()
        expires_at = now + timedelta(days=expires_in_days)

        record: dict[str, Any] = {
            "token_hash": token_hash,
            "client_id": client_id.strip(),
            "description": description.strip(),
            "scopes": sorted(list(set(scopes))),
            "aud": aud.strip(),
            "created_at": _format_iso(now),
            "expires_at": _format_iso(expires_at),
            "status": "ACTIVE",
            "grace_until": None,
            "rotated_to": None,
            "revoked_at": None,
            "revocation_reason": None,
        }

        store = self._read_store()
        store["tokens"][token_hash] = record
        self._write_store(store)
        self._sync_token_to_supabase(record)

        return raw_token, record

    def verify_token(
        self,
        token: Optional[str],
        required_scope: Optional[str] = None,
        requested_aud: Optional[str] = None,
    ) -> tuple[bool, str, Optional[dict[str, Any]]]:
        """Verify token authenticity, status, expiration, audience match, and scope."""
        if not token or not token.strip():
            return False, "missing_token", None

        token_hash = self.hash_token(token)
        store = self._read_store()
        record = store.get("tokens", {}).get(token_hash)

        if not record:
            return False, "invalid_token", None

        status = record.get("status")
        if status == "REVOKED":
            return False, "revoked_token", record

        now = _utc_now()
        if status == "GRACE_PERIOD":
            grace_until_str = record.get("grace_until")
            if not grace_until_str:
                return False, "expired_token", record
            grace_until = _parse_iso(grace_until_str)
            if now > grace_until:
                return False, "expired_token", record
        else:
            expires_at_str = record.get("expires_at")
            if not expires_at_str:
                return False, "expired_token", record
            expires_at = _parse_iso(expires_at_str)
            if now > expires_at:
                return False, "expired_token", record

        # Audience verification (RFC 8707)
        if requested_aud:
            token_aud = record.get("aud")
            if token_aud != requested_aud:
                return False, "audience_mismatch", record

        # Scope verification
        if required_scope:
            token_scopes = record.get("scopes", [])
            if required_scope not in token_scopes:
                return False, "insufficient_scope", record

        return True, "valid", record

    def revoke_token(self, token_hash: str, reason: str = "manual_revocation") -> bool:
        """Revoke a token immediately by its SHA-256 hash."""
        store = self._read_store()
        record = store.get("tokens", {}).get(token_hash)
        if not record:
            return False

        record["status"] = "REVOKED"
        record["revoked_at"] = _format_iso(_utc_now())
        record["revocation_reason"] = reason
        self._write_store(store)
        self._sync_token_to_supabase(record)
        return True

    def revoke_by_token(self, raw_token: str, reason: str = "manual_revocation") -> bool:
        """Revoke a token immediately by its plaintext raw value."""
        return self.revoke_token(self.hash_token(raw_token), reason=reason)

    def revoke_by_client_id(self, client_id: str, reason: str = "client_emergency_revocation") -> int:
        """Emergency revoke all active or grace tokens belonging to client_id."""
        store = self._read_store()
        count = 0
        now_str = _format_iso(_utc_now())
        mutated_records = []
        for record in store.get("tokens", {}).values():
            if record.get("client_id") == client_id and record.get("status") in {"ACTIVE", "GRACE_PERIOD"}:
                record["status"] = "REVOKED"
                record["revoked_at"] = now_str
                record["revocation_reason"] = reason
                mutated_records.append(record)
                count += 1
        if count > 0:
            self._write_store(store)
            for rec in mutated_records:
                self._sync_token_to_supabase(rec)
        return count

    def rotate_token(
        self,
        client_id: str,
        old_token_hash: Optional[str] = None,
        grace_hours: int = DEFAULT_GRACE_HOURS,
        expires_in_days: int = DEFAULT_EXPIRY_DAYS,
    ) -> tuple[str, str, dict[str, Any]]:
        """Rotate token: creates new token and marks old token into GRACE_PERIOD."""
        store = self._read_store()
        tokens = store.get("tokens", {})

        target_records: list[tuple[str, dict[str, Any]]] = []
        if old_token_hash:
            if old_token_hash in tokens and tokens[old_token_hash].get("client_id") == client_id:
                target_records.append((old_token_hash, tokens[old_token_hash]))
            else:
                raise ValueError(f"Token hash {old_token_hash} not found for client_id {client_id}")
        else:
            for h, rec in tokens.items():
                if rec.get("client_id") == client_id and rec.get("status") == "ACTIVE":
                    target_records.append((h, rec))

        if not target_records:
            raise ValueError(f"No active tokens found to rotate for client_id: {client_id}")

        # Preserve scopes and audience from primary active token
        base_record = target_records[0][1]
        scopes = base_record.get("scopes", ["memory:read"])
        aud = base_record.get("aud", DEFAULT_RESOURCE_AUD)
        description = f"Rotated replacement for {client_id}"

        new_raw_token, new_record = self.create_token(
            client_id=client_id,
            scopes=scopes,
            aud=aud,
            description=description,
            expires_in_days=expires_in_days,
        )
        new_hash = new_record["token_hash"]

        now = _utc_now()
        grace_until = _format_iso(now + timedelta(hours=grace_hours))

        # Re-read store to mutate target records
        store = self._read_store()
        for h, _ in target_records:
            if h in store.get("tokens", {}):
                store["tokens"][h]["status"] = "GRACE_PERIOD"
                store["tokens"][h]["grace_until"] = grace_until
                store["tokens"][h]["rotated_to"] = new_hash

        self._write_store(store)
        for h, _ in target_records:
            if h in store.get("tokens", {}):
                self._sync_token_to_supabase(store["tokens"][h])

        return new_raw_token, new_hash, new_record

    def list_tokens(self, client_id: Optional[str] = None) -> list[dict[str, Any]]:
        """List token summaries without revealing sensitive material."""
        store = self._read_store()
        tokens = list(store.get("tokens", {}).values())
        if client_id:
            tokens = [t for t in tokens if t.get("client_id") == client_id]
        return tokens


# Module-level instance and helpers
_default_manager: Optional[TokenManager] = None


def get_default_manager() -> TokenManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = TokenManager()
    return _default_manager


def verify_token(
    token: Optional[str],
    required_scope: Optional[str] = None,
    requested_aud: Optional[str] = None,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Helper for validating tokens with default store."""
    return get_default_manager().verify_token(
        token=token,
        required_scope=required_scope,
        requested_aud=requested_aud,
    )


def build_www_authenticate(
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    scope: Optional[str] = None,
    realm: str = DEFAULT_RESOURCE_AUD,
    resource_metadata: str = "https://mcp.domainanda.com/.well-known/oauth-protected-resource",
) -> str:
    """Builds RFC 9728 & RFC 6750 compliant WWW-Authenticate challenge header value."""
    parts = [f'Bearer realm="{realm}"', f'resource_metadata="{resource_metadata}"']
    if error:
        parts.append(f'error="{error}"')
    if error_description:
        # Sanitize double quotes inside description
        clean_desc = error_description.replace('"', "'")
        parts.append(f'error_description="{clean_desc}"')
    if scope:
        parts.append(f'scope="{scope}"')
    return ", ".join(parts)
