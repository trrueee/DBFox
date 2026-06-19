from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from engine.ai_index import tokenize_query

logger = logging.getLogger("dbfox.tools.db.search")


def db_search(db: Session, datasource_id: str, query: str, limit: int = 20) -> dict[str, Any]:
    """FTS5 search + rule-based scoring against SchemaSearchDoc. Falls back to keyword if FTS unavailable."""
    try:
        fts_results = _fts_search(db, datasource_id, query, limit)
        if fts_results:
            return {"engine": "fts5", "limit": limit, "results": fts_results, "total_matches": len(fts_results)}
    except Exception:
        logger.debug("FTS5 search unavailable, falling back to keyword search", exc_info=True)
    fallback = _fallback_keyword_search(db, datasource_id, query, limit)
    return {"engine": "keyword_fallback", "limit": limit, "results": fallback, "total_matches": len(fallback)}


def _fts_search(db: Session, datasource_id: str, query: str, limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text as sa_text

    tokens = tokenize_query(query)
    valid_tokens = []
    for t in tokens:
        if t.upper() in {"AND", "OR", "NOT", "NEAR"}:
            continue
        # Sanitize token to strip FTS5 operators
        clean_token = re.sub(r'[*^\"()-]', '', t)
        if not clean_token:
            continue
        if not re.match(r"^[a-zA-Z0-9_一-龥]+$", clean_token):
            continue
        valid_tokens.append(clean_token)

    if not valid_tokens:
        return []

    exact_parts = [f'"{t}"' for t in valid_tokens if len(t) >= 2]
    token_parts = [t for t in valid_tokens if len(t) >= 2]
    fts_query = " OR ".join(exact_parts + token_parts)

    sql = sa_text("""
        SELECT d.*, fts.rank
        FROM schema_search_fts fts
        JOIN schema_search_docs d ON d.id = fts.rowid
        WHERE fts MATCH :q AND d.datasource_id = :ds_id
        ORDER BY fts.rank
        LIMIT :lim
    """)
    rows = db.execute(sql, {"q": fts_query, "ds_id": datasource_id, "lim": limit * 3}).fetchall()

    results: list[dict[str, Any]] = []
    seen_tables: set[str] = set()
    for row in rows:
        item = _row_to_search_result(row, valid_tokens, query)
        if item is None:
            continue
        if item["type"] == "table" and item["table_name"] in seen_tables:
            continue
        if item["type"] == "table":
            seen_tables.add(item["table_name"])
        results.append(item)

    results.sort(key=lambda r: (-float(r["score"]), r["type"], r["name"]))
    return results[:limit]


def _row_to_search_result(row, tokens: list[str], query: str) -> dict[str, Any] | None:
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
    aliases_raw = str(getattr(row, "aliases", "") or "")
    terms_raw = str(getattr(row, "business_terms", "") or "")
    desc_raw = str(getattr(row, "ai_description", "") or "")
    name_raw = str(getattr(row, "name", "") or "")

    # exact alias match
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

    # business term coverage
    all_terms = terms_raw.lower().split()
    term_hits = sum(1 for t in tokens if any(t.lower() in term for term in all_terms)) if all_terms else 0
    term_cov = term_hits / max(len(tokens), 1)

    # name token match
    name_lower = name_raw.lower()
    name_hits = sum(1 for t in tokens if t.lower() in name_lower)
    name_cov = name_hits / max(len(tokens), 1)

    # search_text token coverage
    search_text = str(getattr(row, "search_text", "") or "").lower()
    st_hits = sum(1 for t in tokens if t.lower() in search_text) if search_text else 0
    st_cov = st_hits / max(len(tokens), 1)

    # ai_description match
    desc_lower = desc_raw.lower()
    desc_hits = sum(1 for t in tokens if t.lower() in desc_lower) if desc_lower else 0
    desc_cov = desc_hits / max(len(tokens), 1)

    return exact_alias * 15.0 + term_cov * 5.0 + name_cov * 3.0 + st_cov * 3.0 + desc_cov * 2.0


def _compute_reasons(row, tokens: list[str]) -> list[str]:
    reasons = []
    name = str(getattr(row, "name", "")).lower()
    for t in tokens:
        if t.lower() in name:
            reasons.append(f"name_match:{t}")
    aliases = str(getattr(row, "aliases", "")).lower()
    for t in tokens:
        if t.lower() in aliases:
            reasons.append(f"alias_match:{t}")
    desc = str(getattr(row, "ai_description", "")).lower()
    for t in tokens:
        if t.lower() in desc:
            reasons.append(f"ai_description_match:{t}")
    return reasons


def _fallback_keyword_search(db: Session, datasource_id: str, query: str, limit: int) -> list[dict[str, Any]]:
    """Fallback: search SchemaTable and SchemaColumn by name when FTS returns nothing."""
    from engine.models import SchemaTable as ST, SchemaColumn as SC
    from sqlalchemy import or_

    tokens = tokenize_query(query)
    if not tokens:
        return []

    # Filter tables using LIKE for any token
    table_filters = []
    for tok in tokens:
        table_filters.append(ST.table_name.ilike(f"%{tok}%"))
        table_filters.append(ST.table_comment.ilike(f"%{tok}%"))

    table_results: list[dict[str, Any]] = []
    if table_filters:
        tables = db.query(ST).filter(ST.data_source_id == datasource_id, or_(*table_filters)).all()
        for t in tables:
            name = str(t.table_name).lower()
            score = sum(3.0 for tok in tokens if tok.lower() in name)
            if t.table_comment and any(tok.lower() in str(t.table_comment).lower() for tok in tokens):
                score += 1.0
            if score > 0:
                table_results.append({"type": "table", "name": str(t.table_name), "table_name": str(t.table_name), "score": score, "reasons": ["keyword_table_name"]})

    # Filter columns using LIKE for any token
    col_filters = []
    for tok in tokens:
        col_filters.append(SC.column_name.ilike(f"%{tok}%"))
        col_filters.append(SC.column_comment.ilike(f"%{tok}%"))

    col_results: list[dict[str, Any]] = []
    if col_filters:
        columns = db.query(SC).join(ST, SC.table_id == ST.id).filter(
            ST.data_source_id == datasource_id,
            or_(*col_filters)
        ).all()
        for c in columns:
            col_name = str(c.column_name).lower()
            score = sum(2.0 for tok in tokens if tok.lower() in col_name)
            if c.column_comment and any(tok.lower() in str(c.column_comment).lower() for tok in tokens):
                score += 0.5
            if score > 0:
                table_name = str(c.table.table_name) if c.table else ""
                col_results.append({"type": "column", "name": f"{table_name}.{c.column_name}", "table_name": table_name, "column_name": str(c.column_name), "score": score, "reasons": ["keyword_column_name"]})

    results = table_results + col_results
    results.sort(key=lambda r: (-r["score"], r["type"], r["name"]))
    return results[:limit]
