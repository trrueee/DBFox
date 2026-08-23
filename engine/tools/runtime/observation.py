"""Model-visible projection of a tool result.

Projection belongs to the tool contract: the Agent harness persists the
projection without knowing concrete tool names or result shapes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from engine.json_codec import byte_size, to_json_value


RESULT_VALUE_KEYS = frozenset(
    {
        "rows",
        "results",
        "series",
        "previewRows",
        "preview_rows",
    }
)
MAX_FACT_BYTES = 32_768
MAX_PROVIDER_PAYLOAD_BYTES = 65_536
MODEL_RESULT_WINDOW_ROWS = 20
MODEL_RESULT_WINDOW_COLUMNS = 50
MODEL_RESULT_WINDOW_BYTES = 24_000
MODEL_RESULT_CELL_CHARS = 2_000


class ToolObservationProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    facts: dict[str, Any] = Field(default_factory=dict)
    provider_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provider_payload_budget(self) -> "ToolObservationProjection":
        if byte_size(self.provider_payload) > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ValueError(
                "Tool provider payload exceeds the bounded observation contract"
            )
        return self


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


def bounded_tabular_provider_payload(
    *,
    facts: dict[str, Any],
    columns: list[str],
    rows: list[Any],
    total_returned_rows: int,
    source_truncated: bool = False,
) -> dict[str, Any]:
    """Return a structured model window without persisting or string-truncating rows."""

    selected_columns = columns[:MODEL_RESULT_WINDOW_COLUMNS]
    serialized_rows: list[dict[str, Any]] = []
    response_bytes = 2
    cells_truncated = False
    response_truncated = False
    for raw_row in rows[:MODEL_RESULT_WINDOW_ROWS]:
        candidate: dict[str, Any] = {}
        for column in selected_columns:
            raw_value = raw_row.get(column) if isinstance(raw_row, dict) else None
            value = to_json_value(raw_value)
            if isinstance(value, str) and len(value) > MODEL_RESULT_CELL_CHARS:
                value = value[:MODEL_RESULT_CELL_CHARS] + "..."
                cells_truncated = True
            candidate[column] = value
        candidate_bytes = byte_size(candidate)
        separator_bytes = 1 if serialized_rows else 0
        if response_bytes + separator_bytes + candidate_bytes > MODEL_RESULT_WINDOW_BYTES:
            response_truncated = True
            break
        response_bytes += separator_bytes + candidate_bytes
        serialized_rows.append(candidate)
    return {
        **facts,
        "rows": serialized_rows,
        "window": {
            "returned_rows": len(serialized_rows),
            "max_rows": MODEL_RESULT_WINDOW_ROWS,
            "truncated": (
                source_truncated
                or total_returned_rows > len(serialized_rows)
                or len(columns) > len(selected_columns)
                or response_truncated
                or cells_truncated
            ),
            "truncation_reasons": {
                "rows": total_returned_rows > len(serialized_rows),
                "columns": len(columns) > len(selected_columns),
                "response_bytes": response_truncated,
                "cells": cells_truncated,
            },
        },
    }


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
