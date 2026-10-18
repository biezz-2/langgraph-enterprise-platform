"""Authentication Middleware for Secure MCP Ingress.

Implements RFC 9728 and RFC 6750 compliant Bearer token verification,
scope-based authorization, and OAuth protected resource discovery metadata.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Ensure local imports work regardless of execution root
_INGRESS_ROOT = Path(__file__).resolve().parent.parent
if str(_INGRESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_INGRESS_ROOT))

try:
    from auth.token_manager import TokenManager, get_default_manager
except ImportError:
    # Graceful fallback if imported in different packaging context
    TokenManager = None  # type: ignore
    get_default_manager = None  # type: ignore

RESOURCE_METADATA_URI = "/.well-known/oauth-protected-resource"
DEFAULT_METADATA_PATH = _INGRESS_ROOT / "auth" / "protected_resource_metadata.json"

# Scope mappings for MCP tools
TOOL_SCOPE_MAP: Dict[str, str] = {
    # Memory Read Tools
    "memory_recall": "memory:read",
    "memory_list": "memory:read",
    "lgp_memory_query": "memory:read",
    "lgp_memory_organized_summary": "memory:read",
    "graph_query": "memory:read",
    "graph_stats": "memory:read",
    "lgp_graphiti_neuron_graph": "memory:read",
    # Memory Write Tools
    "memory_store": "memory:write",
    "memory_forget": "memory:write",
    "lgp_memory_store_fact": "memory:write",
    "lgp_memory_invalidate_fact": "memory:write",
    "lgp_memory_seed": "memory:write",
}


def get_required_scope_for_tool(tool_name: str) -> str:
    """Returns required OAuth scope for tool; defaults to 'tools:execute'."""
    return TOOL_SCOPE_MAP.get(tool_name, "tools:execute")


def get_required_scope_for_path(path: str, method: str) -> Optional[str]:
    """Returns required OAuth scope for REST endpoints, or None if exempt."""
    if path.startswith("/.well-known/"):
        return None
    if path in ("/health", "/api/health", "/ping", "/readyz", "/healthz"):
        return None
    if path.startswith("/api/memory"):
        return "memory:read" if method.upper() == "GET" else "memory:write"
    return "tools:execute"


class AuthMiddleware:
    """ASGI Middleware verifying Bearer tokens and enforcing scopes."""

    def __init__(
        self,
        app: Any,
        token_manager: Optional[TokenManager] = None,
        metadata_path: Optional[Path] = None,
    ) -> None:
        self.app = app
        if token_manager:
            self.token_manager = token_manager
        elif get_default_manager:
            self.token_manager = get_default_manager()
        else:
            raise RuntimeError("TokenManager is not available")

        self.metadata_path = metadata_path or DEFAULT_METADATA_PATH
        self._cached_metadata: Optional[bytes] = None

    def _get_metadata_bytes(self) -> bytes:
        if self._cached_metadata is None:
            if self.metadata_path.exists():
                with open(self.metadata_path, "rb") as f:
                    self._cached_metadata = f.read()
            else:
                self._cached_metadata = json.dumps({
                    "resource": "https://mcp.domainanda.com/mcp",
                    "authorization_servers": ["https://auth.domainanda.com"],
                    "scopes_supported": ["memory:read", "memory:write", "tools:execute"],
                    "bearer_methods_supported": ["header"],
                    "resource_metadata": RESOURCE_METADATA_URI,
                }).encode("utf-8")
        return self._cached_metadata

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        # 1. Unauthenticated RFC 9728 discovery endpoint
        if path == RESOURCE_METADATA_URI:
            meta_bytes = self._get_metadata_bytes()
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"access-control-allow-origin", b"*"),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": meta_bytes,
            })
            return

        # 2. Extract Bearer token from Authorization header
        raw_headers = dict(scope.get("headers", []))
        auth_header = raw_headers.get(b"authorization", b"").decode("latin1", errors="ignore").strip()

        if not auth_header or not auth_header.startswith("Bearer "):
            await self._send_unauthorized(send, reason="missing_or_malformed_token")
            return

        token_str = auth_header[7:].strip()
        if not token_str:
            await self._send_unauthorized(send, reason="empty_token")
            return

        # 3. Verify token with TokenManager
        is_valid, reason, record = self.token_manager.verify_token(token_str)
        if not is_valid or not record:
            await self._send_unauthorized(send, reason=reason)
            return

        client_id = record.get("client_id", "unknown")
        client_scopes: Set[str] = set(record.get("scopes", []))

        # Store authenticated context in ASGI state
        scope.setdefault("state", {})
        scope["state"]["client_id"] = client_id
        scope["state"]["scopes"] = list(client_scopes)
        scope["state"]["token_record"] = record

        # 4. Check scope authorization
        # Buffer body to inspect JSON-RPC tool calls for specific scope checks
        body_chunks: List[Dict[str, Any]] = []
        body_bytes = bytearray()
        more_body = True

        while more_body:
            message = await receive()
            body_chunks.append(message)
            body_bytes.extend(message.get("body", b""))
            more_body = message.get("more_body", False)

        required_scope: Optional[str] = None
        target_name = path

        if body_bytes:
            try:
                rpc_payload = json.loads(body_bytes.decode("utf-8"))
                if isinstance(rpc_payload, dict) and rpc_payload.get("method") == "tools/call":
                    tool_name = rpc_payload.get("params", {}).get("name", "")
                    target_name = f"tool:{tool_name}"
                    required_scope = get_required_scope_for_tool(tool_name)
            except Exception:
                pass

        if not required_scope:
            required_scope = get_required_scope_for_path(path, method)

        if required_scope and required_scope not in client_scopes:
            await self._send_forbidden(send, required_scope=required_scope, target=target_name, granted_scopes=client_scopes)
            return

        # Replay buffered body chunks to downstream
        replay_idx = 0
        async def replay_receive():
            nonlocal replay_idx
            if replay_idx < len(body_chunks):
                msg = body_chunks[replay_idx]
                replay_idx += 1
                return msg
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _send_unauthorized(self, send: Callable, reason: str = "invalid_token") -> None:
        """Returns 401 Unauthorized with RFC 9728 WWW-Authenticate challenge header."""
        header_val = (
            f'Bearer error="invalid_token", resource_metadata="{RESOURCE_METADATA_URI}"'
        ).encode("utf-8")

        body = json.dumps({
            "error": "unauthorized",
            "message": f"Authentication failed: {reason}",
            "resource_metadata": RESOURCE_METADATA_URI,
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"www-authenticate", header_val),
                (b"content-type", b"application/json"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    async def _send_forbidden(
        self, send: Callable, required_scope: str, target: str, granted_scopes: Set[str]
    ) -> None:
        """Returns 403 Forbidden with RFC 6750 & RFC 9728 WWW-Authenticate challenge header."""
        header_val = (
            f'Bearer error="insufficient_scope", scope="{required_scope}", resource_metadata="{RESOURCE_METADATA_URI}"'
        ).encode("utf-8")

        body = json.dumps({
            "error": "forbidden",
            "message": f"Client does not have required scope '{required_scope}' for '{target}'.",
            "required_scope": required_scope,
            "granted_scopes": sorted(list(granted_scopes)),
            "resource_metadata": RESOURCE_METADATA_URI,
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"www-authenticate", header_val),
                (b"content-type", b"application/json"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
