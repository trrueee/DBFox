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


def test_sql_validate_contract_writes_safety_and_sql():
    safety = {
        "can_execute": True,
        "safe_sql": "SELECT id, platform FROM platform_accounts LIMIT 100",
        "original_sql": "SELECT id, platform FROM platform_accounts",
        "blocked_reasons": [],
    }
    update = apply_tool_observation_to_state(
        state={},
        tool_name="sql.validate",
        observation=_observation(
            "sql.validate",
            output={
                "can_execute": True,
                "safe_sql": safety["safe_sql"],
                "original_sql": safety["original_sql"],
                "execution_safety_decision": safety,
            },
        ),
    )

    assert update["safety"] == safety
    assert update["sql"] == safety["safe_sql"]
    assert update["trace_events"][0]["payload"]["_merge_strategy"] == "reuse"


def test_sql_execute_readonly_contract_writes_execution_sql_and_artifact():
    update = apply_tool_observation_to_state(
        state={"error": "old", "last_error_telemetry": {"old": True}},
        tool_name="sql.execute_readonly",
        observation=_observation(
            "sql.execute_readonly",
            output={"status": "success", "returned_rows": 2, "safe_sql": "SELECT 1"},
        ),
    )

    assert "sql.execute_readonly" in ERROR_CLEARING_TOOLS
    assert "sql.execute_readonly" in ARTIFACT_TOOLS
    assert update["execution"]["success"] is True
    assert update["execution"]["rowCount"] == 2
    assert update["sql"] == "SELECT 1"
    assert update["artifacts"][0]["tool_name"] == "sql.execute_readonly"
    assert update["error"] is None
    assert update["last_error_telemetry"] is None
    assert update["last_failed_tool_call"] is None


def test_db_search_tool_description_uses_semantic_expression_not_keywords():
    from engine.tools.dbfox_tools import SearchInput

    description = SearchInput.model_fields["query"].description or ""
    assert "Keywords" not in description
    assert "semantic search expression" in description
    assert "one expression per call" in description
    assert "make multiple db.search calls" in description
    assert "Chinese synonyms" in description
    assert "English schema terms" in description
    assert "abbreviations" in description
    assert "possible table or column names" in description


def test_environment_get_profile_alias_maps_to_internal_tool_name():
    from engine.tools.runtime.aliases import to_alias, to_internal

    assert to_internal("environment_get_profile") == "environment.get_profile"
    assert to_alias("environment.get_profile") == "environment_get_profile"


def test_unknown_tool_gets_safe_default_reducer_behavior():
    update = apply_tool_observation_to_state(
        state={},
        tool_name="some.unknown.tool",
        observation=_observation("some.unknown.tool"),
    )

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
