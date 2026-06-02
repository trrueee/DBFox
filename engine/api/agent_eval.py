from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DataBoxError
from engine.evaluation.agent_eval import AgentEvalRunner
from engine.evaluation.benchmarks.importer import import_benchmark_cases, load_and_import_benchmark, _get_adapter
from engine.models import AgentEvalCaseResult, AgentEvalRun, AgentGoldenTask
from engine.schemas.agent_eval import (
    AgentBenchmarkImportRequest,
    AgentBenchmarkImportResponse,
    AgentEvalRunRequest,
    AgentEvalRunResponse,
    AgentEvalCaseResultResponse,
    AgentGoldenTaskCreateRequest,
    AgentGoldenTaskResponse,
    AgentGoldenTaskUpdateRequest,
)

logger = logging.getLogger("databox.api.agent_eval")
router = APIRouter()


def _task_to_response(task: AgentGoldenTask) -> AgentGoldenTaskResponse:
    return AgentGoldenTaskResponse(
        id=str(task.id),
        datasource_id=str(task.datasource_id),
        project_id=str(task.project_id) if task.project_id else None,
        name=str(task.name),
        description=str(task.description) if task.description else None,
        question=str(task.question),
        workspace_context_json=str(task.workspace_context_json),
        expected_intent=str(task.expected_intent) if task.expected_intent else None,
        expected_tools_json=str(task.expected_tools_json),
        forbidden_tools_json=str(task.forbidden_tools_json),
        expected_artifact_types_json=str(task.expected_artifact_types_json),
        expected_final_contains_json=str(task.expected_final_contains_json),
        expected_approval_state=str(task.expected_approval_state) if task.expected_approval_state else None,
        expected_sql_required=bool(task.expected_sql_required),
        tags_json=str(task.tags_json),
        source=str(task.source),
        source_case_id=str(task.source_case_id) if task.source_case_id else None,
        difficulty=str(task.difficulty) if task.difficulty else None,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
    )


def _case_to_response(case: AgentEvalCaseResult) -> AgentEvalCaseResultResponse:
    return AgentEvalCaseResultResponse(
        id=str(case.id),
        eval_run_id=str(case.eval_run_id),
        task_id=str(case.task_id),
        run_id=str(case.run_id) if case.run_id else None,
        status=str(case.status),
        score=float(case.score),
        latency_ms=int(case.latency_ms) if case.latency_ms else None,
        actual_intent=str(case.actual_intent) if case.actual_intent else None,
        actual_tools_json=str(case.actual_tools_json),
        actual_artifact_types_json=str(case.actual_artifact_types_json),
        actual_approval_state=str(case.actual_approval_state) if case.actual_approval_state else None,
        actual_sql_json=str(case.actual_sql_json),
        failure_reasons_json=str(case.failure_reasons_json),
        response_json=str(case.response_json),
        created_at=case.created_at.isoformat() if case.created_at else None,
    )


@router.get("/agent-eval/tasks", response_model=list[AgentGoldenTaskResponse])
def api_list_tasks(
    datasource_id: str = Query(...),
    project_id: str | None = Query(None),
    tag: str | None = Query(None),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[Any]:
    query = db.query(AgentGoldenTask).filter(AgentGoldenTask.datasource_id == datasource_id)
    if project_id:
        query = query.filter(AgentGoldenTask.project_id == project_id)
    if tag:
        query = query.filter(AgentGoldenTask.tags_json.contains(tag))
    if source:
        query = query.filter(AgentGoldenTask.source == source)
    tasks = query.order_by(AgentGoldenTask.created_at.desc()).all()
    return [_task_to_response(t) for t in tasks]


@router.post("/agent-eval/tasks", response_model=AgentGoldenTaskResponse)
def api_create_task(req: AgentGoldenTaskCreateRequest, db: Session = Depends(get_db)) -> Any:
    task = AgentGoldenTask(
        datasource_id=req.datasource_id,
        project_id=req.project_id,
        name=req.name,
        description=req.description,
        question=req.question,
        workspace_context_json=req.workspace_context_json,
        expected_intent=req.expected_intent,
        expected_tools_json=req.expected_tools_json,
        forbidden_tools_json=req.forbidden_tools_json,
        expected_artifact_types_json=req.expected_artifact_types_json,
        expected_final_contains_json=req.expected_final_contains_json,
        expected_approval_state=req.expected_approval_state,
        expected_sql_required=req.expected_sql_required,
        tags_json=req.tags_json,
        source=req.source,
        source_case_id=req.source_case_id,
        difficulty=req.difficulty,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_response(task)


@router.put("/agent-eval/tasks/{task_id}", response_model=AgentGoldenTaskResponse)
def api_update_task(task_id: str, req: AgentGoldenTaskUpdateRequest, db: Session = Depends(get_db)) -> Any:
    task = db.query(AgentGoldenTask).filter(AgentGoldenTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": f"Task {task_id} not found."})
    if req.name is not None:
        task.name = req.name  # type: ignore[assignment]
    if req.description is not None:
        task.description = req.description  # type: ignore[assignment]
    if req.question is not None:
        task.question = req.question  # type: ignore[assignment]
    if req.workspace_context_json is not None:
        task.workspace_context_json = req.workspace_context_json  # type: ignore[assignment]
    if req.expected_intent is not None:
        task.expected_intent = req.expected_intent  # type: ignore[assignment]
    if req.expected_tools_json is not None:
        task.expected_tools_json = req.expected_tools_json  # type: ignore[assignment]
    if req.forbidden_tools_json is not None:
        task.forbidden_tools_json = req.forbidden_tools_json  # type: ignore[assignment]
    if req.expected_artifact_types_json is not None:
        task.expected_artifact_types_json = req.expected_artifact_types_json  # type: ignore[assignment]
    if req.expected_final_contains_json is not None:
        task.expected_final_contains_json = req.expected_final_contains_json  # type: ignore[assignment]
    if req.expected_approval_state is not None:
        task.expected_approval_state = req.expected_approval_state  # type: ignore[assignment]
    if req.expected_sql_required is not None:
        task.expected_sql_required = req.expected_sql_required  # type: ignore[assignment]
    if req.tags_json is not None:
        task.tags_json = req.tags_json  # type: ignore[assignment]
    if req.difficulty is not None:
        task.difficulty = req.difficulty  # type: ignore[assignment]
    db.commit()
    db.refresh(task)
    return _task_to_response(task)


@router.delete("/agent-eval/tasks/{task_id}")
def api_delete_task(task_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    task = db.query(AgentGoldenTask).filter(AgentGoldenTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": f"Task {task_id} not found."})
    db.delete(task)
    db.commit()
    return {"success": True}


@router.post("/agent-eval/import-benchmark", response_model=AgentBenchmarkImportResponse)
def api_import_benchmark(req: AgentBenchmarkImportRequest, db: Session = Depends(get_db)) -> Any:
    try:
        tasks = load_and_import_benchmark(
            db,
            datasource_id=req.datasource_id,
            project_id=req.project_id,
            source=req.source,
            file_path=req.file_path,
            payload=req.payload,
            limit=req.limit,
        )
        db.commit()
        return AgentBenchmarkImportResponse(
            source=req.source,
            total_imported=len(tasks),
            task_ids=[str(t.id) for t in tasks],
        )
    except DataBoxError:
        raise
    except Exception as exc:
        logger.exception("Benchmark import failed")
        raise HTTPException(status_code=500, detail={"code": "IMPORT_ERROR", "message": str(exc)})


@router.post("/agent-eval/run", response_model=AgentEvalRunResponse)
def api_run_eval(req: AgentEvalRunRequest, db: Session = Depends(get_db)) -> Any:
    try:
        runner = AgentEvalRunner(db)
        return runner.run(req)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("Agent eval run failed")
        raise HTTPException(status_code=500, detail={"code": "EVAL_RUN_ERROR", "message": str(exc)})


@router.get("/agent-eval/runs", response_model=list[AgentEvalRunResponse])
def api_list_runs(
    datasource_id: str = Query(...),
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[Any]:
    query = db.query(AgentEvalRun).filter(AgentEvalRun.datasource_id == datasource_id)
    if project_id:
        query = query.filter(AgentEvalRun.project_id == project_id)
    runs = query.order_by(AgentEvalRun.created_at.desc()).all()
    return [
        AgentEvalRunResponse(
            id=str(r.id),
            datasource_id=str(r.datasource_id),
            project_id=str(r.project_id) if r.project_id else None,
            status=str(r.status),
            total_cases=int(r.total_cases),
            passed_cases=int(r.passed_cases),
            failed_cases=int(r.failed_cases),
            pass_rate=float(r.pass_rate) if r.pass_rate is not None else None,
            avg_latency_ms=float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
            summary_json=str(r.summary_json),
            created_at=r.created_at.isoformat() if r.created_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            case_results=[],
        )
        for r in runs
    ]


@router.get("/agent-eval/runs/{eval_run_id}", response_model=AgentEvalRunResponse)
def api_get_run(eval_run_id: str, db: Session = Depends(get_db)) -> Any:
    r = db.query(AgentEvalRun).filter(AgentEvalRun.id == eval_run_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail={"code": "EVAL_RUN_NOT_FOUND", "message": f"Eval run {eval_run_id} not found."})
    cases = db.query(AgentEvalCaseResult).filter(
        AgentEvalCaseResult.eval_run_id == eval_run_id
    ).order_by(AgentEvalCaseResult.created_at.asc()).all()
    return AgentEvalRunResponse(
        id=str(r.id),
        datasource_id=str(r.datasource_id),
        project_id=str(r.project_id) if r.project_id else None,
        status=str(r.status),
        total_cases=int(r.total_cases),
        passed_cases=int(r.passed_cases),
        failed_cases=int(r.failed_cases),
        pass_rate=float(r.pass_rate) if r.pass_rate is not None else None,
        avg_latency_ms=float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
        summary_json=str(r.summary_json),
        created_at=r.created_at.isoformat() if r.created_at else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        case_results=[_case_to_response(c) for c in cases],
    )


@router.get("/agent-eval/runs/{eval_run_id}/cases", response_model=list[AgentEvalCaseResultResponse])
def api_get_run_cases(eval_run_id: str, db: Session = Depends(get_db)) -> list[Any]:
    cases = db.query(AgentEvalCaseResult).filter(
        AgentEvalCaseResult.eval_run_id == eval_run_id
    ).order_by(AgentEvalCaseResult.created_at.asc()).all()
    return [_case_to_response(c) for c in cases]
