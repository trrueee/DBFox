from __future__ import annotations

import logging
from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DataBoxAgentState

logger = logging.getLogger("databox.databox_agent.nodes.finalize_node")


def finalize_answer(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Finalize the agent run: extract answer from last AIMessage and set terminal status.

    This node is reached when the model produces a response without tool_calls,
    meaning it considers the task complete.
    """
    messages = state.get("messages", [])
    error = state.get("error")
    pending_approval = state.get("pending_approval")

    # Determine final answer text
    answer_text = ""
    if messages:
        last = messages[-1]
        content = getattr(last, "content", "")
        if isinstance(content, str):
            answer_text = content
        elif isinstance(content, list):
            # Anthropic-style content blocks
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            answer_text = " ".join(parts).strip()

    if pending_approval:
        status = "waiting_approval"
    elif error:
        status = "failed"
    elif answer_text:
        status = "completed"
    else:
        status = "failed"
        if not error:
            error = "Agent completed without producing an answer."

    # Build answer payload for AgentRunResponse compatibility
    existing_answer = state.get("answer")
    if isinstance(existing_answer, dict):
        answer_payload = {
            "answer": answer_text or existing_answer.get("answer") or "",
            "key_findings": existing_answer.get("key_findings") or [],
            "evidence": existing_answer.get("evidence") or [],
            "caveats": existing_answer.get("caveats") or [],
            "recommendations": existing_answer.get("recommendations") or [],
            "follow_up_questions": existing_answer.get("follow_up_questions") or [],
        }
    else:
        answer_payload = {
            "answer": answer_text,
            "key_findings": [],
            "evidence": [],
            "caveats": [],
            "recommendations": [],
            "follow_up_questions": [],
        }

    # Clean up any raw tool node prefix from answer if present
    if isinstance(answer_payload.get("answer"), str):
        ans_str = answer_payload["answer"]
        if ans_str.startswith("[") and "]" in ans_str:
            parts = ans_str.split("]", 1)
            if len(parts) > 1:
                answer_payload["answer"] = parts[1].strip()

    trace_event: dict[str, Any] = {
        "type": "agent.finalized",
        "status": status,
        "has_answer": bool(answer_text),
        "has_error": bool(error),
    }
    if pending_approval:
        trace_event["pending_approval"] = True

    # ---- Auto-write trajectory to memory (Agent v2) -----------------------
    _auto_write_trajectory(state, status, answer_text)

    result: dict[str, Any] = {
        "status": status,
        "answer": answer_payload,
        "final_answer": answer_payload,
        "error": error,
        "trace_events": [trace_event],
        "agent_graph_route": "end",
    }

    if status == "failed" and error:
        error_artifact = _build_and_persist_error_artifact(state, config, str(error))
        if error_artifact is not None:
            result["artifacts"] = [error_artifact]

    return result


def _build_and_persist_error_artifact(
    state: DataBoxAgentState,
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
    state: DataBoxAgentState,
    status: str,
    answer_text: str,
) -> None:
    """Auto-write trajectory + learnings to long-term memory on run completion.

    Best-effort — failures are logged but never block finalization.
    """
    import logging
    _logger = logging.getLogger("databox.databox_agent.nodes.finalize_node")

    try:
        from engine.agent.memory_bridge import write_trajectory

        # Extract user question from first message
        messages = state.get("messages", [])
        question = ""
        if messages:
            first = messages[0]
            content = getattr(first, "content", "")
            if isinstance(content, str):
                question = content
            elif isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                question = " ".join(parts).strip()

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

