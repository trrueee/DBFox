from __future__ import annotations

import argparse
import os
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from eval_common import get_local_token, get_local_token_path, load_llm_config  # noqa: E402


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_sse_lines(response: httpx.Response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data: list[str] = []

    for raw_line in response.iter_lines():
        line = raw_line.strip() if raw_line else ""

        if not line:
            if current_data:
                payload = "\n".join(current_data)
                try:
                    event = json.loads(payload)
                    if current_event:
                        event["_sse_event"] = current_event
                    events.append(event)
                except json.JSONDecodeError:
                    events.append({"_sse_event": current_event or "unknown", "raw": payload})
            current_event = None
            current_data = []
            continue

        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current_data.append(line[len("data:") :].strip())

    return events


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _last_non_empty(values: list[Any]) -> Any:
    for value in reversed(values):
        if value is not None and value != "":
            return value
    return None


def _event_response(event: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(event.get("response"))


def _artifact_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(artifact.get("payload"))


def collect_artifacts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []

    for event in events:
        artifact = _as_dict(event.get("artifact"))
        if artifact:
            artifacts.append(artifact)

        response = _event_response(event)
        for artifact in _as_list(response.get("artifacts")):
            if isinstance(artifact, dict):
                artifacts.append(artifact)

    return artifacts


def collect_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []

    for event in events:
        step = _as_dict(event.get("step"))
        if step:
            steps.append(step)

        response = _event_response(event)
        for step in _as_list(response.get("steps")):
            if isinstance(step, dict):
                steps.append(step)

    return steps


def collect_trace_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace_events: list[dict[str, Any]] = []

    for event in events:
        response = _event_response(event)
        for trace in _as_list(response.get("trace_events")):
            if isinstance(trace, dict):
                trace_events.append(trace)

    return trace_events


def find_step_outputs(
    steps: list[dict[str, Any]],
    trace_events: list[dict[str, Any]],
    *,
    name: str,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []

    for step in steps:
        if step.get("name") == name:
            output = _as_dict(step.get("output"))
            if output:
                outputs.append(output)

    for trace in trace_events:
        if trace.get("name") == name:
            output = _as_dict(trace.get("output"))
            if output:
                outputs.append(output)

    return outputs


def find_step_inputs(
    steps: list[dict[str, Any]],
    trace_events: list[dict[str, Any]],
    *,
    name: str,
) -> list[dict[str, Any]]:
    """Extract input dicts from steps/trace_events matching `name`.

    Unlike find_step_outputs, this reads the **input** field of each
    step / trace_event — which is where model_name, has_api_key, plan_goal
    etc. are actually recorded.
    """
    inputs: list[dict[str, Any]] = []

    for step in steps:
        if step.get("name") == name:
            inp = _as_dict(step.get("input"))
            if inp:
                inputs.append(inp)

    for trace in trace_events:
        if trace.get("name") == name:
            inp = _as_dict(trace.get("input"))
            if inp:
                inputs.append(inp)

    return inputs


def find_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    semantic_ids: set[str] | None = None,
    types: set[str] | None = None,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []

    for artifact in artifacts:
        semantic_id = artifact.get("semantic_id")
        artifact_type = artifact.get("type")

        if semantic_ids is not None and semantic_id not in semantic_ids:
            continue
        if types is not None and artifact_type not in types:
            continue

        matched.append(artifact)

    return matched


def _metadata_from_outputs(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
    for output in outputs:
        meta = _as_dict(output.get("metadata"))
        if meta:
            metadata.append(meta)
    return metadata


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = collect_artifacts(events)
    steps = collect_steps(events)
    trace_events = collect_trace_events(events)

    responses = [_event_response(event) for event in events if _event_response(event)]

    generate_outputs = find_step_outputs(steps, trace_events, name="generate_sql_candidate")
    validate_outputs = find_step_outputs(steps, trace_events, name="validate_sql")
    execute_outputs = find_step_outputs(steps, trace_events, name="execute_sql")

    sql_artifacts = find_artifacts(artifacts, semantic_ids={"sql_candidate", "sql"}, types=None)
    safety_artifacts = find_artifacts(artifacts, semantic_ids={"safety_report"}, types={"safety"})

    response_sql_values = [response.get("sql") for response in responses]
    generate_sql_values = [output.get("sql") for output in generate_outputs]
    artifact_sql_values = [_artifact_payload(artifact).get("sql") for artifact in sql_artifacts]

    response_safety_values = [_as_dict(response.get("safety")) for response in responses]
    response_safe_sql_values = [safety.get("safe_sql") for safety in response_safety_values]
    safety_artifact_payloads = [_artifact_payload(artifact) for artifact in safety_artifacts]
    safety_artifact_safe_sql_values = [payload.get("safe_sql") for payload in safety_artifact_payloads]
    validate_safe_sql_values = [output.get("safe_sql") for output in validate_outputs]

    response_can_execute_values = [safety.get("can_execute") for safety in response_safety_values]
    safety_artifact_can_execute_values = [payload.get("can_execute") for payload in safety_artifact_payloads]
    validate_can_execute_values = [output.get("can_execute") for output in validate_outputs]

    response_blocked_values = [safety.get("blocked_reasons") for safety in response_safety_values]
    safety_artifact_blocked_values = [payload.get("blocked_reasons") for payload in safety_artifact_payloads]
    validate_blocked_values = [output.get("blocked_reasons") for output in validate_outputs]

    metadata_values = _metadata_from_outputs(generate_outputs)
    sql_artifact_metadata_values = [
        _as_dict(_artifact_payload(artifact).get("metadata")) for artifact in sql_artifacts
    ]
    metadata_values.extend(meta for meta in sql_artifact_metadata_values if meta)

    generation_source_values = [meta.get("generation_source") for meta in metadata_values]
    model_values = [output.get("model") for output in generate_outputs]
    model_values.extend(_artifact_payload(artifact).get("model") for artifact in sql_artifacts)

    rewrite_notes: list[str] = []
    for output in generate_outputs:
        for note in _as_list(output.get("rewrite_notes")):
            if isinstance(note, str):
                rewrite_notes.append(note)

    fallback_reason_values: list[Any] = []
    for meta in metadata_values:
        fallback_reason_values.append(meta.get("fallback_reason"))
        rewrite = _as_dict(meta.get("rewrite"))
        fallback_reason_values.append(rewrite.get("fallback_reason"))

    fallback_reason_values.extend(
        note for note in rewrite_notes if isinstance(note, str) and "fallback" in note.lower()
    )

    generation_source = _last_non_empty(generation_source_values)
    if not _last_non_empty(fallback_reason_values) and generation_source and generation_source != "query_plan_rendered":
        fallback_reason_values.append(f"generation_source:{generation_source}")

    event_types = [event.get("type") for event in events if event.get("type")]
    sse_events = [event.get("_sse_event") for event in events if event.get("_sse_event")]
    step_names = [step.get("name") for step in steps if step.get("name")]
    trace_step_names = [trace.get("name") for trace in trace_events if trace.get("name")]
    artifact_semantic_ids = [
        artifact.get("semantic_id") for artifact in artifacts if artifact.get("semantic_id")
    ]

    execute_sql_step = (
        "execute_sql" in step_names
        or "execute_sql" in trace_step_names
        or any(event.get("step", {}).get("name") == "execute_sql" for event in events if isinstance(event.get("step"), dict))
    )
    final_answer_values: list[Any] = []
    final_error_values: list[Any] = []

    for event in events:
        answer = _as_dict(event.get("answer"))
        if answer.get("answer"):
            final_answer_values.append(answer.get("answer"))
        if event.get("error"):
            final_error_values.append(event.get("error"))

    for response in responses:
        answer = _as_dict(response.get("answer"))
        if answer.get("answer"):
            final_answer_values.append(answer.get("answer"))
        if response.get("explanation"):
            final_answer_values.append(response.get("explanation"))
        if response.get("error"):
            final_error_values.append(response.get("error"))

        execution = _as_dict(response.get("execution"))
        if execution.get("error"):
            final_error_values.append(execution.get("error"))

    error_artifacts = find_artifacts(artifacts, types={"error"})
    for artifact in error_artifacts:
        payload = _artifact_payload(artifact)
        if payload.get("error"):
            final_error_values.append(payload.get("error"))

    final_status = _last_non_empty([response.get("status") for response in responses])
    if not final_status:
        final_status = _last_non_empty(event_types) or _last_non_empty(sse_events)

    summary = {
        "events_count": len(events),
        "final_status": final_status,
        "generation_source": generation_source,
        "model": _last_non_empty(model_values),
        "fallback_reason": _last_non_empty(fallback_reason_values),
        "agent_sql": _last_non_empty(response_sql_values + artifact_sql_values + generate_sql_values),
        "safe_sql": _last_non_empty(response_safe_sql_values + safety_artifact_safe_sql_values + validate_safe_sql_values),
        "safety.can_execute": _last_non_empty(
            response_can_execute_values + safety_artifact_can_execute_values + validate_can_execute_values
        ),
        "blocked_reasons": _last_non_empty(
            response_blocked_values + safety_artifact_blocked_values + validate_blocked_values
        ),
        # backward compatible flag; new fields below provide richer info
        "execute_sql_step": execute_sql_step,
        "artifact_count": len(artifacts),
        "final_answer": _last_non_empty(final_answer_values),
        "final_error": _last_non_empty(final_error_values),
        "summary_debug": {
            "event_types": sorted(set(str(v) for v in event_types)),
            "sse_events": sorted(set(str(v) for v in sse_events)),
            "artifact_semantic_ids": sorted(set(str(v) for v in artifact_semantic_ids)),
            "step_names": sorted(set(str(v) for v in step_names)),
            "trace_step_names": sorted(set(str(v) for v in trace_step_names)),
            "has_response": bool(responses),
            "has_artifacts": bool(artifacts),
            "has_trace_events": bool(trace_events),
            "missing_final_status": final_status is None,
        },
    }

    # Extract execute_sql detailed status
    execute_summary = _extract_execute_sql_status(steps, trace_events)
    summary.update(execute_summary)
    # Keep backward compatibility
    summary["execute_sql_step"] = execute_summary["execute_sql_step_appeared"]

    # Extract input fields from generate_sql_candidate step/trace
    generate_inputs = find_step_inputs(steps, trace_events, name="generate_sql_candidate")
    model_name_candidates = []
    has_api_key_candidates = []
    plan_goal_candidates = []
    plan_tables_candidates = []
    schema_size_candidates = []
    for inp in generate_inputs:
        if inp.get("model_name"):
            model_name_candidates.append(inp.get("model_name"))
        if "has_api_key" in inp:
            has_api_key_candidates.append(inp.get("has_api_key"))
        if inp.get("plan_goal"):
            plan_goal_candidates.append(inp.get("plan_goal"))
        if inp.get("plan_candidate_tables"):
            plan_tables_candidates.append(inp.get("plan_candidate_tables"))
        if inp.get("schema_context_size") is not None:
            schema_size_candidates.append(inp.get("schema_context_size"))

    # Also check artifacts for model or metadata
    for art in sql_artifacts:
        payload = _artifact_payload(art)
        if payload.get("model"):
            model_name_candidates.append(payload.get("model"))
        meta = _as_dict(payload.get("metadata"))
        if meta.get("query_plan"):
            qm = meta.get("query_plan")
            if isinstance(qm, dict) and qm.get("mode"):
                # add to summary_debug for diagnosis
                summary["summary_debug"]["plan_mode"] = qm.get("mode")

    summary["model_name_from_input"] = _last_non_empty(model_name_candidates)
    summary["has_api_key_from_input"] = _last_non_empty(has_api_key_candidates)
    summary["plan_goal_from_input"] = _last_non_empty(plan_goal_candidates)
    summary["plan_candidate_tables_from_input"] = plan_tables_candidates[0] if plan_tables_candidates else None
    summary["schema_context_size_from_input"] = schema_size_candidates[0] if schema_size_candidates else None

    # Hard client-side sanitizer: strip data-result claims when execution was skipped.
    # This is a last-resort defense independent of server-side sanitizers.
    _sanitize_misleading_answer(summary)

    return summary


_EVAL_SAFE_ANSWER = (
    "I generated and validated the SQL, but execution was disabled "
    "for this review-only run, so no result set was retrieved. "
    "I cannot make data-result claims until the query is executed."
)

_EVAL_MISLEADING_PHRASES = [
    "returned zero", "no rows returned", "no students",
    "executed successfully", "query executed successfully",
    "returned 0 rows", "returned no results", "0 rows",
    "there are no students", "no data was returned",
    "no matching records",
]


def _sanitize_misleading_answer(summary: dict[str, Any]) -> None:
    """Client-side guard: when execute=false, replace any answer that
    makes data-result claims with a safe no-execution message."""
    executed = summary.get("execute_sql_executed")
    status = summary.get("execute_sql_status")
    if executed is not False and status != "skipped":
        return
    answer = str(summary.get("final_answer") or "")
    lower = answer.lower()
    if any(p in lower for p in _EVAL_MISLEADING_PHRASES):
        summary["final_answer"] = _EVAL_SAFE_ANSWER
        summary["final_answer_sanitized"] = True


def _extract_execute_sql_status(steps: list[dict[str, Any]], trace_events: list[dict[str, Any]]) -> dict[str, Any]:
    execute_steps = []

    for step in steps:
        if step.get("name") == "execute_sql":
            execute_steps.append(step)

    for trace in trace_events:
        if trace.get("name") == "execute_sql":
            execute_steps.append(trace)

    if not execute_steps:
        return {
            "execute_sql_step_appeared": False,
            "execute_sql_status": None,
            "execute_sql_executed": False,
        }

    last = execute_steps[-1]
    status = last.get("status")
    output = last.get("output") if isinstance(last.get("output"), dict) else {}
    input_ = last.get("input") if isinstance(last.get("input"), dict) else {}

    skipped = (
        status == "skipped"
        or input_.get("execute") is False
        or "not executed" in str(output.get("reason", "")).lower()
    )

    executed = bool(
        status == "success"
        and not skipped
        and output.get("success", True) is not False
    )

    return {
        "execute_sql_step_appeared": True,
        "execute_sql_status": status,
        "execute_sql_executed": executed,
    }


def run_case(
    case: dict[str, Any],
    *,
    base_url: str,
    token: str,
    execute: bool,
    max_steps: int,
    llm_config: dict[str, Any] | None = None,
    timeout: int = 180,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None, int | None]:
    run_url = f"{base_url.rstrip('/')}/api/v1/agent-kernel/run/stream"
    payload = {
        "datasource_id": f"ds-spider-{case['db_id'].replace('_', '-')}",
        "question": case["question"],
        "execute": execute,
        "max_steps": max_steps,
    }
    llm_config = llm_config or {}
    if llm_config.get("api_key"):
        payload["api_key"] = llm_config["api_key"]
    if llm_config.get("api_base"):
        payload["api_base"] = llm_config["api_base"]
    if llm_config.get("model_name"):
        payload["model_name"] = llm_config["model_name"]
    headers = {"X-Local-Token": token, "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", run_url, json=payload, headers=headers, timeout=timeout) as resp:
                status_code = resp.status_code
                if status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")[:400]
                    return None, {"error": f"HTTP {status_code}", "body": body}, status_code

                events = parse_sse_lines(resp)
                return events, None, status_code

    except Exception as exc:
        return None, {"error": "exception", "detail": repr(exc), "message": str(exc)}, None


def collect_metadata(
    case_id: str,
    events: list[dict[str, Any]] | None,
    err: dict[str, Any] | None,
    *,
    status_code: int | None,
    execute_requested: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case_id": case_id,
        "error": None,
        "status_code": status_code,
        "events_count": 0,
        "execute_requested": execute_requested,
        "final_status": None,
        "generation_source": None,
        "model": None,
        "fallback_reason": None,
        "agent_sql": None,
        "safe_sql": None,
        "safety.can_execute": None,
        "blocked_reasons": None,
        "execute_sql_step": False,
        "artifact_count": 0,
        "final_answer": None,
        "final_error": None,
        "summary_debug": {},
    }

    if err:
        record["error"] = err
        return record

    events = events or []
    summary = summarize_events(events)
    record.update(summary)
    return record


def write_case_files(
    *,
    save_events_dir: Path | None,
    case_id: str,
    events: list[dict[str, Any]] | None,
    summary: dict[str, Any],
) -> None:
    if save_events_dir is None:
        return

    save_events_dir.mkdir(parents=True, exist_ok=True)
    events_path = save_events_dir / f"{case_id}.events.json"
    summary_path = save_events_dir / f"{case_id}.summary.json"

    events_path.write_text(
        json.dumps(events or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def health_check(base_url: str) -> None:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/v1/health", timeout=3.0)
        if response.status_code != 200:
            print("Health check failed:", response.status_code, response.text[:200])
            print("Please run: python .agent_eval/start_eval_backend.py")
            raise SystemExit(2)
    except Exception as exc:
        print("Health check error for base_url=", base_url)
        print("Error:", exc)
        print("Please run: python .agent_eval/start_eval_backend.py")
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18625")
    parser.add_argument("--cases", default=".agent_eval/cases.smoke_subset.json")
    parser.add_argument("--out", default=".agent_eval/outputs/agent_only_results.jsonl")
    parser.add_argument("--execute", default="false")
    parser.add_argument("--max-steps", default=15, type=int)
    parser.add_argument("--save-events-dir", default=None)
    parser.add_argument("--include-events-in-jsonl", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()

    base_url = args.base_url
    cases_path = Path(args.cases)
    out_path = Path(args.out)
    execute = parse_bool(args.execute)
    save_events_dir = Path(args.save_events_dir) if args.save_events_dir else None

    overrides: dict[str, Any] = {}
    if args.provider:
        overrides["provider"] = args.provider
    if args.model_name:
        overrides["model_name"] = args.model_name
    if args.api_base:
        overrides["api_base"] = args.api_base
    if args.api_key_env:
        overrides["api_key"] = os.getenv(args.api_key_env)

    llm_config = load_llm_config(args.config, overrides=overrides)
    if not llm_config.get("api_key") or not llm_config.get("model_name"):
        print("WARNING: No LLM config available; complex fallback will fail-closed.")

    token_path = get_local_token_path()
    if not token_path:
        print("Local token not found. Ensure backend started and token file exists.")
        raise SystemExit(3)

    health_check(base_url)

    token = get_local_token()

    if not cases_path.exists():
        print("Cases file not found:", cases_path)
        raise SystemExit(4)

    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    outputs: list[dict[str, Any]] = []

    for case in cases:
        case_id = case.get("case_id") or case.get("id")
        if not case_id:
            raise ValueError(f"Case missing case_id/id: {case}")

        print("Running:", case_id)

        events, err, status_code = run_case(
            case,
            base_url=base_url,
            token=token,
            execute=execute,
            max_steps=args.max_steps,
            llm_config=llm_config,
        )

        record = collect_metadata(
            case_id,
            events,
            err,
            status_code=status_code,
            execute_requested=execute,
        )
        record["provider_from_config"] = llm_config.get("provider")
        record["model_from_config"] = llm_config.get("model_name")
        record["has_api_key_from_config"] = bool(llm_config.get("api_key"))

        write_case_files(
            save_events_dir=save_events_dir,
            case_id=case_id,
            events=events,
            summary=record,
        )

        if args.include_events_in_jsonl:
            record["events"] = events or []

        outputs.append(record)
        print("done", case_id, "err=", record.get("error"))
        time.sleep(0.5)

    out_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in outputs),
        encoding="utf-8",
    )
    print("\nWrote", out_path)


if __name__ == "__main__":
    main()
