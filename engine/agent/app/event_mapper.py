from __future__ import annotations

from typing import Any, Iterator

from engine.agent_core.types import (
    AgentArtifact,
    AgentRuntimeEvent,
    AgentRunResponse,
)
from engine.agent_core.artifacts import AgentArtifactIdentity


def observe_events(
    emit: Any,
    update: dict[str, Any],
    agent_state: Any,
    artifact_identity: AgentArtifactIdentity,
    emitted_ids: set[str],
) -> Iterator[AgentRuntimeEvent]:
    """Emit runtime events for new artifacts created by the observe node."""
    artifacts_raw = update.get("artifacts") or []
    for art_dict in artifacts_raw:
        if not isinstance(art_dict, dict):
            continue
        artifact = AgentArtifact.model_validate(art_dict)
        if hasattr(agent_state, 'artifacts'):
            agent_state.artifacts.append(artifact)
        if artifact.id not in emitted_ids:
            emitted_ids.add(artifact.id)
            yield emit("agent.artifact.created", artifact=artifact)
            step_name = _artifact_timeline_step(artifact.type)
            if step_name:
                yield emit(
                    "agent.step.completed",
                    step={
                        "name": step_name,
                        "status": "success",
                        "artifact_id": artifact.id,
                        "artifact_type": artifact.type,
                        "summary": artifact.title,
                    },
                )


def trace_to_events(
    emit: Any, trace: dict[str, Any]
) -> Iterator[AgentRuntimeEvent]:
    """Map internal graph trace logs to user-visible AgentRuntimeEvents."""
    trace_type = trace.get("type", "")
    tool_name = trace.get("tool_name", "")

    tool_to_step_name = {
        "db.observe": "observe_database",
        "db.search": "search_database",
        "db.inspect": "inspect_database",
        "db.preview": "preview_table",
        "db.query": "query_database",
        "db.remember": "remember_database_semantics",
        "result.profile": "profile_result",
        "chart.suggest": "suggest_chart",
        "answer.synthesize": "synthesize_answer",
    }
    mapped_name = tool_to_step_name.get(tool_name, tool_name)

    if trace_type == "agent.tool.started":
        yield emit(
            "agent.step.started",
            step={
                "name": mapped_name,
                "tool_name": tool_name,
                "input": trace.get("input"),
            },
        )
    elif trace_type == "agent.tool.completed":
        payload = trace.get("payload", trace)
        yield emit(
            "agent.step.completed",
            step={
                "name": mapped_name,
                "tool_name": tool_name,
                "status": payload.get("status") if isinstance(payload, dict) else trace.get("status"),
                "latency_ms": payload.get("latency_ms") if isinstance(payload, dict) else trace.get("latency_ms"),
                "input": payload.get("input") if isinstance(payload, dict) else trace.get("input"),
                "output": payload.get("output") if isinstance(payload, dict) else trace.get("output"),
                "error": payload.get("error") if isinstance(payload, dict) else trace.get("error"),
                "merge_strategy": (payload.get("_merge_strategy") if isinstance(payload, dict) else None) or "reuse",
            },
        )
    elif trace_type == "agent.repair.prepared":
        summary = trace.get("recovery_strategy") or "Preparing SQL repair"
        yield emit(
            "agent.progress.update",
            step={
                "name": "sql_repair",
                "status": "running",
                "summary": summary,
                "detail": trace.get("error_class"),
                "attempt": trace.get("attempt"),
            },
        )
    elif trace_type == "agent.repair.attempted":
        summary = trace.get("user_visible_update") or trace.get("recovery_strategy")
        if summary:
            yield emit(
                "agent.progress.update",
                step={
                    "name": "sql_repair",
                    "status": "running",
                    "summary": summary,
                    "detail": trace.get("error_class"),
                    "attempt": trace.get("attempt"),
                },
            )
    elif trace_type == "agent.progress.judged":
        summary = trace.get("user_visible_update") or trace.get("recovery_strategy") or trace.get("reason_summary")
        if summary:
            yield emit(
                "agent.progress.update",
                step={
                    "name": trace.get("failure_layer") or "progress",
                    "status": trace.get("status") or "running",
                    "summary": summary,
                    "detail": trace.get("root_cause"),
                    "fastpath": trace.get("fastpath", False),
                },
            )
    elif trace_type == "agent.model.completed":
        content = _safe_model_progress_text(trace.get("content"))
        tool_names = _tool_call_names(trace.get("tool_calls"))
        if content or tool_names:
            summary = content or f"准备调用工具：{', '.join(tool_names[:3])}"
            yield emit(
                "agent.progress.update",
                step={
                    "name": "model",
                    "status": "running" if tool_names else "success",
                    "summary": summary,
                    "tool_calls": tool_names,
                },
            )
    elif trace_type == "agent.approval.required":
        yield emit("agent.approval.required", step={"name": mapped_name})


def context_update_event(
    emit: Any,
    state: dict[str, Any],
    last_summary: str,
) -> tuple[AgentRuntimeEvent | None, str]:
    """Emit UI context and task lens streaming state updates."""
    from engine.agent.context_pack import build_streaming_context_summary

    summary = build_streaming_context_summary(state)
    if not summary or summary == last_summary:
        return None, last_summary
    step_payload: dict[str, Any] = {
        "summary": summary,
        "repair_mode": bool(state.get("repair_mode")),
    }
    visible = state.get("visible_plan") or {}
    if isinstance(visible, dict):
        task_lens = {
            "goal": str(visible.get("goal") or ""),
            "current_focus": str(visible.get("current_focus") or ""),
            "next_likely": str(visible.get("next_likely") or ""),
            "missing_evidence": list(visible.get("missing_evidence") or []),
        }
        if any(task_lens.values()) or task_lens["missing_evidence"]:
            step_payload["task_lens"] = task_lens

    return emit("agent.context.update", step=step_payload), summary


def final_events(
    emit: Any,
    response: AgentRunResponse,
    agent_state: Any,
    emitted_ids: set[str],
) -> Iterator[AgentRuntimeEvent]:
    """Emit terminal execution artifacts and final answer payloads."""
    for artifact in response.artifacts:
        if artifact.id not in emitted_ids:
            emitted_ids.add(artifact.id)
            yield emit("agent.artifact.created", artifact=artifact)

    if response.answer:
        yield emit("agent.answer.completed", answer_payload=response.answer)


def artifacts_from_state(
    final_state: dict[str, Any], agent_state: Any
) -> list[AgentArtifact]:
    """Build list of unique artifacts merged from graph state and timeline records."""
    seen: set[str] = set()
    result: list[AgentArtifact] = []
    for source in [
        getattr(agent_state, "artifacts", []) or [],
        final_state.get("artifacts") or [],
    ]:
        for item in source:
            try:
                art = AgentArtifact.model_validate(item) if isinstance(item, dict) else item
                if art.id not in seen:
                    seen.add(art.id)
                    result.append(art)
            except Exception:
                pass
    return result


def _artifact_timeline_step(artifact_type: str) -> str | None:
    mapping = {
        "table": "query_database",
        "agent_plan": "planner",
    }
    return mapping.get(artifact_type)


def _safe_model_progress_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("thought:", "reasoning:", "chain of thought:", "思考:", "思考：", "推理:", "推理："):
        if lowered.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    if not text:
        return ""
    if len(text) > 1200:
        return text[:1200].rstrip() + "..."
    return text


def _tool_call_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = ""
        if isinstance(item, dict):
            name = str(item.get("name") or "")
        else:
            name = str(getattr(item, "name", "") or "")
        if name:
            names.append(name)
    return names
