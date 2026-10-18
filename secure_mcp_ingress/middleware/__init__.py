"""Middleware package for Secure MCP Ingress.

Provides:
- AuthMiddleware (RFC 9728 & RFC 6750, 401/403, Bearer token & scope checking)
- InputSanitizer & InputSanitizerMiddleware (OWASP Top 10 for LLM protection)
- SlidingWindowRateLimiter & RateLimiterMiddleware (60 req/min sliding window)
- Hardened server app runner with enforced 127.0.0.1 localhost binding
"""

from middleware.auth_middleware import AuthMiddleware, RESOURCE_METADATA_URI
from middleware.hardened_server_app import (
    ENFORCED_HOST,
    create_hardened_app,
    enforce_localhost_host,
    run_hardened_server,
)
from middleware.input_sanitizer import (
    InputSanitizer,
    InputSanitizerMiddleware,
    SecurityValidationError,
    sanitize_tool_arguments,
)
from middleware.rate_limiter import RateLimiterMiddleware, SlidingWindowRateLimiter

__all__ = [
    "AuthMiddleware",
    "RESOURCE_METADATA_URI",
    "InputSanitizer",
    "InputSanitizerMiddleware",
    "SecurityValidationError",
    "sanitize_tool_arguments",
    "SlidingWindowRateLimiter",
    "RateLimiterMiddleware",
    "ENFORCED_HOST",
    "create_hardened_app",
    "enforce_localhost_host",
    "run_hardened_server",
]
