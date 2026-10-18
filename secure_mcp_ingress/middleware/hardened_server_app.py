"""Hardened Server Wrapper & Runner for Enterprise LangGraph Platform MCP.

Integrates:
1. RateLimiterMiddleware (In-Memory Sliding Window, 60 req/min)
2. AuthMiddleware (RFC 9728 & RFC 6750, Bearer token, Scope authorization)
3. InputSanitizerMiddleware (OWASP LLM Top 10 Injection & Traversal defense)
4. Enforced Localhost Binding (Strict 127.0.0.1 enforcement, 0.0.0.0 blocked)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

import uvicorn
from starlette.applications import Starlette

# Ensure local imports work
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

# Ensure root langgraph project is also available
_LGP_ROOT = _ROOT_DIR.parent
if str(_LGP_ROOT) not in sys.path:
    sys.path.insert(0, str(_LGP_ROOT))

from middleware.auth_middleware import AuthMiddleware, RESOURCE_METADATA_URI
from middleware.input_sanitizer import InputSanitizerMiddleware
from middleware.rate_limiter import RateLimiterMiddleware, SlidingWindowRateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("lgp.mcp.hardened_server")

ENFORCED_HOST = "127.0.0.1"


def enforce_localhost_host(requested_host: Optional[str]) -> str:
    """Enforce strict host binding to 127.0.0.1. Rejects external interfaces."""
    if not requested_host or requested_host.strip() == "":
        return ENFORCED_HOST

    clean_host = requested_host.strip()
    if clean_host != ENFORCED_HOST:
        logger.warning(
            "[SECURITY ENFORCEMENT] Requested host '%s' was rejected! "
            "Policy strictly mandates localhost-only binding (%s). Overriding host to %s.",
            clean_host,
            ENFORCED_HOST,
            ENFORCED_HOST,
        )
        return ENFORCED_HOST

    return ENFORCED_HOST


def get_base_mcp_server() -> Any:
    """Loads default Admin MCP server instance from apps.admin_mcp.mcp_server_cli."""
    try:
        from apps.admin_mcp.mcp_server_cli import mcp
        return mcp
    except Exception as exc:
        logger.warning(
            "Could not load AdminMCPServer from apps.admin_mcp (%s); creating standalone MCPServer",
            exc,
        )
        from mcp.server.mcpserver import MCPServer
        return MCPServer(
            name="Hardened LangGraph MCP Server",
            version="2.0.0",
            description="Secure ingress MCP server with OAuth2 and OWASP defenses",
        )


def create_hardened_app(
    base_app: Optional[Any] = None,
    mcp_server: Optional[Any] = None,
    transport: str = "streamable-http",
    port: int = 8787,
    rate_limit: int = 60,
    window_seconds: float = 60.0,
    auth_metadata_path: Optional[Path] = None,
) -> Any:
    """Assembles and wraps an MCP application with full security middleware stack.

    Stack execution order:
    1. RateLimiterMiddleware (sliding window: 60 req/min)
    2. AuthMiddleware (Bearer token validation, scope check, RFC 9728 401/403)
    3. InputSanitizerMiddleware (OWASP command/traversal/eval validation)
    4. Base MCP Starlette ASGI Application (bound to 127.0.0.1)
    """
    if base_app is None:
        target_server = mcp_server or get_base_mcp_server()
        try:
            from mcp.server.transport_security import TransportSecuritySettings
            sec_settings = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[
                    f"127.0.0.1:{port}",
                    f"localhost:{port}",
                    "127.0.0.1",
                    "localhost",
                ],
            )
        except Exception:
            sec_settings = None

        if transport == "sse":
            base_app = target_server.sse_app(
                transport_security=sec_settings,
                host=f"127.0.0.1:{port}",
            )
        else:
            base_app = target_server.streamable_http_app(
                transport_security=sec_settings,
                host=f"127.0.0.1:{port}",
            )

    # Wrap with security middleware stack
    app = InputSanitizerMiddleware(base_app)
    app = AuthMiddleware(app, metadata_path=auth_metadata_path)
    limiter = SlidingWindowRateLimiter(max_requests=rate_limit, window_seconds=window_seconds)
    app = RateLimiterMiddleware(app, limiter=limiter)

    return app


def run_hardened_server(
    host: str = ENFORCED_HOST,
    port: int = 8787,
    transport: str = "streamable-http",
    rate_limit: int = 60,
) -> None:
    """Starts the hardened MCP server enforcing 127.0.0.1 binding."""
    safe_host = enforce_localhost_host(host)

    logger.info(
        "Initializing Hardened MCP Server: transport=%s, host=%s, port=%d, rate_limit=%d/min",
        transport,
        safe_host,
        port,
        rate_limit,
    )

    if transport == "stdio":
        server = get_base_mcp_server()
        server.run("stdio")
        return

    app = create_hardened_app(
        transport=transport,
        port=port,
        rate_limit=rate_limit,
    )

    uvicorn.run(
        app,
        host=safe_host,
        port=port,
        access_log=True,
        log_level="info",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Secure Hardened LangGraph MCP Server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "sse", "stdio"],
        default=os.getenv("MCP_TRANSPORT", "streamable-http"),
        help="MCP transport protocol",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", ENFORCED_HOST),
        help=f"Host interface (strictly overridden to {ENFORCED_HOST} for security)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8787")),
        help="Port number (default: 8787)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=60,
        help="Sliding window rate limit requests per minute (default: 60)",
    )

    args = parser.parse_args()
    run_hardened_server(
        host=args.host,
        port=args.port,
        transport=args.transport,
        rate_limit=args.rate_limit,
    )
