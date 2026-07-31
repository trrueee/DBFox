from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from engine.json_codec import (
    JsonCodecError,
    byte_size,
    canonical_dumps,
    dumps,
    loads,
)


def test_codec_uses_pydantic_standard_json_representations() -> None:
    value = {
        "at": datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        "amount": Decimal("12.50"),
        "id": UUID("12345678-1234-5678-1234-567812345678"),
    }

    assert loads(dumps(value)) == {
        "at": "2026-01-02T03:04:00Z",
        "amount": "12.50",
        "id": "12345678-1234-5678-1234-567812345678",
    }


def test_codec_rejects_unknown_objects_and_non_finite_numbers() -> None:
    with pytest.raises(JsonCodecError):
        dumps({"value": object()})
    with pytest.raises(JsonCodecError):
        dumps({"value": float("nan")})
    with pytest.raises(JsonCodecError):
        loads('{"value":Infinity}')


def test_canonical_encoding_and_byte_size_are_deterministic() -> None:
    left = canonical_dumps({"b": "中", "a": 1})
    right = canonical_dumps({"a": 1, "b": "中"})

    assert left == right == '{"a":1,"b":"中"}'
    assert byte_size({"b": "中", "a": 1}) == len(left.encode("utf-8"))
