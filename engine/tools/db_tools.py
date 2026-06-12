"""db.* tool handlers — the agent's database exploration toolkit.

Design principles:
  - Agent decides what to do and in what order.
  - Tools enforce safety at the boundary layer.
  - Live introspection hits the real database, not a stale catalog.
  - Synonyms and sensitivity rules live in the database, not in code.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core.tool_registry import ToolContext
from engine.agent_core.types import ToolObservation
from engine.errors import GuardrailValidationError, SQLExecutionError, SQLQueryTimeoutError
from engine.models import DataSource, QueryHistory, SchemaColumn, SchemaTable, SemanticAlias
from engine.policy.redactor import DataRedactor
from engine.sql.executor import execute_query

logger = logging.getLogger("databox.tools.db")

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

MAX_PREVIEW_ROWS = 20
DEFAULT_PREVIEW_ROWS = 10
DEFAULT_SEARCH_LIMIT = 20
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]+")

# Minimal bootstrap — real synonyms live in the SemanticAlias table.
# These defaults are written into the database on first access and never
# used directly.
_BOOTSTRAP_SYNONYMS: dict[str, list[str]] = {
    "用户": ["user", "users", "customer", "member", "account"],
    "会员": ["user", "users", "customer", "member", "account"],
    "客户": ["user", "users", "customer", "member"],
    "手机号": ["phone", "mobile", "tel", "telephone", "msisdn"],
    "手机": ["phone", "mobile", "tel", "telephone", "msisdn"],
    "电话": ["phone", "mobile", "tel", "telephone"],
    "邮箱": ["email", "mail"],
    "邮件": ["email", "mail"],
    "订单": ["order", "orders", "purchase"],
    "商品": ["product", "products", "sku"],
    "支付": ["payment", "payments", "pay"],
    "地址": ["address", "shipping_address"],
    "时间": ["created_at", "updated_at", "date", "time"],
    "渠道": ["channel", "source", "utm"],
}

# Default sensitive-column patterns.  Also bootstrapped into the database,
# but we keep a compiled fallback for the case where the DB store is empty.
_SENSITIVE_PATTERN_STRINGS = [
    r"\b(password|passwd|secret|token|credential|api_key)\b",
    r"\b(email|mail)\b",
    r"\b(phone|mobile|tel|telephone|msisdn)\b",
    r"\b(address|addr|postal|zip_code)\b",
    r"\b(ip_address|ipaddr|client_ip|server_ip)\b",
    r"\b(card|credit_card|debit_card)\b",
    r"\b(ssn|social_security|tax_id|national_id)\b",
    r"\b(passport|driver_license)\b",
]
_SENSITIVE_FALLBACK = re.compile("|".join(_SENSITIVE_PATTERN_STRINGS), re.IGNORECASE)


# ===================================================================
# public tool handlers
# ===================================================================


def db_observe(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Return the database map — tables, domains, counts, query stats.

    Modes
    -----
    - ``"overview"`` (default): full map with schemas + domains.
    - ``"schema"``:  like overview but scoped to one schema.
    - ``"tables"``:  detailed cards for a specific list of tables.
    """
    start = time.perf_counter()
    mode = _validate_mode(args.get("mode"))
    table_names = _string_list(args.get("table_names"))

    tables = _catalog_tables(ctx.db, ctx.request.datasource_id)
    ds = _datasource(ctx.db, ctx.request.datasource_id)
    selected = _filter_tables(tables, table_names)

    output: dict[str, Any] = {
        "datasource_id": ds.id,
        "datasource_name": ds.name,
        "dialect": ds.db_type or "mysql",
        "mode": mode,
        "catalog_status": ds.last_sync_status or ("ready" if tables else "empty"),
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "table_count": len(tables),
        "warnings": _catalog_warnings(tables),
    }

    if mode in ("overview", "schema"):
        output["schemas"] = _schema_sections(ctx.db, selected or tables)
        output["domains"] = _domain_sections(ctx.db, selected or tables)
    elif mode == "tables":
        output["tables"] = [_table_card(ctx.db, ds.id, table) for table in selected]
        output["missing_tables"] = _missing_table_names(tables, table_names)

    return _success("db.observe", args, output, start)


def db_search(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Search tables and columns by keywords, aliases, history, and FK
    expansion.

    Scoring weights (additive):
      - exact name match ...................... +90
      - partial name / token match ............ +60
      - comment / metadata match .............. +30
      - semantic alias match .................. +80
      - history hit ........................... +20
      - FK expansion (connected to high-score)  +15
      - tag match ............................. +10
    """
    start = time.perf_counter()
    query = str(args.get("query") or ctx.request.question or "").strip()
    limit = _clamp(int(args.get("limit", DEFAULT_SEARCH_LIMIT) or DEFAULT_SEARCH_LIMIT), 1, 50)

    tables = _catalog_tables(ctx.db, ctx.request.datasource_id)
    aliases = _load_aliases(ctx.db, ctx.request.datasource_id)
    synonyms = _load_synonyms(ctx.db, ctx.request.datasource_id)
    terms = _expanded_terms(query, synonyms)

    results: list[dict[str, Any]] = []
    for table in tables:
        table_result = _score_table(table, aliases, terms, query)
        if table_result:
            results.append(table_result)
        for col in _ordered_columns(table):
            col_result = _score_column(table, col, aliases, terms, query)
            if col_result:
                results.append(col_result)

    # FK expansion: boost tables connected to high-score tables
    _apply_fk_expansion(results, tables)

    results.sort(key=lambda item: (-float(item["score"]), item["type"], item["name"]))

    output = {
        "query": query,
        "terms": terms,
        "results": results[:limit],
        "total_matches": len(results),
    }
    return _success("db.search", args, output, start)


def db_inspect(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Live introspection of a table or column from the real database.

    Connects to the live database and runs system introspection queries
    (``information_schema``, ``pg_catalog``, ``PRAGMA``) to return the
    current structure — not a stale catalog snapshot.
    """
    start = time.perf_counter()
    target = str(args.get("target") or "").strip()
    if not target:
        return _failed("db.inspect", args, "target is required (table or table.column).", start)

    ds = _datasource(ctx.db, ctx.request.datasource_id)
    dialect = (ds.db_type or "mysql").lower()

    try:
        if dialect == "sqlite":
            output = _sqlite_inspect_detail(ctx.db, ds, target)
        elif dialect == "postgres" or dialect == "postgresql":
            output = _pg_inspect_detail(ctx.db, ds, target)
        else:
            output = _mysql_inspect_detail(ctx.db, ds, target)
    except ValueError as exc:
        return _failed("db.inspect", args, str(exc), start)
    except Exception as exc:
        logger.exception("db.inspect failed for %s", target)
        return _failed("db.inspect", args, f"Inspect error: {exc}", start)

    return _success("db.inspect", args, output, start)


def db_preview(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Preview a small, safe sample of live data from one table.

    Safety: column whitelist, LIMIT ≤ 20, TrustGate, timeout, redaction.
    """
    start = time.perf_counter()
    table_name = str(args.get("table") or args.get("table_name") or "").strip()
    if not table_name:
        return _failed("db.preview", args, "table is required.", start)

    catalog_table = _catalog_table(ctx.db, ctx.request.datasource_id, table_name)
    if catalog_table is None:
        return _failed("db.preview", args, f"Unknown table: {table_name}", start)

    available = {str(c.column_name): c for c in _ordered_columns(catalog_table)}
    requested = _resolve_preview_columns(args, available)
    unknown = [n for n in requested if n not in available]
    if unknown:
        return _failed(
            "db.preview", args,
            f"Unknown column(s) for {table_name}: {', '.join(unknown)}",
            start,
        )

    requested_limit = _clamp(int(args.get("limit", DEFAULT_PREVIEW_ROWS) or DEFAULT_PREVIEW_ROWS), 1, MAX_PREVIEW_ROWS)
    dialect = (ctx.request.datasource_id and _resolve_dialect(ctx)) or "mysql"
    sql = _build_preview_sql(table_name, requested, requested_limit, args, dialect)

    try:
        result = execute_query(
            ctx.db,
            ctx.request.datasource_id,
            sql,
            question=f"Preview table {table_name}",
            safety_policy="table_preview",
        )
    except Exception as exc:
        return _execution_failed("db.preview", args, exc, start)

    sensitivity = _load_sensitivity(ctx.db, ctx.request.datasource_id)
    rows = [_redact_row(row, sensitivity) for row in result.get("rows") or []]
    safe_sql = str((result.get("safetyDecision") or {}).get("safe_sql") or result.get("safe_sql") or sql)

    output = {
        "table": table_name,
        "columns": requested,
        "returned_rows": len(rows),
        "limit_applied": requested_limit,
        "rows": rows,
        "safe_sql": safe_sql,
        "truncated": bool(result.get("truncated")),
        "warnings": result.get("warnings") or [],
        "column_summaries": [_column_summary_preview(available[n]) for n in requested],
        "audit": {
            "readonly_checked": True,
            "limit_enforced": True,
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
    }
    return _success("db.preview", args, output, start)


def db_query(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Execute Agent-written read-only SQL with full safety enforcement.

    The SQL passes through guardrail → TrustGate → dry-run → policy
    before execution.  Agent must write its own SQL — this tool does not
    generate it.
    """
    start = time.perf_counter()
    sql = str(args.get("sql") or "").strip()
    if not sql:
        return _failed("db.query", args, "sql is required.", start)

    try:
        result = execute_query(
            ctx.db,
            ctx.request.datasource_id,
            sql,
            question=str(args.get("question") or ctx.request.question or ""),
            safety_policy="readonly",
        )
    except Exception as exc:
        return _execution_failed("db.query", args, exc, start)

    decision = result.get("safetyDecision") or {}
    safe_sql = str(decision.get("safe_sql") or "").strip()
    sensitivity = _load_sensitivity(ctx.db, ctx.request.datasource_id)
    rows = [_redact_row(row, sensitivity) for row in result.get("rows") or []]

    output = {
        "status": "success",
        "columns": result.get("columns") or [],
        "column_types": _infer_column_types(result),
        "returned_rows": len(rows),
        "truncated": bool(result.get("truncated")),
        "rows": rows,
        "safe_sql": safe_sql or sql,
        "execution_time_ms": result.get("latencyMs", 0),
        "explain_plan": result.get("explainPlan"),
        "warnings": result.get("warnings") or [],
        "audit": {
            "readonly_checked": True,
            "limit_injected": _limit_was_injected(sql, safe_sql),
            "guardrail_result": (result.get("guardrail") or {}).get("result"),
            "trust_gate": True,
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
    }
    return _success("db.query", args, output, start)


def db_remember(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Persist a business-semantic memory proposed by the Agent.

    Memory types
    ------------
    - ``table_alias``         — alias names for a table
    - ``column_alias``        — alias names for a column
    - ``column_values``       — observed enum-like values for a column
    - ``join_path``           — a discovered JOIN relationship + description
    - ``business_definition`` — a named business metric with SQL + description
    """
    start = time.perf_counter()
    memory_type = str(args.get("type") or "").strip()
    target = str(args.get("target") or "").strip()
    evidence = str(args.get("evidence") or args.get("description") or "").strip()

    if not memory_type or not target:
        return _failed("db.remember", args, "type and target are required.", start)

    ds = _datasource(ctx.db, ctx.request.datasource_id)
    # Determine whether user confirmation is required
    needs_approval = _remember_needs_approval(ds, memory_type)

    if memory_type in ("table_alias", "column_alias"):
        return _remember_alias(ctx, args, target, memory_type, evidence, start)

    if memory_type == "column_values":
        return _remember_column_values(ctx, args, target, evidence, needs_approval, start)

    if memory_type == "join_path":
        return _remember_join_path(ctx, args, target, evidence, needs_approval, start)

    if memory_type == "business_definition":
        return _remember_business_def(ctx, args, target, evidence, needs_approval, start)

    return _failed("db.remember", args, f"Unknown memory type: {memory_type}", start)


# ===================================================================
# db.observe helpers
# ===================================================================


def _validate_mode(mode: Any) -> str:
    m = str(mode or "overview").strip().lower()
    return m if m in ("overview", "schema", "tables") else "overview"


def _catalog_warnings(tables: list[SchemaTable]) -> list[str]:
    if not tables:
        return ["Local schema catalog is empty. Run schema.refresh_catalog first."]
    return []


def _schema_sections(db: Session, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    grouped: dict[str, list[SchemaTable]] = defaultdict(list)
    for t in tables:
        grouped[str(t.table_schema or "default")].append(t)
    return [
        {
            "name": schema,
            "table_count": len(rows),
            "tables": [_schema_table_summary(db, t) for t in sorted(rows, key=lambda x: str(x.table_name))],
        }
        for schema, rows in sorted(grouped.items())
    ]


def _schema_table_summary(db: Session, table: SchemaTable) -> dict[str, Any]:
    return {
        "name": str(table.table_name),
        "schema": str(table.table_schema or ""),
        "type": str(table.table_type or "table"),
        "comment": str(table.table_comment or ""),
        "columns": len(table.columns or []),
        "row_estimate": table.row_count_estimate or 0,
        "primary_key": [str(c.column_name) for c in _ordered_columns(table) if c.is_primary_key],
        "tags": _table_tags(table),
        "connected_tables": sorted(_connected_table_names(db, table)),
    }


def _table_card(db: Session, datasource_id: str, table: SchemaTable) -> dict[str, Any]:
    columns = _ordered_columns(table)
    pk = [str(c.column_name) for c in columns if c.is_primary_key]
    stats = _query_stats_for_table(db, datasource_id, str(table.table_name))
    return {
        "name": str(table.table_name),
        "schema": str(table.table_schema or ""),
        "type": str(table.table_type or "table"),
        "comment": str(table.table_comment or ""),
        "row_estimate": table.row_count_estimate or 0,
        "columns": [_column_summary(c) for c in columns],
        "primary_key": pk[0] if len(pk) == 1 else pk,
        "foreign_keys": [_fk_summary(c) for c in columns if c.is_foreign_key],
        "connected_tables": sorted(_connected_table_names(db, table)),
        "tags": _table_tags(table),
        "query_hit_count": stats["hit_count"],
        "last_queried_at": stats["last_queried_at"],
    }


def _query_stats_for_table(db: Session, datasource_id: str, table_name: str) -> dict[str, Any]:
    """Approximate query-hit count and last-queried timestamp for a table."""
    count = (
        db.query(QueryHistory)
        .filter(
            QueryHistory.data_source_id == datasource_id,
            QueryHistory.executed_sql.contains(table_name),
        )
        .count()
    )
    latest = (
        db.query(QueryHistory.created_at)
        .filter(
            QueryHistory.data_source_id == datasource_id,
            QueryHistory.executed_sql.contains(table_name),
        )
        .order_by(QueryHistory.created_at.desc())
        .first()
    )
    return {
        "hit_count": count,
        "last_queried_at": latest[0].isoformat() if latest and latest[0] else None,
    }


def _domain_sections(db: Session, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for t in tables:
        tags = _table_tags(t)
        domain = tags[0] if tags else "other"
        groups[domain].append(str(t.table_name))
    return [
        {"name": d, "label": d, "tables": sorted(names), "table_count": len(names)}
        for d, names in sorted(groups.items())
    ]


def _table_tags(table: SchemaTable) -> list[str]:
    """Derive domain tags from table name.

    In future this will read AI-generated tags from the catalog rather
    than pattern-matching in code.
    """
    name = str(table.table_name or "").lower()
    tags: list[str] = []
    patterns = [
        ("user", ["user", "member", "customer", "account"]),
        ("order", ["order", "cart", "coupon"]),
        ("product", ["product", "category", "sku", "inventory", "item"]),
        ("payment", ["payment", "pay", "refund", "transaction"]),
        ("shipping", ["shipping", "address", "carrier", "logistics"]),
        ("analytics", ["analytics", "click", "recommendation", "event", "log"]),
        ("system", ["system", "admin", "setting", "config"]),
        ("content", ["article", "post", "comment", "review", "tag"]),
    ]
    for tag, needles in patterns:
        if any(needle in name for needle in needles):
            tags.append(tag)
    return tags or ["other"]


def _connected_table_names(db: Session, table: SchemaTable) -> set[str]:
    connected: set[str] = set()
    # outbound FK — table's columns that reference other tables
    for col in (table.columns or []):
        if col.is_foreign_key and col.foreign_table_id:
            target = db.query(SchemaTable).filter(SchemaTable.id == col.foreign_table_id).first()
            if target is not None:
                connected.add(str(target.table_name))
    # inbound FK — other tables' columns that point to this table
    reverse = (
        db.query(SchemaColumn)
        .filter(SchemaColumn.foreign_table_id == table.id)
        .all()
    )
    for col in reverse:
        if col.table is not None:
            connected.add(str(col.table.table_name))
    return connected


def _fk_summary(col: SchemaColumn) -> dict[str, Any]:
    fk_table = getattr(col, "foreign_table", None)
    fk_col = getattr(col, "foreign_column", None)
    return {
        "column": str(col.column_name),
        "references_table": str(fk_table.table_name) if fk_table else None,
        "references_column": str(fk_col.column_name) if fk_col else None,
    }


# ===================================================================
# db.search helpers
# ===================================================================


def _expanded_terms(query: str, synonyms: dict[str, list[str]]) -> list[str]:
    terms: list[str] = []
    for token in TOKEN_RE.findall(query.lower()):
        terms.append(token)
        for syn in synonyms.get(token, []):
            terms.append(syn)
    # dedup preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


def _score_table(
    table: SchemaTable,
    aliases: list[SemanticAlias],
    terms: list[str],
    query: str,
) -> dict[str, Any] | None:
    name = str(table.table_name)
    comment = str(table.table_comment or "")
    haystack = f"{name} {comment} {' '.join(_table_tags(table))}".lower()
    score, reasons = _score_by_terms(name, haystack, terms)

    # alias boost
    for a in aliases:
        if a.target_type == "table" and a.target == name:
            if _alias_matches(a.alias, query, terms):
                score += 80
                reasons.append("alias_match")

    if score <= 0:
        return None
    return {
        "type": "table",
        "name": name,
        "table_name": name,
        "score": round(score / 100, 3),
        "reasons": sorted(set(reasons)),
        "short_comment": comment[:120] if comment else None,
        "tags": _table_tags(table),
        "columns": [str(c.column_name) for c in _ordered_columns(table)][:8],
    }


def _score_column(
    table: SchemaTable,
    col: SchemaColumn,
    aliases: list[SemanticAlias],
    terms: list[str],
    query: str,
) -> dict[str, Any] | None:
    table_name = str(table.table_name)
    col_name = str(col.column_name)
    ref = f"{table_name}.{col_name}"
    haystack = " ".join([
        table_name, col_name,
        str(col.column_type or col.data_type or ""),
        str(col.column_comment or ""),
    ]).lower()
    score, reasons = _score_by_terms(ref, haystack, terms)

    for a in aliases:
        if a.target_type == "column" and a.target == ref:
            if _alias_matches(a.alias, query, terms):
                score += 80
                reasons.append("alias_match")

    if score <= 0:
        return None
    return {
        "type": "column",
        "name": ref,
        "table_name": table_name,
        "column_name": col_name,
        "score": round(score / 100, 3),
        "reasons": sorted(set(reasons)),
        "data_type": str(col.column_type or col.data_type or ""),
        "comment": str(col.column_comment or ""),
    }


def _score_by_terms(name: str, haystack: str, terms: list[str]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    name_lower = name.lower()
    for term in terms:
        token = term.lower()
        if not token:
            continue
        # column refs end with ".token"
        if name_lower == token or name_lower.endswith(f".{token}"):
            score += 90
            reasons.append("name_exact")
        elif token in name_lower:
            score += 60
            reasons.append("name_match")
        elif token in haystack:
            score += 30
            reasons.append("metadata_match")
    return score, reasons


def _alias_matches(alias: str, query: str, terms: list[str]) -> bool:
    al = alias.lower()
    q = query.lower()
    return al in q or any(t in al or al in t for t in terms)


def _apply_fk_expansion(results: list[dict[str, Any]], tables: list[SchemaTable]) -> None:
    """Boost tables that are FK-connected to high-score tables."""
    high_score_tables = {r["table_name"] for r in results if r["type"] == "table" and float(r["score"]) >= 0.6}
    if not high_score_tables:
        return

    # build FK adjacency from catalog
    adj: dict[str, set[str]] = defaultdict(set)
    for t in tables:
        tname = str(t.table_name)
        for c in (t.columns or []):
            if c.is_foreign_key and c.foreign_table_id:
                fk_table = getattr(c, "foreign_table", None)
                if fk_table:
                    adj[tname].add(str(fk_table.table_name))
                    adj[str(fk_table.table_name)].add(tname)

    for r in results:
        tname = r.get("table_name", "")
        if tname in high_score_tables:
            continue
        if tname in adj and (adj[tname] & high_score_tables):
            r["score"] = round(float(r["score"]) + 0.15, 3)
            r.setdefault("reasons", []).append("fk_expansion")


# ===================================================================
# db.inspect helpers  (live introspection)
# ===================================================================


def _parse_target(target: str) -> tuple[str, str | None, str | None]:
    """Parse a target reference into (table_name, column_name, schema_name).

    Supports:
      - "users"              → table, no column, no schema
      - "users.id"           → table, column, no schema
      - "public.users"       → table, no column, schema=public
      - "public.users.id"    → table, column, schema=public
    """
    parts = [p for p in target.split(".") if p]
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        return parts[1], parts[2], parts[0]
    raise ValueError(f"Invalid target: {target}")


def _ds_to_dict(ds: DataSource) -> dict[str, Any]:
    """Convert ORM object to the dict expected by connection-param helpers."""
    return {
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "password_ciphertext": ds.password_ciphertext,
        "password_nonce": ds.password_nonce,
        "password_key_version": ds.password_key_version,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    }


# ---- SQLite live introspection ---------------------------------------


def _sqlite_inspect_detail(db: Session, ds: DataSource, target: str) -> dict[str, Any]:
    table_name, column_name, _schema = _parse_target(target)
    path = str(ds.database_name)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if not _sqlite_table_exists(conn, table_name):
            raise ValueError(f"Table not found: {table_name}")

        payload = _sqlite_table_payload(db, conn, ds.id, table_name)

        if column_name:
            for col in payload["columns"]:
                if col["name"] == column_name:
                    col["object_type"] = "column"
                    col["table"] = table_name
                    return col
            raise ValueError(f"Column not found: {target}")
        return payload


def _sqlite_table_payload(
    db: Session, conn: sqlite3.Connection, datasource_id: str, table_name: str
) -> dict[str, Any]:
    catalog = _catalog_table(db, datasource_id, table_name)
    comment_map: dict[str, str] = {}
    if catalog is not None:
        comment_map = {str(c.column_name): str(c.column_comment or "") for c in _ordered_columns(catalog)}

    fk_by_col = _sqlite_fk_map(conn, table_name)
    columns: list[dict[str, Any]] = []
    pk_cols: list[str] = []

    for row in conn.execute(f"PRAGMA table_info('{_sqlite_escape(table_name)}')"):
        name = str(row["name"])
        is_pk = bool(row["pk"])
        if is_pk:
            pk_cols.append(name)
        columns.append({
            "name": name,
            "type": str(row["type"] or ""),
            "nullable": not bool(row["notnull"] or is_pk),
            "default": row["dflt_value"],
            "primary_key": is_pk,
            "foreign_key": fk_by_col.get(name),
            "comment": comment_map.get(name, ""),
        })

    fks_out = [
        {"column": src, "references": {"table": fk["table"], "column": fk["column"]}}
        for src, fk in sorted(fk_by_col.items())
    ]

    return {
        "object_type": "table",
        "name": table_name,
        "type": _sqlite_table_type(conn, table_name),
        "dialect": "sqlite",
        "comment": str(catalog.table_comment or "") if catalog else "",
        "row_estimate": _sqlite_row_count(conn, table_name),
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys_out": fks_out,
        "foreign_keys_in": _sqlite_reverse_fks(conn, table_name),
        "indexes": _sqlite_indexes(conn, table_name, pk_cols),
        "source": "live",
    }


def _sqlite_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _sqlite_table_type(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return "table"
    return "view" if row["type"] == "view" else "table"


def _sqlite_fk_map(conn: sqlite3.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in conn.execute(f"PRAGMA foreign_key_list('{_sqlite_escape(table_name)}')"):
        result[str(row["from"])] = {"table": str(row["table"]), "column": str(row["to"])}
    return result


def _sqlite_reverse_fks(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    for t in tables:
        src = str(t["name"])
        for fk in conn.execute(f"PRAGMA foreign_key_list('{_sqlite_escape(src)}')"):
            if str(fk["table"]) == table_name:
                result.append({
                    "table": src,
                    "column": str(fk["from"]),
                    "references": {"column": str(fk["to"])},
                })
    return result


def _sqlite_indexes(
    conn: sqlite3.Connection, table_name: str, pk_cols: list[str]
) -> list[dict[str, Any]]:
    indexes: list[dict[str, Any]] = []
    if pk_cols:
        indexes.append({"name": "PRIMARY", "columns": pk_cols, "unique": True})
    for row in conn.execute(f"PRAGMA index_list('{_sqlite_escape(table_name)}')"):
        iname = str(row["name"])
        cols = [
            str(ci["name"])
            for ci in conn.execute(f"PRAGMA index_info('{_sqlite_escape(iname)}')")
            if ci["name"] is not None
        ]
        indexes.append({
            "name": iname,
            "columns": cols,
            "unique": bool(row["unique"]),
        })
    return indexes


def _sqlite_row_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    try:
        row = conn.execute(f'SELECT COUNT(*) FROM "{_sqlite_escape(table_name)}"').fetchone()
        return int(row[0]) if row else None
    except sqlite3.Error:
        return None


def _sqlite_escape(s: str) -> str:
    return s.replace("'", "''")


# ---- MySQL live introspection ----------------------------------------


def _mysql_inspect_detail(db: Session, ds: DataSource, target: str) -> dict[str, Any]:
    table_name, column_name, _schema = _parse_target(target)
    ds_dict = _ds_to_dict(ds)
    from engine.datasource import get_mysql_connection_params
    from engine.sql.executor import get_mysql_pool

    params = get_mysql_connection_params(ds_dict)
    pool = get_mysql_pool(ds.id, params)
    conn = pool.connect()

    try:
        database = ds_dict.get("database_name", "")
        if not _mysql_table_exists(conn, database, table_name):
            raise ValueError(f"Table not found: {table_name}")

        payload = _mysql_table_payload(db, conn, ds.id, database, table_name)

        if column_name:
            for col in payload["columns"]:
                if col["name"] == column_name:
                    col["object_type"] = "column"
                    col["table"] = table_name
                    return col
            raise ValueError(f"Column not found: {target}")
        return payload
    finally:
        conn.close()


def _mysql_table_exists(conn: Any, database: str, table_name: str) -> bool:
    row = conn.cursor().execute(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (database, table_name),
    ).fetchone()
    return row is not None


def _mysql_table_payload(
    db: Session, conn: Any, datasource_id: str, database: str, table_name: str
) -> dict[str, Any]:
    cur = conn.cursor()
    catalog = _catalog_table(db, datasource_id, table_name)
    comment_map: dict[str, str] = {}
    if catalog is not None:
        comment_map = {str(c.column_name): str(c.column_comment or "") for c in _ordered_columns(catalog)}

    # columns
    cur.execute(
        "SELECT c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE, c.COLUMN_DEFAULT, "
        "       c.COLUMN_COMMENT, c.COLUMN_KEY = 'PRI' AS is_pk, "
        "       kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME "
        "FROM information_schema.COLUMNS c "
        "LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu "
        "  ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA "
        " AND c.TABLE_NAME = kcu.TABLE_NAME "
        " AND c.COLUMN_NAME = kcu.COLUMN_NAME "
        " AND kcu.REFERENCED_TABLE_NAME IS NOT NULL "
        "WHERE c.TABLE_SCHEMA = %s AND c.TABLE_NAME = %s "
        "ORDER BY c.ORDINAL_POSITION",
        (database, table_name),
    )
    columns: list[dict[str, Any]] = []
    pk_cols: list[str] = []
    fks_out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        name = str(row[0])
        is_pk = bool(row[5])
        if is_pk:
            pk_cols.append(name)
        fk = None
        if row[6]:
            fk = {"table": str(row[6]), "column": str(row[7])}
            fks_out.append({"column": name, "references": fk})
        columns.append({
            "name": name,
            "type": str(row[1]),
            "nullable": str(row[2]).upper() == "YES",
            "default": row[3],
            "primary_key": is_pk,
            "foreign_key": fk,
            "comment": comment_map.get(name, str(row[4] or "")),
        })

    # reverse FKs
    fks_in: list[dict[str, Any]] = []
    cur.execute(
        "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_COLUMN_NAME "
        "FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME = %s",
        (database, table_name),
    )
    for row in cur.fetchall():
        fks_in.append({
            "table": str(row[0]),
            "column": str(row[1]),
            "references": {"column": str(row[2])},
        })

    # indexes
    indexes: list[dict[str, Any]] = []
    try:
        cur.execute(f"SHOW INDEX FROM `{table_name}` FROM `{database}`")
        index_groups: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            iname = str(row[2])
            if iname not in index_groups:
                index_groups[iname] = {
                    "name": iname,
                    "columns": [],
                    "unique": bool(not row[3]),
                }
            index_groups[iname]["columns"].append(str(row[4]))
        indexes = list(index_groups.values())
    except Exception:
        pass

    # row estimate
    row_est = None
    try:
        cur.execute(
            "SELECT TABLE_ROWS FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (database, table_name),
        )
        est = cur.fetchone()
        if est:
            row_est = int(est[0])
    except Exception:
        pass

    # table comment
    table_comment = ""
    try:
        cur.execute(
            "SELECT TABLE_COMMENT FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (database, table_name),
        )
        tc = cur.fetchone()
        if tc:
            table_comment = str(tc[0] or "")
    except Exception:
        pass

    return {
        "object_type": "table",
        "name": table_name,
        "type": "table",
        "dialect": "mysql",
        "comment": table_comment or (str(catalog.table_comment or "") if catalog else ""),
        "row_estimate": row_est,
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys_out": fks_out,
        "foreign_keys_in": fks_in,
        "indexes": indexes,
        "source": "live",
    }


# ---- PostgreSQL live introspection -----------------------------------


def _pg_inspect_detail(db: Session, ds: DataSource, target: str) -> dict[str, Any]:
    table_name, column_name, schema_name = _parse_target(target)
    ds_dict = _ds_to_dict(ds)
    from engine.datasource import get_postgres_connection_params
    from engine.sql.executor import get_postgres_pool

    params = get_postgres_connection_params(ds_dict)
    pool = get_postgres_pool(ds.id, params)
    conn = pool.connect()

    try:
        schema = schema_name or "public"
        if not _pg_table_exists(conn, schema, table_name):
            raise ValueError(f"Table not found: {schema}.{table_name}")

        payload = _pg_table_payload(db, conn, ds.id, schema, table_name)

        if column_name:
            for col in payload["columns"]:
                if col["name"] == column_name:
                    col["object_type"] = "column"
                    col["table"] = table_name
                    return col
            raise ValueError(f"Column not found: {target}")
        return payload
    finally:
        conn.close()


def _pg_table_exists(conn: Any, schema: str, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (schema, table_name),
    )
    return cur.fetchone() is not None


def _pg_table_payload(
    db: Session, conn: Any, datasource_id: str, schema: str, table_name: str
) -> dict[str, Any]:
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    catalog = _catalog_table(db, datasource_id, table_name)

    # columns
    cur.execute(
        "SELECT c.column_name, c.data_type, c.is_nullable, c.column_default, "
        "       pg_catalog.col_description("
        "         (c.table_schema||'.'||c.table_name)::regclass::oid, c.ordinal_position"
        "       ) AS col_comment, "
        "       CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_pk "
        "FROM information_schema.columns c "
        "LEFT JOIN ("
        "  SELECT ku.table_schema, ku.table_name, ku.column_name "
        "  FROM information_schema.table_constraints tc "
        "  JOIN information_schema.key_column_usage ku "
        "    ON tc.constraint_name = ku.constraint_name "
        "  WHERE tc.constraint_type = 'PRIMARY KEY'"
        ") pk "
        "  ON c.table_schema = pk.table_schema "
        " AND c.table_name = pk.table_name "
        " AND c.column_name = pk.column_name "
        "WHERE c.table_schema = %s AND c.table_name = %s "
        "ORDER BY c.ordinal_position",
        (schema, table_name),
    )
    columns: list[dict[str, Any]] = []
    pk_cols: list[str] = []
    for row in cur.fetchall():
        name = str(row["column_name"])
        is_pk = bool(row["is_pk"])
        if is_pk:
            pk_cols.append(name)
        columns.append({
            "name": name,
            "type": str(row["data_type"]),
            "nullable": str(row["is_nullable"]).upper() == "YES",
            "default": row["column_default"],
            "primary_key": is_pk,
            "foreign_key": None,  # filled below
            "comment": str(row["col_comment"] or ""),
        })

    # FK out
    fks_out: list[dict[str, Any]] = []
    col_map = {c["name"]: c for c in columns}
    cur.execute(
        "SELECT kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "AND tc.table_schema = kcu.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "AND tc.table_schema = ccu.table_schema "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND tc.table_schema = %s AND tc.table_name = %s",
        (schema, table_name),
    )
    for row in cur.fetchall():
        col_name = str(row["column_name"])
        fk = {"table": str(row["ref_table"]), "column": str(row["ref_column"])}
        fks_out.append({"column": col_name, "references": fk})
        if col_name in col_map:
            col_map[col_name]["foreign_key"] = fk

    # FK in (reverse)
    fks_in: list[dict[str, Any]] = []
    cur.execute(
        "SELECT tc.table_name, kcu.column_name, ccu.column_name AS ref_column "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "AND tc.table_schema = kcu.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "AND tc.table_schema = ccu.table_schema "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND tc.table_schema = %s AND ccu.table_name = %s",
        (schema, table_name),
    )
    for row in cur.fetchall():
        fks_in.append({
            "table": str(row["table_name"]),
            "column": str(row["column_name"]),
            "references": {"column": str(row["ref_column"])},
        })

    # indexes
    indexes: list[dict[str, Any]] = []
    try:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = %s AND tablename = %s",
            (schema, table_name),
        )
        for row in cur.fetchall():
            indexes.append({
                "name": str(row["indexname"]),
                "definition": str(row["indexdef"]),
                "unique": "UNIQUE" in str(row["indexdef"]).upper(),
            })
    except Exception:
        pass

    # row estimate
    row_est = None
    try:
        cur.execute(
            "SELECT n_live_tup FROM pg_stat_user_tables "
            "WHERE schemaname = %s AND relname = %s",
            (schema, table_name),
        )
        est = cur.fetchone()
        if est:
            row_est = int(est["n_live_tup"])
    except Exception:
        pass

    # table comment
    table_comment = ""
    try:
        cur.execute(
            "SELECT obj_description(%s::regclass, 'pg_class')", (f"{schema}.{table_name}",)
        )
        tc = cur.fetchone()
        if tc:
            table_comment = str(tc[0] or "")
    except Exception:
        pass

    return {
        "object_type": "table",
        "name": table_name,
        "type": "table",
        "dialect": "postgresql",
        "comment": table_comment or (str(catalog.table_comment or "") if catalog else ""),
        "row_estimate": row_est,
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys_out": fks_out,
        "foreign_keys_in": fks_in,
        "indexes": indexes,
        "source": "live",
    }


# ===================================================================
# db.preview helpers
# ===================================================================


def _resolve_dialect(ctx: ToolContext) -> str:
    ds = _datasource(ctx.db, ctx.request.datasource_id)
    return (ds.db_type or "mysql").lower()


def _resolve_preview_columns(args: dict[str, Any], available: dict[str, SchemaColumn]) -> list[str]:
    requested = _string_list(args.get("columns"))
    if not requested:
        # default: first 8 non-sensitive columns
        safe = [n for n, c in available.items() if not _looks_sensitive(n)]
        return safe[:8]
    return requested


def _validate_sql_fragment(fragment: str, context: str) -> None:
    """Validate a user-supplied SQL fragment using sqlglot AST parsing.

    Rejects fragments containing DML/DDL keywords or multi-statement patterns.
    Uses AST-level validation (same approach as guardrail.py) rather than
    regex blacklists which are inherently bypassable.
    """
    import sqlglot
    import sqlglot.errors

    # Quick rejection of obviously dangerous tokens
    dangerous = {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE",
                 "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "UNION",
                 "INTO", "LOAD_FILE", "SLEEP", "BENCHMARK"}
    tokens = set(re.findall(r"\b\w+\b", fragment.upper()))
    if tokens & dangerous:
        raise ValueError(f"Dangerous keyword in {context} fragment")

    # AST-level validation: try parsing as a standalone expression
    try:
        parsed = sqlglot.parse_one(fragment, read="mysql", error_level=sqlglot.errors.ErrorLevel.RAISE)
        if parsed is None:
            return
        if parsed.key in ("drop", "delete", "insert", "update", "create", "alter",
                          "truncate", "execute", "grant", "revoke"):
            raise ValueError(f"Dangerous statement type '{parsed.key}' in {context} fragment")
    except sqlglot.errors.ParseError:
        # If parse fails, allow it — it might be a valid WHERE/ORDER BY fragment
        # that isn't a complete statement. The token check above catches the worst.
        pass


def _build_preview_sql(
    table_name: str,
    columns: list[str],
    limit: int,
    args: dict[str, Any],
    dialect: str,
) -> str:
    q = "`" if dialect == "mysql" else '"'
    safe_table = f"{q}{table_name}{q}"
    safe_cols = ", ".join(f"{q}{c}{q}" for c in columns)

    sql = f"SELECT {safe_cols} FROM {safe_table}"

    # structured WHERE
    where = args.get("where")
    if isinstance(where, dict):
        cond = _build_where_clause(where, q)
        if cond:
            sql += f" WHERE {cond}"
    elif isinstance(where, str) and where.strip():
        cleaned = where.strip()
        _validate_sql_fragment(cleaned, "WHERE")
        sql += f" WHERE {cleaned}"

    # ORDER BY
    order = args.get("order_by")
    if isinstance(order, str) and order.strip():
        cleaned = order.strip()
        _validate_sql_fragment(cleaned, "ORDER BY")
        sql += f" ORDER BY {cleaned}"

    sql += f" LIMIT {limit}"
    return sql


_SAFE_OPS: frozenset[str] = frozenset({
    "=", "!=", "<>", "<", ">", "<=", ">=",
    "LIKE", "NOT LIKE", "IN", "NOT IN",
    "IS", "IS NOT",
})


def _build_where_clause(where: dict[str, Any], quote: str) -> str | None:
    col = str(where.get("column") or "")
    op = str(where.get("op") or "=").strip().upper()
    value = where.get("value")
    if not col:
        return None
    if op not in _SAFE_OPS:
        raise ValueError(f"Unsafe operator in WHERE clause: {op}")
    safe_col = f"{quote}{col}{quote}"
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


def _column_summary_preview(col: SchemaColumn) -> dict[str, Any]:
    return {
        "name": str(col.column_name),
        "type": str(col.column_type or col.data_type or ""),
        "nullable": bool(col.is_nullable),
        "sensitive": _looks_sensitive(str(col.column_name)),
    }


# ===================================================================
# db.query helpers
# ===================================================================


def _infer_column_types(result: dict[str, Any]) -> list[str]:
    """Best-effort column type extraction from execution result."""
    rows = result.get("rows") or []
    columns = result.get("columns") or []
    if not rows or not columns:
        return []
    first = rows[0]
    types: list[str] = []
    for col in columns:
        val = first.get(col) if isinstance(first, dict) else None
        if val is None:
            types.append("unknown")
        elif isinstance(val, bool):
            types.append("boolean")
        elif isinstance(val, int):
            types.append("integer")
        elif isinstance(val, float):
            types.append("float")
        elif isinstance(val, bytes):
            types.append("binary")
        else:
            types.append("string")
    return types


# ===================================================================
# db.remember helpers
# ===================================================================


def _remember_needs_approval(ds: DataSource, memory_type: str) -> bool:
    env = (ds.env or "dev").lower()
    if memory_type in ("table_alias", "column_alias", "column_values"):
        return env == "prod"
    # join_path, business_definition always need approval
    return True


def _remember_alias(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    memory_type: str,
    evidence: str,
    start: float,
) -> ToolObservation:
    target_type = "column" if "." in target else "table"
    aliases = _string_list(args.get("aliases"))
    value = args.get("value")
    if isinstance(value, str) and value.strip():
        aliases.append(value.strip())
    aliases = sorted(set(a.strip() for a in aliases if a.strip()))

    if not aliases:
        return _failed("db.remember", args, "aliases or value is required.", start)

    created: list[dict[str, Any]] = []
    for alias in aliases:
        existing = (
            ctx.db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == ctx.request.datasource_id,
                SemanticAlias.alias == alias,
                SemanticAlias.target_type == target_type,
                SemanticAlias.target == target,
            )
            .first()
        )
        if existing is None:
            ctx.db.add(SemanticAlias(
                data_source_id=ctx.request.datasource_id,
                alias=alias,
                target_type=target_type,
                target=target,
                description=evidence[:500],
            ))
            created.append({"alias": alias, "target": target, "target_type": target_type})

    ctx.db.commit()
    return _success("db.remember", args, {
        "status": "remembered",
        "type": memory_type,
        "target": target,
        "created": created,
        "will_affect_future_search": len(created) > 0,
    }, start)


def _remember_column_values(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    evidence: str,
    needs_approval: bool,
    start: float,
) -> ToolObservation:
    if needs_approval:
        return _success("db.remember", args, {
            "status": "pending_confirmation",
            "type": "column_values",
            "target": target,
            "reason": "prod environment requires user confirmation for data observations.",
        }, start)

    values = _string_list(args.get("values") or args.get("value"))
    if not values:
        return _failed("db.remember", args, "values list is required for column_values.", start)

    created: list[dict[str, Any]] = []
    for v in values:
        existing = (
            ctx.db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == ctx.request.datasource_id,
                SemanticAlias.alias == v,
                SemanticAlias.target_type == "column_value",
                SemanticAlias.target == target,
            )
            .first()
        )
        if existing is None:
            ctx.db.add(SemanticAlias(
                data_source_id=ctx.request.datasource_id,
                alias=v,
                target_type="column_value",
                target=target,
                description=f"Observed via db.preview. {evidence}"[:500],
            ))
            created.append({"value": v, "target": target})

    ctx.db.commit()
    return _success("db.remember", args, {
        "status": "remembered",
        "type": "column_values",
        "target": target,
        "created": created,
        "will_affect_future_search": len(created) > 0,
    }, start)


def _remember_join_path(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    evidence: str,
    needs_approval: bool,
    start: float,
) -> ToolObservation:
    join_value = args.get("value") or args.get("join_condition")
    if not isinstance(join_value, dict):
        return _failed("db.remember", args,
                        "value must be a join_condition dict {left_table, left_column, right_table, right_column, join_type, description}.",
                        start)

    alias_text = (
        f"{join_value.get('left_table', '')}.{join_value.get('left_column', '')} "
        f"↔ {join_value.get('right_table', '')}.{join_value.get('right_column', '')}"
    )
    description = str(join_value.get("description", evidence))[:500]

    existing = (
        ctx.db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == ctx.request.datasource_id,
            SemanticAlias.target_type == "join_path",
            SemanticAlias.target == target,
            SemanticAlias.alias == alias_text.strip(),
        )
        .first()
    )
    if existing is None:
        ctx.db.add(SemanticAlias(
            data_source_id=ctx.request.datasource_id,
            alias=alias_text.strip(),
            target_type="join_path",
            target=target,
            description=description,
        ))
        ctx.db.commit()

    approval_note = "requires user confirmation" if needs_approval else "saved"
    return _success("db.remember", args, {
        "status": "pending_confirmation" if needs_approval else "remembered",
        "type": "join_path",
        "target": target,
        "join": join_value,
        "note": approval_note,
    }, start)


def _remember_business_def(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    evidence: str,
    needs_approval: bool,
    start: float,
) -> ToolObservation:
    definition = args.get("value") or args.get("definition")
    description = ""
    if isinstance(definition, dict):
        description = str(definition.get("description", definition.get("sql", evidence)))[:500]
    elif isinstance(definition, str):
        description = definition[:500]

    existing = (
        ctx.db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == ctx.request.datasource_id,
            SemanticAlias.target_type == "business_definition",
            SemanticAlias.target == target,
        )
        .first()
    )
    if existing is None:
        ctx.db.add(SemanticAlias(
            data_source_id=ctx.request.datasource_id,
            alias=target,
            target_type="business_definition",
            target=target,
            description=description,
        ))
        ctx.db.commit()

    return _success("db.remember", args, {
        "status": "pending_confirmation" if needs_approval else "remembered",
        "type": "business_definition",
        "target": target,
        "definition": definition,
        "note": "Business definitions always require user confirmation.",
    }, start)


# ===================================================================
# Synonym & sensitivity stores (database-backed)
# ===================================================================


def _load_synonyms(db: Session, datasource_id: str) -> dict[str, list[str]]:
    """Return synonym map for a datasource.

    First call bootstraps the hardcoded defaults into the SemanticAlias
    table.  Subsequent calls read from the database.  User-added aliases
    (via ``db.remember``) are merged in automatically.
    """
    rows = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type.in_(("synonym", "table", "column")),
        )
        .all()
    )
    if not rows:
        _bootstrap_synonyms(db, datasource_id)
        rows = (
            db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type.in_(("synonym", "table", "column")),
            )
            .all()
        )

    result: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        alias = str(r.alias).strip().lower()
        target = str(r.target).strip().lower()
        if r.target_type == "synonym":
            # synonym entries map a Chinese term → English term
            result[alias].append(target)
        elif r.target_type in ("table", "column"):
            # table/column aliases map English name → alias
            result[target].append(alias)
    return dict(result)


def _bootstrap_synonyms(db: Session, datasource_id: str) -> None:
    """Write built-in synonym defaults into the database."""
    for chinese_term, english_terms in _BOOTSTRAP_SYNONYMS.items():
        for eng in english_terms:
            db.add(SemanticAlias(
                data_source_id=datasource_id,
                alias=chinese_term.strip().lower(),
                target_type="synonym",
                target=eng.strip().lower(),
                description="Bootstrapped default",
            ))
    db.commit()


def _load_aliases(db: Session, datasource_id: str) -> list[SemanticAlias]:
    """Return all user-facing aliases (table_alias, column_alias)."""
    return (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type.in_(("table", "column")),
        )
        .all()
    )


def _load_sensitivity(db: Session, datasource_id: str) -> re.Pattern:
    """Return a compiled regex of sensitive column patterns.

    Reads from SemanticAlias rows with target_type='sensitive'.
    Falls back to the built-in default set.
    """
    rows = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type == "sensitive",
        )
        .all()
    )
    if not rows:
        _bootstrap_sensitivity(db, datasource_id)
        rows = (
            db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type == "sensitive",
            )
            .all()
        )

    patterns = [str(r.alias) for r in rows]
    if not patterns:
        return _SENSITIVE_FALLBACK
    return re.compile("|".join(patterns))


def _bootstrap_sensitivity(db: Session, datasource_id: str) -> None:
    """Write built-in sensitivity patterns into the database."""
    for pat in _SENSITIVE_PATTERN_STRINGS:
        db.add(SemanticAlias(
            data_source_id=datasource_id,
            alias=pat,
            target_type="sensitive",
            target="*",
            description="Bootstrapped default",
        ))
    db.commit()


def _looks_sensitive(column_name: str) -> bool:
    """Quick inline check without DB access (used during preview column selection)."""
    return bool(_SENSITIVE_FALLBACK.search(column_name))


# ===================================================================
# shared helpers
# ===================================================================


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
    redacted: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and sensitivity and sensitivity.search(key):
            redacted[key] = DataRedactor.redact_sql(str(value))
        else:
            redacted[key] = value
    return redacted


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
