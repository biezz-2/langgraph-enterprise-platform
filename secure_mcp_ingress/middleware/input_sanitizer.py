"""OWASP LLM Top 10 Input Validator & Sanitizer.

Detects and mitigates:
- Command injection patterns (; rm -rf, curl | bash, $())
- Path traversal (../, ..\\, /etc/passwd, %2e%2e, etc.)
- Arbitrary code execution / eval / exec (eval(), exec(), os.system(), __import__)
- LLM prompt injection (system prompt override, jailbreak markers)
- Null byte poisoning and control character corruption
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple


class SecurityValidationError(Exception):
    """Raised when malicious or unsafe payload patterns are detected."""
    pass


# 1. Path Traversal Patterns
PATH_TRAVERSAL_REGEX = re.compile(
    r"""
    (?:\.\.[/\\])                         |
    (?:\.\.%2[fF])                        |
    (?:\.\.%5[cC])                        |
    (?:%2[eE]%2[eE](?:%2[fF]|%5[cC]|/|\\))|
    (?:/(?:etc/(?:passwd|shadow|sudoers|hosts)|proc/self|sys/kernel)) |
    (?:\\(?:windows[/\\](?:system32|win\.ini)))                        |
    (?:\.ssh[/\\].*id_)                   |
    (?:\.env\b)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# 2. Command Injection Patterns
COMMAND_INJECTION_REGEX = re.compile(
    r"""
    (?:[;&|`]\s*(?:rm\s+-rf|curl|wget|chmod|chown|mkfifo|ncat|netcat|powershell|cmd\.exe|bash|sh|zsh|kill|reboot)) |
    (?:\|\s*(?:ba)?sh)                                        |
    (?:\`[^\`]+\`)                                            |
    (?:\$\([^\)]+\))                                          |
    (?:\$\{[^\}]+\})                                          |
    (?:(?:^|[;&|`\s])(?:nc|netcat)\s+.*-e\s+)                 |
    (?:(?:^|[;&|`\s])(?:rm\s+-rf\s+(?:/|~|\*)))              |
    (?:/bin/(?:ba)?sh\s+-c)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# 3. Code Execution / Eval / Exec Patterns
EVAL_EXEC_REGEX = re.compile(
    r"""
    (?:\b(?:eval|exec|compile|__import__|importlib)\s*\()             |
    (?:\b(?:os\.(?:system|popen|spawn|exec\w*)|subprocess\.(?:Popen|run|call|check_output))\s*\() |
    (?:\b(?:pty\.spawn)\s*\()                                         |
    (?:\b(?:globals|locals)\s*\(\s*\))                               |
    (?:\b__builtins__\b)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# 4. OWASP LLM01: Prompt Injection / System Prompt Tampering
PROMPT_INJECTION_REGEX = re.compile(
    r"""
    (?:\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b)  |
    (?:\bsystem\s+prompt\s+override\b)                              |
    (?:\bdisregard\s+(?:all\s+)?instructions\b)                     |
    (?:\byou\s+are\s+now\s+(?:in\s+DAN\s+mode|unrestricted|an?\s+unfiltered)\b) |
    (?:\bbypass\s+(?:all\s+)?safety\s+filters?\b)                   |
    (?:\boutput\s+the\s+system\s+prompt\b)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Dangerous control chars to strip (allow newline \n, return \r, tab \t)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputSanitizer:
    """OWASP-compliant input validator and sanitizer."""

    def __init__(self, max_depth: int = 10, max_str_length: int = 250000) -> None:
        self.max_depth = max_depth
        self.max_str_length = max_str_length

    def sanitize_string(self, text: str) -> str:
        """Strip null bytes and non-printable control characters, normalize NFKC."""
        if not isinstance(text, str):
            return text
        # Remove null bytes immediately
        cleaned = text.replace("\x00", "")
        # Remove illegal control chars
        cleaned = CONTROL_CHAR_REGEX.sub("", cleaned)
        # Normalize Unicode to prevent normalization bypasses
        return unicodedata.normalize("NFKC", cleaned)

    def scan_string_for_threats(self, text: str) -> Optional[str]:
        """Scans string for path traversal, command injection, eval/exec, and prompt injection."""
        if not text or not isinstance(text, str):
            return None

        # 1. Check command injection
        match = COMMAND_INJECTION_REGEX.search(text)
        if match:
            return f"Command injection pattern detected: '{match.group(0)}'"

        # 2. Check eval / code execution
        match = EVAL_EXEC_REGEX.search(text)
        if match:
            return f"Dangerous code execution pattern detected: '{match.group(0)}'"

        # 3. Check OWASP LLM01 prompt injection
        match = PROMPT_INJECTION_REGEX.search(text)
        if match:
            return f"Prompt injection pattern detected: '{match.group(0)}'"

        # 4. Check path traversal (raw and double URL-decoded)
        unquoted = urllib.parse.unquote(urllib.parse.unquote(text))
        match = PATH_TRAVERSAL_REGEX.search(text) or PATH_TRAVERSAL_REGEX.search(unquoted)
        if match:
            return f"Path traversal attempt detected: '{match.group(0)}'"

        return None

    def validate_and_sanitize(
        self, data: Any, current_depth: int = 0
    ) -> Tuple[bool, Optional[str], Any]:
        """Recursively validates and sanitizes arbitrary JSON-like structures.

        Returns:
            (is_valid: bool, error_message: Optional[str], sanitized_data: Any)
        """
        if current_depth > self.max_depth:
            return False, f"Maximum JSON nesting depth ({self.max_depth}) exceeded", data

        if isinstance(data, str):
            if len(data) > self.max_str_length:
                return False, f"String exceeds maximum allowed length ({self.max_str_length})", data
            threat = self.scan_string_for_threats(data)
            if threat:
                return False, threat, data
            return True, None, self.sanitize_string(data)

        elif isinstance(data, dict):
            sanitized_dict: Dict[str, Any] = {}
            for k, v in data.items():
                if not isinstance(k, str):
                    return False, f"Dictionary key must be string, got {type(k).__name__}", data
                clean_key = self.sanitize_string(k)
                key_threat = self.scan_string_for_threats(clean_key)
                if key_threat:
                    return False, f"Key contains security violation: {key_threat}", data

                valid, err, clean_val = self.validate_and_sanitize(v, current_depth + 1)
                if not valid:
                    return False, err, data
                sanitized_dict[clean_key] = clean_val
            return True, None, sanitized_dict

        elif isinstance(data, list):
            sanitized_list: List[Any] = []
            for item in data:
                valid, err, clean_item = self.validate_and_sanitize(item, current_depth + 1)
                if not valid:
                    return False, err, data
                sanitized_list.append(clean_item)
            return True, None, sanitized_list

        elif isinstance(data, (int, float, bool)) or data is None:
            return True, None, data

        else:
            return False, f"Unsupported data type in payload: {type(data).__name__}", data

    def sanitize_tool_arguments(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Validates and sanitizes tool arguments before execution in LangGraph."""
        if not isinstance(arguments, dict):
            return False, "Tool arguments must be a dictionary/object", {}

        clean_tool_name = self.sanitize_string(tool_name)
        tool_threat = self.scan_string_for_threats(clean_tool_name)
        if tool_threat:
            return False, f"Tool name security violation: {tool_threat}", {}

        valid, err, sanitized_args = self.validate_and_sanitize(arguments)
        if not valid:
            return False, err, {}

        return True, None, sanitized_args


# Module-level singleton
_default_sanitizer = InputSanitizer()


def sanitize_tool_arguments(
    tool_name: str, arguments: Dict[str, Any]
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    return _default_sanitizer.sanitize_tool_arguments(tool_name, arguments)


class InputSanitizerMiddleware:
    """ASGI Middleware scanning incoming tool payloads for OWASP LLM vulnerabilities."""

    def __init__(self, app: Any, sanitizer: Optional[InputSanitizer] = None) -> None:
        self.app = app
        self.sanitizer = sanitizer or _default_sanitizer

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        # Buffer incoming request body
        body_chunks: List[Dict[str, Any]] = []
        body_bytes = bytearray()
        more_body = True

        while more_body:
            message = await receive()
            body_chunks.append(message)
            body_bytes.extend(message.get("body", b""))
            more_body = message.get("more_body", False)

        if not body_bytes:
            # Replay empty body
            async def replay_empty():
                return body_chunks.pop(0) if body_chunks else {"type": "http.request", "body": b"", "more_body": False}
            await self.app(scope, replay_empty, send)
            return

        # Attempt to inspect JSON / JSON-RPC payload
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not JSON or malformed; let downstream handle parse errors
            replay_idx = 0
            async def replay_raw():
                nonlocal replay_idx
                if replay_idx < len(body_chunks):
                    msg = body_chunks[replay_idx]
                    replay_idx += 1
                    return msg
                return {"type": "http.request", "body": b"", "more_body": False}
            await self.app(scope, replay_raw, send)
            return

        # Check if this is an MCP JSON-RPC tool call
        if isinstance(payload, dict) and payload.get("method") == "tools/call":
            params = payload.get("params", {})
            tool_name = params.get("name", "unknown")
            arguments = params.get("arguments", {})

            valid, err_msg, clean_args = self.sanitizer.sanitize_tool_arguments(tool_name, arguments)
            if not valid:
                rpc_id = payload.get("id")
                err_resp = json.dumps({
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {
                        "code": -32602,
                        "message": f"OWASP Security Violation: {err_msg}",
                    },
                }).encode("utf-8")

                await send({
                    "type": "http.response.start",
                    "status": 400,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-content-type-options", b"nosniff"),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": err_resp,
                })
                return

            # Re-serialize sanitized payload into body
            payload["params"]["arguments"] = clean_args
            sanitized_body = json.dumps(payload).encode("utf-8")

            async def replay_sanitized():
                return {"type": "http.request", "body": sanitized_body, "more_body": False}

            await self.app(scope, replay_sanitized, send)
            return

        # General JSON payload validation
        valid, err_msg, sanitized_payload = self.sanitizer.validate_and_sanitize(payload)
        if not valid:
            err_resp = json.dumps({
                "error": "bad_request",
                "message": f"OWASP Security Violation: {err_msg}",
            }).encode("utf-8")

            await send({
                "type": "http.response.start",
                "status": 400,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": err_resp,
            })
            return

        sanitized_body = json.dumps(sanitized_payload).encode("utf-8")

        async def replay_clean():
            return {"type": "http.request", "body": sanitized_body, "more_body": False}

        await self.app(scope, replay_clean, send)
