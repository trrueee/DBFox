from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

from engine.evaluation.retrieval_ab.spider_fixture import EvaluationCase
from engine.llm.factory import get_chat_model


DEFAULT_PLANNER_MODEL = "qwen-plus"
DEFAULT_PLANNER_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def plan_search_expressions(
    case: EvaluationCase,
    *,
    model: str | None = None,
    max_expressions: int = 4,
) -> tuple[str, ...]:
    """Use an LLM to derive schema search expressions from a benchmark question.

    The planner only sees the natural-language question and db_id. It must not
    receive the gold SQL, because this mode is meant to emulate the agent's
    search planning rather than leak labels into retrieval.
    """
    if max_expressions <= 0:
        return ()

    chat_model = get_chat_model(
        model_name=_planner_model(model),
        api_key=_planner_api_key(),
        api_base=_planner_api_base(),
        temperature=0.0,
        max_tokens=500,
        timeout=60.0,
    )
    response = chat_model.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You plan schema search expressions for a Text-to-SQL agent. "
                    "Return only compact JSON with key search_expressions. "
                    "Generate 2 to 4 short expressions that a database schema search tool should run. "
                    "Cover the original wording, entity/domain nouns, action/object nouns, metric words, "
                    "English schema terms, abbreviations, and likely table or column names. "
                    "Do not write SQL. Do not explain."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "db_id": case.db_id,
                        "question": case.question,
                        "max_expressions": max_expressions,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )
    expressions = _parse_search_expression_response(_message_text(response))
    return normalize_search_expressions(expressions, fallback=case.question, max_expressions=max_expressions)


def normalize_search_expressions(
    values: Iterable[Any],
    *,
    fallback: str,
    max_expressions: int = 4,
) -> tuple[str, ...]:
    expressions: list[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip().strip("-•* ")
        if not text:
            continue
        if text.lower() in {item.lower() for item in expressions}:
            continue
        expressions.append(text)
        if len(expressions) >= max_expressions:
            break

    if not expressions and fallback.strip():
        expressions.append(fallback.strip())
    return tuple(expressions[:max_expressions])


def _parse_search_expression_response(text: str) -> tuple[str, ...]:
    stripped = _strip_code_fence(text)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        raw = parsed.get("search_expressions") or parsed.get("queries") or parsed.get("expressions")
        if isinstance(raw, list):
            return tuple(str(item) for item in raw)
    if isinstance(parsed, list):
        return tuple(str(item) for item in parsed)

    lines = []
    for line in stripped.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return tuple(lines)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return str(content or "").strip()


def _planner_model(model: str | None) -> str:
    return (
        model
        or os.getenv("DBFOX_RETRIEVAL_PLANNER_MODEL")
        or os.getenv("QWEN_MODEL_NAME")
        or os.getenv("OPENAI_MODEL_NAME")
        or DEFAULT_PLANNER_MODEL
    ).strip()


def _planner_api_key() -> str:
    return (
        os.getenv("DBFOX_RETRIEVAL_PLANNER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("QWEN_API_KEY")
        or os.getenv("DBFOX_LLM_API_KEY")
        or os.getenv("DBFOX_EMBEDDING_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or ""
    ).strip()


def _planner_api_base() -> str:
    return (
        os.getenv("DBFOX_RETRIEVAL_PLANNER_BASE_URL")
        or os.getenv("QWEN_API_BASE")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("DBFOX_EMBEDDING_BASE_URL")
        or DEFAULT_PLANNER_BASE_URL
    ).strip()
