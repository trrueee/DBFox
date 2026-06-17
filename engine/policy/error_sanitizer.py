"""Error message sanitization to prevent sensitive information leakage."""

from __future__ import annotations

import re
from typing import Any


# Patterns that should never appear in client-facing error messages
_SENSITIVE_PATTERNS = [
    # ── Passwords and credentials ──
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(secret|token|api[_-]?key|apikey)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(credential|passphrase|private[_-]?key)\s*[:=]\s*\S+"),

    # ── Connection strings ──
    re.compile(r"(?i)(mysql|postgres|postgresql|sqlite|mongodb)://\S+"),
    re.compile(r"(?i)(mssql|sqlserver)://\S+"),
    re.compile(r"(?i)(redis|rediss)://\S+"),
    re.compile(r"(?i)jdbc:\S+"),

    # ── Driver error password leaks ──
    # "using password: YES" / "using password: <actual_password>"
    re.compile(r"(?i)using\s+password\s*:\s*\S+"),

    # ── Auth tokens ──
    re.compile(r"(?i)Authorization\s*:\s*Bearer\s+\S+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"),

    # ── AWS access keys ──
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)aws[_-]?(access[_-]?key[_-]?id|secret[_-]?access[_-]?key)\s*[:=]\s*\S+"),

    # ── File paths that may contain sensitive info ──
    re.compile(r"(?i)/home/\w+/\.\w+"),
    re.compile(r"(?i)C:\\Users\\\w+\\"),

    # ── Token-like strings (long alphanumeric) ──
    re.compile(r"\b[A-Za-z0-9+/=]{32,}\b"),

    # ── IP:port with embedded credentials ──
    re.compile(r"(?i)\S+:\S+@\d+\.\d+\.\d+\.\d+"),
]

# Replacement placeholder
_REDACTED = "[REDACTED]"


def sanitized_http_detail(exc: Exception, code: str) -> dict[str, Any]:
    """Return a sanitized HTTP error detail dict for an exception.

    Use this in API route ``except`` blocks instead of
    ``{"code": ..., "message": str(exc)}`` to prevent driver error
    messages, connection strings, and credentials from leaking to
    the client.

    >>> sanitized_http_detail(ValueError("mysql://root:secret@1.2.3.4/db"), "BAD_INPUT")
    {"code": "BAD_INPUT", "message": "[REDACTED]://[REDACTED]:[REDACTED]@1.2.3.4/db"}
    """
    return {"code": code, "message": sanitize_error_message(str(exc))}


def sanitize_error_message(message: str) -> str:
    """Remove sensitive patterns from error messages before returning to client.

    This function strips passwords, tokens, connection strings, and other
    sensitive information from error messages to prevent information leakage.

    Args:
        message: The original error message

    Returns:
        Sanitized message safe for client display
    """
    if not message:
        return message

    sanitized = message
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)

    return sanitized
