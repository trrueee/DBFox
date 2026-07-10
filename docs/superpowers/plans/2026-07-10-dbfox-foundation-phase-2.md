# DBFox Foundation Redesign — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the session-coupled Agent runtime and fragile desktop streaming state with a run-scoped durable state machine, artifact-backed results, ordered event outbox, real cancellation, and bounded frontend state.

**Architecture:** Phase 2 consumes Phase 1's `CredentialVault`, `ConnectionFactory`, `ExecutionPolicy`, `ResultArtifact`, and Alembic-only metadata database. It creates a new `engine.agent_runtime` package rather than extending the existing mixed service/coordinator implementation. A run is the unit of execution, checkpointing, cancellation, approval, and SSE replay; a conversation is a projection over completed messages and runs.

**Tech Stack:** Python 3.12, FastAPI/SSE, SQLAlchemy 2, LangGraph, SQLite, React 19, TypeScript, Zustand, Vitest.

## Global Constraints

- Phase 1 must be accepted before starting this phase.
- Do not reuse legacy `AgentRun`, event, approval, checkpoint, or session-checkpoint behavior as a compatibility layer.
- `run_id`, not `session_id`, is the only LangGraph checkpoint namespace.
- A complete SQL result is stored as a Phase 1 `ResultArtifact`, never appended to graph state.
- Every externally visible event is persisted in the transactional outbox before it is streamed.
- A cancellation transition is terminal and cannot be overwritten by completion.
- The renderer never stores secrets; it uses only Phase 1 credential IDs.

---

## File Structure

- Create: `engine/agent_runtime/models.py`
  - Defines run state, approval, outbox, checkpoint reference, and versioned transition types.
- Create: `engine/agent_runtime/repository.py`
  - Owns transactional persistence and compare-and-swap transitions.
- Create: `engine/agent_runtime/state_machine.py`
  - Owns legal run transitions, approval consumption, and cancellation state.
- Create: `engine/agent_runtime/runner.py`
  - Starts/resumes a run-scoped graph and binds cancellation/checkpoint context.
- Create: `engine/agent_runtime/outbox.py`
  - Persists, replays, and dispatches ordered SSE events.
- Create: `engine/agent_runtime/checkpoints.py`
  - Owns lifespan-scoped saver and retention.
- Create: `engine/agent_runtime/artifacts.py`
  - Bridges SQL ResultArtifact references into Agent evidence.
- Create: `desktop/src/features/conversation/sseParser.ts`
  - Single stateful SSE parser with bounded buffers and EOF flushing.
- Create: `desktop/src/features/conversation/runController.ts`
  - Owns per-run AbortController and targeted cancellation.
- Create: `desktop/src/lib/csvSafety.ts`
  - Shared formula-safe cell conversion.
- Test: `engine/agent/tests/test_run_state_machine.py`
- Test: `engine/agent/tests/test_agent_outbox.py`
- Test: `engine/agent/tests/test_agent_cancellation.py`
- Test: `engine/agent/tests/test_agent_checkpoint_retention.py`
- Test: `engine/agent/tests/test_message_compaction_protocol.py`
- Test: `desktop/src/features/conversation/__tests__/sseParser.test.ts`
- Test: `desktop/src/features/conversation/__tests__/runController.test.ts`
- Test: `desktop/src/stores/__tests__/datasourceStore.race.test.ts`
- Test: `desktop/src/lib/__tests__/csvSafety.test.ts`
- Modify: `engine/api/agent.py`, `engine/agent/runtime.py`, `engine/agent/app/*`, `engine/agent_core/*`, `engine/agent/graph/*`, `engine/memory/*`
  - Move callers to the new runtime package, then delete legacy orchestration paths.
- Modify: `engine/models.py`, `engine/migrations/*`
  - Add v2 Agent run/outbox/artifact relations and delete/reset obsolete state structures.
- Modify: `desktop/src/stores/conversationStore.ts`, `desktop/src/stores/datasourceStore.ts`, `desktop/src/features/conversation/*`, `desktop/src/lib/api/*`, `desktop/src/features/workspace/artifacts/artifactActions.ts`
  - Use the new run/event API, robust parser, targeted cancellation, race guards, and CSV safety.

## Task 1: Introduce the Versioned Agent Run Data Model

**Files:**

- Create: `engine/agent_runtime/models.py`
- Create: `engine/agent_runtime/repository.py`
- Modify: `engine/models.py`
- Create: `engine/migrations/versions/4d6e8f0a1b2c_agent_runtime_v2.py`
- Test: `engine/agent/tests/test_run_state_machine.py`

**Interfaces:**

- Produces `RunStatus`, `RunRecord`, `ApprovalRecord`, `OutboxEventRecord`, and
  `RunVersionConflict`.
- Produces repository methods `create_run`, `transition`, `request_cancel`,
  `consume_approval`, and `list_events_after`.

- [ ] **Step 1: Write failing state-transition tests**

```python
def test_run_transition_uses_optimistic_version(db_session) -> None:
    run = repository.create_run(
        db_session,
        run_id="run-1",
        conversation_id="conv-1",
        datasource_id="ds-1",
        llm_credential_id="cred_llm_1",
    )

    repository.transition(
        db_session,
        run_id=run.id,
        expected_version=run.version,
        target=RunStatus.RUNNING,
    )

    with pytest.raises(RunVersionConflict):
        repository.transition(
            db_session,
            run_id=run.id,
            expected_version=run.version,
            target=RunStatus.CANCELLED,
        )


def test_terminal_cancel_cannot_be_overwritten_by_completion(db_session) -> None:
    run = seed_running_run(db_session)
    cancelled = repository.request_cancel(db_session, run.id, run.version)

    with pytest.raises(IllegalRunTransition):
        repository.transition(
            db_session,
            run_id=run.id,
            expected_version=cancelled.version,
            target=RunStatus.COMPLETED,
        )
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_run_state_machine.py -q
```

Expected: imports fail because the v2 state model does not exist.

- [ ] **Step 3: Implement the immutable run contract**

Create state definitions with exactly these legal transitions:

```python
class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


LEGAL_TRANSITIONS = {
    RunStatus.CREATED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.WAITING_APPROVAL, RunStatus.CANCELLING, RunStatus.COMPLETED, RunStatus.FAILED},
    RunStatus.WAITING_APPROVAL: {RunStatus.RUNNING, RunStatus.CANCELLING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.CANCELLING: {RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.CANCELLED: set(),
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
}
```

Use a `version` integer in every conditional SQLAlchemy update. Persist
immutable datasource ID, datasource generation, LLM credential ID, and the
run-scoped checkpoint namespace. Do not use session ID as a checkpoint ID.

- [ ] **Step 4: Run state-machine tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_run_state_machine.py -q
```

Expected: pass, including duplicate transition and terminal-state assertions.

## Task 2: Persist Agent Events Through a Transactional Outbox

**Files:**

- Create: `engine/agent_runtime/outbox.py`
- Modify: `engine/agent_runtime/repository.py`
- Modify: `engine/api/agent.py`
- Test: `engine/agent/tests/test_agent_outbox.py`

**Interfaces:**

- Produces `append_event_in_transaction(session, run_id, event_type, payload)`.
- Produces `replay_events(run_id, after_sequence) -> Iterator[PersistedEvent]`.
- Produces `GET /agent/runs/{run_id}/events?after_sequence=42`.

- [ ] **Step 1: Write outbox durability tests**

```python
def test_run_exists_before_started_event_is_observable(db_session) -> None:
    run = start_run_with_outbox(db_session, "run-1")
    event = next(replay_events(db_session, run.id, after_sequence=0))

    assert event.sequence == 1
    assert event.type == "agent.run.started"
    assert repository.get_run(db_session, run.id) is not None


def test_replay_returns_strictly_ordered_persisted_events(db_session) -> None:
    run = seed_run_with_events(db_session, event_count=3)
    events = list(replay_events(db_session, run.id, after_sequence=1))

    assert [event.sequence for event in events] == [2, 3]
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_agent_outbox.py -q
```

Expected: current live SSE/persistence ordering cannot satisfy the test.

- [ ] **Step 3: Implement outbox-first streaming**

Persist run state and event in the same DB transaction. Give each run an
atomic monotonic sequence. The SSE endpoint streams only persisted events and
can replay after a provided sequence. Delete the legacy buffered-event path
after first-party callers use the outbox.

- [ ] **Step 4: Run outbox/API tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_agent_outbox.py engine\tests\test_agent_api.py -q
```

Expected: pass without requiring a live LLM.

## Task 3: Implement Approval CAS, Run-Scoped Checkpoints, and Real Cancellation

**Files:**

- Create: `engine/agent_runtime/state_machine.py`
- Create: `engine/agent_runtime/runner.py`
- Create: `engine/agent_runtime/checkpoints.py`
- Modify: `engine/sql/execution/query_registry.py`
- Modify: `engine/api/agent.py`
- Test: `engine/agent/tests/test_agent_cancellation.py`
- Test: `engine/agent/tests/test_approval_resume.py`
- Test: `engine/agent/tests/test_agent_checkpoint_retention.py`

**Interfaces:**

- `approve_and_resume(run_id, approval_id, expected_checkpoint_version)`.
- `cancel_run(run_id)` requests durable cancellation and invokes active
  execution cancellation.
- `RunCheckpointManager` is created once in FastAPI lifespan and closed once.

- [ ] **Step 1: Write approval/cancel concurrency failures**

```python
def test_concurrent_resume_consumes_an_approval_once(db_session) -> None:
    approval = seed_waiting_approval(db_session, run_id="run-1", checkpoint_version=7)

    outcomes = run_concurrently(
        lambda: approve_and_resume(db_session_factory, "run-1", approval.id, 7),
        count=2,
    )

    assert sorted(outcome.code for outcome in outcomes) == ["APPROVAL_CONFLICT", "RESUMED"]


def test_cancel_interrupts_active_execution_before_completion(db_session, fake_query_registry) -> None:
    run = seed_running_run(db_session, execution_id="exec-1")
    cancel_run(db_session, run.id, query_registry=fake_query_registry)

    assert fake_query_registry.cancelled == ["exec-1"]
    assert repository.get_run(db_session, run.id).status is RunStatus.CANCELLING
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_approval_resume.py engine\agent\tests\test_agent_cancellation.py -q
```

Expected: legacy resume/cancel behavior permits duplicate or ineffective work.

- [ ] **Step 3: Implement run-scoped execution**

Approval records include `run_id`, `checkpoint_id`, `checkpoint_version`,
`status`, `consumed_at`, and expiry. A single transaction checks the waiting
run, approved record, checkpoint version, and unused state before consuming
the approval. The runner uses `thread_id=run_id` and resolves the credential
through Phase 1's vault at execution time.

Allocate an execution ID before the SQL begins. Cancellation calls the query
registry immediately, marks the run cancelling, and graph nodes inspect a
run-local cancellation token between model/tool steps. Completion uses a
conditional terminal transition and cannot overwrite a cancellation.

Build the LangGraph saver once in FastAPI lifespan. Active runs retain their
checkpoint; terminal runs have checkpoints removed on successful finalization
or by bounded retention cleanup.

- [ ] **Step 4: Run concurrency and lifecycle tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_approval_resume.py engine\agent\tests\test_agent_cancellation.py engine\agent\tests\test_agent_checkpoint_retention.py -q
```

Expected: pass, including a duplicate-resume race.

## Task 4: Move Full Query Results out of Graph State and Repair Context Semantics

**Files:**

- Create: `engine/agent_runtime/artifacts.py`
- Modify: `engine/agent/graph/state.py`
- Modify: `engine/tools/runtime/state_reducer.py`
- Modify: `engine/agent_core/answer.py`
- Modify: `engine/memory/memory_compactor.py`
- Modify: `engine/agent/context_pack.py`
- Modify: `engine/agent/nodes/turn_node.py`
- Test: `engine/agent/tests/test_agent_artifact_state.py`
- Test: `engine/agent/tests/test_message_compaction_protocol.py`
- Test: `engine/agent/tests/test_context_pack_current_goal.py`

**Interfaces:**

- Produces `AgentEvidenceArtifact(result_artifact_id, preview_rows, columns,
  row_count, truncation)`.
- Graph state accepts bounded evidence references only.

- [ ] **Step 1: Write state-size and protocol tests**

```python
def test_graph_state_keeps_only_preview_and_result_artifact_id() -> None:
    state = reduce_sql_execution(
        initial_state(),
        execution_with_rows(row_count=10_000, payload_bytes=2_000_000),
    )

    unit = state["analysis_units"][0]
    assert unit["result_artifact_id"].startswith("result_")
    assert len(unit["preview_rows"]) <= 10
    assert "rows" not in unit


def test_compaction_keeps_tool_result_immediately_after_its_ai_call() -> None:
    compacted = compact_messages(messages_with_tool_call_and_result_over_limit())
    assert_tool_protocol_order(compacted)


def test_context_pack_uses_current_state_question_not_old_history() -> None:
    pack = build_context_pack(state_with_old_and_new_questions())
    assert pack.user_goal == "new question"
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_agent_artifact_state.py engine\agent\tests\test_message_compaction_protocol.py engine\agent\tests\test_context_pack_current_goal.py -q
```

Expected: current state contains full rows, compaction reorders tools, and
ContextPack selects the old message.

- [ ] **Step 3: Implement artifact-backed evidence**

Have SQL tools create/read Phase 1 `ResultArtifact` records. Replace result
rows in graph state with a bounded preview, truncation metadata, and artifact
ID. Make final answer code retrieve only the required bounded evidence.

Compact messages by selecting original indices and retaining each AI tool-call
plus its ToolMessage(s) as one atomic ordered group. Make `state.question` the
authoritative current goal and replace, rather than append, rolling summaries
under a fixed character/token budget.

- [ ] **Step 4: Run state/context tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests\test_agent_artifact_state.py engine\agent\tests\test_message_compaction_protocol.py engine\agent\tests\test_context_pack_current_goal.py -q
```

Expected: pass and state/checkpoint payload is bounded.

## Task 5: Replace Desktop LLM/Run/SSE State with Targeted, Bounded Controllers

**Files:**

- Create: `desktop/src/features/conversation/sseParser.ts`
- Create: `desktop/src/features/conversation/runController.ts`
- Modify: `desktop/src/lib/api/agent.ts`
- Modify: `desktop/src/features/conversation/conversationRepository.ts`
- Modify: `desktop/src/features/conversation/streamEventBatcher.ts`
- Modify: `desktop/src/stores/conversationStore.ts`
- Modify: `desktop/src/lib/llmConfig.ts`
- Modify: `desktop/src/stores/datasourceStore.ts`
- Test: `desktop/src/features/conversation/__tests__/sseParser.test.ts`
- Test: `desktop/src/features/conversation/__tests__/runController.test.ts`
- Test: `desktop/src/stores/__tests__/datasourceStore.race.test.ts`

**Interfaces:**

- Produces `SseParser.push(chunk)`, `finish()`, and bounded parse errors.
- Produces `RunController.start(runId, conversationId)`, `cancel(runId)`, and
  `finish(runId)`.
- Requires `agentApi.cancelAgentRun(runId)` for every user cancellation.

- [ ] **Step 1: Write SSE and targeted-cancel failures**

```typescript
it("parses a CRLF separator split across chunks and flushes EOF", () => {
  const parser = new SseParser();
  expect(parser.push("event: agent.answer.delta\r")).toEqual([]);
  expect(parser.push("\ndata: {\"text\":\"A\"}\r\n\r")).toEqual([]);
  expect(parser.push("\n")).toEqual([{ type: "agent.answer.delta", data: { text: "A" } }]);
  expect(parser.finish()).toEqual([]);
});


it("cancels only the addressed run and calls the backend", async () => {
  const controller = new RunController(fakeCancelApi);
  controller.start("run-a", "conversation-a");
  controller.start("run-b", "conversation-b");

  await controller.cancel("run-a");

  expect(fakeCancelApi).toHaveBeenCalledWith("run-a");
  expect(controller.isAborted("run-a")).toBe(true);
  expect(controller.isAborted("run-b")).toBe(false);
});
```

- [ ] **Step 2: Run frontend tests and verify red**

Run:

```powershell
npx vitest run src/features/conversation/__tests__/sseParser.test.ts src/features/conversation/__tests__/runController.test.ts src/stores/__tests__/datasourceStore.race.test.ts --maxWorkers=1
```

Expected: new modules are absent and current global abort/stale response logic
cannot satisfy the assertions.

- [ ] **Step 3: Implement one parser and run controller**

Make every Agent/conversation stream use `SseParser`; remove duplicated parser
logic. Retain raw buffer until a complete logical line separator is present,
flush `TextDecoder` at EOF, parse a terminal residual event, and cap buffer
and event sizes.

Use `RunController` instead of a global AbortController collection. On cancel,
abort only that fetch and call the backend API. Ensure batcher flushes before
terminal rehydration and uses a timeout fallback when rAF is unavailable.

For schema fetches, increment a generation value before each request and apply
responses only when both generation and active datasource ID still match.

- [ ] **Step 4: Run frontend race tests**

Run:

```powershell
npx vitest run src/features/conversation/__tests__/sseParser.test.ts src/features/conversation/__tests__/runController.test.ts src/stores/__tests__/datasourceStore.race.test.ts src/stores/__tests__/conversationStore.test.ts --maxWorkers=1
```

Expected: pass; no test may call a real `127.0.0.1` service.

## Task 6: Add Conversation Pagination, CSV Safety, and Bounded UI Caches

**Files:**

- Create: `desktop/src/lib/csvSafety.ts`
- Modify: `engine/agent_core/persistence/conversation_records.py`
- Modify: `engine/api/conversations.py`
- Modify: `desktop/src/features/workspace/artifacts/artifactActions.ts`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/useSqlBackedDataView.ts`
- Test: `engine/tests/test_conversation_pagination.py`
- Test: `desktop/src/lib/__tests__/csvSafety.test.ts`
- Test: `desktop/src/features/workspace/table/__tests__/tablePreviewCache.test.ts`

- [ ] **Step 1: Write pagination/CSV/cache failures**

```python
def test_conversation_summary_endpoint_returns_cursor_page_not_all_records(db_session) -> None:
    seed_conversations(db_session, count=75)
    page = list_conversation_summaries(db_session, limit=50, cursor=None)

    assert len(page.items) == 50
    assert page.next_cursor is not None
```

```typescript
it.each(["=1+1", "\t=1+1", " \r@SUM(A1:A2)", "\uFEFF+1+1"])(
  "forces formula-like cell %s to text",
  (value) => expect(toSafeCsvCell(value)).toMatch(/^'/),
);

it("bounds preview cache and aborts superseded searches", async () => {
  const cache = new TablePreviewCache({ maxEntries: 20 });
  await fillCache(cache, 25);
  expect(cache.size).toBe(20);
});
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_conversation_pagination.py -q
npx vitest run src/lib/__tests__/csvSafety.test.ts src/features/workspace/table/__tests__/tablePreviewCache.test.ts --maxWorkers=1
```

Expected: current unbounded data paths fail the contract.

- [ ] **Step 3: Implement bounded data APIs**

Return cursor-paginated summaries and event pages. Do not eager-load all
messages/runs/artifacts/events into summary endpoints. Extract one CSV formula
safety function and use it for inline artifacts and backend-contracted exports.
Replace the global preview Map with an LRU capped at 20 entries, debounce
searches 300 ms, and abort superseded requests.

- [ ] **Step 4: Run pagination/cache tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_conversation_pagination.py -q
npx vitest run src/lib/__tests__/csvSafety.test.ts src/features/workspace/table/__tests__/tablePreviewCache.test.ts --maxWorkers=1
```

Expected: pass.

## Task 7: Verify and Commit Phase 2

- [ ] **Step 1: Run Agent and frontend focused suites**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\agent\tests engine\tests\test_agent_api.py engine\tests\test_conversation_pagination.py -q -m "not real_llm and not e2e"
npx vitest run src/features/conversation src/stores src/lib --maxWorkers=1
```

Expected: pass without live LLM/database/network dependencies.

- [ ] **Step 2: Measure state and event budgets**

Run benchmark tests that create 20 large-result artifacts and 5,000 stream
deltas. Assert a completed run checkpoint remains below 2 MiB, a live event
queue remains bounded, and 5,000 reducer events complete in less than 100 ms.

- [ ] **Step 3: Commit Phase 2**

```powershell
git add engine/agent_runtime engine/agent engine/agent_core engine/memory engine/api desktop/src engine/models.py engine/migrations
git commit -m "refactor: replace agent runtime with durable run state machine"
```
