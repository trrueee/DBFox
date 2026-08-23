"""Data DLC preview input rejects raw SQL at its public type boundary."""

import pytest

from dlcs.dbfox_data.backend.tool_contracts import DataPreviewInput


def test_preview_input_rejects_string_where() -> None:
    """Pydantic rejects raw SQL; filters use the declared list contract."""
    with pytest.raises(Exception):  # ValidationError
        DataPreviewInput(table="orders", where="1=1 UNION SELECT password FROM users")


def test_preview_input_rejects_string_order_by() -> None:
    """Pydantic rejects raw SQL; ordering uses the declared list contract."""
    with pytest.raises(Exception):  # ValidationError
        DataPreviewInput(table="orders", order_by="id DESC; SELECT password FROM users")


def test_preview_input_accepts_structured_where() -> None:
    inp = DataPreviewInput(
        table="orders",
        where={"column": "status", "op": "=", "value": "active"},
    )
    assert inp.where is not None
    assert inp.where.model_dump(mode="json") == {
        "column": "status",
        "op": "=",
        "value": "active",
    }


def test_preview_input_accepts_structured_order_by() -> None:
    inp = DataPreviewInput(
        table="orders",
        order_by=[{"column": "id", "direction": "DESC"}],
    )
    assert [item.model_dump(mode="json") for item in (inp.order_by or [])] == [
        {"column": "id", "direction": "DESC"}
    ]


def test_preview_input_accepts_explicit_null_order_by() -> None:
    inp = DataPreviewInput.model_validate({"table": "orders", "order_by": None})

    assert inp.order_by is None
    schema = DataPreviewInput.model_json_schema()
    order_schema = schema["properties"]["order_by"]
    assert any(item.get("type") == "null" for item in order_schema["anyOf"])
