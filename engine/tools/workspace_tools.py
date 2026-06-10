from __future__ import annotations

import re
import time
from typing import Any, Callable

from engine.agent_core.registry import AgentToolContext, FunctionAgentTool, ToolSpec
from engine.tools.sql_tools import _prepare_generated_sql, validate_sql_tool
from engine.agent_core.types import ToolObservation
from engine.sql.guardrail import guardrail_check


WorkspaceBody = Callable[[], dict[str, Any]]
WORKSPACE_TOOL_NAMES = [
    "workspace.explain_sql",
    "workspace.fix_sql",
    "workspace.optimize_sql",
    "workspace.rewrite_sql",
    "workspace.explain_result",
    "workspace.continue_from_artifact",
    "workspace.explain_schema",
]


def build_workspace_tools() -> list[FunctionAgentTool]:
    return [
        _tool("workspace.explain_sql", "Explain the current SQL without executing it.", _explain_sql),
        _tool("workspace.fix_sql", "Suggest a safe read-only fix for the current SQL error.", _fix_sql),
        _tool("workspace.optimize_sql", "Suggest a safer or more efficient read-only SQL rewrite.", _optimize_sql),
        _tool("workspace.rewrite_sql", "Rewrite the current SQL for clarity without execution.", _rewrite_sql),
        _tool("workspace.explain_result", "Explain the latest result preview without executing SQL.", _explain_result),
        _tool("workspace.continue_from_artifact", "Continue from a selected Agent artifact.", _continue_from_artifact),
        _tool("workspace.explain_schema", "Explain selected or linked schema context.", _explain_schema),
    ]


def _tool(name: str, description: str, handler: Callable[[dict[str, Any], AgentToolContext], ToolObservation]) -> FunctionAgentTool:
    return FunctionAgentTool(
        spec=ToolSpec(
            name=name,
            description=description,
            risk_level="safe",
            requires_approval=False,
            idempotent=True,
        ),
        handler=handler,
    )


def _explain_sql(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.explain_sql", _tool_input(input, ctx), lambda: _sql_answer(ctx, "explain_sql"))


def _fix_sql(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.fix_sql", _tool_input(input, ctx), lambda: _sql_answer(ctx, "fix_sql"))


def _optimize_sql(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.optimize_sql", _tool_input(input, ctx), lambda: _sql_answer(ctx, "optimize_sql"))


def _rewrite_sql(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.rewrite_sql", _tool_input(input, ctx), lambda: _sql_answer(ctx, "rewrite_sql"))


def _explain_result(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.explain_result", _tool_input(input, ctx), lambda: _result_answer(input, ctx))


def _continue_from_artifact(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.continue_from_artifact", _tool_input(input, ctx), lambda: _artifact_answer(input, ctx))


def _explain_schema(input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
    return _observe("workspace.explain_schema", _tool_input(input, ctx), lambda: _schema_answer(input, ctx))


def _sql_answer(ctx: AgentToolContext, intent: str) -> dict[str, Any]:
    workspace = ctx.request.workspace_context
    sql = _active_sql(ctx)
    last_error = str(workspace.last_error or "").strip() if workspace else ""
    context_summary = _context_summary(ctx)
    safety_notes: list[str] = []
    suggestions: list[dict[str, Any]] = []

    if not sql:
        return _workspace_payload(
            intent=intent,
            answer="I need an active SQL editor selection before I can help with this SQL.",
            suggestions=[],
            context_summary=context_summary,
            safety_notes=["No SQL was supplied in workspace context."],
        )

    proposed_sql = _proposed_sql(ctx, sql, intent)
    warnings: list[str] = []
    if proposed_sql:
        validation = _validate_proposed_sql(ctx, proposed_sql)
        warnings = validation["warnings"]
        if validation["accepted"]:
            suggestions.append(
                {
                    "id": f"{intent}_apply",
                    "title": _suggestion_title(intent),
                    "explanation": _suggestion_explanation(intent, last_error),
                    "proposed_sql": validation["safe_sql"] or proposed_sql,
                    "action": "apply_to_editor",
                    "confidence": "medium",
                    "warnings": warnings,
                }
            )
        else:
            safety_notes.extend(warnings or ["The proposed SQL did not pass read-only guardrails."])

    answer = _sql_explanation(sql, intent, last_error, bool(suggestions))
    return _workspace_payload(
        intent=intent,
        answer=answer,
        suggestions=suggestions,
        context_summary=context_summary,
        safety_notes=safety_notes,
    )


def _result_answer(input: dict[str, Any], ctx: AgentToolContext) -> dict[str, Any]:
    bundle = _bundle(input)
    workspace = ctx.request.workspace_context
    workspace_bundle_value = bundle.get("workspace")
    workspace_bundle: dict[str, Any] = workspace_bundle_value if isinstance(workspace_bundle_value, dict) else {}
    preview = workspace_bundle.get("last_query_result_preview")
    if not isinstance(preview, dict) and workspace:
        preview = workspace.last_query_result_preview
    columns_value = preview.get("columns") if isinstance(preview, dict) else []
    rows_value = preview.get("rows") if isinstance(preview, dict) else []
    columns: list[Any] = columns_value if isinstance(columns_value, list) else []
    rows: list[Any] = rows_value if isinstance(rows_value, list) else []
    row_count = preview.get("rowCount", len(rows)) if isinstance(preview, dict) else 0
    answer = (
        f"The latest result preview has {row_count} rows across {len(columns)} columns"
        f"{': ' + ', '.join(str(column) for column in columns[:8]) if columns else ''}. "
        "I am only using the preview already in the workspace; no query was executed."
    )
    return _workspace_payload(
        intent="explain_result",
        answer=answer,
        suggestions=[],
        context_summary=_context_summary(ctx),
        safety_notes=["Result explanation used the supplied preview only."],
    )


def _artifact_answer(input: dict[str, Any], ctx: AgentToolContext) -> dict[str, Any]:
    bundle = _bundle(input)
    artifact_value = bundle.get("selected_artifact")
    artifact: dict[str, Any] | None = artifact_value if isinstance(artifact_value, dict) else None
    payload_value = artifact.get("payload") if artifact else None
    payload: dict[str, Any] = payload_value if isinstance(payload_value, dict) else {}
    sql = _sql_from_payload(payload)
    suggestions: list[dict[str, Any]] = []
    safety_notes: list[str] = []
    if sql:
        validation = _validate_proposed_sql(ctx, sql)
        if validation["accepted"]:
            suggestions.append(
                {
                    "id": "continue_from_artifact_apply",
                    "title": "Apply artifact SQL",
                    "explanation": "Use the selected artifact SQL as an editor draft.",
                    "proposed_sql": validation["safe_sql"] or sql,
                    "action": "apply_to_editor",
                    "confidence": "medium",
                    "warnings": validation["warnings"],
                }
            )
        else:
            safety_notes.extend(validation["warnings"])
    title = artifact.get("title") if isinstance(artifact, dict) else None
    answer = (
        f"I found the selected artifact `{title or 'artifact'}` and prepared safe next-step context."
        if artifact
        else "No selected artifact payload was available in the workspace context."
    )
    return _workspace_payload(
        intent="continue_from_artifact",
        answer=answer,
        suggestions=suggestions,
        context_summary=_context_summary(ctx),
        safety_notes=safety_notes,
    )


def _schema_answer(input: dict[str, Any], ctx: AgentToolContext) -> dict[str, Any]:
    bundle = _bundle(input)
    tables_value = bundle.get("selected_table_schema")
    linking_value = bundle.get("schema_linking")
    tables: list[Any] = tables_value if isinstance(tables_value, list) else []
    linking: dict[str, Any] = linking_value if isinstance(linking_value, dict) else {}
    selected_names_value = linking.get("selected_tables")
    selected_names = [str(item) for item in selected_names_value] if isinstance(selected_names_value, list) else []
    table_names = [
        str(table.get("name"))
        for table in tables
        if isinstance(table, dict) and table.get("name")
    ] or selected_names
    suggestions: list[dict[str, Any]] = []
    if tables and isinstance(tables[0], dict):
        candidate = _select_from_table(tables[0])
        if candidate:
            validation = _validate_proposed_sql(ctx, candidate)
            if validation["accepted"]:
                suggestions.append(
                    {
                        "id": "explain_schema_select",
                        "title": "Open table preview SQL",
                        "explanation": "Draft a read-only preview query for the selected table.",
                        "proposed_sql": validation["safe_sql"] or candidate,
                        "action": "apply_to_editor",
                        "confidence": "medium",
                        "warnings": validation["warnings"],
                    }
                )
    answer = (
        f"Selected schema context is focused on {', '.join(table_names[:6])}. "
        "Use the listed columns and semantic aliases as grounding for follow-up SQL drafts."
        if table_names
        else "No selected table schema was available; I used the compressed schema-linking context instead."
    )
    return _workspace_payload(
        intent="explain_schema",
        answer=answer,
        suggestions=suggestions,
        context_summary=_context_summary(ctx),
        safety_notes=["Schema assistance did not execute SQL."],
    )


def _proposed_sql(ctx: AgentToolContext, sql: str, intent: str) -> str | None:
    cleaned = _strip_editor_annotations(sql).strip().rstrip(";")
    if not cleaned:
        return None
    if intent == "explain_sql":
        return cleaned
    if intent == "fix_sql":
        fixed, _notes, _metadata = _prepare_generated_sql(ctx.db, ctx.request.datasource_id, cleaned)
        return fixed or cleaned
    if intent == "optimize_sql":
        optimized = _normalize_sql(cleaned)
        if not re.search(r"\blimit\s+\d+\b", optimized, flags=re.IGNORECASE):
            optimized = f"{optimized} LIMIT 100"
        fixed, _notes, _metadata = _prepare_generated_sql(ctx.db, ctx.request.datasource_id, optimized)
        return fixed or optimized
    if intent == "rewrite_sql":
        rewritten = _normalize_sql(cleaned)
        fixed, _notes, _metadata = _prepare_generated_sql(ctx.db, ctx.request.datasource_id, rewritten)
        return fixed or rewritten
    return cleaned


def _validate_proposed_sql(ctx: AgentToolContext, sql: str) -> dict[str, Any]:
    guardrail = guardrail_check(sql)
    warnings = [str(item.get("message")) for item in guardrail.get("checks", []) if item.get("message")]
    if guardrail["result"] == "reject":
        return {"accepted": False, "safe_sql": None, "warnings": warnings or [guardrail["message"]]}
    validation = validate_sql_tool(ctx.db, ctx.request.datasource_id, guardrail.get("safeSql") or sql)
    output = validation.output or {}
    if validation.status == "failed" or not output.get("can_execute"):
        reason = validation.error or output.get("revise_suggestion") or "SQL did not pass schema/read-only validation."
        return {"accepted": False, "safe_sql": None, "warnings": warnings + [str(reason)]}
    safe_sql = str(output.get("safe_sql") or guardrail.get("safeSql") or sql)
    return {"accepted": True, "safe_sql": safe_sql, "warnings": warnings}


def _workspace_payload(
    *,
    intent: str,
    answer: str,
    suggestions: list[dict[str, Any]],
    context_summary: str,
    safety_notes: list[str],
) -> dict[str, Any]:
    proposed_sql = ""
    for suggestion in suggestions:
        proposed_sql = str(suggestion.get("proposed_sql") or "").strip()
        if proposed_sql:
            break
    return {
        "intent": intent,
        "answer": answer,
        "suggestions": suggestions,
        "proposed_sql": proposed_sql or None,
        "context_summary": context_summary,
        "safety_notes": safety_notes,
    }


def _tool_input(input: dict[str, Any], ctx: AgentToolContext) -> dict[str, Any]:
    return {
        "intent": input.get("intent"),
        "datasource_id": ctx.request.datasource_id,
        "has_workspace_context": bool(ctx.request.workspace_context),
        "has_context_bundle": isinstance(input.get("context_bundle"), dict),
    }


def _observe(name: str, tool_input: dict[str, Any], body: WorkspaceBody) -> ToolObservation:
    start = time.perf_counter()
    try:
        return ToolObservation(
            name=name,
            status="success",
            input=tool_input,
            output=body(),
            error=None,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception as exc:
        return ToolObservation(
            name=name,
            status="failed",
            input=tool_input,
            output=None,
            error=str(exc),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


def _active_sql(ctx: AgentToolContext) -> str:
    workspace = ctx.request.workspace_context
    if workspace is None:
        return ""
    return str(workspace.selected_sql or workspace.active_sql or "").strip()


def _bundle(input: dict[str, Any]) -> dict[str, Any]:
    bundle = input.get("context_bundle")
    return bundle if isinstance(bundle, dict) else {}


def _context_summary(ctx: AgentToolContext) -> str:
    workspace = ctx.request.workspace_context
    if workspace is None:
        return "No workspace context was supplied."
    pieces = []
    if workspace.active_sql or workspace.selected_sql:
        pieces.append("active SQL")
    if workspace.last_query_result_preview:
        pieces.append("last result")
    if workspace.last_error:
        pieces.append("last error")
    if workspace.selected_table_names:
        pieces.append(f"selected table: {', '.join(workspace.selected_table_names[:4])}")
    if workspace.selected_artifact_id:
        pieces.append(f"selected artifact: {workspace.selected_artifact_id}")
    return "; ".join(pieces) or "Workspace context was supplied."


def _sql_explanation(sql: str, intent: str, last_error: str, has_suggestion: bool) -> str:
    compact = _normalize_sql(sql)
    table_refs = sorted(set(re.findall(r"\bfrom\s+([`\w.]+)|\bjoin\s+([`\w.]+)", compact, flags=re.IGNORECASE)))
    flattened_tables = [item for pair in table_refs for item in pair if item]
    table_text = f" It references {', '.join(flattened_tables[:6])}." if flattened_tables else ""
    if intent == "fix_sql":
        return (
            f"I reviewed the active SQL against the last error: {last_error or 'no explicit error message'}."
            f"{table_text} {'A guarded editor suggestion is ready.' if has_suggestion else 'I could not produce a guarded editor suggestion.'}"
        )
    if intent == "optimize_sql":
        return f"I reviewed the SQL for a safer read-only editor draft.{table_text} The suggestion keeps execution disabled."
    if intent == "rewrite_sql":
        return f"I rewrote the SQL as an editor-only draft with normalized formatting.{table_text}"
    return f"I can explain this SQL without executing it.{table_text} Review the draft in the editor before running anything."


def _suggestion_title(intent: str) -> str:
    return {
        "explain_sql": "Keep SQL in editor",
        "fix_sql": "Apply fixed SQL",
        "optimize_sql": "Apply optimized SQL",
        "rewrite_sql": "Apply rewritten SQL",
    }.get(intent, "Apply SQL")


def _suggestion_explanation(intent: str, last_error: str) -> str:
    if intent == "fix_sql":
        return f"Drafted from the active SQL and last error: {last_error or 'not supplied'}."
    if intent == "optimize_sql":
        return "Adds safe normalization such as a LIMIT when missing and keeps the query read-only."
    if intent == "rewrite_sql":
        return "Normalizes the query text for review in the SQL editor."
    return "Copies the current SQL into the editor for manual review."


def _select_from_table(table: dict[str, Any]) -> str:
    table_name = str(table.get("name") or "").strip()
    columns_value = table.get("columns")
    columns: list[Any] = columns_value if isinstance(columns_value, list) else []
    column_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("name")
    ][:12]
    if not table_name or not column_names:
        return ""
    return f"SELECT {', '.join(column_names)} FROM {table_name} LIMIT 100"


def _sql_from_payload(payload: dict[str, Any]) -> str:
    for key in ("proposed_sql", "sql", "safe_sql"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    suggestions = payload.get("suggestions")
    if isinstance(suggestions, list):
        for suggestion in suggestions:
            if isinstance(suggestion, dict) and isinstance(suggestion.get("proposed_sql"), str):
                return str(suggestion["proposed_sql"]).strip()
    return ""


def _strip_editor_annotations(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not re.match(r"\s*@", line))


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().rstrip(";")
