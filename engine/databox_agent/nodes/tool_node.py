from __future__ import annotations

import json
import logging
import time
from typing import Any
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.sandbox.base import ExecutionContext
from engine.agent.types import ToolObservation
from engine.agent.tool_runtime_gateway import ToolRuntimeGateway
from engine.agent.tool_registry import ToolContext
from engine.databox_agent.graph.state import DataBoxAgentState
from engine.databox_agent.tools.tool_aliases import to_internal, to_alias
from engine.databox_agent.environment.dialect_resolver import resolve_datasource_dialect

logger = logging.getLogger("databox.databox_agent.nodes.tool_node")


def _step_name(tool_name: str) -> str:
    step_names = {
        "followup.load_context": "load_follow_up_context",
        "schema.build_context": "build_schema_context",
        "query_plan.build": "build_query_plan",
        "sql.generate": "generate_sql_candidate",
        "sql.validate": "validate_sql",
        "sql.execute_readonly": "execute_sql",
        "sql.skip_execution": "skip_execution",
        "sql.revise": "revise_sql",
        "result.profile": "profile_result",
        "chart.suggest": "suggest_chart",
        "followup.suggest": "suggest_followups",
        "answer.synthesize": "answer_synthesizer",
        "schema.list_tables": "list_tables",
        "schema.describe_table": "describe_table",
        "schema.refresh_catalog": "refresh_catalog",
        "memory.search": "memory_search",
        "memory.write": "memory_write",
        "memory.delete": "memory_delete",
        "memory.summarize_session": "summarize_session",
    }
    return step_names.get(tool_name, tool_name)


def execute_allowed_tools(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable") or {}
    registry = configurable.get("registry")
    db = configurable.get("db")
    req = configurable.get("request")

    allowed_tool_calls = state.get("allowed_tool_calls") or []

    messages = []
    tool_results = []
    trace_events = []

    for call in allowed_tool_calls:
        raw_name = call["name"]
        internal_name = to_internal(raw_name)
        alias_name = to_alias(internal_name)
        args = call["args"] or {}
        call_id = call["id"]

        logger.info("Executing tool %s with args %s", internal_name, args)

        trace_events.append({
            "type": "agent.tool.started",
            "tool_name": internal_name,
        })

        observation = _execute_tool(registry, db, req, state, internal_name, args)

        tool_results.append(observation.model_dump(mode="json"))

        content = _summarize_for_model(internal_name, observation)

        messages.append(
            ToolMessage(
                content=content,
                tool_call_id=call_id,
                name=alias_name,
            )
        )

        trace_events.append({
            "type": "agent.tool.completed",
            "tool_name": internal_name,
            "status": observation.status,
            "latency_ms": observation.latency_ms,
        })

    return {
        "messages": messages,
        "last_tool_results": tool_results,
        "allowed_tool_calls": [],
        "trace_events": trace_events,
    }


def _execute_tool(
    registry: Any,
    db: Any,
    req: Any,
    state: dict[str, Any],
    tool_name: str,
    args: dict[str, Any],
) -> ToolObservation:
    tool = registry.require(tool_name)
    if hasattr(tool, "base_tool") and tool.base_tool is not None:
        merged_args = dict(args)
        if "question" not in merged_args and req is not None:
            merged_args["question"] = req.question
        if "schema_context" not in merged_args:
            merged_args["schema_context"] = state.get("schema_context")
        if "query_plan" not in merged_args:
            merged_args["query_plan"] = state.get("query_plan")
        if "follow_up_context" not in merged_args:
            merged_args["follow_up_context"] = state.get("follow_up_context")
        if "safety" not in merged_args:
            merged_args["safety"] = state.get("safety")
        if "execution" not in merged_args:
            merged_args["execution"] = state.get("execution")
        if "result_profile" not in merged_args:
            merged_args["result_profile"] = state.get("result_profile")
        if "chart_suggestion" not in merged_args:
            merged_args["chart_suggestion"] = state.get("chart_suggestion")
        if "suggestions" not in merged_args:
            merged_args["suggestions"] = state.get("suggestions")
        if "error" not in merged_args:
            merged_args["error"] = state.get("error")
        if "sql" not in merged_args:
            merged_args["sql"] = state.get("sql")

        datasource_id = req.datasource_id if req else ""
        dialect = resolve_datasource_dialect(db, datasource_id) if db else "mysql"
        exec_ctx = ExecutionContext(
            thread_id=str(state.get("thread_id") or state.get("session_id") or ""),
            datasource_id=datasource_id,
            db_dialect=dialect,
            read_only=tool.spec.policy.side_effect != "write",
            db_session=db,
            api_key=req.api_key if req else None,
            api_base=req.api_base if req else None,
            model_name=req.model_name if req else None,
        )
        start_time = time.perf_counter()
        try:
            base_tool = tool.base_tool
            validated_input = base_tool.input_schema.model_validate(merged_args)
            output_model = base_tool.execute(validated_input, exec_ctx)
            output_dict = output_model.model_dump(mode="json")
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            status = "skipped" if tool_name == "sql.skip_execution" else "success"
            obs_name = _step_name(tool_name)
            return ToolObservation(
                name=obs_name,
                status=status,
                input=args,
                output=output_dict,
                error=None,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            obs_name = _step_name(tool_name)
            return ToolObservation(
                name=obs_name,
                status="failed",
                input=args,
                output=None,
                error=str(exc),
                latency_ms=latency_ms,
            )

    ctx_state = dict(state)
    ctx_state["_current_tool_name"] = tool_name
    ctx = ToolContext(db=db, request=req, state=ctx_state)
    validated_args = ToolRuntimeGateway.validate_input(tool.spec.name, tool.spec.input_model, args)
    observation = tool.handler(ctx, validated_args)
    return ToolRuntimeGateway.validate_observation_output(tool.spec.name, tool.spec.output_model, observation)


def _summarize_for_model(tool_name: str, obs: Any) -> str:
    """Produce a concise ToolMessage for the LLM.

    Avoids dumping raw DDL, full result rows, or large JSON blobs
    into the model's context. Each tool type gets a tailored summary.
    """
    if obs.status == "failed":
        return f"[{tool_name}] FAILED: {obs.error or 'Unknown error'}"

    output = obs.output or {}

    if tool_name == "schema.build_context":
        tables = output.get("selected_tables") or output.get("candidate_tables") or []
        count = output.get("selected_schema_table_count", len(tables))
        return (
            f"[schema.build_context] OK. Selected {count} table(s): {', '.join(str(t) for t in tables[:10])}. "
            f"Schema context ready for query planning or SQL generation."
        )

    if tool_name == "query_plan.build":
        goal = output.get("analysis_goal", "")
        metrics = output.get("metrics") or []
        dims = output.get("dimensions") or []
        tables = output.get("candidate_tables") or []
        return (
            f"[query_plan.build] OK. Goal: {goal}. "
            f"Metrics: {len(metrics)}, Dimensions: {len(dims)}, Tables: {', '.join(str(t) for t in tables[:8])}."
        )

    if tool_name == "sql.generate":
        sql = output.get("sql") or ""
        preview = sql[:300] + ("..." if len(sql) > 300 else "")
        return f"[sql.generate] OK.\n```sql\n{preview}\n```"

    if tool_name == "sql.validate":
        can_exec = output.get("can_execute", False)
        requires = output.get("requires_confirmation", False)
        blocked = output.get("blocked_reasons") or []
        safe = output.get("safe_sql") or ""
        parts = [f"[sql.validate] can_execute={can_exec}, requires_confirmation={requires}"]
        if blocked:
            parts.append(f"blocked_reasons={blocked}")
        if safe:
            parts.append(f"safe_sql={safe[:200]}")
        return " ".join(parts)

    if tool_name == "sql.execute_readonly":
        success = output.get("success", False)
        row_count = output.get("rowCount", 0)
        columns = output.get("columns") or []
        return (
            f"[sql.execute_readonly] success={success}, "
            f"rows={row_count}, columns={', '.join(str(c) for c in columns[:15])}"
        )

    if tool_name == "sql.revise":
        can_fix = output.get("can_fix", False)
        fixed = output.get("fixed_sql", "")
        reason = output.get("reason", "")
        if not can_fix:
            return (
                f"[sql.revise] can_fix=False. The SQL validator rejected this query "
                f"and it CANNOT be automatically fixed. DO NOT call sql.revise again. "
                f"Instead, either generate a completely new SQL with sql.generate, "
                f"or explain the issue to the user and finalize. "
                f"Reason: {reason}"
            )
        preview = fixed[:200] + ("..." if len(fixed) > 200 else "") if fixed else ""
        return f"[sql.revise] can_fix=True, reason={reason}" + (f"\n```sql\n{preview}\n```" if preview else "")

    if tool_name == "result.profile":
        row_count = output.get("row_count", 0)
        facts = output.get("notable_facts") or []
        anomalies = output.get("anomalies") or []
        return (
            f"[result.profile] OK. rows={row_count}, "
            f"notable_facts={facts[:5]}, anomalies={anomalies[:3]}"
        )

    if tool_name == "chart.suggest":
        chart_type = output.get("type", "unknown")
        x_col = output.get("x", "")
        y_col = output.get("y", "")
        reason = output.get("reason", "")
        return f"[chart.suggest] type={chart_type}, x={x_col}, y={y_col}, reason={reason}"

    if tool_name == "answer.synthesize":
        answer_text = output.get("answer", "")
        return f"[answer.synthesize] {answer_text[:500]}"

    if tool_name == "followup.suggest":
        suggestions = output.get("suggestions") or []
        return f"[followup.suggest] {len(suggestions)} suggestion(s) generated."

    if tool_name.startswith("workspace."):
        answer = output.get("answer", "")
        proposed = output.get("proposed_sql", "")
        parts = [f"[{tool_name}] {answer[:300]}"]
        if proposed:
            parts.append(f"proposed_sql={proposed[:200]}")
        return " ".join(parts)

    if tool_name == "schema.list_tables":
        tables = output.get("tables") or []
        names = [t.get("table_name", "") for t in tables[:20]]
        return f"[schema.list_tables] {len(tables)} table(s): {', '.join(names)}"

    if tool_name == "schema.describe_table":
        cols = output.get("columns") or []
        col_names = [c.get("column_name", "") for c in cols[:20]]
        return f"[schema.describe_table] {output.get('table_name', '?')}: {len(cols)} column(s): {', '.join(col_names)}"

    if tool_name == "schema.refresh_catalog":
        return (
            f"[schema.refresh_catalog] synced={output.get('synced')}, "
            f"tables_created={output.get('tables_created')}, "
            f"columns_created={output.get('columns_created')}"
        )

    if tool_name == "memory.search":
        memories = output.get("memories") or []
        lines = [f"[memory.search] {len(memories)} result(s):"]
        for m in memories[:5]:
            lines.append(f"  [{m.get('type')}] {m.get('text', '')[:120]}")
        return "\n".join(lines)

    if tool_name == "memory.write":
        return f"[memory.write] {output.get('type')} → {output.get('status')} (id={output.get('memory_id', '?')})"

    if tool_name == "memory.delete":
        return f"[memory.delete] deleted={output.get('deleted')}"

    if tool_name == "memory.summarize_session":
        return f"[memory.summarize_session] {output.get('summary', '')[:300]}"

    # Generic fallback — compact JSON without huge data
    compact: dict[str, Any] = {}
    for k, v in (output if isinstance(output, dict) else {}).items():
        if isinstance(v, str) and len(v) > 200:
            compact[k] = v[:200] + "..."
        elif isinstance(v, list) and len(v) > 5:
            compact[k] = v[:5]
        else:
            compact[k] = v
    return f"[{tool_name}] OK. {json.dumps(compact, ensure_ascii=False, default=str)[:600]}"
