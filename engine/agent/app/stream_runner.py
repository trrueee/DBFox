from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from engine.agent.app.event_mapper import (
    context_update_event,
    observe_events,
    trace_to_events,
)
from engine.agent.graph.state import DBFoxAgentState, sync_state_namespaces
from engine.agent_core.types import AgentRuntimeEvent


class AgentStreamRunner:
    """Merge graph stream chunks into state and runtime events."""

    def __init__(self, persistence: Any):
        self.persistence = persistence
        self._list_keys: set[str] | None = None

    def stream_and_merge(
        self,
        app: Any,
        input_value: Any,
        config: Any,
        accumulated_state: dict[str, Any],
        emit: Any,
        agent_state: Any,
        artifact_identity: Any,
        emitted_artifact_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        last_context_summary = ""
        for chunk in app.stream(input_value, config=config, stream_mode=["updates", "custom"]):
            mode = "updates"
            payload = chunk
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, payload = chunk

            if mode == "custom":
                event = self._custom_stream_event(emit, payload)
                if event is not None:
                    yield event
                continue

            if mode != "updates" or not isinstance(payload, dict):
                continue

            for node_name, update in payload.items():
                if not isinstance(update, dict):
                    continue

                self._merge_state(accumulated_state, update)
                node_str = str(node_name)

                if node_str == "observe":
                    for event in observe_events(
                        emit, update, agent_state, artifact_identity, emitted_artifact_ids
                    ):
                        self.persistence.persist_artifact_event(
                            agent_state.session_id,
                            event,
                            index=len(emitted_artifact_ids),
                        )
                        yield event

                if node_str in ("observe", "progress", "repair"):
                    context_event, last_context_summary = context_update_event(
                        emit, accumulated_state, last_context_summary,
                    )
                    if context_event is not None:
                        yield context_event

                if "trace_events" in update:
                    for trace_event in update["trace_events"]:
                        if isinstance(trace_event, dict):
                            yield from trace_to_events(emit, trace_event)

    def _custom_stream_event(self, emit: Any, payload: Any) -> AgentRuntimeEvent | None:
        if not isinstance(payload, dict) or payload.get("type") != "agent.answer.delta":
            return None
        content = payload.get("content")
        if not isinstance(content, str) or not content:
            return None
        return emit("agent.answer.delta", content=content, persist=False)

    def _merge_state(self, target: dict[str, Any], update: dict[str, Any]) -> None:
        from typing import get_args, get_origin
        import typing

        if self._list_keys is None:
            list_keys = set()
            for key, ann in DBFoxAgentState.__annotations__.items():
                origin = get_origin(ann)
                if origin is list or ann is list:
                    list_keys.add(key)
                elif origin is typing.Annotated or (hasattr(typing, "_AnnotatedAlias") and isinstance(ann, typing._AnnotatedAlias)):
                    args = get_args(ann)
                    if args and (get_origin(args[0]) is list or args[0] is list):
                        list_keys.add(key)
            self._list_keys = list_keys

        replace_keys = {
            "allowed_tool_calls",
            "blocked_tool_calls",
            "pending_tool_calls",
            "last_tool_results",
            "allowed_tool_groups",
        }

        for key, value in update.items():
            if key in self._list_keys and key not in replace_keys:
                if isinstance(value, list):
                    if value and isinstance(value[0], dict) and value[0].get("__clear__"):
                        target[key] = list(value[1:])
                    else:
                        target.setdefault(key, []).extend(value)
                continue

            if isinstance(value, dict) and isinstance(target.get(key), dict):
                target[key] = {**target[key], **value}
            else:
                target[key] = value
        sync_state_namespaces(target)
