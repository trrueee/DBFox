"""Tests for db_preview safety wrapper — raw string rejection at the type boundary."""

import pytest

from engine.errors import ToolInputError
from engine.tools.builtin.contracts import DataPreviewInput
from engine.tools.db.preview import db_preview


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
    assert [item.model_dump(mode="json") for item in inp.order_by] == [
        {"column": "id", "direction": "DESC"}
    ]


def test_safe_preview_wrapper_rejects_raw_where_before_db_access() -> None:
    with pytest.raises(ToolInputError, match="WHERE"):
        db_preview(
            None,  # type: ignore[arg-type]
            "ds-1",
            table="orders",
            where="1=1 UNION SELECT password FROM users",  # type: ignore[arg-type]
        )


def test_safe_preview_wrapper_rejects_raw_order_by_before_db_access() -> None:
    with pytest.raises(ToolInputError, match="ORDER BY"):
        db_preview(
            None,  # type: ignore[arg-type]
            "ds-1",
            table="orders",
            order_by="id DESC; SELECT password FROM users",  # type: ignore[arg-type]
        )
