import datetime
import decimal
import pytest
from engine.sql.row_serializer import _process_rows, _serialize_value

# covers: ROW-1 Columns count > max_columns
def test_row1_column_truncation():
    cols = [f"col_{i}" for i in range(150)]
    raw = [{f"col_{i}": "val" for i in range(150)}]
    rows, columns, truncated, _ = _process_rows(raw, cols, max_columns=100)
    assert len(columns) == 100
    assert columns[-1] == "col_99"

# covers: ROW-2 Cell character truncation
def test_row2_cell_character_truncation():
    cols = ["col_1"]
    long_str = "A" * 6000
    raw = [{"col_1": long_str}]
    rows, columns, truncated, _ = _process_rows(raw, cols, max_cell_chars=5000)
    assert len(rows[0]["col_1"]) == 5003  # 5000 + "..."
    assert rows[0]["col_1"].endswith("...")

# covers: ROW-3 Response bytes limit truncation
def test_row3_response_bytes_limit():
    cols = ["col_1"]
    raw = [{"col_1": "A" * 1500000}, {"col_1": "B" * 1500000}]
    rows, columns, truncated, _ = _process_rows(raw, cols, max_cell_chars=3000000, max_response_bytes=2*1024*1024)
    assert len(rows) == 1
    assert truncated is True

# covers: ROW-4 Exact limit boundary
def test_row4_exact_limit_boundary():
    cols = ["col_1"]
    raw = [{"col_1": "A" * 100}]
    rows, columns, truncated, response_bytes = _process_rows(raw, cols, max_response_bytes=200)
    assert len(rows) == 1
    assert truncated is False

# covers: ROW-5 0 rows case
def test_row5_zero_rows():
    cols = ["col_1"]
    rows, columns, truncated, response_bytes = _process_rows([], cols)
    assert rows == []
    assert truncated is False
    assert response_bytes == 2

# covers: ROW-6 Decimal/Datetime/bytes serialization
def test_row6_serialization_types():
    assert _serialize_value(decimal.Decimal("12.34")) == "12.34"
    dt = datetime.datetime(2026, 6, 17, 12, 0, 0)
    assert _serialize_value(dt) == "2026-06-17T12:00:00"
    d = datetime.date(2026, 6, 17)
    assert _serialize_value(d) == "2026-06-17"
    assert _serialize_value(b"hello") == "<binary>"
    assert _serialize_value(None) is None
    assert _serialize_value("hello") == "hello"
