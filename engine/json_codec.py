"""Single strict JSON boundary for durable state, APIs, and size accounting."""

from __future__ import annotations

import json
from typing import Any, TypeAlias, cast

from pydantic_core import to_json

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)


class JsonCodecError(ValueError):
    """Raised when a value cannot cross DBFox's JSON boundary."""


def _reject_non_finite(value: str) -> None:
    raise JsonCodecError(f"Non-finite number is not valid JSON: {value}")


def to_json_value(value: Any) -> JsonValue:
    """Normalize supported Python/Pydantic values through pydantic-core.

    Datetimes, UUIDs, enums, decimals, dataclasses, and Pydantic models use
    Pydantic's standard JSON representation. Unknown objects and non-finite
    numbers fail instead of being silently coerced with ``str()``.
    """

    try:
        encoded = to_json(
            value,
            ensure_ascii=False,
            by_alias=True,
            inf_nan_mode="constants",
            serialize_unknown=False,
        )
        return cast(
            JsonValue,
            json.loads(encoded, parse_constant=_reject_non_finite),
        )
    except JsonCodecError:
        raise
    except (TypeError, ValueError) as exc:
        raise JsonCodecError(f"Value is not JSON serializable: {exc}") from exc


def dumps(
    value: Any,
    *,
    canonical: bool = False,
    indent: int | None = None,
) -> str:
    normalized = to_json_value(value)
    separators = None if indent is not None else (",", ":")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        indent=indent,
        separators=separators,
        sort_keys=canonical,
    )


def canonical_dumps(value: Any) -> str:
    return dumps(value, canonical=True)


def loads(value: str | bytes | bytearray) -> JsonValue:
    try:
        return cast(
            JsonValue,
            json.loads(value, parse_constant=_reject_non_finite),
        )
    except JsonCodecError:
        raise
    except (TypeError, ValueError) as exc:
        raise JsonCodecError(f"Invalid JSON: {exc}") from exc


def load_object(value: str | bytes | bytearray) -> dict[str, JsonValue]:
    parsed = loads(value)
    if not isinstance(parsed, dict):
        raise JsonCodecError("JSON value must be an object")
    return parsed


def load_array(value: str | bytes | bytearray) -> list[JsonValue]:
    parsed = loads(value)
    if not isinstance(parsed, list):
        raise JsonCodecError("JSON value must be an array")
    return parsed


def byte_size(value: Any) -> int:
    return len(dumps(value).encode("utf-8"))
