# Answer Streaming Runtime Boundary

> 2026-06-28 | Clarify how DBFox should stream final answer text without confusing it with progress/runtime trace events.

## Context

DBFox already intentionally exposes the middle execution process to the user: steps, tool calls, context updates, artifacts, approval state, and final run status are all part of the product experience. This note is not about hiding intermediate thinking or making the Agent feel like a black box.

The issue is narrower: final answer text currently arrives only at completion time. Adding answer streaming should not turn final answer text into `agent.progress.update`, and should not leak raw LangGraph chunk formats into the frontend.

## Current Code Shape

- `AgentRuntimeEventType` has `agent.answer.completed`, but live runtime events do not yet include `agent.answer.delta`.
- `AgentVisibleEvent` already has the conceptual shape for `agent.answer.delta` with a `content` field. This means answer delta is already a known product-level concept, but it is not wired into live SSE runtime events.
- `final_events()` emits `agent.answer.completed` with the complete `AgentAnswer` payload.
- `_stream_and_merge()` currently runs LangGraph with `stream_mode="updates"`, so only node update state is mapped into DBFox runtime events.
- The real final answer is produced by `answer.synthesize`, which calls `synthesize_agent_answer()`.
- `synthesize_agent_answer()` currently uses `model.invoke(...)`, so it returns the final model response at once rather than streaming chunks.
- The frontend conversation reducer currently replaces assistant message content when it sees a completed answer; it does not have append semantics for answer deltas.

## True Streaming Criterion

Real answer streaming means the final-answer model call must expose chunks while the model is still generating text.

The clearest implementation is to use the model streaming API inside answer synthesis:

```text
for chunk in model.stream(messages):
    emit agent.answer.delta(content=chunk_text)
    buffer chunk_text
```

Then DBFox builds the final `AgentAnswer` from the buffered text and emits `agent.answer.completed`.

By contrast, this is not real model streaming:

```text
response = model.invoke(messages)
for chunk in split(response.content):
    emit agent.answer.delta(content=chunk)
```

That can create a typing effect and test the frontend append path, but it does not reduce time-to-first-answer-token because the model has already completed before any delta is emitted.

LangGraph `stream_mode=["updates", "messages"]` may also be a real streaming route, but only if its `messages` stream actually captures the LLM call that happens inside `answer.synthesize` and lets DBFox reliably identify those chunks as final-answer chunks. If that is not reliable, DBFox should implement explicit `model.stream(...)` in answer synthesis.

## Design Decision

Final answer text belongs to the `answer` semantic channel.

Do not stream final answer text through `agent.progress.update`. Progress events should continue to describe process state such as searching schema, inspecting tables, validating SQL, executing SQL, repairing, and synthesizing.

The correct runtime shape should be:

```text
answer generation starts
  -> agent.answer.delta      # append visible answer text chunk
  -> agent.answer.delta
  -> ...
  -> agent.answer.completed  # authoritative complete AgentAnswer
```

`agent.answer.completed` remains the source of truth. The frontend should use completed answer content to overwrite or reconcile the temporarily streamed text.

## Product Semantics

Middle process remains visible:

```text
agent.step.started
agent.step.completed
agent.progress.update
agent.context.update
agent.artifact.created
agent.approval.required
```

Final answer text uses answer events:

```text
agent.answer.delta
agent.answer.completed
```

This keeps DBFox domain events stable while allowing internal implementation to use LangGraph streaming, model callbacks, or a custom answer streaming path.

## Implementation Options

### Option A: Fake streaming after completion

Generate the complete answer as today, split `answer.answer` into chunks, emit `agent.answer.delta` chunks, then emit `agent.answer.completed`.

Pros:

- Minimal backend change.
- Validates frontend append/reconcile behavior.
- Does not require changing `synthesize_agent_answer()`.

Cons:

- Not real model streaming.
- Does not reduce time-to-first-token.
- Only improves visual typing effect.

Use only as a temporary UI/protocol test.

### Option B: LangGraph messages streaming

Run LangGraph with `stream_mode=["updates", "messages"]` and inspect message metadata.

Expected mapping:

```text
updates  -> progress / context / artifact / step events
messages -> answer.delta only when the chunk belongs to answer synthesis
```

This option is only valid if message chunks from the final answer synthesis LLM call are actually visible to LangGraph streaming and can be filtered reliably.

Do not map all `messages` chunks to `agent.answer.delta`. ReAct planner/tool-selection model text and answer synthesis text are different product concepts.

### Option C: Explicit answer synthesis streaming

Change final answer generation so the LLM streams chunks while building the final `AgentAnswer`.

High-level flow:

```text
synthesize_agent_answer_stream(...)
  for chunk in model.stream(messages):
      emit agent.answer.delta(content=chunk_text)
      buffer chunk_text
  build AgentAnswer(answer="".join(buffer), ...)
  emit agent.answer.completed(answer_payload=agent_answer)
```

This is the most deterministic real streaming path if Option B cannot reliably capture the tool-internal LLM call.

The main design choice is how answer synthesis gets access to the event emitter.

#### C1. Preferred clean shape: answer synthesis node

Move final answer synthesis into an explicit graph node/path that can emit runtime events directly through the service-level mapper.

Pros:

- Clean separation between tool execution and user-facing answer streaming.
- Easier to keep answer events out of generic progress events.
- Easier to test as a graph/runtime behavior.

Cons:

- Requires a slightly larger graph refactor.

#### C2. Smaller incremental shape: tool callback

Keep `answer.synthesize` as a tool, but extend `ToolRunContext` with an optional answer-delta callback.

Example concept:

```python
ToolRunContext(..., emit_answer_delta: Callable[[str], None] | None = None)
```

Then `AnswerSynthesizeTool.run()` passes that callback into `synthesize_agent_answer()`.

Pros:

- Smaller change around the existing `answer.synthesize` tool.
- Keeps the current tool contract mostly intact.

Cons:

- Couples tool runtime to live event emission.
- Needs care so tests and non-SSE runs still work.

## Runtime Event Contract

Add to backend runtime types:

```python
AgentRuntimeEventType += "agent.answer.delta"
AgentRuntimeEvent.content: str | None = None
```

Add to frontend runtime types:

```ts
type AgentRuntimeEventType = ... | "agent.answer.delta"
interface AgentRuntimeEvent {
  content?: string | null
}
```

Delta event payload:

```json
{
  "type": "agent.answer.delta",
  "content": "partial answer text"
}
```

Completed event stays as-is:

```json
{
  "type": "agent.answer.completed",
  "answer": {
    "answer": "complete final answer",
    "key_findings": [],
    "evidence": [],
    "caveats": [],
    "recommendations": [],
    "follow_up_questions": []
  }
}
```

## Frontend Reducer Contract

Frontend behavior should be:

```text
agent.answer.delta:
  append event.content to assistant message content
  keep message status = streaming

agent.answer.completed:
  replace assistant message content with event.answer.answer
  set message status = completed
  store full AgentAnswer on the run
```

This makes streamed text fast but non-authoritative. Completed answer is authoritative.

## Persistence Policy

Do not persist every token-level `agent.answer.delta` by default.

Recommended policy:

- SSE emits answer delta events live.
- Runtime event store persists `agent.answer.completed` as the durable answer.
- If delta persistence is ever needed, batch by time or character count instead of one event per token.

Reason: token-level persistence can create hundreds or thousands of event rows for one answer.

## Testing Strategy

Backend tests:

- Runtime type accepts `agent.answer.delta` with `content`.
- Answer streaming emits one or more delta events before `agent.answer.completed`.
- `agent.answer.completed` remains emitted with complete `AgentAnswer`.
- Progress events are not used for final answer body text.
- Delta events are not persisted when persistence policy disables delta storage.

Frontend tests:

- `agent.answer.delta` appends text to the assistant message.
- `agent.answer.completed` replaces streamed text with the final complete answer.
- Existing `agent.answer.completed` behavior still works when no deltas are present.
- Run answer state remains the structured `AgentAnswer`, not plain streamed text.

## Next Discussion Points

1. Choose implementation path: LangGraph messages stream vs. explicit `model.stream(...)` in answer synthesis.
2. Decide whether to first land protocol/frontend append support with fake streaming.
3. Decide delta persistence policy implementation detail.
4. Audit current `answer.synthesize` and `synthesize_agent_answer()` tests before changing them to stream.
