"""Verify every registered tool has a valid state contract."""

from __future__ import annotations

from engine.agent_core.tool_contract import TOOL_CONTRACTS, get_contract, ToolStateContract
from engine.agent_core.databinding import apply_tool_result_to_state, TOOL_STATE_APPLIERS
from engine.agent_core.types import ToolObservation


# ── Every tool handler must have a matching contract ──

def test_all_handlers_have_contracts():
    """Every tool with a state applier must be in TOOL_CONTRACTS."""
    unregistered = []
    for tool_name in TOOL_STATE_APPLIERS:
        if tool_name not in TOOL_CONTRACTS and not tool_name.startswith("workspace."):
            unregistered.append(tool_name)
    assert unregistered == [], f"Tools without contracts: {unregistered}"


# ── Contracts for db.* tools with side effects must clear error state on success ──

REQUIRE_ERROR_CLEAR = {"db.query", "db.preview", "db.inspect"}


def test_db_tools_clear_error_on_success():
    for name in REQUIRE_ERROR_CLEAR:
        contract = TOOL_CONTRACTS.get(name)
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
