from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Iterator
from typing import Any


DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@")

# Keep this list aligned with desktop/src/features/workspace/artifacts/artifactActions.ts.
# It intentionally covers every C0/C1 control character in addition to the Unicode
# whitespace code points defined by ECMAScript.  Spreadsheet applications commonly
# ignore one or more of these characters before deciding whether a cell is a formula.
_CSV_UNICODE_WHITESPACE_CODEPOINTS = frozenset(
    {
        0x0020,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    }
)
_NEGATIVE_DECIMAL_LITERAL = re.compile(r"^-(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?$")


def _is_csv_leading_ignorable(character: str) -> bool:
    """Return whether spreadsheet formula detection may ignore ``character``.

    The function is deliberately explicit instead of relying on ``str.isspace`` so
    the frontend and backend use the same Unicode contract.
    """

    codepoint = ord(character)
    return (
        codepoint == 0xFEFF  # Unicode BOM / zero-width no-break space.
        or 0x0000 <= codepoint <= 0x001F  # Includes TAB, CR, and LF.
        or 0x007F <= codepoint <= 0x009F
        or codepoint in _CSV_UNICODE_WHITESPACE_CODEPOINTS
    )


def _csv_formula_candidate(text: str) -> str:
    index = 0
    while index < len(text) and _is_csv_leading_ignorable(text[index]):
        index += 1
    return text[index:]


def _is_plain_negative_number(text: str) -> bool:
    """Preserve canonical negative numeric literals without treating them as formulas."""

    return bool(_NEGATIVE_DECIMAL_LITERAL.fullmatch(text))


def escape_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    candidate = _csv_formula_candidate(text)
    if not candidate or candidate[0] not in DANGEROUS_CSV_PREFIXES:
        return text

    # A literal such as -10 is ordinary data, not an executable spreadsheet
    # expression.  Keep only the deliberately narrow canonical decimal/exponent
    # form unmodified; values such as "-1+1" still receive the text marker.
    if candidate[0] == "-" and _is_plain_negative_number(candidate):
        return text

    return "'" + text


class CsvExportService:
    @staticmethod
    def stream_csv(rows: Iterable[dict[str, Any]], columns: list[str]) -> Iterator[str]:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        # A column name can originate from an alias or a database object name, so it
        # must receive the same spreadsheet formula protection as row data.
        writer.writerow({column: escape_csv_cell(column) for column in columns})
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for row in rows:
            writer.writerow({column: escape_csv_cell(row.get(column, "")) for column in columns})
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

