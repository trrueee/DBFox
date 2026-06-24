"""AI schema enrichment — LLM batch tagging, jieba tokenizer, search_text builder."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger("dbfox.ai_index")

# ── Tokenization ────────────────────────────────────────────────────────────────

# Lazy-load jieba to avoid import cost when ai_index is unused
_jieba_loaded = False


def _ensure_jieba():
    global _jieba_loaded
    if not _jieba_loaded:
        import jieba
        jieba.setLogLevel(logging.WARNING)
        _jieba_loaded = True


def _lcut(text: str) -> list[str]:
    """jieba lcut polyfill — works with both jieba and jieba3k."""
    import jieba
    if hasattr(jieba, "lcut"):
        return list(jieba.lcut(text))
    return list(jieba.cut(text))


def tokenize_query(query: str) -> list[str]:
    """Tokenize a user query into Chinese + English tokens."""
    _ensure_jieba()
    import jieba

    tokens: list[str] = []
    # English / numeric tokens
    eng_tokens = re.findall(r"[A-Za-z0-9_]+", query)
    tokens.extend(t for t in eng_tokens if len(t) >= 2)

    # Chinese via jieba
    chinese_part = re.sub(r"[A-Za-z0-9_]+", " ", query)
    tokens.extend(t.strip() for t in _lcut(chinese_part) if t.strip())

    return list(dict.fromkeys(tokens))  # dedup, preserve order


def segment_for_fts(text: str) -> str:
    """Segment Chinese text with jieba for FTS5 insertion (spaces between words)."""
    _ensure_jieba()
    import jieba
    if not text:
        return ""
    # Split on existing whitespace, segment each chunk
    parts = text.split()
    result: list[str] = []
    for part in parts:
        if re.search(r"[一-鿿]", part):
            result.extend(_lcut(part))
        else:
            result.append(part)
    return " ".join(result)


# ── Search text builders ─────────────────────────────────────────────────────────

def build_table_search_text(
    table_name: str,
    ai_description: str | None,
    semantic_tags: list[str] | None,
    business_terms: list[str] | None,
    aliases: list[str] | None,
    table_role: str | None,
    grain: str | None,
    column_names: list[str],
    column_ai_descriptions: dict[str, str | None],
    relation_text: str | None,
) -> str:
    """Construct the FTS5 search_text for one table."""
    parts: list[str] = []

    parts.append(f"表名: {table_name}")
    if ai_description:
        parts.append(f"业务描述: {ai_description}")
    if semantic_tags:
        parts.append(f"语义标签: {' '.join(semantic_tags)}")
    if business_terms:
        parts.append(f"业务术语: {' '.join(business_terms)}")
    if aliases:
        parts.append(f"别名: {' '.join(aliases)}")
    if table_role:
        parts.append(f"表角色: {table_role}")
    if grain:
        parts.append(f"表粒度: {grain}")

    # Columns
    col_parts: list[str] = []
    for cname in column_names:
        cdesc = column_ai_descriptions.get(cname)
        col_parts.append(f"{cname}{' ' + cdesc if cdesc else ''}")
    parts.append(f"字段: {' '.join(col_parts)}")

    if relation_text:
        parts.append(f"关系: {relation_text}")

    raw = " ".join(parts)
    return segment_for_fts(raw)


def build_column_search_text(
    column_name: str,
    table_name: str,
    ai_description: str | None,
    semantic_tags: list[str] | None,
    business_terms: list[str] | None,
    column_role: str | None,
    metric_type: str | None,
) -> str:
    """Construct the FTS5 search_text for one column."""
    parts: list[str] = []

    parts.append(f"字段名: {column_name}")
    parts.append(f"所属表: {table_name}")
    if ai_description:
        parts.append(f"字段描述: {ai_description}")
    if semantic_tags:
        parts.append(f"语义标签: {' '.join(semantic_tags)}")
    if business_terms:
        parts.append(f"业务术语: {' '.join(business_terms)}")
    if column_role:
        parts.append(f"字段角色: {column_role}")
    if metric_type:
        parts.append(f"指标类型: {metric_type}")

    raw = " ".join(parts)
    return segment_for_fts(raw)


# ── Schema hash (for incremental refresh) ────────────────────────────────────────

def compute_schema_hash(table) -> str:
    """Compute a stable structural hash for a SchemaTable.
    Changes when columns, types, or comments change.
    """
    import hashlib

    digest = hashlib.sha256()
    digest.update(str(table.table_name or "").encode())
    for col in sorted(getattr(table, "columns", []) or [], key=lambda c: str(c.column_name)):
        digest.update(str(col.column_name or "").encode())
        digest.update(str(col.column_type or col.data_type or "").encode())
        digest.update(str(col.column_comment or "").encode())
    return digest.hexdigest()


# ── LLM enrichment ───────────────────────────────────────────────────────────────

def enrich_tables_batch(
    tables_context: list[dict[str, Any]],
    *,
    provider: str = "aliyun",
    model: str = "qwen-plus",
    api_key: str | None = None,
    api_base: str | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Call LLM to generate AI metadata for a batch of tables.

    Returns:
        {"tables": [{name, ai_description, semantic_tags, business_terms, aliases,
                      table_role, grain, subject_area, ai_confidence,
                      columns: [{name, ai_description, semantic_tags, business_terms,
                                  aliases, column_role, metric_type, ai_confidence}]}]}
    """
    if not tables_context:
        return {"tables": []}

    prompt = _build_enrich_prompt(tables_context)
    last_error = None

    for attempt in range(max_retries):
        try:
            result = _call_llm(
                prompt,
                provider=provider,
                model=model,
                api_key=api_key,
                api_base=api_base,
            )
            parsed = json.loads(result) if isinstance(result, str) else result
            _validate_enrich_result(parsed, [t["name"] for t in tables_context])
            return parsed
        except Exception as exc:
            last_error = exc
            logger.warning("LLM enrich attempt %d/%d failed: %s", attempt + 1, max_retries, exc)
            time.sleep(0.5 * (attempt + 1))

    raise RuntimeError(f"LLM enrichment failed after {max_retries} attempts: {last_error}")


def _build_enrich_prompt(tables: list[dict[str, Any]]) -> str:
    """Build the structured prompt for schema enrichment."""
    import json as _json
    context = _json.dumps(tables, ensure_ascii=False, indent=2, default=str)
    return f"""You are a database schema analyst. For each table below, generate business-meaningful metadata in Chinese.

Output JSON only — no commentary. For each table:
- ai_description: 1-2 sentences describing the business meaning of this table
- semantic_tags: 3-6 Chinese tags capturing domain, behavior, and usage
- business_terms: 3-8 searchable business terms users might query for (Chinese + English abbreviations)
- aliases: common abbreviations and alternative names (English)
- table_role: one of [fact, dim, bridge, log, agg]
- grain: what one row represents (e.g. "按用户、日期聚合")
- subject_area: one of [user, order, product, payment, content, traffic, system, other]
- ai_confidence: 0-1 confidence score

For each column:
- ai_description: 1 sentence about the business meaning
- semantic_tags: 1-3 tags
- business_terms: 1-3 searchable terms
- aliases: abbreviations (e.g. feat_id for feature_id)
- column_role: one of [dimension, measure, time, id, status]
- metric_type: one of [count, amount, rate, duration] if column_role=measure, else null
- ai_confidence: 0-1

Table context:
{context}

Return JSON:
{{"tables": [{{"name": "...", "ai_description": "...", ...}}]}}"""


def _call_llm(
    prompt: str,
    *,
    provider: str,
    model: str,
    api_key: str | None = None,
    api_base: str | None = None,
) -> str:
    """Call the configured LLM provider. Extend this for additional providers."""
    if provider == "aliyun":
        return _call_aliyun_llm(prompt, model=model, api_key=api_key, api_base=api_base)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _call_aliyun_llm(
    prompt: str,
    *,
    model: str,
    api_key: str | None = None,
    api_base: str | None = None,
) -> str:
    """Call Aliyun (Qwen) via OpenAI-compatible API.

    API key resolution mirrors engine.llm.factory.get_chat_model so that
    the same .env vars work for both Agent conversations and AI enrichment.
    """
    import os
    import httpx
    from openai import OpenAI

    # ── API key ──
    resolved_api_key = str(api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not resolved_api_key:
        raise RuntimeError("请先在设置中配置 LLM API Key。")

    # ── API base ──
    resolved_api_base = (
        api_base
        or os.getenv("OPENAI_API_BASE")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).strip()

    # ── Timing & token budget ──
    prompt_chars = len(prompt)
    # Rough estimate: 1 token ≈ 1.5 chars for Chinese, 4 chars for English
    estimated_input_tokens = int(prompt_chars / 2.5)
    output_tokens = min(8192, max(2048, estimated_input_tokens * 2))

    # ── Call with timeout ──
    timeout = httpx.Timeout(30.0, read=120.0)
    client = OpenAI(
        api_key=resolved_api_key,
        base_url=resolved_api_base,
        timeout=timeout,
        max_retries=0,  # we handle retries in enrich_tables_batch
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=output_tokens,
    )

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("AI enrichment returned empty response")

    # Strip markdown code fences (any flavour: ```json, ```, etc.)
    import re as _re
    content = _re.sub(r"^```[a-z]*\s*\n?", "", content.strip(), flags=_re.IGNORECASE)
    content = _re.sub(r"\n?```\s*$", "", content)

    return content


def _validate_enrich_result(result: dict[str, Any], expected_table_names: list[str]) -> None:
    """Validate LLM output structure. Raises ValueError on mismatch."""
    tables = result.get("tables")
    if not isinstance(tables, list) or len(tables) == 0:
        raise ValueError("AI result missing 'tables' array")
    returned_names = {t.get("name") for t in tables if isinstance(t, dict)}
    missing = set(expected_table_names) - returned_names
    if missing:
        raise ValueError(f"AI result missing tables: {missing}")
