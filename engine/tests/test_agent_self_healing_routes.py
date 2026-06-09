from __future__ import annotations

from engine.agent_kernel.graph_standalone import _after_observe, _transient_retry_node


def test_retryable_tool_error_routes_to_retry_node() -> None:
    state = {
        "last_tool_name": "sql.execute_readonly",
        "last_error_telemetry": {
            "retryable": True,
            "tool_name": "sql.execute_readonly",
            "error_type": "OperationalError",
        },
        "last_failed_tool_call": {"tool_name": "sql.execute_readonly", "args": {}},
        "retry_counters": {},
    }

    assert _after_observe(state) == "transient_retry"


def test_retry_node_replays_failed_tool_call() -> None:
    state = {
        "last_error_telemetry": {
            "retryable": True,
            "tool_name": "sql.execute_readonly",
            "error_type": "OperationalError",
        },
        "last_failed_tool_call": {"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}},
        "retry_counters": {},
    }

    update = _transient_retry_node(state)

    assert update["pending_tool_call"]["tool_name"] == "sql.execute_readonly"
    assert update["pending_tool_call"]["args"] == {"sql": "SELECT 1"}
    assert update["retry_counters"]["sql.execute_readonly"] == 1


def test_non_retryable_sql_error_routes_to_revision() -> None:
    state = {
        "sql": "SELECT bad_column FROM orders",
        "last_tool_name": "sql.execute_readonly",
        "last_error_telemetry": {
            "retryable": False,
            "tool_name": "sql.execute_readonly",
            "error_type": "ProgrammingError",
        },
        "last_failed_tool_call": {"tool_name": "sql.execute_readonly", "args": {}},
        "revision_count": 0,
    }

    assert _after_observe(state) == "revise_sql"
