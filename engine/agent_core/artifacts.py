from __future__ import annotations

from typing import Any
import re

from engine.agent_core.types import AgentAnswer, AgentArtifact, AgentArtifactPresentation


class AgentArtifactIdentity:
    def __init__(self, run_id: str | None = None):
        self.run_id = run_id
        self._counter = 0

    def next_id(self, semantic_id: str) -> str:
        if not self.run_id:
            return semantic_id
        self._counter += 1
        return f"agent/run/{self.run_id}/artifact/{self._counter:03d}/{semantic_id}"

    def stable_id(self, semantic_id: str) -> str:
        if not self.run_id:
            return semantic_id
        return f"agent/run/{self.run_id}/artifact/{semantic_id}"


def build_agent_artifacts(
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    chart_suggestion: dict[str, Any] | None,
    answer: AgentAnswer | None,
    error: str | None = None,
    datasource_id: str | None = None,
    identity: AgentArtifactIdentity | None = None,
) -> list[AgentArtifact]:
    artifacts: list[AgentArtifact] = []

    if query_plan:
        artifacts.append(build_query_plan_artifact(query_plan, identity=identity))

    if sql:
        artifacts.append(build_sql_artifact(sql, safety=safety, execution=execution, identity=identity))

    if safety:
        artifacts.append(build_safety_artifact(safety, identity=identity))

    if execution and execution.get("success"):
        artifacts.append(build_result_view_artifact(execution, datasource_id=datasource_id, safety=safety, identity=identity))

    if chart_suggestion and chart_suggestion.get("type") and chart_suggestion.get("type") != "table":
        artifacts.append(build_chart_artifact(chart_suggestion, safety=safety, execution=execution, identity=identity))

    if error:
        artifacts.append(build_error_artifact(error, safety=safety, execution=execution, identity=identity))

    return sorted(artifacts, key=lambda artifact: artifact.presentation.priority)


def build_query_plan_artifact(
    query_plan: dict[str, Any],
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "query_plan",
        "query_plan",
        "Query plan",
        query_plan,
        mode="dock",
        priority=80,
        collapsed=True,
        identity=identity,
        produced_by_step="build_query_plan",
    )


def build_agent_plan_artifact(
    plan: dict[str, Any],
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "agent_plan_draft",
        "agent_plan",
        "Agent plan",
        plan,
        mode="dock",
        priority=90,
        collapsed=True,
        identity=identity,
        artifact_id=identity.stable_id("agent_plan_draft") if identity else None,
        produced_by_step="plan_agent",
    )


def build_sql_suggestion_artifact(
    payload: dict[str, Any],
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    raw_suggestions = payload.get("suggestions")
    suggestions: list[Any] = raw_suggestions if isinstance(raw_suggestions, list) else []
    first_sql = ""
    for suggestion in suggestions:
        if isinstance(suggestion, dict) and isinstance(suggestion.get("proposed_sql"), str):
            first_sql = str(suggestion["proposed_sql"]).strip()
            if first_sql:
                break
    if not first_sql and isinstance(payload.get("proposed_sql"), str):
        first_sql = str(payload["proposed_sql"]).strip()

    return _artifact(
        "sql_suggestion",
        "sql_suggestion",
        "SQL suggestion",
        {**payload, "proposed_sql": first_sql or payload.get("proposed_sql")},
        mode="both",
        priority=25,
        identity=identity,
        produced_by_step=str(payload.get("produced_by_step") or "db.query"),
        depends_on=["agent_plan_draft"],
    )


def build_sql_artifact(
    sql: str,
    *,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None = None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    execution_meta = _execution_meta(execution or (safety or {}).get("execution"))
    payload: dict[str, Any] = {
        "purpose": "分析查询",
        "sql": sql,
        "used_tables": _used_tables(sql),
        "validation_status": "passed" if _safety_state(safety).get("can_execute") else "unknown",
        "execution_status": "completed" if execution_meta else "not_executed",
        "safety_state": _safety_state(safety),
        **execution_meta,
    }
    generation_metadata = safety.get("generation_metadata") if isinstance(safety, dict) else None
    if isinstance(generation_metadata, dict):
        payload["generation_metadata"] = generation_metadata
    return _artifact(
        "sql_candidate",
        "sql",
        "Validated SQL",
        payload,
        mode="dock",
        priority=70,
        collapsed=True,
        identity=identity,
        produced_by_step="validate_sql",
        depends_on=["query_plan"],
    )


def build_safety_artifact(
    safety: dict[str, Any],
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "safety_report",
        "safety",
        "Safety report",
        safety,
        mode="dock",
        priority=75,
        collapsed=True,
        identity=identity,
        produced_by_step="validate_sql",
        depends_on=["sql_candidate"],
    )


def build_result_view_artifact(
    execution: dict[str, Any],
    datasource_id: str | None = None,
    *,
    safety: dict[str, Any] | None = None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    # Fingerprint the SQL so each distinct query gets its own result view artifact.
    sql = _execution_sql(execution)
    semantic_id = "result_view" if not sql else f"result_view_{_sql_fingerprint(sql)}"
    
    all_rows = execution.get("rows") or []
    preview_rows = all_rows[:10]
    
    return _artifact(
        semantic_id,
        "result_view",
        "Result view",
        {
            "storageMode": "payload", # Legacy compatibility, switch to sql_backed later
            "datasourceId": datasource_id or "",
            "sourceSqlSemanticId": "sql_candidate",
            "sourceSql": sql,
            "safeSql": sql,
            "columns": execution.get("columns", []),
            "previewRows": preview_rows,
            "previewRowCount": len(preview_rows),
            "rows": all_rows, # Legacy compatibility
            "rowCount": execution.get("rowCount", len(all_rows)),
            "returnedRows": execution.get("returnedRows", len(all_rows)),
            "latencyMs": execution.get("latencyMs", 0),
            "truncated": bool(execution.get("truncated")),
            "warnings": _string_list(execution.get("warnings")),
            "notices": _string_list(execution.get("notices")),
            "used_tables": _used_tables(sql or ""),
            "safety_state": _safety_state(safety),
        },
        mode="both",
        priority=20,
        identity=identity,
        produced_by_step="execute_sql",
        depends_on=["sql_candidate", "safety_report"],
    )


def build_chart_artifact(
    chart_suggestion: dict[str, Any],
    *,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None = None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    sql = _execution_sql(execution) if execution else None
    table_sem = "result_table" if not sql else f"result_table_{_sql_fingerprint(sql)}"
    sem_id = "chart_suggestion" if not sql else f"chart_suggestion_{_sql_fingerprint(sql)}"
    chart_type = str(chart_suggestion.get("chart_type") or chart_suggestion.get("type") or "bar").strip().lower()
    return _artifact(
        sem_id,
        "chart",
        "Chart suggestion",
        {
            **chart_suggestion,
            "type": chart_type,
            "chart_type": chart_type,
            "x": chart_suggestion.get("x") or "",
            "y": chart_suggestion.get("y") or "",
            "aggregation": chart_suggestion.get("aggregation") or "",
            "reason": chart_suggestion.get("reason") or "",
            "series": chart_suggestion.get("series") or [],
            "source_refs": _chart_source_refs(chart_suggestion),
            "safety_state": _safety_state(safety),
        },
        mode="inline",
        priority=30,
        identity=identity,
        produced_by_step="suggest_chart",
        depends_on=[table_sem],
    )


def build_error_artifact(
    error: str,
    *,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "agent_error",
        "error",
        "Agent stopped",
        {
            "error": error,
            "recovery_guidance": _recovery_guidance(error, safety, execution),
            "safety_state": _safety_state(safety),
        },
        mode="both",
        priority=1,
        identity=identity,
        produced_by_step="agent_finalize",
        depends_on=["safety_report"],
    )


def _safety_state(safety: dict[str, Any] | None) -> dict[str, Any]:
    if not safety:
        return {"available": False}
    return {
        "available": True,
        "passed": bool(safety.get("passed")),
        "can_execute": bool(safety.get("can_execute")),
        "requires_confirmation": bool(safety.get("requires_confirmation")),
        "guardrail_result": (safety.get("guardrail") or {}).get("result") if isinstance(safety.get("guardrail"), dict) else None,
        "schema_warnings_count": len(safety.get("schema_warnings") or []),
    }


def _execution_meta(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    meta: dict[str, Any] = {}
    if isinstance(value.get("rowCount"), int):
        meta["rowCount"] = value["rowCount"]
    if isinstance(value.get("latencyMs"), int | float):
        meta["latencyMs"] = value["latencyMs"]
    if isinstance(value.get("status"), str):
        meta["execution_status"] = value["status"]
    return meta


def _used_tables(sql: str) -> list[str]:
    tables: list[str] = []
    for match in re.finditer(r"\b(?:from|join)\s+([`\"\[]?[\w.]+[`\"\]]?)", sql, flags=re.IGNORECASE):
        raw = match.group(1).strip("`\"[]")
        table = raw.split(".")[-1]
        if table and table not in tables:
            tables.append(table)
    return tables


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _chart_source_refs(chart_suggestion: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for metric in chart_suggestion.get("metrics") or []:
        if not isinstance(metric, dict):
            continue
        label = str(metric.get("name") or metric.get("label") or metric.get("source_column") or "")
        formula = str(metric.get("expression") or metric.get("formula") or metric.get("source_column") or "")
        field = str(metric.get("source_column") or metric.get("field") or "")
        if label and formula and field:
            refs.append({"label": label, "formula": formula, "field": field})
    for dimension in chart_suggestion.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        field = str(dimension.get("column") or dimension.get("field") or "")
        label = str(dimension.get("name") or dimension.get("label") or field)
        transform = dimension.get("transform")
        formula = f"{transform}({field})" if transform and field else field
        if label and formula and field:
            refs.append({"label": label, "formula": formula, "field": field})
    return refs


def _recovery_guidance(
    error: str,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
) -> str:
    if safety and safety.get("revise_suggestion"):
        return str(safety["revise_suggestion"])
    if execution and execution.get("revise_suggestion"):
        return str(execution["revise_suggestion"])
    if safety and safety.get("requires_confirmation"):
        return "Review the SQL and datasource environment, then rerun after manual confirmation."
    if "max_steps" in error:
        return "Increase max_steps or run a narrower question so the agent can finish validation and synthesis."
    return "Open the trace drawer, review the blocked SQL and safety report, then retry with a narrower question."


def _artifact(
    semantic_id: str,
    artifact_type: str,
    title: str,
    payload: dict[str, Any],
    mode: str,
    priority: int,
    collapsed: bool = False,
    identity: AgentArtifactIdentity | None = None,
    artifact_id: str | None = None,
    produced_by_step: str | None = None,
    depends_on: list[str] | None = None,
) -> AgentArtifact:
    return AgentArtifact(
        id=artifact_id or (identity.next_id(semantic_id) if identity else semantic_id),
        semantic_id=semantic_id,
        type=artifact_type,  # type: ignore[arg-type]
        title=title,
        payload=payload,
        presentation=AgentArtifactPresentation(
            mode=mode,  # type: ignore[arg-type]
            priority=priority,
            collapsed=collapsed,
        ),
        produced_by_step=produced_by_step,
        depends_on=depends_on or [],
    )


def _execution_sql(execution: dict[str, Any] | None) -> str | None:
    if not execution:
        return None
    sql = execution.get("sql") or execution.get("safe_sql") or execution.get("original_sql")
    if not sql:
        return None
    return str(sql).strip()


def _sql_fingerprint(sql: str) -> str:
    import hashlib
    return hashlib.md5(sql.encode("utf-8")).hexdigest()[:8]
