from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from engine.tools.runtime.context import ToolContext
from engine.ai_index import tokenize_query
from engine.models import SchemaSearchDoc
from engine.tools.db._common import (
    _catalog_tables,
    _clamp,
    _ordered_columns,
    DEFAULT_SEARCH_LIMIT,
    tool_handler,
)


@tool_handler("db.search")
def db_search(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Search tables and columns via FTS5 when AI-enriched; fallback to keyword otherwise."""
    query = str(args.get("query") or ctx.request.question or "").strip()
    limit = _clamp(int(args.get("limit", DEFAULT_SEARCH_LIMIT) or DEFAULT_SEARCH_LIMIT), 1, 50)

    # Check if AI enrichment has run (schema_search_docs exists)
    has_docs = (
        ctx.db.query(SchemaSearchDoc)
        .filter(SchemaSearchDoc.datasource_id == ctx.request.datasource_id)
        .first()
    )

    if has_docs is not None:
        results = _fts_search(ctx.db, ctx.request.datasource_id, query, limit)
        return {
            "query": query,
            "limit": limit,
            "engine": "fts5",
            "results": results,
            "total_matches": len(results),
        }
    else:
        results = _fallback_keyword_search(ctx, query, limit)
        return {
            "query": query,
            "limit": limit,
            "engine": "keyword_fallback",
            "results": results,
            "total_matches": len(results),
        }


def _fts_search(db: Session, datasource_id: str, query: str, limit: int) -> list[dict[str, Any]]:
    """FTS5-based search using AI-enriched schema_search_docs."""
    from sqlalchemy import text as sa_text

    tokens = tokenize_query(query)
    
    # Filter tokens to prevent FTS5 operator injection and enforce character whitelist
    valid_tokens = []
    for t in tokens:
        if t.upper() in {"AND", "OR", "NOT", "NEAR"}:
            continue
        if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$", t):
            continue
        valid_tokens.append(t)
    tokens = valid_tokens

    if not tokens:
        return []

    # Build FTS5 query: exact phrases + OR tokens
    exact_parts = [f'"{t}"' for t in tokens if len(t) >= 2]
    token_parts = [t for t in tokens if len(t) >= 2]
    fts_query = " OR ".join(exact_parts + token_parts)

    # FTS5 recall
    sql = sa_text("""
        SELECT d.*, fts.rank
        FROM schema_search_fts fts
        JOIN schema_search_docs d ON d.id = fts.rowid
        WHERE fts MATCH :q AND d.datasource_id = :ds_id
        ORDER BY fts.rank
        LIMIT :lim
    """)
    rows = db.execute(sql, {"q": fts_query, "ds_id": datasource_id, "lim": limit * 3}).fetchall()

    # Score and group
    results: list[dict[str, Any]] = []
    seen_tables: set[str] = set()
    for row in rows:
        item = _row_to_search_result(row, tokens, query)
        if item is None:
            continue
        if item["type"] == "table":
            if item["table_name"] in seen_tables:
                continue
            seen_tables.add(item["table_name"])
        results.append(item)

    results.sort(key=lambda r: (-float(r["score"]), r["type"], r["name"]))
    return results[:limit]


def _row_to_search_result(row, tokens: list[str], query: str) -> dict[str, Any] | None:
    """Convert a schema_search_docs row to a search result dict with scoring."""
    entity_type = str(getattr(row, "entity_type", "table") or "table")
    score = _compute_total_score(row, tokens, query)
    if score <= 0:
        return None

    item: dict[str, Any] = {
        "type": entity_type,
        "name": str(getattr(row, "name", "")),
        "table_name": str(getattr(row, "table_name", "")),
        "score": round(score, 3),
        "reasons": _compute_reasons(row, tokens),
    }

    if entity_type == "table":
        item["ai_description"] = str(getattr(row, "ai_description", "") or "")
        item["table_role"] = str(getattr(row, "table_role", "") or "")

        try:
            item["semantic_tags"] = json.loads(getattr(row, "semantic_tags", "[]") or "[]")
        except (json.JSONDecodeError, TypeError):
            item["semantic_tags"] = []

    if entity_type == "column":
        item["column_name"] = str(getattr(row, "column_name", ""))
        item["column_role"] = str(getattr(row, "column_role", "") or "")
        item["metric_type"] = str(getattr(row, "metric_type", "") or "")

    return item


def _compute_total_score(row, tokens: list[str], query: str) -> float:
    """Compute unified total_score."""
    aliases_raw = str(getattr(row, "aliases", "") or "")
    terms_raw = str(getattr(row, "business_terms", "") or "")
    desc_raw = str(getattr(row, "ai_description", "") or "")
    name_raw = str(getattr(row, "name", "") or "")

    # exact_alias_match (0 or 1)
    exact_alias = 0.0
    for token in tokens:
        if token.lower() in aliases_raw.lower():
            exact_alias = 1.0
            break
    if not exact_alias:
        for token in tokens:
            if token.lower() == name_raw.lower() or name_raw.lower().endswith(f".{token.lower()}"):
                exact_alias = 1.0
                break

    # business_term_match (coverage ratio)
    all_terms = terms_raw.lower().split()
    if all_terms:
        hits = sum(1 for t in all_terms if any(tok.lower() in t for tok in tokens))
        term_score = hits / len(all_terms) if all_terms else 0
    else:
        term_score = 0.0

    # field_name_match (token coverage in search_text)
    search_text = str(getattr(row, "search_text", "") or "").lower()
    if tokens:
        hits = sum(1 for tok in tokens if tok.lower() in search_text)
        field_score = hits / len(tokens)
    else:
        field_score = 0.0

    # ai_description_match
    desc_lower = desc_raw.lower()
    if tokens and desc_lower:
        hits = sum(1 for tok in tokens if tok.lower() in desc_lower)
        desc_score = hits / len(tokens)
    else:
        desc_score = 0.0

    # structure_boost
    col_role = str(getattr(row, "column_role", "") or "")
    m_type = str(getattr(row, "metric_type", "") or "")
    struct_score = 0.0
    if col_role == "time":
        struct_score += 0.3
    if col_role == "measure" or m_type:
        struct_score += 0.3
    if col_role == "dimension":
        struct_score += 0.2

    # usage_boost — placeholder
    usage_score = 0.0

    total = (
        exact_alias * 0.25
        + term_score * 0.25
        + field_score * 0.20
        + desc_score * 0.15
        + min(struct_score, 1.0) * 0.10
        + usage_score * 0.05
    )
    return total * 100


def _compute_reasons(row, tokens: list[str]) -> list[str]:
    """Generate human-readable reasons for the match."""
    reasons: list[str] = []
    name = str(getattr(row, "name", "") or "")
    aliases = str(getattr(row, "aliases", "") or "")
    terms = str(getattr(row, "business_terms", "") or "")
    table_name = str(getattr(row, "table_name", "") or "")

    for token in tokens:
        tl = token.lower()
        if tl == name.lower() or name.lower().endswith(f".{tl}"):
            reasons.append(f"精确名称命中: {token}")
        elif tl in aliases.lower():
            reasons.append(f"别名命中: {token}")
        elif tl in terms.lower():
            reasons.append(f"业务词命中: {token}")

    col_role = str(getattr(row, "column_role", "") or "")
    m_type = str(getattr(row, "metric_type", "") or "")
    if col_role == "time":
        reasons.append("时间字段加权")
    if m_type:
        reasons.append("指标字段加权")
    if table_name and any(tok.lower() in table_name.lower() for tok in tokens):
        reasons.append("表名命中")

    return reasons[:6]


def _fallback_keyword_search(ctx: ToolContext, query: str, limit: int) -> list[dict[str, Any]]:
    """Fallback keyword search: table/column name + comment match, no AI tags, no bootstrap synonyms."""
    tables = _catalog_tables(ctx.db, ctx.request.datasource_id)

    results: list[dict[str, Any]] = []
    query_lower = query.lower()
    for table in tables:
        tname = str(table.table_name).lower()
        tcomment = str(table.table_comment or "").lower()
        if query_lower in tname or query_lower in tcomment:
            results.append({
                "type": "table",
                "name": str(table.table_name),
                "table_name": str(table.table_name),
                "score": 0.5 if query_lower in tname else 0.3,
                "reasons": ["名称匹配" if query_lower in tname else "注释匹配"],
                "columns": [str(c.column_name) for c in _ordered_columns(table)][:8],
            })
        for col in _ordered_columns(table):
            cname = str(col.column_name).lower()
            ccomment = str(col.column_comment or "").lower()
            if query_lower in cname or query_lower in ccomment:
                results.append({
                    "type": "column",
                    "name": f"{table.table_name}.{col.column_name}",
                    "table_name": str(table.table_name),
                    "column_name": str(col.column_name),
                    "score": 0.4 if query_lower in cname else 0.2,
                    "reasons": ["字段名匹配" if query_lower in cname else "字段注释匹配"],
                })

    results.sort(key=lambda r: (-float(r["score"]), r["type"], r["name"]))
    return results[:limit]
