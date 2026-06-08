from __future__ import annotations

from typing import Any
from uuid import uuid4

from engine.agent.types import ToolObservation


def apply_tool_result_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
) -> dict[str, Any]:
    output = observation.output or {}
    update: dict[str, Any] = {
        "tool_results": [observation.model_dump(mode="json")],
        "trace_events": [
            {
                "type": "tool.completed",
                "payload": {
                    "tool_name": tool_name,
                    "observation_name": observation.name,
                    "status": observation.status,
                },
            }
        ],
    }

    if observation.status == "failed":
        update["error"] = observation.error or f"{tool_name} failed."
        if output:
            if tool_name == "sql.execute_readonly":
                update["execution"] = output
        return update

    if tool_name == "followup.load_context":
        update["followup_context"] = output

    elif tool_name == "schema.build_context":
        update["schema_context"] = output

    elif tool_name == "query_plan.build":
        update["query_plan"] = output

    elif tool_name == "sql.generate":
        sql = str(output.get("sql") or "").strip()
        update["sql_candidate"] = output
        update["sql"] = sql or state.get("sql")

    elif tool_name == "sql.validate":
        safe_sql = str(output.get("safe_sql") or "").strip()
        update["safety"] = output
        if safe_sql:
            update["sql"] = safe_sql

    elif tool_name == "sql.execute_readonly":
        update["execution"] = output

    elif tool_name == "sql.skip_execution":
        update["execution"] = output

    elif tool_name == "sql.revise":
        update["revision_attempted"] = True
        fixed_sql = str(output.get("fixed_sql") or "").strip()
        if fixed_sql:
            update["sql"] = fixed_sql
            update["error"] = None
        else:
            update["error"] = str(output.get("revise_suggestion") or output.get("reason") or state.get("error") or "SQL revision could not produce a safe executable query.")

    elif tool_name == "result.profile":
        update["result_profile"] = output

    elif tool_name == "chart.suggest":
        update["chart_suggestion"] = output

    elif tool_name == "followup.suggest":
        raw_suggestions = output.get("suggestions")
        if isinstance(raw_suggestions, list):
            update["suggestions"] = [dict(item) for item in raw_suggestions if isinstance(item, dict)]

    elif tool_name == "answer.synthesize":
        update["answer"] = output
        update["final_answer"] = output
        update["status"] = "completed"

    elif tool_name.startswith("workspace."):
        suggestions = output.get("suggestions") if isinstance(output.get("suggestions"), list) else []
        evidence: list[dict[str, Any]] = []
        if suggestions or output.get("proposed_sql"):
            evidence.append(
                {
                    "artifact_id": "sql_suggestion",
                    "label": "SQL suggestion",
                    "value": suggestions[0].get("title") if suggestions and isinstance(suggestions[0], dict) else "workspace suggestion",
                }
            )
        update["answer"] = {
            "answer": str(output.get("answer") or ""),
            "key_findings": [],
            "evidence": evidence,
            "caveats": [],
            "recommendations": [],
            "follow_up_questions": [],
        }
        update["final_answer"] = update["answer"]
        update["status"] = "completed"

    if tool_name in {"sql.generate", "sql.validate", "sql.execute_readonly", "result.profile", "chart.suggest", "answer.synthesize"}:
        update["artifacts"] = [_artifact_event(tool_name, output)]
    if tool_name.startswith("workspace."):
        update["artifacts"] = [_artifact_event(tool_name, output)]

    return update


def merge_state(state: dict[str, Any], update: dict[str, Any]) -> None:
    additive_keys = {"messages", "plan_events", "tool_results", "artifacts", "trace_events"}
    for key, value in update.items():
        if key in additive_keys:
            current = state.setdefault(key, [])
            if isinstance(current, list) and isinstance(value, list):
                current.extend(value)
            else:
                state[key] = value
        else:
            state[key] = value


def _artifact_event(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"artifact_{uuid4().hex}",
        "tool_name": tool_name,
        "payload": payload,
    }
