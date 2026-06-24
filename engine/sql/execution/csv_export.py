from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from typing import Any


DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@")


def escape_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(DANGEROUS_CSV_PREFIXES):
        return "'" + text
    return text


class CsvExportService:
    @staticmethod
    def stream_csv(rows: Iterable[dict[str, Any]], columns: list[str]) -> Iterator[str]:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for row in rows:
            writer.writerow({column: escape_csv_cell(row.get(column, "")) for column in columns})
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

