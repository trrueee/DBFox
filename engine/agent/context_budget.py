"""Typed, deterministic budgeting for complete model requests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
import math
from typing import Any

from engine.json_codec import canonical_dumps


def estimate_text_tokens(value: str) -> int:
    # Provider-neutral and deliberately conservative for mixed CJK/JSON input.
    return max(1, math.ceil(len(value.encode("utf-8")) / 3))


def estimate_message_tokens(message: dict[str, Any]) -> int:
    return 6 + estimate_text_tokens(str(message.get("content") or ""))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)


def estimate_input_item_tokens(item: dict[str, Any]) -> int:
    """Conservatively estimate any Responses input Item, not only messages."""
    if item.get("type") == "message":
        return estimate_message_tokens(item)
    encoded = canonical_dumps(item)
    return 6 + estimate_text_tokens(encoded)


def estimate_input_items_tokens(items: list[dict[str, Any]]) -> int:
    return sum(estimate_input_item_tokens(item) for item in items)


def estimate_tool_schema_tokens(schemas: list[dict[str, Any]]) -> int:
    if not schemas:
        return 0
    encoded = canonical_dumps(schemas)
    return estimate_text_tokens(encoded)


class ContextSegmentKind(StrEnum):
    SYSTEM = "system"
    CURRENT_REQUEST = "current_request"
    RUN_FOCUS = "run_focus"
    PREVIOUS_RUN_OUTCOME = "previous_run_outcome"
    SELECTED_ARTIFACT = "selected_artifact"
    RESOURCE_DIRECTORY = "resource_directory"
    INPUT_REFERENCES = "input_references"
    WORKSPACE_CONTEXT = "workspace_context"
    SESSION_MEMORY = "session_memory"
    CONVERSATION_ARCHIVE = "conversation_archive"
    FACTUAL_CONTEXT = "factual_context"
    WORKING_STATE_FRAGMENT = "working_state_fragment"
    RESOURCE_FRAGMENT = "resource_fragment"
    EVIDENCE_FRAGMENT = "evidence_fragment"
    HISTORY = "history"


class ContextPriority(IntEnum):
    SYSTEM = 1_000
    CURRENT_REQUEST = 950
    RUN_FOCUS = 875
    PREVIOUS_RUN_OUTCOME = 865
    SELECTED_ARTIFACT = 850
    RESOURCE_DIRECTORY = 846
    INPUT_REFERENCES = 844
    WORKSPACE_CONTEXT = 840
    WORKING_STATE_FRAGMENT = 820
    RESOURCE_FRAGMENT = 815
    EVIDENCE_FRAGMENT = 810
    FACTUAL_CONTEXT = 775
    CONVERSATION_ARCHIVE = 760
    SESSION_MEMORY = 750
    HISTORY = 100


@dataclass(frozen=True)
class ContextBudgetSegment:
    kind: ContextSegmentKind
    role: str
    payload: str
    priority: int
    sequence: int = 0
    prefix: str = ""
    suffix: str = ""
    required: bool = False
    truncatable: bool = False

    def render(self, payload: str | None = None) -> dict[str, Any]:
        value = self.payload if payload is None else payload
        return {"role": self.role, "content": f"{self.prefix}{value}{self.suffix}"}


class ContextBudgetExceeded(ValueError):
    pass


@dataclass(frozen=True)
class ContextBudgetResult:
    messages: list[dict[str, Any]]
    estimated_tokens: int
    message_tokens: int
    reserved_tokens: int
    max_prompt_tokens: int
    omitted_messages: int
    truncated_messages: int

    def telemetry(self) -> dict[str, int]:
        return {
            "estimated_prompt_tokens": self.estimated_tokens,
            "message_tokens": self.message_tokens,
            "reserved_tokens": self.reserved_tokens,
            "max_prompt_tokens": self.max_prompt_tokens,
            "omitted_messages": self.omitted_messages,
            "truncated_messages": self.truncated_messages,
        }


def _truncate_segment(
    segment: ContextBudgetSegment,
    token_budget: int,
) -> dict[str, Any] | None:
    marker = "\n[context truncated by runtime budget]"
    fixed = segment.render("")
    fixed_cost = estimate_message_tokens(fixed) + estimate_text_tokens(marker)
    if token_budget <= fixed_cost:
        return None
    payload_budget = token_budget - fixed_cost
    low, high = 0, len(segment.payload)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_text_tokens(segment.payload[:middle]) <= payload_budget:
            low = middle
        else:
            high = middle - 1
    if low <= 0:
        return None
    return segment.render(segment.payload[:low].rstrip() + marker)


class ContextBudgetPlanner:
    def __init__(self, *, max_prompt_tokens: int) -> None:
        self.max_prompt_tokens = max(1_024, int(max_prompt_tokens))

    def fit(
        self,
        segments: list[ContextBudgetSegment],
        *,
        reserved_tokens: int = 0,
    ) -> ContextBudgetResult:
        reserved = max(0, int(reserved_tokens))
        available = self.max_prompt_tokens - reserved
        if available <= 0:
            raise ContextBudgetExceeded(
                "Tool schemas consume the complete model input budget"
            )

        required = [(index, item) for index, item in enumerate(segments) if item.required]
        selected: dict[int, dict[str, Any]] = {}
        consumed = 0
        truncated = 0

        # Required segments preserve their declared order. Trusted system policy
        # is never silently truncated; user payloads may be safely shortened
        # inside their complete structural wrapper.
        for index, segment in required:
            message = segment.render()
            cost = estimate_message_tokens(message)
            remaining = available - consumed
            if cost <= remaining:
                selected[index] = message
                consumed += cost
                continue
            if not segment.truncatable:
                raise ContextBudgetExceeded(
                    f"Required {segment.kind.value} exceeds the model input budget"
                )
            shortened = _truncate_segment(segment, remaining)
            if shortened is None:
                raise ContextBudgetExceeded(
                    f"Required {segment.kind.value} cannot retain a valid envelope"
                )
            selected[index] = shortened
            consumed += estimate_message_tokens(shortened)
            truncated += 1

        optional = [
            (index, item)
            for index, item in enumerate(segments)
            if not item.required
        ]
        optional.sort(
            key=lambda pair: (pair[1].priority, pair[1].sequence, pair[0]),
            reverse=True,
        )
        omitted = 0
        for index, segment in optional:
            message = segment.render()
            cost = estimate_message_tokens(message)
            if consumed + cost <= available:
                selected[index] = message
                consumed += cost
            else:
                omitted += 1

        messages = [selected[index] for index in sorted(selected)]
        message_tokens = estimate_messages_tokens(messages)
        return ContextBudgetResult(
            messages=messages,
            estimated_tokens=message_tokens + reserved,
            message_tokens=message_tokens,
            reserved_tokens=reserved,
            max_prompt_tokens=self.max_prompt_tokens,
            omitted_messages=omitted,
            truncated_messages=truncated,
        )
