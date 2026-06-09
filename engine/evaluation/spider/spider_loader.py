from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpiderExample:
    db_id: str
    question: str
    gold_sql: str
    db_path: Path
    difficulty: str | None = None
    raw: dict[str, Any] | None = field(default=None, compare=False)


def load_spider_examples(
    spider_root: str | Path,
    *,
    split: str = "dev",
    limit: int | None = None,
    db_ids: set[str] | None = None,
) -> list[SpiderExample]:
    root = Path(spider_root)
    json_path = root / f"{split}.json"

    if not json_path.exists():
        raise FileNotFoundError(f"Spider split file not found: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    examples: list[SpiderExample] = []

    for item in data:
        if not isinstance(item, dict):
            continue
        db_id = str(item.get("db_id") or "")
        if db_ids and db_id not in db_ids:
            continue

        db_path = root / "database" / db_id / f"{db_id}.sqlite"
        examples.append(
            SpiderExample(
                db_id=db_id,
                question=str(item.get("question") or ""),
                gold_sql=str(item.get("query") or item.get("gold_sql") or ""),
                db_path=db_path,
                difficulty=item.get("difficulty"),
                raw=item,
            )
        )

        if limit is not None and len(examples) >= limit:
            break

    return examples
