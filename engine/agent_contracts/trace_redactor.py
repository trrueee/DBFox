from __future__ import annotations

import json
import re
from typing import Any

from engine.policy.redactor import DataRedactor


MAX_TRACE_EVENT_BYTES = 32 * 1024
MAX_TRACE_STRING_CHARS = 2_000
MAX_TRACE_LIST_ITEMS = 20
MAX_TRACE_ROW_ITEMS = 5
MAX_TRACE_DEPTH = 6

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "passphrase",
    "private_key",
    "privatekey",
    "ciphertext",
    "nonce",
)
_SQL_KEY_PARTS = ("sql", "query")
_SQL_LITERAL_PATTERN = re.compile(r"'(?:''|[^'])*'")


class AgentTraceRedactor:
    def redact(self, value: Any) -> Any:
        return self._redact_value(value, key="", depth=0)

    def cap_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        capped = dict(event_data)
        if self._payload_size(capped) <= MAX_TRACE_EVENT_BYTES:
            return capped

        if capped.get("output") is not None:
            capped["output"] = {
                "_truncated": True,
                "message": "Trace output exceeded the event size limit; inspect the linked artifact instead.",
            }
        if self._payload_size(capped) <= MAX_TRACE_EVENT_BYTES:
            return capped

        if capped.get("input") is not None:
            capped["input"] = {
                "_truncated": True,
                "message": "Trace input exceeded the event size limit.",
            }
        if capped.get("error"):
            capped["error"] = str(capped["error"])[:MAX_TRACE_STRING_CHARS]
        return capped

    def _redact_value(self, value: Any, key: str, depth: int) -> Any:
        key_lower = key.lower()
        if any(part in key_lower for part in _SENSITIVE_KEY_PARTS):
            return "[REDACTED]"
        if depth > MAX_TRACE_DEPTH:
            return "[TRUNCATED_DEPTH]"

        if isinstance(value, dict):
            return {
                str(item_key): self._redact_value(item_value, str(item_key), depth + 1)
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            limit = MAX_TRACE_ROW_ITEMS if key_lower in {"rows", "sample_rows"} else MAX_TRACE_LIST_ITEMS
            redacted = [self._redact_value(item, key, depth + 1) for item in value[:limit]]
            if len(value) > limit:
                redacted.append({"_truncated": len(value) - limit})
            return redacted
        if isinstance(value, str):
            return self._redact_string(value, key_lower)
        return value

    def _redact_string(self, value: str, key_lower: str) -> str:
        redacted = DataRedactor.redact_sql(value)
        if any(part in key_lower for part in _SQL_KEY_PARTS):
            redacted = _SQL_LITERAL_PATTERN.sub("'[REDACTED_LITERAL]'", redacted)
        max_chars = MAX_TRACE_STRING_CHARS
        if key_lower in {"schema_context", "prompt", "llm_prompt"}:
            max_chars = min(max_chars, 1_000)
        if len(redacted) > max_chars:
            return redacted[:max_chars] + "...[TRUNCATED]"
        return redacted

    def _payload_size(self, value: dict[str, Any]) -> int:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
