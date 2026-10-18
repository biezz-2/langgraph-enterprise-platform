"""In-memory sliding window rate limiter for MCP Ingress.

Enforces 60 requests/minute per client ID or IP address using a sliding window log.
Returns HTTP 429 Too Many Requests when quota is exceeded.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: Dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def is_allowed(self, key: str, cost: int = 1) -> Tuple[bool, int, float]:
        """Check if request is allowed under the sliding window limit.

        Returns:
            (allowed: bool, current_count: int, retry_after: float)
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # Periodic cleanup of idle keys every 300 seconds
            if now - self._last_cleanup > 300.0:
                self._cleanup_stale_keys_locked(cutoff)
                self._last_cleanup = now

            timestamps = self._records[key]

            # Evict timestamps outside the sliding window
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            current_count = len(timestamps)

            if current_count + cost > self.max_requests:
                # Limit exceeded; calculate retry_after until oldest request expires
                oldest_timestamp = timestamps[0] if timestamps else cutoff
                retry_after = max(0.1, (oldest_timestamp + self.window_seconds) - now)
                return False, 0, retry_after

            # Allow request and append timestamp
            for _ in range(cost):
                timestamps.append(now)

            remaining = max(0, self.max_requests - (current_count + cost))
            return True, remaining, 0.0

    def get_remaining(self, key: str) -> int:
        """Returns remaining request quota for the key."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._records.get(key)
            if not timestamps:
                return self.max_requests
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            return max(0, self.max_requests - len(timestamps))

    def reset(self, key: Optional[str] = None) -> None:
        """Resets tracking records for a key or all keys."""
        with self._lock:
            if key is not None:
                self._records.pop(key, None)
            else:
                self._records.clear()

    def _cleanup_stale_keys_locked(self, cutoff: float) -> None:
        """Removes expired entries while lock is held."""
        empty_keys = []
        for key, timestamps in self._records.items():
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if not timestamps:
                empty_keys.append(key)
        for key in empty_keys:
            del self._records[key]


class RateLimiterMiddleware:
    """ASGI Middleware enforcing sliding window rate limiting."""

    def __init__(
        self,
        app: Any,
        limiter: Optional[SlidingWindowRateLimiter] = None,
        max_requests: int = 60,
        window_seconds: float = 60.0,
    ) -> None:
        self.app = app
        self.limiter = limiter or SlidingWindowRateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Exempt metadata discovery and internal health checks from rate limiting
        path = scope.get("path", "")
        if path.startswith("/.well-known/oauth-protected-resource"):
            await self.app(scope, receive, send)
            return

        client_key = self._resolve_client_key(scope)
        allowed, remaining, retry_after = self.limiter.is_allowed(client_key)
        retry_after_int = int(math.ceil(retry_after))

        if not allowed:
            response_body = json.dumps({
                "error": "too_many_requests",
                "message": f"Rate limit of {self.limiter.max_requests} requests per minute exceeded.",
                "retry_after_seconds": retry_after_int,
            }).encode("utf-8")

            headers = [
                (b"content-type", b"application/json"),
                (b"retry-after", str(retry_after_int).encode("ascii")),
                (b"x-ratelimit-limit", str(self.limiter.max_requests).encode("ascii")),
                (b"x-ratelimit-remaining", b"0"),
                (b"x-ratelimit-reset", str(retry_after_int).encode("ascii")),
            ]

            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": headers,
            })
            await send({
                "type": "http.response.body",
                "body": response_body,
            })
            return

        # Wrap send to inject rate limit headers on response
        async def send_with_headers(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                extra_headers = [
                    (b"x-ratelimit-limit", str(self.limiter.max_requests).encode("ascii")),
                    (b"x-ratelimit-remaining", str(remaining).encode("ascii")),
                ]
                headers = list(message.get("headers", [])) + extra_headers
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _resolve_client_key(self, scope: Dict[str, Any]) -> str:
        """Resolve client identifier based on state client_id, auth token, or IP."""
        # 1. State client_id if already authenticated upstream
        state = scope.get("state", {})
        if state.get("client_id"):
            return f"client:{state['client_id']}"

        # 2. Check Authorization header
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("latin1", errors="ignore")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()
            if raw_token:
                token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:16]
                return f"token:{token_hash}"

        # 3. Client IP (from X-Forwarded-For or ASGI client connection)
        x_forwarded = headers.get(b"x-forwarded-for", b"").decode("latin1", errors="ignore")
        if x_forwarded:
            ip = x_forwarded.split(",")[0].strip()
            if ip:
                return f"ip:{ip}"

        client_info = scope.get("client")
        if client_info and len(client_info) > 0 and client_info[0]:
            return f"ip:{client_info[0]}"

        return "client:unknown"
