from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class BenchmarkCase(BaseModel):
    source: str
    source_case_id: str
    db_id: str | None = None
    question: str
    gold_sql: str | None = None
    evidence: str | None = None
    difficulty: str | None = None
    schema_payload: dict[str, Any] = {}
    tags: list[str] = []


class BenchmarkAdapter(Protocol):
    source: str

    def load_cases(
        self,
        path: str | None = None,
        payload: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[BenchmarkCase]:
        ...
