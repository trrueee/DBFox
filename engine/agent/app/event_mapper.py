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
                "phase": _artifact_phase(artifact.type),
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

    from engine.agent.tools.tool_aliases import STEP_NAME_MAP
    mapped_name = STEP_NAME_MAP.get(tool_name, tool_name)

    if trace_type == "agent.tool.started":
        yield emit(
            "agent.step.started",
            step={
                "name": mapped_name,
                "tool_name": tool_name,
                "phase": _phase_for_tool(tool_name),
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
                "phase": _phase_for_tool(tool_name),
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
                "phase": "repairing",
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
                    "phase": "repairing",
                    "status": "running",
                    "summary": summary,
                    "detail": trace.get("error_class"),
                    "attempt": trace.get("attempt"),
                    "error_class": trace.get("error_class"),
                    "failed_sql": trace.get("failed_sql"),
                    "failure_layer": trace.get("failure_layer"),
                    "root_cause": trace.get("root_cause"),
                    "recovery_strategy": trace.get("recovery_strategy"),
                },
            )
    elif trace_type == "agent.progress.judged":
        summary = trace.get("user_visible_update") or trace.get("recovery_strategy") or trace.get("reason_summary")
        if summary:
            yield emit(
                "agent.progress.update",
                step={
                    "name": trace.get("failure_layer") or "progress",
                    "phase": _phase_for_progress(trace),
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
                    "phase": "understanding",
                    "status": "running" if tool_names else "success",
                    "summary": summary,
                    "tool_calls": tool_names,
                },
            )
    elif trace_type == "agent.approval.required":
        yield emit("agent.approval.required", step={"name": mapped_name, "phase": "validating"})


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
    memory_refs = _memory_references(state)
    semantic_refs = _semantic_references(state)
    if isinstance(visible, dict):
        task_lens = {
            "goal": str(visible.get("goal") or ""),
            "current_focus": str(visible.get("current_focus") or ""),
            "next_likely": str(visible.get("next_likely") or ""),
            "missing_evidence": list(visible.get("missing_evidence") or []),
        }
        if memory_refs:
            task_lens["memory_references"] = memory_refs
        if semantic_refs:
            task_lens["semantic_references"] = semantic_refs
        if any(task_lens.values()) or task_lens["missing_evidence"]:
            step_payload["task_lens"] = task_lens
    elif memory_refs or semantic_refs:
        step_payload["task_lens"] = {
            "goal": "",
            "current_focus": "",
            "next_likely": "",
            "missing_evidence": [],
            "memory_references": memory_refs,
            "semantic_references": semantic_refs,
        }

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


def _artifact_phase(artifact_type: str) -> str:
    mapping = {
        "sql": "generating_sql",
        "sql_suggestion": "generating_sql",
        "safety": "validating",
        "table": "executing",
        "result_view": "executing",
        "chart": "synthesizing",
        "error": "repairing",
        "query_plan": "understanding",
        "agent_plan": "understanding",
    }
    return mapping.get(artifact_type, "synthesizing")


def _phase_for_tool(tool_name: str) -> str:
    lowered = (tool_name or "").lower()
    if "repair" in lowered:
        return "repairing"
    if lowered.startswith("db.search") or "schema" in lowered and "inspect" not in lowered:
        return "searching_schema"
    if lowered.startswith("db.inspect") or lowered.startswith("db.preview"):
        return "inspecting"
    if "sql.validate" in lowered or "safety" in lowered or "guardrail" in lowered:
        return "validating"
    if "sql.execute" in lowered or lowered.startswith("db.query") or "readonly" in lowered:
        return "executing"
    if "chart" in lowered or "answer" in lowered or "memory" in lowered:
        return "synthesizing"
    if "sql" in lowered:
        return "generating_sql"
    return "understanding"


def _phase_for_progress(trace: dict[str, Any]) -> str:
    name = str(trace.get("failure_layer") or trace.get("name") or "").lower()
    status = str(trace.get("status") or "").lower()
    if "repair" in name or "repair" in status:
        return "repairing"
    if "sql" in name and "valid" in name:
        return "validating"
    if "execute" in name or "query" in name:
        return "executing"
    if "answer" in name or "final" in name:
        return "synthesizing"
    return "understanding"


def _memory_references(state: dict[str, Any]) -> list[dict[str, str]]:
    raw = state.get("memory_references") or []
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, str]] = []
    for item in raw[:5]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("title") or "").strip()
        summary = str(item.get("summary") or item.get("value") or "").strip()
        source = str(item.get("source") or "memory").strip() or "memory"
        if label:
            refs.append({"label": label, "summary": summary, "source": source})
    return refs


def _semantic_references(state: dict[str, Any]) -> list[dict[str, str]]:
    semantic = state.get("semantic_resolution") or {}
    if not isinstance(semantic, dict):
        return []
    raw_aliases = semantic.get("semantic_aliases_used") or semantic.get("aliases_used") or []
    if not isinstance(raw_aliases, list):
        return []
    refs: list[dict[str, str]] = []
    for item in raw_aliases[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("alias") or item.get("label") or "").strip()
        target = str(item.get("target") or item.get("summary") or item.get("column") or "").strip()
        source = str(item.get("source") or "semantic").strip() or "semantic"
        if label:
            refs.append({"label": label, "summary": target, "source": source})
    return refs


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
