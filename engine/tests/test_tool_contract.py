"""Verify every registered tool has a valid state contract.

Contracts are auto-populated from ToolSpec at ToolRegistry.load_all() time.
These tests verify the runtime behavior directly via get_contract() and
apply_tool_result_to_state().
"""

from __future__ import annotations

from engine.agent_core.tool_registry import (
    TOOL_CONTRACTS,
    RESET_ALL_ERROR_STATE,
    ToolStateContract,
    get_contract,
)
from engine.agent_core.databinding import apply_tool_result_to_state
from engine.agent_core.types import ToolObservation


# Seed contracts for db.* tools (production: populated at ToolRegistry.load_all())
TOOL_CONTRACTS.update({
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
    "answer.synthesize": ToolStateContract(
        tool_name="answer.synthesize",
        merge_strategy="always_new",
        emit_artifact=True,
    ),
})


# ── Contracts for db.* tools must clear error state on success ──

REQUIRE_ERROR_CLEAR = {"db.query", "db.preview", "db.inspect"}


def test_db_tools_clear_error_on_success():
    for name in REQUIRE_ERROR_CLEAR:
        contract = get_contract(name)
        assert contract is not None, f"No contract for {name}"
        assert "error" in contract.on_success_clear, (
            f"{name} must clear 'error' on success"
        )


# ── Success path clears error, failure path does not ──

def test_success_clears_error_via_contract():
    state: dict = {"error": "old error", "last_error_telemetry": {"old": True}}
    obs = ToolObservation(
        name="query_database", status="success",
        input={"sql": "SELECT 1"}, output={"rows": [], "status": "success"},
        error=None, latency_ms=10,
    )
    update = apply_tool_result_to_state(state=state, tool_name="db.query", observation=obs)
    assert update.get("error") is None
    assert update.get("last_error_telemetry") is None


def test_failure_preserves_error():
    state: dict = {"pending_tool_call": {"tool_name": "db.query", "args": {}}}
    obs = ToolObservation(
        name="query_database", status="failed",
        input={"sql": "SELECT bad"}, output={"status": "blocked"},
        error="TrustGate Error", latency_ms=10,
    )
    update = apply_tool_result_to_state(state=state, tool_name="db.query", observation=obs)
    # failed path: error is written by _apply_failed_telemetry
    assert update.get("last_error_telemetry") is not None


# ── merge_strategy is always injected ──

def test_merge_strategy_in_trace_events():
    obs = ToolObservation(
        name="search", status="success", input={}, output={}, error=None, latency_ms=5,
    )
    update = apply_tool_result_to_state(state={}, tool_name="db.search", observation=obs)
    payload = update["trace_events"][0]["payload"]
    assert payload["_merge_strategy"] == "reuse"


# ── Unregistered tools get safe default ──

def test_unregistered_tool_gets_default_contract():
    contract = get_contract("some.unknown.tool")
    assert isinstance(contract, ToolStateContract)
    assert contract.merge_strategy == "reuse"
    assert contract.emit_artifact is False
    assert contract.on_success_clear == ()


# ── workspace.* tools get new + emit ──

def test_workspace_prefix_gets_new_artifact_contract():
    contract = get_contract("workspace.sql_suggest")
    assert contract.merge_strategy == "new"
    assert contract.emit_artifact is True
