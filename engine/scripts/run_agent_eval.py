#!/usr/bin/env python3
"""Agent Eval CLI — run golden-task evaluations from the command line.

Usage:
    python -m engine.scripts.run_agent_eval --datasource-id demo --fixtures
    python -m engine.scripts.run_agent_eval --datasource-id demo --source internal --json
    python -m engine.scripts.run_agent_eval --datasource-id demo --file-path ./cases.json --source custom
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

# Ensure the engine package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.db import SessionLocal, engine, Base
from engine.models import AgentGoldenTask
from engine.evaluation.agent_eval import AgentEvalRunner
from engine.evaluation.benchmarks.importer import load_and_import_benchmark
from engine.schemas.agent_eval import AgentEvalRunRequest
from engine.errors import DBFoxError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("run_agent_eval")

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "..", "evaluation", "fixtures", "agent_golden_tasks.json")


def load_fixtures(db: Any, datasource_id: str, project_id: str | None = None) -> list[AgentGoldenTask]:
    if not os.path.exists(FIXTURES_PATH):
        logger.warning("Fixtures file not found: %s", FIXTURES_PATH)
        return []

    with open(FIXTURES_PATH, encoding="utf-8") as fh:
        items = json.load(fh)

    tasks: list[AgentGoldenTask] = []
    for item in items:
        existing = db.query(AgentGoldenTask).filter(AgentGoldenTask.id == item.get("id")).first()
        if existing:
            logger.info("Fixture already exists: %s", item.get("id"))
            tasks.append(existing)
            continue

        task = AgentGoldenTask(
            id=item.get("id"),
            datasource_id=datasource_id,
            project_id=project_id,
            name=item.get("name", ""),
            description=item.get("description"),
            question=item.get("question", ""),
            workspace_context_json=item.get("workspace_context_json", "{}"),
            expected_intent=item.get("expected_intent"),
            expected_tools_json=item.get("expected_tools_json", "[]"),
            forbidden_tools_json=item.get("forbidden_tools_json", "[]"),
            expected_artifact_types_json=item.get("expected_artifact_types_json", "[]"),
            expected_final_contains_json=item.get("expected_final_contains_json", "[]"),
            expected_approval_state=item.get("expected_approval_state"),
            expected_sql_required=item.get("expected_sql_required", False),
            tags_json=item.get("tags_json", "[]"),
            source=item.get("source", "internal"),
            source_case_id=item.get("source_case_id"),
            difficulty=item.get("difficulty"),
        )
        db.add(task)
        tasks.append(task)

    db.commit()
    logger.info("Loaded %d fixtures", len(tasks))
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Eval Runner")
    parser.add_argument("--datasource-id", required=True, help="Target datasource ID")
    parser.add_argument("--project-id", default=None, help="Optional project ID")
    parser.add_argument("--fixtures", action="store_true", help="Load internal fixtures before running")
    parser.add_argument("--source", default="internal", help="Filter by source (internal/spider/bird/custom)")
    parser.add_argument("--file-path", default=None, help="Path to benchmark file for import")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to import")
    parser.add_argument("--execute", type=str, default="false", help="Allow SQL execution (true/false)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON summary")

    args = parser.parse_args()
    datasource_id: str = args.datasource_id
    project_id: str | None = args.project_id
    execute_flag: bool = args.execute.lower() in ("true", "1", "yes")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        task_ids: list[str] | None = None

        if args.fixtures:
            tasks = load_fixtures(db, datasource_id, project_id)
            task_ids = [str(t.id) for t in tasks]

        if args.file_path and args.source != "internal":
            imported = load_and_import_benchmark(
                db,
                datasource_id=datasource_id,
                project_id=project_id,
                source=args.source,
                file_path=args.file_path,
                limit=args.limit,
            )
            db.commit()
            logger.info("Imported %d benchmark cases", len(imported))
            if task_ids is None:
                task_ids = []
            task_ids.extend(str(t.id) for t in imported)

        req = AgentEvalRunRequest(
            datasource_id=datasource_id,
            project_id=project_id,
            task_ids=task_ids,
            source=args.source if not args.fixtures else None,
            execute=execute_flag,
        )

        runner = AgentEvalRunner(db)
        result = runner.run(req)

        if args.json_output:
            print(json.dumps({
                "id": result.id,
                "status": result.status,
                "total_cases": result.total_cases,
                "passed_cases": result.passed_cases,
                "failed_cases": result.failed_cases,
                "pass_rate": result.pass_rate,
                "avg_latency_ms": result.avg_latency_ms,
                "failures": [
                    {
                        "task_id": cr.task_id,
                        "status": cr.status,
                        "score": cr.score,
                        "failure_reasons": cr.failure_reasons_json,
                    }
                    for cr in result.case_results
                    if cr.status != "passed"
                ],
            }, ensure_ascii=False, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"Agent Eval Results")
            print(f"{'='*60}")
            print(f"Eval Run ID : {result.id}")
            print(f"Status      : {result.status}")
            print(f"Total Cases : {result.total_cases}")
            print(f"Passed      : {result.passed_cases}")
            print(f"Failed      : {result.failed_cases}")
            print(f"Pass Rate   : {result.pass_rate}")
            print(f"Avg Latency : {result.avg_latency_ms}ms")
            print(f"{'='*60}")

            failures = [cr for cr in result.case_results if cr.status != "passed"]
            if failures:
                print(f"\nFailures ({len(failures)}):")
                for cr in failures:
                    print(f"  - task={cr.task_id} score={cr.score} status={cr.status}")
                    if cr.failure_reasons_json:
                        try:
                            reasons = json.loads(cr.failure_reasons_json)
                            for r in reasons:
                                print(f"      {r}")
                        except json.JSONDecodeError:
                            print(f"      {cr.failure_reasons_json}")
            print()

    except DBFoxError as exc:
        logger.error("Eval error: %s (code=%s)", exc, exc.code)
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error during eval")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
