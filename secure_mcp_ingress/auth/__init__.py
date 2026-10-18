"""Auth package for Secure MCP Ingress."""

try:
    from .token_manager import (
        DEFAULT_EXPIRY_DAYS,
        DEFAULT_GRACE_HOURS,
        DEFAULT_RESOURCE_AUD,
        SUPPORTED_SCOPES,
        TokenManager,
        build_www_authenticate,
        get_default_manager,
        verify_token,
    )
except ImportError:
    from auth.token_manager import (
        DEFAULT_EXPIRY_DAYS,
        DEFAULT_GRACE_HOURS,
        DEFAULT_RESOURCE_AUD,
        SUPPORTED_SCOPES,
        TokenManager,
        build_www_authenticate,
        get_default_manager,
        verify_token,
    )

__all__ = [
    "TokenManager",
    "verify_token",
    "build_www_authenticate",
    "get_default_manager",
    "DEFAULT_RESOURCE_AUD",
    "DEFAULT_EXPIRY_DAYS",
    "DEFAULT_GRACE_HOURS",
    "SUPPORTED_SCOPES",
]
