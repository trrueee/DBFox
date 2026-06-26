from __future__ import annotations

import json

from engine.agent_core.events import build_trace_events
from engine.agent_core.trace_redactor import MAX_TRACE_EVENT_BYTES
from engine.agent_core.types import AgentStep


def test_trace_events_are_redacted_and_limited() -> None:
    step = AgentStep(
        name="execute_sql",
        status="success",
        input={
            "sql": "SELECT id FROM users WHERE email = 'alice@example.com' AND token = 'secret-token'",
            "api_key": "sk-test-secret",
            "schema_context": "x" * 80_000,
        },
        output={
            "rows": [{"email": f"user{index}@example.com", "value": index} for index in range(12)],
            "password": "plain-secret",
            "large_payload": "y" * 80_000,
        },
        error=None,
        latency_ms=7,
    )

    events = build_trace_events([step])
    serialized = json.dumps([event.model_dump(mode="json") for event in events], ensure_ascii=False)

    assert "alice@example.com" not in serialized
    assert "sk-test-secret" not in serialized
    assert "plain-secret" not in serialized
    assert "secret-token" not in serialized
    assert "[REDACTED]" in serialized
    assert all(
        len(json.dumps(event.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")) <= MAX_TRACE_EVENT_BYTES
        for event in events
    )

    completed = events[1]
    assert completed.output is not None
    rows = completed.output["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 6
    assert rows[-1] == {"_truncated": 7}


def test_trace_error_redacts_auth_headers() -> None:
    step = AgentStep(
        name="call_model",
        status="failed",
        input={},
        output=None,
        error=(
            "request failed Authorization: Bearer trace-secret-token "
            "X-Local-Token: local-runtime-token"
        ),
        latency_ms=1,
    )

    events = build_trace_events([step])
    completed = events[1]

    assert completed.error is not None
    assert "trace-secret-token" not in completed.error
    assert "local-runtime-token" not in completed.error
    assert "Authorization: Bearer [REDACTED]" in completed.error
    assert "X-Local-Token: [REDACTED]" in completed.error
