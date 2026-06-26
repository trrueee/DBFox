from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.evaluation.retrieval_ab.metrics import extract_expected_schema_from_sql
from engine.evaluation.spider.spider_loader import SpiderExample, load_spider_examples


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    db_id: str
    question: str
    gold_sql: str
    expected_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    difficulty: str | None = None
    tags: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


def make_spider_case(raw: dict[str, Any], *, index: int) -> EvaluationCase:
    db_id = str(raw.get("db_id") or "").strip()
    gold_sql = str(raw.get("query") or raw.get("gold_sql") or "")
    expected = extract_expected_schema_from_sql(gold_sql)
    expected_tables = _tuple_or_default(raw.get("expected_tables"), expected.tables)
    expected_columns = _tuple_or_default(raw.get("expected_columns"), expected.columns)
    return EvaluationCase(
        case_id=str(raw.get("case_id") or f"spider_{db_id}_{index:03d}"),
        db_id=db_id,
        question=str(raw.get("question") or ""),
        gold_sql=gold_sql,
        expected_tables=expected_tables,
        expected_columns=expected_columns,
        difficulty=str(raw.get("difficulty")) if raw.get("difficulty") else None,
        tags=_tuple_or_default(raw.get("tags"), ()),
        raw=raw,
    )


def spider_example_to_case(example: SpiderExample, *, index: int) -> EvaluationCase:
    raw = dict(example.raw or {})
    raw.setdefault("db_id", example.db_id)
    raw.setdefault("question", example.question)
    raw.setdefault("gold_sql", example.gold_sql)
    raw.setdefault("difficulty", example.difficulty)
    return make_spider_case(raw, index=index)


def load_spider_cases(
    cases_path: str | Path,
    *,
    db_ids: Iterable[str] = (),
    limit: int | None = None,
) -> tuple[EvaluationCase, ...]:
    path = Path(cases_path)
    db_filter = {db_id for db_id in db_ids if db_id}
    if path.suffix.lower() == ".json":
        items = json.loads(path.read_text(encoding="utf-8"))
        cases: list[EvaluationCase] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if db_filter and str(item.get("db_id") or "") not in db_filter:
                continue
            cases.append(make_spider_case(item, index=len(cases) + 1))
            if limit is not None and len(cases) >= limit:
                break
        return tuple(cases)

    examples = load_spider_examples(path, limit=limit, db_ids=db_filter or None)
    return tuple(spider_example_to_case(example, index=index) for index, example in enumerate(examples, start=1))


def register_spider_datasource(db_session: Any, example: SpiderExample) -> tuple[str, list[str]]:
    from engine.evaluation.spider.spider_eval import _ensure_spider_sqlite_datasource

    return _ensure_spider_sqlite_datasource(db_session, example)


def _tuple_or_default(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if str(item))
    return default
