from __future__ import annotations
import re
from typing import Any
from sqlglot import exp
from engine.errors import ToolInputError
from engine.sql.parser import normalize_dialect

# Whitelist regex for standard safe SQL identifiers (tables, schemas, columns)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def escape_identifier(name: str, dialect: str) -> str:
    """Safely escape a SQL identifier (table, schema, column name) using sqlglot."""
    sqlglot_dialect = normalize_dialect(dialect)
    return exp.to_identifier(name).sql(sqlglot_dialect, identify=True)

def safe_identifier(name: str, dialect: str) -> str:
    """Validate identifier against a strict whitelist, then escape it."""
    if not name or not _IDENT_RE.fullmatch(name):
        raise ToolInputError(f"Invalid SQL identifier: {name!r}")
    return escape_identifier(name, dialect)

def catalog_identifier(name: str, dialect: str) -> str:
    """Escape an identifier already validated against a trusted catalog."""
    if not name or "\x00" in name:
        raise ToolInputError(f"Invalid SQL identifier: {name!r}")
    return escape_identifier(name, dialect)

def _safe_or_catalog_identifier(name: str, dialect: str, catalog_validated: bool) -> str:
    if catalog_validated:
        return catalog_identifier(name, dialect)
    return safe_identifier(name, dialect)

def safe_table(schema: str | None, table: str, dialect: str) -> str:
    """Construct a safe schema-qualified or plain table identifier."""
    if schema:
        return f"{safe_identifier(schema, dialect)}.{safe_identifier(table, dialect)}"
    return safe_identifier(table, dialect)

_SAFE_OPS: frozenset[str] = frozenset({
    "=", "!=", "<>", "<", ">", "<=", ">=",
    "LIKE", "NOT LIKE", "ILIKE", "NOT ILIKE", "IN", "NOT IN",
    "IS", "IS NOT",
})

def _normalize_where_op(op: str, dialect: str) -> str:
    if op in {"ILIKE", "NOT ILIKE"} and normalize_dialect(dialect) != "postgres":
        return op.replace("ILIKE", "LIKE")
    return op

def build_where_clause(where: dict[str, Any], dialect: str, *, catalog_validated: bool = False) -> str | None:
    """Build a safe WHERE clause, validating columns and operator safety."""
    col = str(where.get("column") or "")
    op = str(where.get("op") or "=").strip().upper()
    value = where.get("value")
    if not col:
        return None
    if op not in _SAFE_OPS:
        raise ValueError(f"Unsafe operator in WHERE clause: {op}")
    op = _normalize_where_op(op, dialect)
    
    safe_col = _safe_or_catalog_identifier(col, dialect, catalog_validated)
    if value is None:
        return f"{safe_col} IS NULL"
    if isinstance(value, (int, float)):
        return f"{safe_col} {op} {value}"
    if isinstance(value, bool):
        return f"{safe_col} {op} {1 if value else 0}"
    if op in ("IN", "NOT IN") and isinstance(value, list):
        escaped = ", ".join(f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" for v in value)
        return f"{safe_col} {op} ({escaped})"
    escaped = str(value).replace("'", "''")
    return f"{safe_col} {op} '{escaped}'"

def build_order_clause(order: dict[str, Any], dialect: str, *, catalog_validated: bool = False) -> str | None:
    """Build a safe ORDER BY expression validating columns."""
    col = str(order.get("column") or "").strip()
    if not col:
        return None
    direction = str(order.get("direction") or "ASC").strip().upper()
    if direction not in ("ASC", "DESC"):
        direction = "ASC"
    safe_col = _safe_or_catalog_identifier(col, dialect, catalog_validated)
    return f"{safe_col} {direction}"

def build_select(
    table: str,
    columns: list[str] | None,
    where: dict[str, Any] | None,
    order: Any | None,
    limit: int | None,
    dialect: str,
    catalog_validated_identifiers: bool = False,
) -> str:
    """Build a complete SELECT query with strict parameter validation."""
    safe_table = _safe_or_catalog_identifier(table, dialect, catalog_validated_identifiers)
    if not columns:
        safe_cols = "*"
    else:
        safe_cols = ", ".join(
            _safe_or_catalog_identifier(c, dialect, catalog_validated_identifiers)
            for c in columns
        )
    
    sql = f"SELECT {safe_cols} FROM {safe_table}"
    if where:
        cond = build_where_clause(where, dialect, catalog_validated=catalog_validated_identifiers)
        if cond:
            sql += f" WHERE {cond}"
    
    if order:
        if isinstance(order, dict):
            clause = build_order_clause(order, dialect, catalog_validated=catalog_validated_identifiers)
            if clause:
                sql += f" ORDER BY {clause}"
        elif isinstance(order, list):
            clauses = [
                build_order_clause(o, dialect, catalog_validated=catalog_validated_identifiers)
                for o in order if o
            ]
            clauses = [c for c in clauses if c]
            if clauses:
                sql += f" ORDER BY {', '.join(clauses)}"
                
    if limit is not None:
        sql += f" LIMIT {limit}"
    return sql
