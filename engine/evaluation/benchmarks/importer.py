from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from engine.evaluation.benchmarks.base import BenchmarkCase
from engine.models import AgentGoldenTask

logger = logging.getLogger("dbfox.benchmarks.importer")

_DEFAULT_EXPECTED_TOOLS = [
    "schema.build_context",
    "query_plan.build",
    "sql.generate_candidate",
    "sql.validate",
]

_DEFAULT_FORBIDDEN_TOOLS = [
    "@limit",
    "@chart",
    "@export",
    "backup.create",
    "backup.restore",
    "ddl.execute",
]

_DEFAULT_EXPECTED_ARTIFACTS = [
    "agent_plan",
    "query_plan",
    "sql",
    "safety",
]


def import_benchmark_cases(
    db: Session,
    datasource_id: str,
    project_id: str | None,
    source: str,
    cases: list[BenchmarkCase],
) -> list[AgentGoldenTask]:
    tasks: list[AgentGoldenTask] = []
    for case in cases:
        tags = list(set(case.tags + [source]))
        if case.difficulty:
            tags.append(case.difficulty)
        if case.db_id:
            tags.append(case.db_id)

        task = AgentGoldenTask(
            datasource_id=datasource_id,
            project_id=project_id,
            name=f"{source}/{case.source_case_id}",
            description=case.evidence,
            question=case.question,
            workspace_context_json="{}",
            expected_intent=None,
            expected_tools_json=json.dumps(_DEFAULT_EXPECTED_TOOLS),
            forbidden_tools_json=json.dumps(_DEFAULT_FORBIDDEN_TOOLS),
            expected_artifact_types_json=json.dumps(_DEFAULT_EXPECTED_ARTIFACTS),
            expected_final_contains_json="[]",
            expected_approval_state=None,
            expected_sql_required=False,
            tags_json=json.dumps(tags),
            source=source,
            source_case_id=case.source_case_id,
            difficulty=case.difficulty,
        )
        db.add(task)
        tasks.append(task)

    db.flush()
    logger.info("Imported %d %s benchmark cases as AgentGoldenTasks", len(tasks), source)
    return tasks


_ADAPTERS: dict[str, Any] = {}


def _get_adapter(source: str) -> Any:
    if source not in _ADAPTERS:
        if source == "spider":
            from engine.evaluation.benchmarks.spider import SpiderAdapter
            _ADAPTERS[source] = SpiderAdapter()
        elif source == "bird":
            from engine.evaluation.benchmarks.bird import BIRDAdapter
            _ADAPTERS[source] = BIRDAdapter()
        elif source == "custom":
            from engine.evaluation.benchmarks.custom import CustomAdapter
            _ADAPTERS[source] = CustomAdapter()
        else:
            from engine.evaluation.benchmarks.custom import CustomAdapter
            _ADAPTERS[source] = CustomAdapter()
    return _ADAPTERS[source]


def load_and_import_benchmark(
    db: Session,
    datasource_id: str,
    project_id: str | None,
    source: str,
    file_path: str | None = None,
    payload: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[AgentGoldenTask]:
    adapter = _get_adapter(source)
    cases = adapter.load_cases(path=file_path, payload=payload, limit=limit)
    if not cases:
        return []
    return import_benchmark_cases(db, datasource_id, project_id, source, cases)
