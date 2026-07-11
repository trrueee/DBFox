# Error Boundary Contract

## Goal

No untrusted exception text may cross into an HTTP/SSE response, browser state,
Agent state, LangGraph checkpoint, event payload, SQLite record, or log. This
includes provider, driver, tunnel, vault, user-input, and chained exception
text.

## Authoritative model

Failure data that crosses a trust boundary is an allowlisted error code, not a
message or an exception:

```python
class ErrorCode(StrEnum):
    INTERNAL = "INTERNAL_ERROR"
    DATASOURCE_CONNECTION = "DATASOURCE_CONNECTION_FAILED"
    SSH_TUNNEL = "SSH_TUNNEL_FAILED"
    AGENT_RUNTIME = "AGENT_RUNTIME_ERROR"
    TOOL_EXECUTION = "TOOL_EXECUTION_ERROR"
    EVALUATION = "EVALUATION_ERROR"
```

The code-to-message/status mapping is private, static, and finite. Only that
mapping may render a public message. Callers must map arbitrary exceptions to
a fixed fallback code before building state, observations, persistence DTOs,
or responses.

## Rules

- Never serialize `str(exc)`, `exc.args`, exception causes, tracebacks, or
  provider/driver response text.
- Logs record a fixed operation and allowlisted error code; they do not accept
  an exception object or arbitrary context string.
- `ToolObservation`, Agent state, trace events, checkpoints, runtime events,
  evaluation results, tunnel state, and health records persist error codes
  only.
- A LangGraph node must convert an exception before returning state because a
  graph checkpoint can be written before application-level persistence runs.
- API handlers may propagate deliberately typed, static public errors, but
  must map all catch-all exceptions to a fixed internal code.
- Existing persisted error strings, agent checkpoints/events, evaluation
  failures, datasource health text, tunnel text, and logs require destructive
  reset or rotation; they cannot be retroactively trusted.

## Verification

Every new boundary needs a sentinel exception regression that proves the
sentinel is absent from logs, public responses, in-memory boundary DTOs,
LangGraph checkpoint bytes, and persisted SQLite JSON/text. Add a policy test
for boundary modules that rejects raw exception formatting and traceback
logging.
