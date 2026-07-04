from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import RemoveMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.graph.context import graph_context
from engine.agent_core.memory import sql_fingerprint, upsert_memory_ref
from engine.llm import get_chat_model


RECENT_TURN_KEEP = 4
RECENT_TURN_BATCH_SIZE = 3
logger = logging.getLogger("dbfox.dbfox_agent.nodes.turn_node")


@dataclass(frozen=True)
class CompactionPlan:
    to_summarize: list[Any]
    remove_messages: list[Any]


def build_turn_reset_update(
    *,
    run_id: str,
    session_id: str,
    datasource_id: str,
    question: str,
    execute: bool,
    max_steps: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "thread_id": session_id,
        "session_id": session_id,
        "datasource_id": datasource_id,
        "parent_run_id": None,
        "execute": execute,
        "max_steps": max_steps,
        "step_count": 0,
        "status": "running",
        "error": None,
        "messages": [{"role": "user", "content": question}],
        "pending_tool_calls": [],
        "allowed_tool_calls": [],
        "blocked_tool_calls": [],
        "last_tool_results": [],
        "last_observation": None,
        "last_tool_name": None,
        "last_tool_metadata": None,
        "sql": None,
        "sql_candidate": None,
        "safety": None,
        "execution": None,
        "chart_suggestion": None,
        "suggestions": [{"__clear__": True}],
        "analysis_units": [{"__clear__": True}],
        "current_analysis_unit_id": None,
        "answer": None,
        "final_answer": None,
        "pending_approval": None,
        "approval_result": None,
        "revision_attempted": False,
        "revision_count": 0,
        "repair_mode": False,
        "repair_stats": None,
        "repair_trace": [{"__clear__": True}],
        "progress_decision": None,
        "replan_count": 0,
        "consecutive_blocks": 0,
        "tool_call_history": [{"__clear__": True}],
        "artifacts": [{"__clear__": True}],
        "trace_events": [{"__clear__": True}],
        "runtime_events": [{"__clear__": True}],
        "plan_events": [{"__clear__": True}],
    }


def plan_message_compaction(
    messages: list[Any],
    *,
    keep_recent: int,
    batch_size: int,
) -> CompactionPlan:
    old_count = max(0, len(messages) - keep_recent)
    if old_count < batch_size:
        return CompactionPlan(to_summarize=[], remove_messages=[])
    batch = list(messages[:batch_size])
    return CompactionPlan(to_summarize=batch, remove_messages=batch)


def start_turn(state: dict[str, Any]) -> dict[str, Any]:
    return build_turn_reset_update(
        run_id=str(state.get("run_id") or ""),
        session_id=str(state.get("session_id") or state.get("thread_id") or ""),
        datasource_id=str(state.get("datasource_id") or ""),
        question=str(state.get("question") or ""),
        execute=bool(state.get("execute", True)),
        max_steps=int(state.get("max_steps") or 50),
    )


def finalize_turn(state: dict[str, Any], config: RunnableConfig | None = None) -> dict[str, Any]:
    artifact_refs, sql_refs = extract_sql_backed_refs(state)
    update: dict[str, Any] = {}
    llm_config = _llm_config_from_graph(config)

    next_artifact_refs = list(state.get("artifact_ref_index") or [])
    for ref in artifact_refs:
        next_artifact_refs = upsert_memory_ref(next_artifact_refs, ref, max_refs=30)

    next_sql_refs = list(state.get("sql_ref_index") or [])
    for ref in sql_refs:
        next_sql_refs = upsert_memory_ref(next_sql_refs, ref, max_refs=30)

    if artifact_refs:
        update["artifact_ref_index"] = [{"__clear__": True}, *next_artifact_refs]
    if sql_refs:
        update["sql_ref_index"] = [{"__clear__": True}, *next_sql_refs]

    turn_summary = _recent_turn_summary(state, artifact_refs, sql_refs)
    if turn_summary:
        next_recent_turns = _dict_list(state.get("recent_turns")) + [turn_summary]
        conversation_summary, next_recent_turns = _compact_recent_turns(
            str(state.get("conversation_summary") or ""),
            next_recent_turns,
            **llm_config,
        )
        update["recent_turns"] = [{"__clear__": True}, *next_recent_turns]
        if conversation_summary:
            update["conversation_summary"] = conversation_summary

    message_removals = _message_removal_updates(
        state.get("messages"),
        keep_recent=RECENT_TURN_KEEP,
        batch_size=RECENT_TURN_BATCH_SIZE,
    )
    if message_removals:
        update["messages"] = message_removals
        update["summary_cursor_message_id"] = message_removals[-1].id

    if artifact_refs or turn_summary:
        update["active_task"] = _active_task_update(state, artifact_refs)

    return update


def extract_sql_backed_refs(
    state: dict[str, Any],
    *,
    now: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timestamp = now or ""
    datasource_id = str(state.get("datasource_id") or "")
    artifact_refs: list[dict[str, Any]] = []
    sql_refs: list[dict[str, Any]] = []

    for artifact in state.get("artifacts") or []:
        if not isinstance(artifact, dict) or artifact.get("type") != "result_view":
            continue
        payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
        if payload.get("storageMode") != "sql_backed":
            continue
        source_sql = _first_str(payload, ("sourceSql", "source_sql", "safeSql", "safe_sql"))
        safe_sql = _first_str(payload, ("safeSql", "safe_sql", "sourceSql", "source_sql"))
        if not safe_sql:
            continue
        artifact_id = str(artifact.get("id") or "")
        if not artifact_id:
            continue

        ref_datasource_id = _first_str(payload, ("datasourceId", "datasource_id")) or datasource_id
        fingerprint = sql_fingerprint(safe_sql)
        columns = _str_list(payload.get("columns"))
        tables = _str_list(payload.get("used_tables"))
        source_sql_artifact_id = _first_str(
            payload,
            ("sourceSqlArtifactKey", "sourceSqlArtifactId", "source_sql_artifact_id"),
        ) or None
        source_sql_semantic_id = _first_str(
            payload,
            ("sourceSqlSemanticKey", "sourceSqlSemanticId", "source_sql_semantic_id"),
        ) or None
        title = str(artifact.get("title") or "Result view")

        artifact_refs.append(
            {
                "id": f"mem_result_{artifact_id}",
                "kind": "result_view_ref",
                "datasource_id": ref_datasource_id,
                "artifact_id": artifact_id,
                "source_sql_artifact_id": source_sql_artifact_id,
                "source_sql_semantic_id": source_sql_semantic_id,
                "source_sql": source_sql,
                "safe_sql": safe_sql,
                "sql_fingerprint": fingerprint,
                "columns": columns,
                "row_count": payload.get("rowCount"),
                "latency_ms": payload.get("latencyMs"),
                "preview_rows": payload.get("previewRows") if isinstance(payload.get("previewRows"), list) else [],
                "purpose": title,
                "last_run_id": state.get("run_id"),
                "last_used_at": timestamp,
                "pinned": False,
            }
        )
        sql_refs.append(
            {
                "id": f"mem_sql_{fingerprint}",
                "kind": "sql_ref",
                "datasource_id": ref_datasource_id,
                "artifact_id": artifact_id,
                "source_sql_artifact_id": source_sql_artifact_id,
                "source_sql_semantic_id": source_sql_semantic_id,
                "source_sql": source_sql,
                "safe_sql": safe_sql,
                "sql_fingerprint": fingerprint,
                "columns": columns,
                "tables": tables,
                "purpose": title,
                "last_run_id": state.get("run_id"),
                "last_used_at": timestamp,
                "verified": True,
                "pinned": False,
            }
        )

    return artifact_refs, sql_refs


def _active_task_update(state: dict[str, Any], artifact_refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = dict(state.get("active_task") or {})
    if state.get("run_id"):
        active["last_successful_run_id"] = state.get("run_id")
    if artifact_refs:
        active["current_result_ref_id"] = artifact_refs[0].get("id")
        active["current_result_artifact_id"] = artifact_refs[0].get("artifact_id")
        active["current_source_sql_artifact_id"] = artifact_refs[0].get("source_sql_artifact_id")
        active["current_sql_fingerprint"] = artifact_refs[0].get("sql_fingerprint")
    return active or None


def _recent_turn_summary(
    state: dict[str, Any],
    artifact_refs: list[dict[str, Any]],
    sql_refs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    question = str(state.get("question") or "").strip()
    answer = _answer_text(state.get("final_answer")) or _answer_text(state.get("answer"))
    if not question and not answer:
        return None
    return {
        "run_id": state.get("run_id"),
        "question": question,
        "answer": answer,
        "sql_fingerprints": [
            str(ref.get("sql_fingerprint"))
            for ref in sql_refs
            if ref.get("sql_fingerprint")
        ],
        "artifact_ids": [
            str(ref.get("artifact_id"))
            for ref in artifact_refs
            if ref.get("artifact_id")
        ],
        "source_sql_artifact_ids": [
            str(ref.get("source_sql_artifact_id"))
            for ref in artifact_refs
            if ref.get("source_sql_artifact_id")
        ],
    }


def _compact_recent_turns(
    conversation_summary: str,
    recent_turns: list[dict[str, Any]],
    *,
    keep_recent: int = RECENT_TURN_KEEP,
    batch_size: int = RECENT_TURN_BATCH_SIZE,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    old_count = max(0, len(recent_turns) - keep_recent)
    if old_count < batch_size:
        return conversation_summary, recent_turns

    batch = recent_turns[:batch_size]
    kept = recent_turns[batch_size:]
    compacted = _llm_summarize_turn_batch(
        conversation_summary,
        batch,
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
    ) or _deterministic_turn_summary(batch)
    if not compacted:
        return conversation_summary, kept
    if conversation_summary.strip():
        return f"{conversation_summary.rstrip()}\n{compacted}", kept
    return compacted, kept


def _llm_config_from_graph(config: RunnableConfig | None) -> dict[str, str | None]:
    if config is None:
        return {"model_name": None, "api_key": None, "api_base": None}
    try:
        ctx = graph_context(config)
    except Exception:
        return {"model_name": None, "api_key": None, "api_base": None}
    return {
        "model_name": ctx.model_name,
        "api_key": ctx.api_key,
        "api_base": ctx.api_base,
    }


def _llm_summarize_turn_batch(
    conversation_summary: str,
    batch: list[dict[str, Any]],
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> str | None:
    if not _has_llm_credentials(api_key):
        return None
    try:
        model = get_chat_model(
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            temperature=0.0,
            max_tokens=700,
            timeout=60.0,
        )
        response = model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Summarize old DBFox analysis turns into durable session memory. "
                        "Preserve user intent, decisions, verified SQL/result references, "
                        "and follow-up context. Do not invent facts."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "existing_summary": conversation_summary,
                            "turns_to_compress": batch,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            ]
        )
    except Exception as exc:
        logger.debug("LLM turn summary failed; falling back to deterministic compaction: %s", exc)
        return None
    text = _message_text(response)
    return text if text else None


def _deterministic_turn_summary(batch: list[dict[str, Any]]) -> str:
    lines = [_format_turn_for_summary(turn) for turn in batch]
    return "\n".join(line for line in lines if line)


def _has_llm_credentials(api_key: str | None) -> bool:
    return bool(
        (api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("QWEN_API_KEY") or os.environ.get("DBFOX_LLM_API_KEY") or "").strip()
    )


def _message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return str(content or "").strip()


def _format_turn_for_summary(turn: dict[str, Any]) -> str:
    question = _truncate(str(turn.get("question") or "").strip(), 160)
    answer = _truncate(str(turn.get("answer") or "").strip(), 240)
    refs = _format_turn_refs(turn)
    if question and answer:
        base = f"- {question} -> {answer}"
    elif question:
        base = f"- {question}"
    elif answer:
        base = f"- {answer}"
    else:
        base = ""
    if not base or not refs:
        return base
    return f"{base} [{refs}]"


def _format_turn_refs(turn: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("artifact_ids", "source_sql_artifact_ids", "sql_fingerprints"):
        values = _str_list(turn.get(field))
        if values:
            parts.append(f"{field}={','.join(values[:5])}")
    return "; ".join(parts)


def _answer_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    for key in ("answer", "content", "text", "message"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not item.get("__clear__")]


def _message_removal_updates(
    messages: Any,
    *,
    keep_recent: int,
    batch_size: int,
) -> list[RemoveMessage]:
    if not isinstance(messages, list):
        return []
    plan = plan_message_compaction(messages, keep_recent=keep_recent, batch_size=batch_size)
    removals: list[RemoveMessage] = []
    for message in plan.remove_messages:
        message_id = getattr(message, "id", None)
        if isinstance(message_id, str) and message_id:
            removals.append(RemoveMessage(id=message_id))
    return removals


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
        elif isinstance(item, dict):
            raw = item.get("name") or item.get("field") or item.get("column")
            if isinstance(raw, str) and raw.strip():
                items.append(raw.strip())
    return items
