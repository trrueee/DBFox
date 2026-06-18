from __future__ import annotations

import functools
import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from engine.tools.runtime.context import ToolContext
from engine.agent_core.types import ToolObservation
from engine.errors import DBFoxError, GuardrailValidationError, SQLExecutionError, SQLQueryTimeoutError, ToolInputError
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.policy.sensitivity import _SENSITIVE_FALLBACK

logger = logging.getLogger("dbfox.tools.db")

MAX_PREVIEW_ROWS = 20
DEFAULT_PREVIEW_ROWS = 10
DEFAULT_SEARCH_LIMIT = 20
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]+")


def tool_handler(name: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
            start = time.perf_counter()
            try:
                output = fn(ctx, args)
                return _success(name, args, output, start)
            except ToolInputError as exc:
                return _failed(name, args, str(exc), start)
            except ValueError as exc:
                return _failed(name, args, str(exc), start)
            except DBFoxError as exc:
                logger.exception("Tool %s failed", name)
                return _execution_failed(name, args, exc, start)
            except Exception as exc:
                logger.exception("Tool %s failed unexpectedly", name)
                return _execution_failed(name, args, exc, start)
        return wrapper
    return decorator


def _load_sensitivity(db: Session, datasource_id: str) -> re.Pattern:
    from engine.policy.sensitivity import load_sensitivity
    return load_sensitivity(db, datasource_id)


def _bootstrap_sensitivity(db: Session, datasource_id: str) -> None:
    from engine.policy.sensitivity import _bootstrap_sensitivity as bs
    bs(db, datasource_id)


def _looks_sensitive(column_name: str) -> bool:
    return bool(_SENSITIVE_FALLBACK.search(column_name))


def _datasource(db: Session, datasource_id: str) -> DataSource:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if ds is None:
        raise ValueError("Data source not found")
    return ds


def _catalog_tables(db: Session, datasource_id: str) -> list[SchemaTable]:
    return (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name)
        .all()
    )


def _catalog_table(db: Session, datasource_id: str, name: str) -> SchemaTable | None:
    return (
        db.query(SchemaTable)
        .filter(
            SchemaTable.data_source_id == datasource_id,
            SchemaTable.table_name == name,
        )
        .first()
    )


def _ordered_columns(table: SchemaTable) -> list[SchemaColumn]:
    return sorted(
        list(table.columns or []),
        key=lambda c: (c.ordinal_position or 10_000, str(c.column_name)),
    )


def _filter_tables(tables: list[SchemaTable], names: list[str]) -> list[SchemaTable]:
    if not names:
        return tables
    wanted = {n.lower() for n in names}
    return [t for t in tables if str(t.table_name).lower() in wanted]


def _missing_table_names(tables: list[SchemaTable], names: list[str]) -> list[str]:
    existing = {str(t.table_name).lower() for t in tables}
    return [n for n in names if n.lower() not in existing]


def _column_summary(col: SchemaColumn) -> dict[str, Any]:
    return {
        "name": str(col.column_name),
        "type": str(col.column_type or col.data_type or ""),
        "nullable": bool(col.is_nullable),
        "default": col.column_default,
        "primary_key": bool(col.is_primary_key),
        "foreign_key": bool(col.is_foreign_key),
        "comment": str(col.column_comment or ""),
    }


def _redact_row(row: dict[str, Any], sensitivity: re.Pattern | None = None) -> dict[str, Any]:
    from engine.policy.sensitivity import redact_row
    return redact_row(row, sensitivity)


def _limit_was_injected(original_sql: str, safe_sql: str) -> bool:
    original_has = bool(re.search(r"\blimit\b", original_sql, re.IGNORECASE))
    safe_has = bool(re.search(r"\blimit\b", safe_sql, re.IGNORECASE))
    return safe_has and (not original_has or _normalize_sql(original_sql) != _normalize_sql(safe_sql))


def _normalize_sql(sql: str) -> str:
    return " ".join(str(sql or "").strip().lower().split())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    return []


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


def _success(name: str, args: dict[str, Any], output: dict[str, Any], start: float) -> ToolObservation:
    return ToolObservation(
        name=name, status="success", input=args, output=output, error=None,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


def _failed(name: str, args: dict[str, Any], error: str, start: float) -> ToolObservation:
    return ToolObservation(
        name=name, status="failed", input=args, output=None, error=error,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


def _execution_failed(name: str, args: dict[str, Any], exc: Exception, start: float) -> ToolObservation:
    elapsed = int((time.perf_counter() - start) * 1000)
    if isinstance(exc, GuardrailValidationError):
        checks = getattr(exc, "checks", []) or []
        return ToolObservation(
            name=name, status="failed", input=args,
            output={
                "status": "blocked",
                "checks": checks,
                "blocked_reasons": [
                    str(item.get("rule", "guardrail"))
                    for item in checks
                    if isinstance(item, dict)
                ],
                "audit": {"readonly_checked": True, "trust_gate": True},
            },
            error=str(exc), latency_ms=elapsed,
        )
    if isinstance(exc, SQLQueryTimeoutError):
        status = "timeout"
    elif isinstance(exc, SQLExecutionError):
        status = "execution_failed"
    else:
        status = "failed"
    return ToolObservation(
        name=name, status="failed", input=args,
        output={"status": status, "error_type": exc.__class__.__name__},
        error=str(exc), latency_ms=elapsed,
    )
