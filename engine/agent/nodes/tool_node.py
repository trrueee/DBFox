from __future__ import annotations

import json
import logging
from typing import Any, Callable
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from engine.agent_core.types import ToolObservation
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.tools.tool_aliases import to_internal, to_alias
from engine.tools.runtime.runtime import ToolRuntime

logger = logging.getLogger("dbfox.dbfox_agent.nodes.tool_node")

def execute_allowed_tools(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = graph_context(config)
    registry = ctx.registry
    db = ctx.db
    req = ctx.request

    allowed_tool_calls = state.get("allowed_tool_calls") or []

    messages = []
    tool_results = []
    trace_events = []
    emit_answer_delta = _answer_delta_writer()

    for call in allowed_tool_calls:
        raw_name = call["name"]
        internal_name = to_internal(raw_name)
        alias_name = to_alias(internal_name)
        args = call["args"] or {}
        call_id = call["id"]

        logger.info("Executing tool %s", internal_name)

        trace_events.append({
            "type": "agent.tool.started",
            "tool_name": internal_name,
        })

        observation = _execute_tool(
            registry, db, req, state, internal_name, args,
            emit_answer_delta=emit_answer_delta,
        )

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
            "input": observation.input,
            "output": observation.output,
            "error": observation.error,
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
    *,
    emit_answer_delta: Callable[[str], None] | None = None,
) -> ToolObservation:
    """Execute a single tool call through the typed ToolRuntime."""
    logger.debug(
        "[DEBUG TOOL] tool_name=%s, state.get('safety')=%s, state.get('execute')=%s",
        tool_name, state.get("safety"), state.get("execute"),
    )
    return ToolRuntime(registry).invoke(
        tool_name=tool_name,
        raw_input=args,
        state=dict(state),
        request=req,
        db=db,
        emit_answer_delta=emit_answer_delta,
    )


def _answer_delta_writer() -> Callable[[str], None] | None:
    try:
        from langgraph.config import get_stream_writer

        stream_writer = get_stream_writer()
    except Exception:
        return None

    def emit(content: str) -> None:
        if content:
            stream_writer({"type": "agent.answer.delta", "content": content})

    return emit


# ---------------------------------------------------------------------------
# Tool observation summarizers — one function per tool type.
#
# Each summarizer produces a concise, LLM-facing string from a tool's output
# dict, avoiding dumping raw DDL / full result rows / large JSON into context.
# Registered in _SUMMARIZERS below and dispatched by tool_name.
# ---------------------------------------------------------------------------

_Summarizer = Callable[[dict[str, Any]], str]


def _summarize_sql_validate(output: dict[str, Any]) -> str:
    can_exec = output.get("can_execute", False)
    requires = output.get("requires_confirmation", False)
    blocked = output.get("blocked_reasons") or []
    safe = output.get("safe_sql") or ""
    parts = [f"[sql.validate] can_execute={can_exec}, requires_confirmation={requires}"]
    if blocked:
        parts.append(f"blocked_reasons={blocked}")
    if safe:
        parts.append(f"safe_sql={safe[:200]}")
    if can_exec and not requires:
        parts.append("NEXT: call sql.execute_readonly without passing SQL text.")
    if requires:
        parts.append("→ NEXT: wait for user approval before executing.")
    return " ".join(parts)


def _summarize_sql_execute_readonly(output: dict[str, Any]) -> str:
    success = output.get("success", False)
    row_count = output.get("rowCount", 0)
    columns = output.get("columns") or []
    return (
        f"[sql.execute_readonly] success={success}, "
        f"rows={row_count}, columns={', '.join(str(c) for c in columns[:15])}"
    )


def _summarize_chart_suggest(output: dict[str, Any]) -> str:
    chart_type = output.get("type", "unknown")
    x_col = output.get("x", "")
    y_col = output.get("y", "")
    reason = output.get("reason", "")
    return f"[chart.suggest] type={chart_type}, x={x_col}, y={y_col}, reason={reason}"


def _summarize_schema_list_tables(output: dict[str, Any]) -> str:
    tables = output.get("tables") or []
    names = [t.get("table_name", "") for t in tables[:20]]
    return f"[schema.list_tables] {len(tables)} table(s): {', '.join(names)}"


def _summarize_schema_describe_table(output: dict[str, Any]) -> str:
    cols = output.get("columns") or []
    col_names = [c.get("column_name", "") for c in cols[:20]]
    return f"[schema.describe_table] {output.get('table_name', '?')}: {len(cols)} column(s): {', '.join(col_names)}"


def _summarize_schema_list_tables_page(output: dict[str, Any]) -> str:
    p = output.get("page") or {}
    tables = output.get("tables") or []
    names = [t.get("table_name", "") for t in tables[:15]]
    return (
        f"[schema.list_tables_page] page {p.get('offset', 0)}-{p.get('offset', 0) + len(tables)} "
        f"of {p.get('total', '?')} (has_more={p.get('has_more', False)}): "
        f"{', '.join(names)}"
    )


def _summarize_schema_expand_related(output: dict[str, Any]) -> str:
    seed = output.get("seed_table") or {}
    related = output.get("related_tables") or []
    names = [r.get("table_name", "") for r in related[:15]]
    return (
        f"[schema.expand_related_tables] {seed.get('table_name', '?')} → "
        f"{len(related)} related: {', '.join(names)}"
    )


def _summarize_schema_refresh_catalog(output: dict[str, Any]) -> str:
    return (
        f"[schema.refresh_catalog] synced={output.get('synced')}, "
        f"tables_created={output.get('tables_created')}, "
        f"columns_created={output.get('columns_created')}"
    )


def _summarize_db_observe(output: dict[str, Any]) -> str:
    table_count = output.get("table_count", 0)
    mode = output.get("mode", "full")
    domains = output.get("domains") or []
    domain_names = [d.get("name") for d in domains[:8]]
    if mode == "summary":
        hint = output.get("next_action_hint", "")
        hint_short = hint[:200] + "..." if len(hint) > 200 else hint
        return (
            f"[db.observe] LARGE CATALOG ({table_count} tables). "
            f"Domains: {domain_names}. {hint_short}"
        )
    schemas = output.get("schemas") or []
    return (
        f"[db.observe] {table_count} table(s), "
        f"schemas={len(schemas)}, domains={domain_names}."
    )


def _summarize_db_search(output: dict[str, Any]) -> str:
    results = output.get("results") or []
    parts = []
    for item in results[:8]:
        parts.append(
            f"{item.get('name')} ({item.get('type')}, score={item.get('score')}, "
            f"reasons={','.join(item.get('reasons') or [])})"
        )
    return f"[db.search] {len(results)} result(s): " + "; ".join(parts)


def _summarize_db_inspect(output: dict[str, Any]) -> str:
    if output.get("object_type") == "column":
        fk = output.get("foreign_key") or {}
        fk_text = f", fk={fk.get('table')}.{fk.get('column')}" if fk else ""
        return (
            f"[db.inspect] column {output.get('table')}.{output.get('name')} "
            f"type={output.get('type')}, nullable={output.get('nullable')}{fk_text}"
        )
    columns = output.get("columns") or []
    fks = output.get("foreign_keys") or []
    indexes = output.get("indexes") or []
    col_names = [c.get("name", "") for c in columns[:20]]
    return (
        f"[db.inspect] table {output.get('name')}: {len(columns)} column(s), "
        f"fks={len(fks)}, indexes={len(indexes)}. Columns: {', '.join(col_names)}"
    )


def _summarize_db_preview(output: dict[str, Any]) -> str:
    rows = output.get("rows") or []
    columns = output.get("columns") or []
    return (
        f"[db.preview] table={output.get('table')}, rows={len(rows)}, "
        f"columns={', '.join(str(c) for c in columns[:15])}. "
        f"Sample={json.dumps(rows[:3], ensure_ascii=False, default=str)[:500]}"
    )


def _summarize_db_query(output: dict[str, Any]) -> str:
    rows = output.get("rows") or []
    columns = output.get("columns") or []
    return (
        f"[db.query] status={output.get('status')}, rows={output.get('returned_rows')}, "
        f"columns={', '.join(str(c) for c in columns[:15])}. "
        f"Sample={json.dumps(rows[:5], ensure_ascii=False, default=str)[:700]}"
    )


def _summarize_default(output: dict[str, Any]) -> str:
    """Generic fallback — compact JSON without huge data."""
    compact: dict[str, Any] = {}
    for k, v in output.items():
        if isinstance(v, str) and len(v) > 200:
            compact[k] = v[:200] + "..."
        elif isinstance(v, list) and len(v) > 5:
            compact[k] = v[:5]
        else:
            compact[k] = v
    return json.dumps(compact, ensure_ascii=False, default=str)[:600]


_SUMMARIZERS: dict[str, _Summarizer] = {
    # ── Active tools (tool-layer-v2) ──
    "chart.suggest": _summarize_chart_suggest,
    "schema.list_tables": _summarize_schema_list_tables,
    "schema.list_tables_page": _summarize_schema_list_tables_page,
    "schema.expand_related_tables": _summarize_schema_expand_related,
    "schema.describe_table": _summarize_schema_describe_table,
    "schema.refresh_catalog": _summarize_schema_refresh_catalog,
    "db.observe": _summarize_db_observe,
    "db.search": _summarize_db_search,
    "db.inspect": _summarize_db_inspect,
    "db.preview": _summarize_db_preview,
    "db.query": _summarize_db_query,
    "sql.validate": _summarize_sql_validate,
    "sql.execute_readonly": _summarize_sql_execute_readonly,
}


def _summarize_for_model(tool_name: str, obs: Any) -> str:
    """Produce a concise ToolMessage for the LLM.

    Avoids dumping raw DDL, full result rows, or large JSON blobs
    into the model's context. Each tool type gets a tailored summary
    via the _SUMMARIZERS dispatch table; unknown tools fall back to a
    compact JSON dump.
    """
    if obs.status == "failed":
        return f"[{tool_name}] FAILED: {obs.error or 'Unknown error'}"

    output = obs.output or {}
    if not isinstance(output, dict):
        output = {}
    summarizer = _SUMMARIZERS.get(tool_name)
    if summarizer is not None:
        return summarizer(output)
    return f"[{tool_name}] OK. {_summarize_default(output)}"
