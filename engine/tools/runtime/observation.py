"""Model-visible projection of a tool result.

Projection belongs to the tool contract: the Agent harness persists the
projection without knowing concrete tool names or result shapes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from engine.json_codec import byte_size


RESULT_VALUE_KEYS = frozenset({
    "rows",
    "results",
    "series",
    "previewRows",
    "preview_rows",
})
MAX_FACT_BYTES = 32_768


class ToolObservationProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    facts: dict[str, Any] = Field(default_factory=dict)


def safe_observation_facts(value: dict[str, Any]) -> dict[str, Any]:
    sanitized = _remove_result_values(value)
    if _encoded_size(sanitized) <= MAX_FACT_BYTES:
        return sanitized

    compact: dict[str, Any] = {
        "truncated": True,
        "availableKeys": sorted(str(key) for key in sanitized)[:256],
    }
    items = list(sanitized.items())
    items.sort(
        key=lambda item: (
            isinstance(item[1], (dict, list)),
            _encoded_size(item[1]),
            str(item[0]),
        )
    )
    for key, item in items:
        candidate = {**compact, str(key): item}
        if _encoded_size(candidate) <= MAX_FACT_BYTES:
            compact[str(key)] = item
            continue
        summary = _structural_summary(item)
        candidate = {**compact, str(key): summary}
        if _encoded_size(candidate) <= MAX_FACT_BYTES:
            compact[str(key)] = summary
    return compact


def _encoded_size(value: Any) -> int:
    return byte_size(value)


def _structural_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "truncated": True,
            "keyCount": len(value),
            "availableKeys": sorted(str(key) for key in value)[:128],
        }
    if isinstance(value, list):
        return {
            "truncated": True,
            "itemCount": len(value),
        }
    text = str(value)
    return {
        "truncated": True,
        "characterCount": len(text),
    }


def _remove_result_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _remove_result_values(item)
            for key, item in value.items()
            if str(key) not in RESULT_VALUE_KEYS
        }
    if isinstance(value, list):
        return [_remove_result_values(item) for item in value]
    return value
