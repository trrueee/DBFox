#!/usr/bin/env python3
"""Canonicalize Spider gold SQL for lower-case MySQL imports."""

from __future__ import annotations

import re
import sqlglot


def _table_name_map(table_names: list[str]) -> dict[str, str]:
    return {
        str(table).strip().lower(): str(table).strip()
        for table in table_names
        if str(table).strip()
    }


def _rewrite_with_sqlglot(
    gold_sql: str,
    table_map: dict[str, str],
) -> tuple[str, list[str]]:
    sqlglot.parse_one(gold_sql, read="mysql")
    return _rewrite_source_preserving(gold_sql, table_map), []


def _rewrite_non_string_region(region: str, table_map: dict[str, str]) -> str:
    table_alternatives = "|".join(
        re.escape(name)
        for name in sorted(table_map.keys(), key=len, reverse=True)
    )
    if not table_alternatives:
        return region

    pattern = re.compile(
        rf"(?P<prefix>\b(?:FROM|JOIN)\s+)(?P<quote>`?)(?P<table>{table_alternatives})(?P=quote)",
        re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        table = match.group("table")
        canonical = table_map.get(table.lower(), table)
        return f"{match.group('prefix')}{match.group('quote')}{canonical}{match.group('quote')}"

    return pattern.sub(replace, region)


def _rewrite_source_preserving(
    gold_sql: str,
    table_map: dict[str, str],
) -> str:
    parts: list[str] = []
    idx = 0
    in_quote: str | None = None
    region_start = 0

    while idx < len(gold_sql):
        char = gold_sql[idx]
        if in_quote is None:
            if char in ("'", '"'):
                if region_start < idx:
                    parts.append(_rewrite_non_string_region(gold_sql[region_start:idx], table_map))
                in_quote = char
                region_start = idx
            idx += 1
            continue

        if char == in_quote:
            next_idx = idx + 1
            if next_idx < len(gold_sql) and gold_sql[next_idx] == in_quote:
                idx += 2
                continue
            parts.append(gold_sql[region_start:next_idx])
            in_quote = None
            region_start = next_idx
            idx = next_idx
            continue

        if char == "\\":
            idx += 2
            continue

        idx += 1

    if region_start < len(gold_sql):
        tail = gold_sql[region_start:]
        if in_quote is None:
            parts.append(_rewrite_non_string_region(tail, table_map))
        else:
            parts.append(tail)

    return "".join(parts)


def _rewrite_with_tokenizer(
    gold_sql: str,
    table_map: dict[str, str],
) -> tuple[str, list[str]]:
    rewritten = _rewrite_source_preserving(gold_sql, table_map)
    warnings = ["parser_failed_fallback_tokenizer_used"]
    if rewritten == gold_sql:
        warnings.append("fallback_tokenizer_no_change")
    return rewritten, warnings


def canonicalize_gold_sql_with_warnings(
    gold_sql: str,
    db_id: str,
    table_names: list[str],
) -> tuple[str, list[str]]:
    """Return gold SQL with physical MySQL table identifiers canonicalized.

    Only table identifiers matching the imported schema are rewritten. String
    literals and column identifiers are left untouched.
    """
    if not gold_sql:
        return gold_sql, []

    table_map = _table_name_map(table_names)
    if not table_map:
        return gold_sql, [f"canonicalization_skipped_no_tables:{db_id}"]

    try:
        return _rewrite_with_sqlglot(gold_sql, table_map)
    except Exception as exc:
        rewritten, warnings = _rewrite_with_tokenizer(gold_sql, table_map)
        warnings.insert(0, f"sqlglot_parse_failed:{type(exc).__name__}:{exc}")
        return rewritten, warnings


def canonicalize_gold_sql_for_mysql(
    gold_sql: str,
    db_id: str,
    table_names: list[str],
) -> str:
    """Canonicalize Spider gold SQL table names for lower-case MySQL tables."""
    canonical_sql, _warnings = canonicalize_gold_sql_with_warnings(
        gold_sql,
        db_id=db_id,
        table_names=table_names,
    )
    return canonical_sql
