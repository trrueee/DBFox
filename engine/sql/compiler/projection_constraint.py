from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.agent_core.semantic_contract import QueryContract


class SQLProjectionConstraintVerifier:
    """AST-level guardrail for projection-only SQL retries."""

    def validate_retry(
        self,
        original_sql: str,
        retry_sql: str,
        contract: QueryContract,
    ) -> bool:
        import sqlglot
        from sqlglot import exp

        try:
            orig = sqlglot.parse_one(original_sql, read="mysql")
            retry = sqlglot.parse_one(retry_sql, read="mysql")
        except Exception:
            return False

        def norm(expr: exp.Expression | None) -> str:
            if expr is None:
                return ""
            return expr.sql(dialect="mysql")

        orig_tables = {t.name.lower() for t in orig.find_all(exp.Table)}
        retry_tables = {t.name.lower() for t in retry.find_all(exp.Table)}
        if orig_tables != retry_tables:
            return False

        orig_select = next(orig.find_all(exp.Select), None)
        retry_select = next(retry.find_all(exp.Select), None)
        if orig_select is None or retry_select is None:
            return False

        if self._join_signature(orig_select, exp, norm) != self._join_signature(retry_select, exp, norm):
            return False

        for clause in ("where", "group", "having", "order", "limit"):
            if norm(orig_select.args.get(clause)) != norm(retry_select.args.get(clause)):
                return False

        if contract.distinct and contract.distinct.required:
            orig_distinct = bool(orig_select.args.get("distinct"))
            retry_distinct = bool(retry_select.args.get("distinct"))
            if orig_distinct and not retry_distinct:
                return False

        return True

    def _join_signature(
        self,
        select_node: Any,
        exp: Any,
        norm: Callable[[Any], str],
    ) -> list[tuple[str, str, str]]:
        sigs: list[tuple[str, str, str]] = []
        for join in select_node.args.get("joins") or []:
            side = str(join.args.get("side") or "").lower()
            table = join.this
            table_name = table.name.lower() if isinstance(table, exp.Table) else "?"
            sigs.append((side, table_name, norm(join.args.get("on"))))
        return sorted(sigs)
