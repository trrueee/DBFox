"""Tests for db_preview safety wrapper — raw string rejection at the type boundary."""

import pytest

from engine.tools.dbfox_tools import PreviewInput
from engine.tools.db.preview import db_preview


def test_preview_input_rejects_string_where() -> None:
    """Pydantic rejects raw string WHERE — only dict | None accepted."""
    with pytest.raises(Exception):  # ValidationError
        PreviewInput(table="orders", where="1=1 UNION SELECT password FROM users")


def test_preview_input_rejects_string_order_by() -> None:
    """Pydantic rejects raw string ORDER BY — only dict | list[dict] | None accepted."""
    with pytest.raises(Exception):  # ValidationError
        PreviewInput(table="orders", order_by="id DESC; SELECT password FROM users")


def test_preview_input_accepts_structured_where() -> None:
    inp = PreviewInput(table="orders", where={"column": "status", "op": "=", "value": "active"})
    assert inp.where == {"column": "status", "op": "=", "value": "active"}


def test_preview_input_accepts_structured_order_by() -> None:
    inp = PreviewInput(table="orders", order_by={"column": "id", "direction": "desc"})
    assert inp.order_by == {"column": "id", "direction": "desc"}


def test_safe_preview_wrapper_rejects_raw_where_before_db_access() -> None:
    with pytest.raises(ValueError, match="WHERE"):
        db_preview(
            None,  # type: ignore[arg-type]
            "ds-1",
            table="orders",
            where="1=1 UNION SELECT password FROM users",  # type: ignore[arg-type]
        )


def test_safe_preview_wrapper_rejects_raw_order_by_before_db_access() -> None:
    with pytest.raises(ValueError, match="ORDER BY"):
        db_preview(
            None,  # type: ignore[arg-type]
            "ds-1",
            table="orders",
            order_by="id DESC; SELECT password FROM users",  # type: ignore[arg-type]
        )
