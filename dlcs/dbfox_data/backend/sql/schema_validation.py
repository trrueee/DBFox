"""Catalog-backed table validation for SQL before execution."""

from __future__ import annotations

from collections.abc import Callable

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, TokenError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import find_all_in_scope, traverse_scope


class CatalogSchemaValidator:
    """Warn about tables the current catalog does not contain.

    The lookup returns ``None`` when the catalog is not ready for the current
    resource generation; in that case validation is skipped rather than
    producing false warnings for every table.
    """

    def __init__(
        self,
        *,
        dialect: str,
        lookup: Callable[[frozenset[str]], set[str] | None],
    ) -> None:
        self._dialect = dialect
        self._lookup = lookup

    def __call__(self, query: str | exp.Expression) -> list[str]:
        try:
            expression = sqlglot.parse_one(query, read=self._dialect) if isinstance(query, str) else query.copy()
            normalized = normalize_identifiers(expression, dialect=self._dialect)
            requested = frozenset(
                ".".join(part for part in (source.catalog, source.db, source.name) if part)
                for scope in traverse_scope(normalized)
                for _, source in scope.selected_sources.values()
                if isinstance(source, exp.Table) and isinstance(source.this, exp.Identifier)
            )
        except (OptimizeError, ParseError, TokenError):
            # Identifier discovery is advisory. Guardrail and EXPLAIN decide execution.
            return []
        if not requested:
            return []
        found = self._lookup(requested)
        if found is None:
            return []
        return [
            f"表 {name} 不在当前 Catalog 中；请刷新 Catalog 或核对名称。"
            for name in sorted(requested - found)
        ]


def aggregates_across_join_sources(query: exp.Expression) -> bool:
    """Identify duplicate-sensitive measures over distinct inputs in a JOIN scope."""
    try:
        for scope in traverse_scope(query):
            select = scope.expression
            if not isinstance(select, exp.Select) or not select.args.get("joins"):
                continue
            source_names = scope.selected_sources.keys()
            measure_sources: set[str] = set()
            for projection in select.selects:
                for aggregate in find_all_in_scope(projection, exp.Sum, exp.Avg, exp.Count):
                    if isinstance(aggregate.this, exp.Distinct):
                        continue
                    sources = {column.table for column in find_all_in_scope(aggregate, exp.Column)}
                    if len(sources) == 1 and sources <= source_names:
                        measure_sources.update(sources)
            if len(measure_sources) > 1:
                return True
    except OptimizeError:
        # SQL scope discovery is advisory; syntax has its own validation path.
        return False
    return False
