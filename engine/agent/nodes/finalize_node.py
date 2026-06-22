from __future__ import annotations

import logging
from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.message_utils import first_user_text, is_ai_message, message_content_text, message_tool_calls

logger = logging.getLogger("dbfox.dbfox_agent.nodes.finalize_node")


def finalize_answer(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Finalize the agent run — mark status, persist, write trajectory."""

    messages = state.get("messages", [])
    error = state.get("error")
    pending_approval = state.get("pending_approval")
    terminal_failed = state.get("status") == "failed"

    existing_answer = state.get("answer")
    answer_dict = existing_answer if isinstance(existing_answer, dict) else {}
    has_answer = bool(answer_dict.get("answer") or "")
    had_error_before_finalize = bool(error)

    if not has_answer and not terminal_failed:
        for msg in reversed(messages):
            if is_ai_message(msg) and not message_tool_calls(msg):
                content = message_content_text(msg)
                if content:
                    answer_dict = {
                        "answer": content,
                        "key_findings": [],
                        "caveats": [],
                        "recommendations": [],
                        "follow_up_questions": [],
                    }
                    has_answer = True
                    break

    if pending_approval:
        status = "waiting_approval"
    elif has_answer:
        status = "completed"
        if had_error_before_finalize:
            answer_dict.setdefault("caveats", []).append(
                "部分后续检查未完成，结果可能不完整。"
            )
        error = None
    elif error:
        status = "failed"
    else:
        status = "failed"
        if not error:
            error = "Agent completed without producing an answer."

    # Ensure answer has evidence from analysis_units if missing
    if has_answer and not answer_dict.get("evidence"):
        artifact_evidence = _build_artifact_evidence(state.get("artifacts") or [])
        if artifact_evidence:
            answer_dict["evidence"] = artifact_evidence
        else:
            from engine.agent_core.answer import _build_evidence
            units = state.get("analysis_units") or []
            answer_dict["evidence"] = [
                ev.model_dump() for ev in _build_evidence(units)
            ]

    trace_event: dict[str, Any] = {
        "type": "agent.finalized",
        "status": status,
        "has_answer": has_answer,
        "has_error": had_error_before_finalize,
    }

    _auto_write_trajectory(state, status, str(answer_dict.get("answer") or ""))

    result: dict[str, Any] = {
        "status": status,
        "answer": answer_dict,
        "final_answer": answer_dict,
        "error": error,
        "trace_events": [trace_event],
        "agent_graph_route": "end",
    }

    if status == "failed" and error:
        error_artifact = _build_and_persist_error_artifact(state, config, str(error))
        if error_artifact is not None:
            result["artifacts"] = [error_artifact]

    return result


def _build_artifact_evidence(artifacts: list[Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    sql_count = 0
    result_count = 0
    for artifact in artifacts:
        artifact_type = _artifact_field(artifact, "type")
        artifact_id = _artifact_field(artifact, "semantic_id") or _artifact_field(artifact, "id")
        if not artifact_id:
            continue
        if artifact_type in {"sql", "sql_suggestion"}:
            sql_count += 1
            evidence.append({"artifact_id": artifact_id, "label": f"SQL #{sql_count}", "value": None})
            continue
        if artifact_type in {"result_view", "table"}:
            result_count += 1
            payload = _artifact_payload(artifact)
            row_count = _payload_number(payload, "rowCount", "row_count", "returnedRows", "returned_rows")
            label = f"结果 {row_count} 行" if row_count is not None else f"结果 #{result_count}"
            evidence.append({"artifact_id": artifact_id, "label": label, "value": row_count})
    return evidence


def _artifact_field(artifact: Any, key: str) -> str:
    if isinstance(artifact, dict):
        value = artifact.get(key)
    else:
        value = getattr(artifact, key, None)
    return str(value) if value else ""


def _artifact_payload(artifact: Any) -> dict[str, Any]:
    if isinstance(artifact, dict):
        payload = artifact.get("payload")
    else:
        payload = getattr(artifact, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _payload_number(payload: dict[str, Any], *keys: str) -> int | float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    pass
    return None


def _build_and_persist_error_artifact(
    state: DBFoxAgentState,
    config: RunnableConfig,
    error: str,
) -> dict[str, Any] | None:
    """Emit the terminal `agent_error` artifact for failed runs.

    Gives the frontend a structured error card with recovery guidance and the
    safety state at the moment of failure. Best-effort persistence to DB.
    """
    existing = state.get("artifacts") or []
    for item in existing:
        sem_id = item.get("semantic_id") if isinstance(item, dict) else getattr(item, "semantic_id", None)
        if sem_id == "agent_error":
            return None

    try:
        from engine.agent_core.artifacts import AgentArtifactIdentity, build_error_artifact

        run_id = str(state.get("run_id") or "")
        artifact = build_error_artifact(
            error,
            safety=state.get("safety"),
            execution=state.get("execution"),
            identity=AgentArtifactIdentity(run_id),
        )
    except Exception as exc:
        logger.warning("Failed to build error artifact: %s", exc)
        return None

    try:
        from engine.agent.graph.context import graph_context
        from engine.agent_core import persistence as ap
        from engine.models import AgentArtifactRecord

        db = graph_context(config).db
        if db is not None:
            run_id = str(state.get("run_id") or "")
            thread_id = str(state.get("thread_id") or run_id)
            existing_count = db.query(AgentArtifactRecord).filter(
                AgentArtifactRecord.run_id == run_id
            ).count()
            ap.record_artifact(db, thread_id, run_id, artifact, sequence=existing_count + 1)
    except Exception as exc:
        logger.warning("Failed to save error artifact to DB: %s", exc)

    return artifact.model_dump(mode="json")


def _auto_write_trajectory(
    state: DBFoxAgentState,
    status: str,
    answer_text: str,
) -> None:
    """Auto-write trajectory + learnings to long-term memory on run completion.

    Best-effort — failures are logged but never block finalization.
    """
    import logging
    _logger = logging.getLogger("dbfox.dbfox_agent.nodes.finalize_node")

    try:
        from engine.agent.memory_bridge import write_trajectory

        # Extract user question from first message
        messages = state.get("messages", [])
        question = first_user_text(messages)

        # Extract tables from schema context
        schema_ctx = state.get("schema_context")
        tables: list[str] = []
        if isinstance(schema_ctx, dict):
            tables = schema_ctx.get("selected_tables") or []

        # Extract tools used from trace events
        trace_events = state.get("trace_events") or []
        tools_used: list[str] = []
        for te in trace_events:
            if isinstance(te, dict) and te.get("type") == "agent.tool.completed":
                tn = te.get("tool_name")
                if tn and tn not in tools_used:
                    tools_used.append(tn)

        # Extract SQL
        sql = state.get("sql")
        if isinstance(sql, dict):
            sql = sql.get("sql") or str(sql)
        elif not isinstance(sql, str):
            sql = None

        # Extract join paths from semantic resolution
        sem_res = state.get("semantic_resolution")
        join_paths: list[str] = []
        semantic_terms: list[dict[str, str]] = []
        if isinstance(sem_res, dict):
            jps = sem_res.get("join_paths") or []
            for jp in jps:
                if isinstance(jp, dict):
                    join_paths.append(
                        f"{jp.get('from_table', '?')}.{jp.get('from_column', '?')} "
                        f"↔ {jp.get('to_table', '?')}.{jp.get('to_column', '?')}"
                    )
                elif isinstance(jp, str):
                    join_paths.append(jp)
            # Semantic terms
            resolved = sem_res.get("resolved_terms") or []
            for rt in resolved:
                if isinstance(rt, dict):
                    semantic_terms.append({
                        "term": rt.get("term", ""),
                        "mapping": rt.get("mapping") or rt.get("definition", ""),
                    })

        write_trajectory(
            question=question,
            status=status,
            tables=tables,
            sql=sql,
            tools_used=tools_used,
            result_summary=answer_text[:300] if answer_text else None,
            join_paths=join_paths,
            semantic_terms=semantic_terms,
            user_id=state.get("user_id") or state.get("thread_id"),
            datasource_id=str(state.get("datasource_id") or ""),
            project_id=state.get("project_id"),
            run_id=state.get("run_id"),
            session_id=state.get("thread_id") or state.get("session_id"),
        )
    except Exception as exc:
        _logger.warning("Failed to auto-write trajectory: %s", exc)

