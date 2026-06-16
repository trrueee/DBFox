"""Declarative per-tool state contracts — success cleanup, failure telemetry, merge strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MergeStrategy = Literal["reuse", "new", "always_new"]


@dataclass(frozen=True)
class ToolStateContract:
    tool_name: str
    on_success_clear: tuple[str, ...] = ()   # keys set to None on success
    on_success_reset: tuple[str, ...] = ()   # keys reset via RESET_* constants
    merge_strategy: MergeStrategy = "reuse"
    emit_artifact: bool = False


# ── Reusable reset groups ──
RESET_ERROR = ("error",)
RESET_SELF_HEALING = ("last_error_telemetry", "last_failed_tool_call")
RESET_ALL_ERROR_STATE = RESET_ERROR + RESET_SELF_HEALING


TOOL_CONTRACTS: dict[str, ToolStateContract] = {
    # ── Database operations ──
    "db.query": ToolStateContract(
        tool_name="db.query",
        on_success_clear=RESET_ALL_ERROR_STATE,
        emit_artifact=True,
    ),
    "db.preview": ToolStateContract(
        tool_name="db.preview",
        on_success_clear=RESET_ALL_ERROR_STATE,
        emit_artifact=True,
    ),
    "db.inspect": ToolStateContract(
        tool_name="db.inspect",
        on_success_clear=RESET_ALL_ERROR_STATE,
        merge_strategy="new",
    ),
    "db.search": ToolStateContract(tool_name="db.search"),
    "db.observe": ToolStateContract(tool_name="db.observe"),
    "db.remember": ToolStateContract(
        tool_name="db.remember",
        merge_strategy="new",
    ),

    # ── Schema operations ──
    "schema.list_tables": ToolStateContract(tool_name="schema.list_tables"),
    "schema.describe_table": ToolStateContract(tool_name="schema.describe_table"),
    "schema.refresh_catalog": ToolStateContract(
        tool_name="schema.refresh_catalog",
        merge_strategy="new",
    ),

    # ── Semantic / memory ──
    "semantic.resolve": ToolStateContract(tool_name="semantic.resolve"),
    "memory.search": ToolStateContract(tool_name="memory.search"),
    "memory.write": ToolStateContract(
        tool_name="memory.write",
        merge_strategy="new",
    ),

    # ── Analysis / synthesis ──
    "environment.get_profile": ToolStateContract(tool_name="environment.get_profile"),
    "result.profile": ToolStateContract(
        tool_name="result.profile",
        merge_strategy="new",
        emit_artifact=True,
    ),
    "chart.suggest": ToolStateContract(
        tool_name="chart.suggest",
        merge_strategy="new",
        emit_artifact=True,
    ),
    "answer.synthesize": ToolStateContract(
        tool_name="answer.synthesize",
        merge_strategy="always_new",
        emit_artifact=True,
    ),
}


def get_contract(tool_name: str) -> ToolStateContract:
    """Return the contract for a tool, or a safe default for unregistered tools."""
    if tool_name in TOOL_CONTRACTS:
        return TOOL_CONTRACTS[tool_name]
    if tool_name.startswith("workspace."):
        return ToolStateContract(
            tool_name=tool_name,
            merge_strategy="new",
            emit_artifact=True,
        )
    return ToolStateContract(tool_name=tool_name)
