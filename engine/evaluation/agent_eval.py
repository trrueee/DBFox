from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.agent import DBFoxAgentRuntime
from engine.agent_core.types import AgentRunRequest, AgentWorkspaceContext
from engine.evaluation.agent_case_evaluator import AgentCaseEvaluator
from engine.models import AgentEvalCaseResult, AgentEvalRun, AgentGoldenTask
from engine.schemas.agent_eval import AgentEvalRunRequest, AgentEvalRunResponse, AgentEvalCaseResultResponse

logger = logging.getLogger("dbfox.agent_eval")


class AgentEvalRunner:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.evaluator = AgentCaseEvaluator()

    def run(self, req: AgentEvalRunRequest) -> AgentEvalRunResponse:
        query = self.db.query(AgentGoldenTask).filter(
            AgentGoldenTask.datasource_id == req.datasource_id
        )
        if req.project_id:
            query = query.filter(AgentGoldenTask.project_id == req.project_id)
        if req.task_ids:
            query = query.filter(AgentGoldenTask.id.in_(req.task_ids))
        if req.tags:
            for tag in req.tags:
                query = query.filter(AgentGoldenTask.tags_json.contains(tag))
        if req.source:
            query = query.filter(AgentGoldenTask.source == req.source)

        tasks = query.all()
        if not tasks:
            return AgentEvalRunResponse(
                id="",
                datasource_id=req.datasource_id,
                project_id=req.project_id,
                status="completed",
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                pass_rate=None,
                avg_latency_ms=None,
                summary_json="{}",
                created_at="",
                completed_at="",
                case_results=[],
            )

        eval_run = AgentEvalRun(
            datasource_id=req.datasource_id,
            project_id=req.project_id,
            source_filter_json=json.dumps({"source": req.source, "tags": req.tags}),
            status="running",
            total_cases=len(tasks),
            passed_cases=0,
            failed_cases=0,
            created_at=datetime.now(UTC),
        )
        self.db.add(eval_run)
        self.db.flush()

        passed = 0
        failed = 0
        total_latency = 0
        case_telemetries: list[dict[str, Any]] = []
        case_responses: list[AgentEvalCaseResultResponse] = []
        runtime = DBFoxAgentRuntime(self.db)

        for task in tasks:
            try:
                start = time.monotonic()
                workspace_ctx = _build_workspace_context(task)
                agent_req = AgentRunRequest(
                    datasource_id=str(task.datasource_id),
                    question=str(task.question),
                    session_id=None,
                    execute=req.execute,
                    llm_credential_id=req.llm_credential_id,
                    api_base=req.api_base,
                    model_name=req.model_name,
                    workspace_context=workspace_ctx,
                )
                events_payload: list[dict[str, Any]] = []
                response = None
                for event in runtime.run_iter(agent_req):
                    events_payload.append(event.model_dump(mode="json"))
                    if event.response is not None:
                        response = event.response
                if response is None:
                    raise RuntimeError("Agent eval case completed without a final response.")
                latency_ms = int((time.monotonic() - start) * 1000)
                total_latency += latency_ms

                trace_payload = [event.model_dump(mode="json") for event in response.trace_events]
                actual_sql = _actual_sql_values(response, events_payload)
                runtime_telemetry = _runtime_product_telemetry(events_payload, response)
                case_telemetries.append(runtime_telemetry)
                evaluation = self.evaluator.evaluate(task, response, events=events_payload, trace=trace_payload)

                case_result = AgentEvalCaseResult(
                    eval_run_id=str(eval_run.id),
                    task_id=str(task.id),
                    run_id=response.run_id,
                    status="passed" if evaluation.passed else "failed",
                    score=evaluation.score,
                    latency_ms=latency_ms,
                    actual_intent=evaluation.actual.get("actual_intent"),
                    actual_tools_json=json.dumps(evaluation.actual.get("actual_tools", [])),
                    actual_artifact_types_json=json.dumps(evaluation.actual.get("actual_artifact_types", [])),
                    actual_approval_state=evaluation.actual.get("actual_approval_state"),
                    actual_sql_json=json.dumps(actual_sql),
                    failure_reasons_json=json.dumps(evaluation.failure_reasons),
                    response_json=_safe_response_json(response, eval_telemetry=runtime_telemetry),
                    created_at=datetime.now(UTC),
                )
                self.db.add(case_result)
                self.db.flush()

                if evaluation.passed:
                    passed += 1
                else:
                    failed += 1

                case_responses.append(AgentEvalCaseResultResponse(
                    id=str(case_result.id),
                    eval_run_id=str(case_result.eval_run_id),
                    task_id=str(case_result.task_id),
                    run_id=str(case_result.run_id) if case_result.run_id else None,
                    status=str(case_result.status),
                    score=float(case_result.score),
                    latency_ms=int(case_result.latency_ms) if case_result.latency_ms else None,
                    actual_intent=str(case_result.actual_intent) if case_result.actual_intent else None,
                    actual_tools_json=str(case_result.actual_tools_json),
                    actual_artifact_types_json=str(case_result.actual_artifact_types_json),
                    actual_approval_state=str(case_result.actual_approval_state) if case_result.actual_approval_state else None,
                    actual_sql_json=str(case_result.actual_sql_json),
                    failure_reasons_json=str(case_result.failure_reasons_json),
                    response_json=str(case_result.response_json),
                    created_at=case_result.created_at.isoformat() if case_result.created_at else None,
                ))

            except Exception as exc:
                logger.exception("Eval case failed for task %s: %s", task.id, exc)
                failed += 1
                case_result = AgentEvalCaseResult(
                    eval_run_id=str(eval_run.id),
                    task_id=str(task.id),
                    run_id=None,
                    status="error",
                    score=0.0,
                    latency_ms=None,
                    actual_intent=None,
                    actual_tools_json="[]",
                    actual_artifact_types_json="[]",
                    actual_approval_state=None,
                    actual_sql_json="[]",
                    failure_reasons_json=json.dumps([str(exc)]),
                    response_json="{}",
                    created_at=datetime.now(UTC),
                )
                self.db.add(case_result)
                self.db.flush()
                case_responses.append(AgentEvalCaseResultResponse(
                    id=str(case_result.id),
                    eval_run_id=str(case_result.eval_run_id),
                    task_id=str(case_result.task_id),
                    run_id=None,
                    status="error",
                    score=0.0,
                    latency_ms=None,
                    failure_reasons_json=str(case_result.failure_reasons_json),
                    actual_intent=None,
                    actual_tools_json="[]",
                    actual_artifact_types_json="[]",
                    actual_approval_state=None,
                    actual_sql_json="[]",
                    response_json="{}",
                    created_at=case_result.created_at.isoformat() if case_result.created_at else None,
                ))

        pass_rate_value = round(passed / max(len(tasks), 1), 4)
        avg_latency_value = round(total_latency / max(len(tasks), 1), 2) if total_latency > 0 else None

        eval_run.status = "completed"  # type: ignore[assignment]
        eval_run.passed_cases = passed  # type: ignore[assignment]
        eval_run.failed_cases = failed  # type: ignore[assignment]
        eval_run.pass_rate = pass_rate_value  # type: ignore[assignment]
        eval_run.avg_latency_ms = avg_latency_value  # type: ignore[assignment]
        eval_run.summary_json = json.dumps({  # type: ignore[assignment]
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate_value,
            "avg_latency_ms": avg_latency_value,
            "runtime_telemetry": _summarize_runtime_telemetry(case_telemetries),
        })
        eval_run.completed_at = datetime.now(UTC)  # type: ignore[assignment]

        self.db.commit()

        return AgentEvalRunResponse(
            id=str(eval_run.id),
            datasource_id=str(eval_run.datasource_id),
            project_id=str(eval_run.project_id) if eval_run.project_id else None,
            status=str(eval_run.status),
            total_cases=int(eval_run.total_cases),
            passed_cases=int(eval_run.passed_cases),
            failed_cases=int(eval_run.failed_cases),
            pass_rate=float(eval_run.pass_rate) if eval_run.pass_rate is not None else None,
            avg_latency_ms=float(eval_run.avg_latency_ms) if eval_run.avg_latency_ms is not None else None,
            summary_json=str(eval_run.summary_json),
            created_at=eval_run.created_at.isoformat() if eval_run.created_at else None,
            completed_at=eval_run.completed_at.isoformat() if eval_run.completed_at else None,
            case_results=case_responses,
        )


def _build_workspace_context(task: AgentGoldenTask) -> AgentWorkspaceContext | None:
    try:
        data = json.loads(str(task.workspace_context_json))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    selected = data.get("selected_table_names")
    return AgentWorkspaceContext(
        datasource_id=str(task.datasource_id),
        active_sql=data.get("active_sql"),
        last_error=data.get("last_error"),
        last_query_result_preview=data.get("last_query_result_preview"),
        selected_table_names=list(selected) if isinstance(selected, list) else [],
        selected_artifact_id=data.get("selected_artifact_id"),
        recent_agent_run_id=data.get("recent_agent_run_id"),
    )


def _safe_response_json(response: Any, *, eval_telemetry: dict[str, Any] | None = None) -> str:
    try:
        data = response.model_dump()
        if eval_telemetry is not None:
            data["eval_telemetry"] = eval_telemetry
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def _runtime_product_telemetry(events: list[dict[str, Any]], response: Any) -> dict[str, Any]:
    stage_counts: dict[str, int] = {}
    stage_durations_ms: dict[str, int] = {}
    error_classes: list[str] = []
    root_causes: list[str] = []
    recovery_strategies: list[str] = []
    failure_layer: str | None = None
    repair_attempts: set[str] = set()
    repair_events_without_attempt = 0

    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue

        phase = _clean_string(step.get("phase") or step.get("stage"))
        if phase:
            stage_counts[phase] = stage_counts.get(phase, 0) + 1
            duration_ms = _step_duration_ms(step)
            if duration_ms is not None:
                stage_durations_ms[phase] = stage_durations_ms.get(phase, 0) + duration_ms

        step_failure_layer = _clean_string(step.get("failure_layer"))
        if failure_layer is None and step_failure_layer:
            failure_layer = step_failure_layer
        _append_unique(error_classes, step.get("error_class"))
        _append_unique(root_causes, step.get("root_cause"))
        _append_unique(recovery_strategies, step.get("recovery_strategy"))

        if _is_repair_step(step):
            attempt = step.get("attempt")
            if attempt is None:
                repair_events_without_attempt += 1
            else:
                repair_attempts.add(str(attempt))

    final_status = _clean_string(getattr(response, "status", None))
    response_success = getattr(response, "success", None)
    if isinstance(response_success, bool):
        final_success = response_success
    else:
        final_success = final_status in {"success", "completed", "complete"}

    return {
        "stage_counts": stage_counts,
        "stage_durations_ms": stage_durations_ms,
        "repair_count": len(repair_attempts) + repair_events_without_attempt,
        "failure_layer": failure_layer,
        "error_classes": error_classes,
        "root_causes": root_causes,
        "recovery_strategies": recovery_strategies,
        "final_status": final_status,
        "final_success": final_success,
    }


def _summarize_runtime_telemetry(case_telemetries: list[dict[str, Any]]) -> dict[str, Any]:
    stage_counts: dict[str, int] = {}
    stage_durations_ms: dict[str, int] = {}
    failure_layers: dict[str, int] = {}
    error_classes: dict[str, int] = {}
    final_success_cases = 0
    repair_count = 0

    for telemetry in case_telemetries:
        if telemetry.get("final_success") is True:
            final_success_cases += 1
        repair_count += int(telemetry.get("repair_count") or 0)
        _merge_int_map(stage_counts, telemetry.get("stage_counts"))
        _merge_int_map(stage_durations_ms, telemetry.get("stage_durations_ms"))

        failure_layer = _clean_string(telemetry.get("failure_layer"))
        if failure_layer:
            failure_layers[failure_layer] = failure_layers.get(failure_layer, 0) + 1
        for error_class in telemetry.get("error_classes") or []:
            value = _clean_string(error_class)
            if value:
                error_classes[value] = error_classes.get(value, 0) + 1

    return {
        "final_success_cases": final_success_cases,
        "repair_count": repair_count,
        "stage_counts": stage_counts,
        "stage_durations_ms": stage_durations_ms,
        "failure_layers": failure_layers,
        "error_classes": error_classes,
    }


def _step_duration_ms(step: dict[str, Any]) -> int | None:
    for container in (step, step.get("output")):
        if not isinstance(container, dict):
            continue
        for key in ("duration_ms", "durationMs", "latency_ms", "latencyMs"):
            value = container.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(float(value))
                except ValueError:
                    continue
    return None


def _is_repair_step(step: dict[str, Any]) -> bool:
    phase = _clean_string(step.get("phase") or step.get("stage"))
    name = _clean_string(step.get("name") or step.get("tool_name"))
    return phase == "repairing" or name in {"sql_repair", "sql.repair"} or bool(step.get("recovery_strategy"))


def _append_unique(values: list[str], raw: Any) -> None:
    value = _clean_string(raw)
    if value and value not in values:
        values.append(value)


def _merge_int_map(target: dict[str, int], raw: Any) -> None:
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        cleaned_key = _clean_string(key)
        if not cleaned_key or isinstance(value, bool) or not isinstance(value, int | float):
            continue
        target[cleaned_key] = target.get(cleaned_key, 0) + int(value)


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _actual_sql_values(response: Any, events: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            sql = value.strip()
            if sql and sql not in values:
                values.append(sql)

    add(getattr(response, "sql", None))
    for step in getattr(response, "steps", []) or []:
        output = getattr(step, "output", None)
        if isinstance(output, dict):
            add(output.get("sql"))
            add(output.get("safe_sql"))
            decision = output.get("execution_safety_decision")
            if isinstance(decision, dict):
                add(decision.get("safe_sql"))
                add(decision.get("original_sql"))

    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        add(step.get("sql"))
        add(step.get("safe_sql"))
    return values
