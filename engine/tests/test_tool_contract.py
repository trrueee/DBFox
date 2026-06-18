"""Verify BaseTool runtime state reduction contracts."""

from __future__ import annotations

from engine.agent_core.types import ToolObservation
from engine.tools.runtime.state_reducer import (
    ARTIFACT_TOOLS,
    ERROR_CLEARING_TOOLS,
    apply_tool_observation_to_state,
)


def _observation(name: str, *, status: str = "success", output: dict | None = None) -> ToolObservation:
    return ToolObservation(
        name=name,
        status=status,
        input={},
        output=output or {},
        error=None if status == "success" else "boom",
        latency_ms=5,
    )


def test_db_tools_clear_error_on_success():
    for name in {"db.query", "db.preview", "db.inspect"}:
        assert name in ERROR_CLEARING_TOOLS
        update = apply_tool_observation_to_state(
            state={"error": "old", "last_error_telemetry": {"old": True}},
            tool_name=name,
            observation=_observation(name),
        )
        assert update["error"] is None
        assert update["last_error_telemetry"] is None
        assert update["last_failed_tool_call"] is None


def test_failure_preserves_telemetry():
    update = apply_tool_observation_to_state(
        state={"pending_tool_call": {"tool_name": "db.query", "args": {"sql": "SELECT bad"}}},
        tool_name="db.query",
        observation=_observation("db.query", status="failed", output={"retryable": False}),
    )

    assert update["last_failed_tool_call"]["tool_name"] == "db.query"
    assert update["last_error_telemetry"] == {"retryable": False}
    assert update["execution"]["success"] is False
    assert update["error"] == "boom"


def test_result_profile_contract_writes_profile_and_artifact():
    output = {"row_count": 3, "notable_facts": ["x"]}
    update = apply_tool_observation_to_state(
        state={},
        tool_name="result.profile",
        observation=_observation("result.profile", output=output),
        merge_strategy="new",
    )

    assert "result.profile" in ARTIFACT_TOOLS
    assert update["result_profile"] == output
    assert update["trace_events"][0]["payload"]["_merge_strategy"] == "new"
    assert update["artifacts"][0]["tool_name"] == "result.profile"


def test_db_query_contract_writes_execution_and_sql():
    update = apply_tool_observation_to_state(
        state={},
        tool_name="db.query",
        observation=_observation(
            "db.query",
            output={"status": "success", "returned_rows": 1, "safe_sql": "SELECT 1"},
        ),
    )

    assert update["execution"]["success"] is True
    assert update["execution"]["rowCount"] == 1
    assert update["sql"] == "SELECT 1"
    assert update["trace_events"][0]["payload"]["_merge_strategy"] == "reuse"


def test_unknown_tool_gets_safe_default_reducer_behavior():
    update = apply_tool_observation_to_state(
        state={},
        tool_name="some.unknown.tool",
        observation=_observation("some.unknown.tool"),
    )

    assert "result_profile" not in update
    assert "artifacts" not in update
    assert update["trace_events"][0]["payload"]["_merge_strategy"] == "reuse"


def test_reducer_uses_declared_merge_strategy():
    update = apply_tool_observation_to_state(
        state={},
        tool_name="custom.tool",
        observation=_observation("custom.tool"),
        merge_strategy="always_new",
    )

    assert update["trace_events"][0]["payload"]["_merge_strategy"] == "always_new"
