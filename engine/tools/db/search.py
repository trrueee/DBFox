from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from engine.ai_index import tokenize_query
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception

logger = logging.getLogger("dbfox.tools.db.search")


SEARCHED_FIELDS = [
    "name",
    "ai_description",
    "semantic_tags",
    "business_terms",
    "aliases",
    "table_role",
    "grain",
    "subject_area",
    "column_role",
    "metric_type",
    "column_summary",
    "relation_summary",
    "search_text",
    "table_name",
    "table_comment",
    "column_name",
    "column_comment",
]

REASON_FIELD_MAP = {
    "name_match": "name",
    "alias_match": "aliases",
    "semantic_tag_match": "semantic_tags",
    "business_term_match": "business_terms",
    "ai_description_match": "ai_description",
    "search_text_match": "search_text",
    "keyword_table_name": "table_name",
    "keyword_column_name": "column_name",
}


def db_search(db: Session, datasource_id: str, query: str, limit: int = 20) -> dict[str, Any]:
    """FTS5 search + rule-based scoring against SchemaSearchDoc. Falls back to keyword if FTS unavailable."""
    tokens = _tokenize_search_query(query)
    if not tokens:
        return _search_response("empty", query, tokens, limit, [])

    try:
        fts_results = _fts_search(db, datasource_id, tokens, limit)
        if fts_results:
            return _search_response("fts5", query, tokens, limit, fts_results)
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.DB_SEARCH_FTS_FALLBACK,
            exc=exc,
            level="warning",
        )
    fallback = _fallback_keyword_search(db, datasource_id, tokens, limit)
    return _search_response("keyword_fallback", query, tokens, limit, fallback)


def _tokenize_search_query(query: str) -> list[str]:
    valid_tokens: list[str] = []
    for token in tokenize_query(query):
        if token.upper() in {"AND", "OR", "NOT", "NEAR"}:
            continue
        clean_token = re.sub(r'[*^\"()-]', '', token)
        if not clean_token:
            continue
        if not re.match(r"^[a-zA-Z0-9_一-龥]+$", clean_token):
            continue
        if clean_token not in valid_tokens:
            valid_tokens.append(clean_token)
    return valid_tokens


def _search_response(engine: str, query: str, tokens: list[str], limit: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    matched_fields = sorted({
        field
        for result in results
        for field in result.get("matched_fields", [])
    })
    return {
        "engine": engine,
        "original_query": query,
        "tokens": tokens,
        "searched_fields": SEARCHED_FIELDS,
        "matched_fields": matched_fields,
        "limit": limit,
        "results": results,
        "total_matches": len(results),
    }


def _fts_search(db: Session, datasource_id: str, tokens: list[str], limit: int) -> list[dict[str, Any]]:
    exact_parts = [f'"{t}"' for t in tokens if len(t) >= 2]
    token_parts = [t for t in tokens if len(t) >= 2]
    # For CJK text, FTS5's unicode61 tokenizer treats each character as a
    # token, but jieba segments into words. Add individual CJK chars so the
    # MATCH query actually finds FTS5-indexed content.
    cjk_chars: list[str] = []
    for t in tokens:
        cjk_chars.extend(re.findall(r"[一-鿿]", t))
    token_parts.extend(cjk_chars)
    fts_query = " OR ".join(exact_parts + token_parts)

    # Use raw DBAPI connection for FTS5 MATCH with CJK characters to avoid
    # SQLAlchemy sa_text parameter encoding issues.
    try:
        raw_conn = db.connection().connection
        import sqlite3 as _sqlite3
        if not isinstance(raw_conn, _sqlite3.Connection):
            raw_conn = getattr(raw_conn, "driver_connection", None) or getattr(raw_conn, "connection", None)
        if raw_conn is not None:
            safe_q = fts_query.replace("'", "''")
            raw_sql = (
                f"SELECT d.*, fts.rank FROM schema_search_fts fts "
                f"JOIN schema_search_docs d ON d.id = fts.rowid "
                f"WHERE schema_search_fts MATCH '{safe_q}' "
                f"AND d.datasource_id = ? "
                f"ORDER BY fts.rank LIMIT ?"
            )
            cursor = raw_conn.execute(raw_sql, (datasource_id, limit * 3))
            rows_raw = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, r)) for r in rows_raw]
            # Wrap as objects with attribute access for _row_to_search_result
            _Row = type("_Row", (), {})
            wrapped_rows = []
            for r in rows:
                obj = _Row()
                for k, v in r.items():
                    setattr(obj, k, v)
                wrapped_rows.append(obj)
            rows = wrapped_rows
        else:
            rows = []
    except Exception:
        rows = []

    results: list[dict[str, Any]] = []
    seen_tables: set[str] = set()
    for row in rows:
        item = _row_to_search_result(row, tokens)
        if item is None:
            continue
        if item["type"] == "table" and item["table_name"] in seen_tables:
            continue
        if item["type"] == "table":
            seen_tables.add(item["table_name"])
        results.append(item)

    results.sort(key=lambda r: (-float(r["score"]), r["type"], r["name"]))
    return results[:limit]


def _row_to_search_result(row, tokens: list[str]) -> dict[str, Any] | None:
    entity_type = str(getattr(row, "entity_type", "table") or "table")
    score = _compute_total_score(row, tokens)
    if score <= 0:
        return None
    reasons = _compute_reasons(row, tokens)

    item: dict[str, Any] = {
        "type": entity_type,
        "name": str(getattr(row, "name", "")),
        "table_name": str(getattr(row, "table_name", "")),
        "score": round(score, 3),
        "reasons": reasons,
        "matched_fields": _matched_fields_from_reasons(reasons),
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


def _matched_fields_from_reasons(reasons: list[str]) -> list[str]:
    fields: list[str] = []
    for reason in reasons:
        prefix = reason.split(":", 1)[0]
        field = REASON_FIELD_MAP.get(prefix)
        if field and field not in fields:
            fields.append(field)
    return sorted(fields)


def _compute_total_score(row, tokens: list[str]) -> float:
    aliases_raw = str(getattr(row, "aliases", "") or "")
    terms_raw = str(getattr(row, "business_terms", "") or "")
    semantic_tags_raw = str(getattr(row, "semantic_tags", "") or "")
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

    # business term / semantic tag coverage
    all_terms = f"{terms_raw} {semantic_tags_raw}".lower().split()
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
    semantic_tags = str(getattr(row, "semantic_tags", "")).lower()
    for t in tokens:
        if t.lower() in semantic_tags:
            reasons.append(f"semantic_tag_match:{t}")
    business_terms = str(getattr(row, "business_terms", "")).lower()
    for t in tokens:
        if t.lower() in business_terms:
            reasons.append(f"business_term_match:{t}")
    desc = str(getattr(row, "ai_description", "")).lower()
    for t in tokens:
        if t.lower() in desc:
            reasons.append(f"ai_description_match:{t}")
    search_text = str(getattr(row, "search_text", "")).lower()
    for t in tokens:
        if t.lower() in search_text:
            reasons.append(f"search_text_match:{t}")
    return reasons


def _fallback_keyword_search(db: Session, datasource_id: str, tokens: list[str], limit: int) -> list[dict[str, Any]]:
    """Fallback: search schema docs first, then raw table/column names."""
    from engine.models import SchemaSearchDoc as SD, SchemaTable as ST, SchemaColumn as SC
    from sqlalchemy import or_

    doc_filters = []
    for tok in tokens:
        like = f"%{tok}%"
        doc_filters.extend(
            [
                SD.name.ilike(like),
                SD.ai_description.ilike(like),
                SD.semantic_tags.ilike(like),
                SD.business_terms.ilike(like),
                SD.aliases.ilike(like),
                SD.table_role.ilike(like),
                SD.grain.ilike(like),
                SD.subject_area.ilike(like),
                SD.column_role.ilike(like),
                SD.metric_type.ilike(like),
                SD.column_summary.ilike(like),
                SD.relation_summary.ilike(like),
                SD.search_text.ilike(like),
            ]
        )

    doc_results: list[dict[str, Any]] = []
    seen_docs: set[tuple[str, str, str]] = set()
    if doc_filters:
        docs = (
            db.query(SD)
            .filter(SD.datasource_id == datasource_id, or_(*doc_filters))
            .all()
        )
        for doc in docs:
            item = _row_to_search_result(doc, tokens)
            if item is None:
                continue
            key = (
                str(item.get("type") or ""),
                str(item.get("table_name") or ""),
                str(item.get("column_name") or ""),
            )
            if key in seen_docs:
                continue
            seen_docs.add(key)
            doc_results.append(item)

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
                table_results.append({
                    "type": "table",
                    "name": str(t.table_name),
                    "table_name": str(t.table_name),
                    "score": score,
                    "reasons": ["keyword_table_name"],
                    "matched_fields": ["table_name"],
                })

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
                col_results.append({
                    "type": "column",
                    "name": f"{table_name}.{c.column_name}",
                    "table_name": table_name,
                    "column_name": str(c.column_name),
                    "score": score,
                    "reasons": ["keyword_column_name"],
                    "matched_fields": ["column_name"],
                })

    results = doc_results + table_results + col_results
    results.sort(key=lambda r: (-r["score"], r["type"], r["name"]))
    return results[:limit]
