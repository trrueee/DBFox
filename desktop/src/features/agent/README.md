# Agent Feature Boundary

`features/agent` is the frontend surface for the Agent runtime. It renders Agent runs, streamed steps, artifacts, answers, trace evidence, and follow-up prompts.

Owned here:
- `AgentWorkspace`
- `AgentNarrativeStream`
- `ArtifactInspector`
- Agent artifact views
- Agent follow-up context creation
- Agent draft state rendering while SSE events are still arriving

Backend counterpart:

```text
engine/agent/
  runtime.py
  tools.py
  types.py
  artifacts.py
  events.py
  persistence.py
```

Not owned here:
- SQL Editor `@` annotations.
- Query Action processors.
- Low-level schema linking or semantic alias configuration, except as data already returned by Agent responses.

The runtime contract should stay:

```text
AgentRunRequest
  -> Agent runtime step chain
  -> AgentRuntimeEvent stream
  -> AgentArtifact evidence
  -> final AgentAnswer after validation
  -> AgentRunResponse
```

Agent answers should remain evidence-grounded. Do not token-stream final business conclusions before safety checks, execution/profile artifacts, and response contract validation have completed.
