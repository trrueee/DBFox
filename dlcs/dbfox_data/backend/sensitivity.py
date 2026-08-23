"""Data-owned default sensitivity and row-redaction rules."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_PATTERN_STRINGS = (
    r"\b(password|passwd|secret|token|credential|api_key)\b",
    r"\b(email|mail)\b",
    r"\b(phone|mobile|tel|telephone|msisdn)\b",
    r"\b(address|addr|postal|zip_code)\b",
    r"\b(ip_address|ipaddr|client_ip|server_ip)\b",
    r"\b(card|credit_card|debit_card)\b",
    r"\b(ssn|social_security|tax_id|national_id)\b",
    r"\b(passport|driver_license)\b",
)
SAFE_PATTERN_SET = frozenset(SENSITIVE_PATTERN_STRINGS)
SENSITIVE_FALLBACK = re.compile(
    "|".join(SENSITIVE_PATTERN_STRINGS),
    re.IGNORECASE,
)


def is_sensitive_name(column_name: str) -> bool:
    return bool(SENSITIVE_FALLBACK.search(column_name))


def redact_row(
    row: dict[str, Any],
    sensitivity: re.Pattern[str] | None = None,
    *,
    sensitive_columns: set[str] | None = None,
) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in row.items():
        forced = sensitive_columns is not None and key in sensitive_columns
        if forced or (sensitivity and sensitivity.search(key)):
            redacted[key] = None if value is None else "[REDACTED]"
        else:
            redacted[key] = value
    return redacted
