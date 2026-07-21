from __future__ import annotations

import csv
import io

from engine.sql.execution.csv_export import CsvExportService, escape_csv_cell


def test_escape_csv_cell_uses_the_cross_runtime_formula_guard_contract() -> None:
    assert escape_csv_cell(None) == ""
    assert escape_csv_cell("=1+1") == "'=1+1"
    assert escape_csv_cell("+cmd") == "'+cmd"
    assert escape_csv_cell("@user") == "'@user"
    assert escape_csv_cell("\ufeff=1+1") == "'\ufeff=1+1"
    assert escape_csv_cell("\u2003\t\r\n@cmd") == "'\u2003\t\r\n@cmd"
    assert escape_csv_cell("\x00\x1f+cmd") == "'\x00\x1f+cmd"
    assert escape_csv_cell("\n\t=SUM(1,2)") == "'\n\t=SUM(1,2)"
    assert escape_csv_cell("safe\n=1+1") == "safe\n=1+1"
    assert escape_csv_cell("safe") == "safe"


def test_escape_csv_cell_preserves_ordinary_negative_numbers_but_not_expressions() -> None:
    assert escape_csv_cell("-10") == "-10"
    assert escape_csv_cell("\u00a0-0.25e3") == "\u00a0-0.25e3"
    assert escape_csv_cell("-1+1") == "'-1+1"


def test_csv_export_protects_headers_and_multiline_cells() -> None:
    columns = ["\ufeff=column", "note"]
    rows = iter(
        [
            {"\ufeff=column": "\n\t=SUM(1,2)", "note": "first\nsecond"},
            {"\ufeff=column": "Alice", "note": None},
        ]
    )

    body = "".join(CsvExportService.stream_csv(rows, columns))

    assert list(csv.DictReader(io.StringIO(body))) == [
        {"'\ufeff=column": "'\n\t=SUM(1,2)", "note": "first\nsecond"},
        {"'\ufeff=column": "Alice", "note": ""},
    ]
