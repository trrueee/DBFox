from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from engine.evaluation.benchmarks.base import BenchmarkCase

logger = logging.getLogger("dbfox.benchmarks.spider")


class SpiderAdapter:
    source = "spider"

    def load_cases(
        self,
        path: str | None = None,
        payload: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[BenchmarkCase]:
        cases: list[BenchmarkCase] = []

        if payload is not None:
            items_raw = payload.get("cases")
            items: list[Any] = list(items_raw) if isinstance(items_raw, list) else [payload]
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                cases.append(BenchmarkCase(
                    source="spider",
                    source_case_id=item.get("id") or f"spider_payload_{i}",
                    db_id=item.get("db_id"),
                    question=str(item.get("question") or item.get("query") or ""),
                    gold_sql=item.get("query") or item.get("gold_sql"),
                    difficulty=item.get("difficulty"),
                    tags=["spider"] + (list(item.get("tags", [])) if isinstance(item.get("tags"), list) else []),
                ))

        if path is not None:
            p = Path(path)
            if not p.exists():
                logger.warning("Spider benchmark path does not exist: %s", path)
                return cases
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                items = raw if isinstance(raw, list) else [raw]
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    if limit is not None and len(cases) >= limit:
                        break
                    cases.append(BenchmarkCase(
                        source="spider",
                        source_case_id=item.get("id") or f"spider_file_{i}",
                        db_id=item.get("db_id"),
                        question=str(item.get("question") or item.get("query") or ""),
                        gold_sql=item.get("query") or item.get("gold_sql"),
                        difficulty=item.get("difficulty"),
                        tags=["spider"],
                    ))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to parse Spider benchmark file: %s", exc)

        if limit is not None:
            cases = cases[:limit]

        return cases
