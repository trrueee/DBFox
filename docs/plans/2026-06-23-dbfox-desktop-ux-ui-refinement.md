# DBFox Desktop UX/UI Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the UX/UI review into a stable, professional desktop Agent workspace: fewer streaming re-renders, no trace jump on completion, clearer phase progress, reusable artifact shell, more polished SQL/table/chart artifacts, and token-consistent light/dark surfaces.

**Architecture:** The work is split into four layers. First stabilize `RunTracePanel` and streaming state updates, then isolate conversation view models and list indexing, then introduce reusable artifact presentation primitives, and finally add restrained motion and chart focus behavior. Each task is independently testable and should be committed separately.

**Tech Stack:** React 19, TypeScript, Zustand 5, Vitest, Testing Library, CSS tokens, ECharts via `echarts-for-react`, Monaco via `@monaco-editor/react`, existing CSS animation utilities. Do not add `framer-motion`; use CSS transitions/animations and existing dependencies.

---

## Requirements Source

This plan implements the review attached at:

`C:\Users\Lenovo\.codex\attachments\1fd66ba9-f301-40ff-8c68-69a066eb9d84\pasted-text.txt`

Primary requirements from the report:

- Fix `RunTracePanel` phase status merging so `running` does not stay sticky after a later success/completed event.
- Replace native `<details open={run.status === ...}>` trace shell with controlled state so completion does not collapse the panel abruptly.
- Add a compact phase progress strip above the detailed stage list.
- Stop `ConversationWorkspace` from subscribing to the whole conversation store.
- Avoid O(messages x runs/artifacts) lookup in `MessageList`.
- Batch/throttle streaming events and avoid store writes when the derived value has not changed.
- Replace artifact `if` chains with a registry and introduce a reusable `ArtifactCard` shell.
- Improve SQL artifact rendering with read-only Monaco.
- Improve table artifacts toward a data-grid feel while keeping current result paging behavior.
- Add chart focus/expanded analysis behavior and remove `document.querySelector` chart export.
- Continue token cleanup for surfaces/radius/shadow, especially table, toolbar, input, tab, and artifact surfaces.
- Add low-noise message and panel motion respecting `prefers-reduced-motion`.

## File Structure

### Run Trace

- `desktop/src/features/conversation/workspace/runTraceModel.ts`
  - Owns event filtering, phase classification, status merging, context references, repair summaries, and run summary text.
- `desktop/src/features/conversation/workspace/RunTracePanel.tsx`
  - Renders the controlled trace shell, summary button, phase stepper, repair/context cards, stage list, and debug details.
- `desktop/src/features/conversation/workspace/RunPhaseStepper.tsx`
  - Renders a compact 9-phase progress strip from model output.
- `desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx`
  - Covers trace rendering and controlled expansion behavior.
- `desktop/src/features/conversation/workspace/__tests__/runTraceModel.test.ts`
  - Covers pure phase/status/model behavior.

### Conversation Streaming And View Model

- `desktop/src/features/conversation/workspace/useConversationViewModel.ts`
  - Selects only the current conversation data/actions from Zustand.
- `desktop/src/features/conversation/workspace/MessageList.tsx`
  - Uses memoized maps for run/artifact lookup and CSS message entry animation.
- `desktop/src/features/conversation/workspace/__tests__/MessageList.test.tsx`
  - Covers O(M+N) mapping behavior through rendered output.
- `desktop/src/stores/conversationStore.ts`
  - Adds `applyStreamEvents`, no-op guards, and batched stream event application.
- `desktop/src/stores/agentStore.ts`
  - Adds no-op guards and requestAnimationFrame batching for the legacy workspace stream path.
- `desktop/src/stores/__tests__/conversationStore.test.ts`
  - Covers duplicate/no-op stream events and batched event application.
- `desktop/src/stores/__tests__/agentStore.test.ts`
  - Covers legacy event handler avoiding unchanged timeline writes.

### Artifact Presentation

- `desktop/src/features/workspace/artifacts/ArtifactCard.tsx`
  - Reusable artifact shell with icon, title, badge, description, meta, body, and actions slots.
- `desktop/src/features/workspace/artifacts/ArtifactRenderer.tsx`
  - Uses a typed renderer registry instead of `if` chain.
- `desktop/src/features/workspace/artifacts/SqlArtifactView.tsx`
  - Uses `ArtifactCard` and read-only Monaco.
- `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
  - Becomes an orchestrator after extracting focused subcomponents/hooks.
- `desktop/src/features/workspace/artifacts/table/useArtifactTableData.ts`
  - Owns search, sorting, backend result paging, CSV rows, loading, warnings, notices.
- `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx`
  - Owns table rendering, numeric alignment, null pill, sticky header, row hover state.
- `desktop/src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx`
  - Owns search, refresh, export, copy controls.
- `desktop/src/features/workspace/artifacts/table/ArtifactTableFooter.tsx`
  - Owns row count, latency, truncation, page controls.
- `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`
  - Uses `ref` for ECharts instance, supports expanded focus height and resize.
- `desktop/src/features/workspace/artifacts/useChartTheme.ts`
  - Reads CSS chart/text/font tokens.
- `desktop/src/features/workspace/artifacts/useChartOption.ts`
  - Builds ECharts option from artifact, chart type, compact state, and theme.
- `desktop/src/features/workspace/artifacts/useChartExport.ts`
  - Exports PNG from ECharts instance.

### Styling And Tokens

- `desktop/src/styles/tokens.css`
  - Adds missing semantic surface/radius/shadow aliases used by artifacts and trace.
- `desktop/src/App.css`
  - Replaces remaining high-frequency hardcoded surface/radius/shadow values.
- `desktop/src/features/conversation/workspace/conversationWorkspace.css`
  - Adds trace controlled panel styles, phase stepper, message entry animation, artifact polish.
- `desktop/src/components/data-grid/data-grid.css`
  - Aligns table/data-grid visual language with artifact table styling.
- `desktop/src/__tests__/agentVisualTokens.test.ts`
  - Extends token guard for surfaces/radius/shadow and artifact CSS.

---

### Task 1: Extract Run Trace Model And Fix Sticky Running Status

**Files:**
- Create: `desktop/src/features/conversation/workspace/runTraceModel.ts`
- Create: `desktop/src/features/conversation/workspace/__tests__/runTraceModel.test.ts`
- Modify: `desktop/src/features/conversation/workspace/RunTracePanel.tsx`
- Test: `desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx`

- [ ] **Step 1: Write the failing model test**

Create `desktop/src/features/conversation/workspace/__tests__/runTraceModel.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ConversationRun } from "../../../../types/conversation";
import { buildRunTraceModel } from "../runTraceModel";

describe("runTraceModel", () => {
  it("uses the latest successful phase event instead of keeping running sticky", () => {
    const run: ConversationRun = {
      id: "run-1",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析订单",
      status: "completed",
      events: [
        {
          event_id: "validate-started",
          run_id: "run-1",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.step.started",
          step: {
            phase: "validating",
            tool_name: "sql.validate",
            status: "running",
            summary: "正在校验 SQL",
          },
        },
        {
          event_id: "validate-completed",
          run_id: "run-1",
          sequence: 2,
          created_at_ms: 2,
          type: "agent.step.completed",
          step: {
            phase: "validating",
            tool_name: "sql.validate",
            status: "completed",
            summary: "只读 SQL，可执行",
          },
        },
      ],
    };

    const model = buildRunTraceModel(run);

    expect(model.stages).toHaveLength(1);
    expect(model.stages[0]).toMatchObject({
      phase: "validating",
      status: "success",
      summary: "只读 SQL，可执行",
    });
  });

  it("keeps a failed phase failed even when later informational events arrive", () => {
    const run: ConversationRun = {
      id: "run-2",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析退款",
      status: "failed",
      events: [
        {
          event_id: "execute-failed",
          run_id: "run-2",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.step.failed",
          step: {
            phase: "executing",
            tool_name: "sql.execute_readonly",
            status: "failed",
            summary: "字段不存在",
          },
        },
        {
          event_id: "execute-observed",
          run_id: "run-2",
          sequence: 2,
          created_at_ms: 2,
          type: "agent.progress.update",
          step: {
            phase: "executing",
            status: "success",
            summary: "准备修复",
          },
        },
      ],
    };

    const model = buildRunTraceModel(run);

    expect(model.stages[0].status).toBe("failed");
    expect(model.stages[0].summary).toBe("准备修复");
  });
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd desktop
npm run test -- --run src/features/conversation/workspace/__tests__/runTraceModel.test.ts
```

Expected: FAIL because `runTraceModel.ts` does not exist.

- [ ] **Step 3: Move pure trace logic into `runTraceModel.ts`**

Create `desktop/src/features/conversation/workspace/runTraceModel.ts` with the logic currently embedded in `RunTracePanel.tsx`. Export these types/functions:

```ts
import type { AgentRuntimeEvent } from "../../../lib/api/types";
import type { ConversationRun } from "../../../types/conversation";

export const PHASE_ORDER = [
  "understanding",
  "searching_schema",
  "inspecting",
  "generating_sql",
  "validating",
  "executing",
  "repairing",
  "synthesizing",
  "completed",
] as const;

export type TimelinePhase = (typeof PHASE_ORDER)[number] | "approval";

export const PHASE_LABELS: Record<TimelinePhase, string> = {
  understanding: "理解问题",
  searching_schema: "搜索结构",
  inspecting: "检查数据",
  generating_sql: "生成 SQL",
  validating: "安全校验",
  executing: "执行查询",
  repairing: "自动修复",
  synthesizing: "整理回答",
  completed: "完成",
  approval: "等待确认",
};

export interface TimelineStage {
  phase: TimelinePhase;
  label: string;
  status: "idle" | "running" | "success" | "failed";
  summary: string;
  events: AgentRuntimeEvent[];
}

export interface RunTraceModel {
  events: AgentRuntimeEvent[];
  stages: TimelineStage[];
  contextReferences: Array<{ kind: "memory" | "semantic"; title: string; items: ContextReference[] }>;
  repairSummaries: RepairSummary[];
  summary: string;
}

interface ContextReference {
  label: string;
  summary: string;
  source: string;
}

interface RepairSummary {
  key: string;
  attemptLabel: string;
  errorClass: string;
  update: string;
  failedSql: string;
  rootCause: string;
  recoveryStrategy: string;
}

export function buildRunTraceModel(run: ConversationRun): RunTraceModel {
  const events = (run.events || []).filter((event) => String(event.type) !== "agent.answer.delta");
  const stages = buildTimelineStages(run, events);
  return {
    events,
    stages,
    contextReferences: contextReferenceCards(events),
    repairSummaries: repairSummaryCards(events),
    summary: runSummary(run, events, stages),
  };
}
```

Use this status merge in the same file:

```ts
function eventStatus(event: AgentRuntimeEvent): TimelineStage["status"] {
  const rawType = String(event.type);
  const status = stepValue(event, "status").toLowerCase();
  if (rawType.includes("failed") || status === "failed" || status === "error") return "failed";
  if (rawType.includes("completed") || status === "success" || status === "completed") return "success";
  if (rawType.includes("started") || status === "running") return "running";
  return "success";
}

function mergeStageStatus(
  current: TimelineStage["status"],
  next: TimelineStage["status"],
): TimelineStage["status"] {
  if (current === "failed" || next === "failed") return "failed";
  return next;
}
```

- [ ] **Step 4: Update `RunTracePanel.tsx` to use the model**

Replace the local model-building variables:

```tsx
const { stages, contextReferences, repairSummaries, summary } = buildRunTraceModel(run);
```

Import:

```tsx
import { buildRunTraceModel, type TimelinePhase, type TimelineStage } from "./runTraceModel";
```

Keep rendering unchanged in this task except for removed local helpers.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/conversation/workspace/__tests__/runTraceModel.test.ts src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/features/conversation/workspace/runTraceModel.ts desktop/src/features/conversation/workspace/RunTracePanel.tsx desktop/src/features/conversation/workspace/__tests__/runTraceModel.test.ts desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx
git commit -m "fix: stabilize run trace phase status"
```

---

### Task 2: Replace Native Trace Details With Controlled Panel And Phase Stepper

**Files:**
- Create: `desktop/src/features/conversation/workspace/RunPhaseStepper.tsx`
- Modify: `desktop/src/features/conversation/workspace/RunTracePanel.tsx`
- Modify: `desktop/src/features/conversation/workspace/conversationWorkspace.css`
- Modify: `desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx`

- [ ] **Step 1: Add tests for completion without abrupt collapse**

Add this test to `RunTracePanel.test.tsx`:

```tsx
import { fireEvent } from "@testing-library/react";

it("keeps a running trace expanded when the same run completes", () => {
  const runningRun: ConversationRun = {
    id: "run-controlled",
    conversation_id: "conv-1",
    datasource_id: "ds-1",
    question: "分析订单",
    status: "running",
    events: [
      {
        event_id: "evt-running",
        run_id: "run-controlled",
        sequence: 1,
        created_at_ms: 1,
        type: "agent.step.started",
        step: { phase: "executing", status: "running", summary: "执行查询中" },
      },
    ],
  };
  const completedRun: ConversationRun = {
    ...runningRun,
    status: "completed",
    events: [
      ...runningRun.events,
      {
        event_id: "evt-completed",
        run_id: "run-controlled",
        sequence: 2,
        created_at_ms: 2,
        type: "agent.run.completed",
        step: { phase: "completed", status: "success", summary: "任务完成" },
      },
    ],
  };

  const { rerender, container } = render(<RunTracePanel run={runningRun} />);
  expect(container.querySelector(".conv-run-trace")?.getAttribute("data-expanded")).toBe("true");

  rerender(<RunTracePanel run={completedRun} />);

  expect(container.querySelector(".conv-run-trace")?.getAttribute("data-expanded")).toBe("true");
  expect(screen.getByText("任务完成")).toBeTruthy();
});

it("lets the user collapse and expand the trace manually", () => {
  const run: ConversationRun = {
    id: "run-toggle",
    conversation_id: "conv-1",
    datasource_id: "ds-1",
    question: "分析订单",
    status: "completed",
    events: [],
  };

  const { container } = render(<RunTracePanel run={run} />);
  const toggle = screen.getByRole("button", { name: /执行过程/ });

  expect(container.querySelector(".conv-run-trace")?.getAttribute("data-expanded")).toBe("false");
  fireEvent.click(toggle);
  expect(container.querySelector(".conv-run-trace")?.getAttribute("data-expanded")).toBe("true");
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd desktop
npm run test -- --run src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx
```

Expected: FAIL because the component still renders native `<details>` and does not expose `data-expanded`.

- [ ] **Step 3: Create `RunPhaseStepper.tsx`**

```tsx
import { PHASE_LABELS, PHASE_ORDER, type TimelineStage } from "./runTraceModel";

export function RunPhaseStepper({ stages }: { stages: TimelineStage[] }) {
  const byPhase = new Map(stages.map((stage) => [stage.phase, stage]));
  return (
    <div className="conv-phase-stepper" aria-label="Agent execution phases">
      {PHASE_ORDER.map((phase) => {
        const status = byPhase.get(phase)?.status ?? "idle";
        return (
          <span
            key={phase}
            className={`conv-phase-dot is-${status}`}
            title={PHASE_LABELS[phase]}
            aria-label={`${PHASE_LABELS[phase]} ${status}`}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Implement controlled trace shell**

In `RunTracePanel.tsx`, import hooks and stepper:

```tsx
import { useEffect, useRef, useState } from "react";
import { RunPhaseStepper } from "./RunPhaseStepper";
```

Replace `<details>` with:

```tsx
const initiallyExpanded = run.status === "running" || run.status === "failed" || run.status === "waiting_approval";
const [expanded, setExpanded] = useState(initiallyExpanded);
const userToggledRef = useRef(false);

useEffect(() => {
  if (run.status === "running" || run.status === "failed" || run.status === "waiting_approval") {
    setExpanded(true);
    return;
  }
  if (!userToggledRef.current && run.status === "completed") {
    setExpanded((value) => value);
  }
}, [run.status]);

const toggleExpanded = () => {
  userToggledRef.current = true;
  setExpanded((value) => !value);
};
```

Render shell:

```tsx
<section className="conv-run-trace" data-expanded={expanded ? "true" : "false"}>
  <button
    type="button"
    className="conv-run-trace-summary"
    aria-expanded={expanded}
    onClick={toggleExpanded}
  >
    {run.status === "failed" ? <XCircle size={14} /> : <Activity size={14} />}
    <span>{summary}</span>
    {stages.length > 0 && <span className="conv-run-count">{stages.length}</span>}
  </button>
  <RunPhaseStepper stages={stages} />
  <div className="conv-run-trace-body" hidden={!expanded}>
    {/* existing trace body */}
  </div>
</section>
```

- [ ] **Step 5: Add CSS for the controlled shell and progress strip**

In `conversationWorkspace.css`, replace `summary` selectors with `.conv-run-trace-summary` selectors and add:

```css
.conv-run-trace {
  overflow: hidden;
}

.conv-run-trace-summary {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  padding: 0 0 8px;
  background: transparent;
  color: var(--agent-text-muted);
  font: inherit;
  font-size: var(--agent-font-title);
  cursor: pointer;
  text-align: left;
}

.conv-phase-stepper {
  display: grid;
  grid-template-columns: repeat(9, minmax(0, 1fr));
  gap: 4px;
  margin: 2px 0 12px;
}

.conv-phase-dot {
  position: relative;
  height: 3px;
  border-radius: var(--radius-pill);
  background: var(--agent-border);
  overflow: hidden;
}

.conv-phase-dot.is-success {
  background: var(--agent-accent);
}

.conv-phase-dot.is-failed {
  background: var(--trust-danger);
}

.conv-phase-dot.is-running {
  background: var(--agent-accent-soft);
}

@media (prefers-reduced-motion: no-preference) {
  .conv-phase-dot.is-running::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, var(--agent-accent), transparent);
    animation: conv-phase-scan 1.1s ease-in-out infinite;
  }

  .conv-run-trace[data-expanded="true"] .conv-run-trace-body {
    animation: conv-trace-open 180ms cubic-bezier(0.16, 1, 0.3, 1) both;
  }
}

@keyframes conv-phase-scan {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}

@keyframes conv-trace-open {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 6: Update old tests that expect native `details`**

Replace checks like:

```ts
expect(container.querySelector("details")?.hasAttribute("open")).toBe(false);
```

With:

```ts
expect(container.querySelector(".conv-run-trace")?.getAttribute("data-expanded")).toBe("false");
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx src/features/conversation/workspace/__tests__/runTraceModel.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/conversation/workspace/RunPhaseStepper.tsx desktop/src/features/conversation/workspace/RunTracePanel.tsx desktop/src/features/conversation/workspace/conversationWorkspace.css desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx
git commit -m "feat: add controlled run trace progress"
```

---

### Task 3: Add Conversation View Model Selectors And O(M+N) Message Mapping

**Files:**
- Create: `desktop/src/features/conversation/workspace/useConversationViewModel.ts`
- Create: `desktop/src/features/conversation/workspace/__tests__/MessageList.test.tsx`
- Modify: `desktop/src/features/conversation/workspace/ConversationWorkspace.tsx`
- Modify: `desktop/src/features/conversation/workspace/MessageList.tsx`

- [ ] **Step 1: Write MessageList mapping test**

Create `MessageList.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../../types/conversation";
import { MessageList } from "../MessageList";

describe("MessageList", () => {
  beforeEach(() => cleanup());

  it("attaches runs and artifacts to the addressed assistant message", () => {
    const messages: ConversationMessage[] = [
      {
        id: "user-1",
        conversation_id: "conv-1",
        role: "user",
        content: "分析订单",
        status: "completed",
        sequence: 1,
        created_at: null,
        updated_at: null,
      },
      {
        id: "assistant-1",
        conversation_id: "conv-1",
        role: "assistant",
        content: "订单查询完成。",
        status: "completed",
        sequence: 2,
        created_at: null,
        updated_at: null,
      },
    ];
    const runs: ConversationRun[] = [
      {
        id: "run-1",
        conversation_id: "conv-1",
        datasource_id: "ds-1",
        question: "分析订单",
        assistant_message_id: "assistant-1",
        status: "completed",
        answer: {
          answer: "订单查询完成。",
          key_findings: [],
          evidence: [{ artifact_id: "sql_candidate", label: "SQL #1" }],
          caveats: [],
          recommendations: [],
          follow_up_questions: [],
        },
        events: [],
      },
    ];
    const artifacts: ConversationArtifact[] = [
      {
        id: "artifact-sql",
        semantic_id: "sql_candidate",
        conversation_id: "conv-1",
        run_id: "run-1",
        message_id: "assistant-1",
        type: "sql",
        title: "SQL",
        status: "completed",
        payload: { sql: "SELECT id FROM orders" },
        depends_on: [],
      },
    ];

    render(
      <MessageList
        messages={messages}
        runs={runs}
        artifacts={artifacts}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onResolveApproval={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "SQL #1" })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run the test**

Run:

```bash
cd desktop
npm run test -- --run src/features/conversation/workspace/__tests__/MessageList.test.tsx
```

Expected: PASS before optimization. This test locks current behavior before changing lookup strategy.

- [ ] **Step 3: Create `useConversationViewModel.ts`**

```ts
import { useMemo } from "react";
import { useConversationStore } from "../../../stores/conversationStore";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../types/conversation";

export function useConversationViewModel(conversationId: string) {
  const detail = useConversationStore((state) => state.detailById[conversationId]);
  const messagesById = useConversationStore((state) => state.messagesById);
  const runsById = useConversationStore((state) => state.runsById);
  const artifactsById = useConversationStore((state) => state.artifactsById);
  const openConversation = useConversationStore((state) => state.openConversation);
  const sendMessage = useConversationStore((state) => state.sendMessage);
  const cancelRun = useConversationStore((state) => state.cancelRun);
  const resolveApproval = useConversationStore((state) => state.resolveApproval);

  const messages = useMemo<ConversationMessage[]>(
    () => detail?.messages.map((item) => messagesById[item.id] || item) || [],
    [detail, messagesById],
  );

  const runs = useMemo<ConversationRun[]>(
    () => detail?.runs.map((item) => runsById[item.id] || item) || [],
    [detail, runsById],
  );

  const artifacts = useMemo<ConversationArtifact[]>(
    () =>
      detail?.artifacts.map((item) => artifactsById[item.id] || item) ||
      Object.values(artifactsById).filter((item) => item.conversation_id === conversationId),
    [artifactsById, conversationId, detail],
  );

  const runningRun = useMemo(
    () => runs.find((run) => run.status === "running" || run.status === "waiting_approval") || null,
    [runs],
  );

  return {
    detail,
    messages,
    runs,
    artifacts,
    runningRun,
    openConversation,
    sendMessage,
    cancelRun,
    resolveApproval,
  };
}
```

- [ ] **Step 4: Update `ConversationWorkspace.tsx`**

Replace:

```tsx
const store = useConversationStore();
const detail = store.detailById[conversationId];
```

With:

```tsx
const {
  detail,
  messages,
  runs,
  artifacts,
  runningRun,
  openConversation,
  sendMessage,
  cancelRun,
  resolveApproval,
} = useConversationViewModel(conversationId);
```

Use:

```tsx
useEffect(() => {
  if (!detail && conversationId) void openConversation(conversationId);
}, [conversationId, detail, openConversation]);
```

And update callbacks:

```tsx
onResolveApproval={(runId, approvalId, approved) => void resolveApproval(runId, approvalId, approved)}
onSend={(text) => void sendMessage(conversationId, text)}
onCancel={() => runningRun && cancelRun(runningRun.id)}
```

- [ ] **Step 5: Optimize `MessageList.tsx` lookup**

Change imports:

```tsx
import { useEffect, useMemo, useRef } from "react";
```

Add maps:

```tsx
const runsByAssistantMessageId = useMemo(
  () => new Map(runs.map((run) => [run.assistant_message_id, run])),
  [runs],
);

const artifactsByMessageId = useMemo(() => {
  const map = new Map<string, ConversationArtifact[]>();
  for (const artifact of artifacts) {
    const key = artifact.message_id || "";
    map.set(key, [...(map.get(key) || []), artifact]);
  }
  return map;
}, [artifacts]);
```

Replace per-message lookup:

```tsx
const run = runsByAssistantMessageId.get(message.id);
const messageArtifacts = artifactsByMessageId.get(message.id) || [];
```

- [ ] **Step 6: Add message entry animation**

In `conversationWorkspace.css`:

```css
@media (prefers-reduced-motion: no-preference) {
  .conv-message {
    animation: conv-message-in 180ms cubic-bezier(0.16, 1, 0.3, 1) both;
  }
}

@keyframes conv-message-in {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.985);
    filter: blur(2px);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
    filter: blur(0);
  }
}
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/conversation/workspace/__tests__/MessageList.test.tsx src/features/conversation/workspace/__tests__/MessageBubble.test.tsx src/stores/__tests__/conversationStore.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/conversation/workspace/useConversationViewModel.ts desktop/src/features/conversation/workspace/ConversationWorkspace.tsx desktop/src/features/conversation/workspace/MessageList.tsx desktop/src/features/conversation/workspace/conversationWorkspace.css desktop/src/features/conversation/workspace/__tests__/MessageList.test.tsx
git commit -m "perf: isolate conversation workspace rendering"
```

---

### Task 4: Batch Stream Events And Avoid No-Op Store Writes

**Files:**
- Create: `desktop/src/features/conversation/streamEventBatcher.ts`
- Modify: `desktop/src/stores/conversationStore.ts`
- Modify: `desktop/src/stores/agentStore.ts`
- Modify: `desktop/src/stores/__tests__/conversationStore.test.ts`
- Modify: `desktop/src/stores/__tests__/agentStore.test.ts`

- [ ] **Step 1: Add conversation store no-op tests**

Add to `conversationStore.test.ts`:

```ts
it("does not replace a run when a duplicate event is ignored", () => {
  const store = useConversationStore.getState();
  store.loadConversation({
    id: "conv-events",
    title: "Events",
    datasource_id: "ds-1",
    context_tables: [],
    created_at: null,
    updated_at: null,
    messages: [
      {
        id: "assistant-events",
        conversation_id: "conv-events",
        role: "assistant",
        content: "",
        status: "streaming",
        sequence: 1,
        created_at: null,
        updated_at: null,
      },
    ],
    runs: [],
    artifacts: [],
    approvals: [],
  });
  const event = {
    event_id: "event-same",
    run_id: "run-events",
    sequence: 1,
    created_at_ms: 1,
    type: "agent.progress.update",
    conversation_id: "conv-events",
    assistant_message_id: "assistant-events",
    step: { phase: "understanding", status: "running", summary: "理解问题" },
  } as const;

  store.applyStreamEvent(event);
  const firstRun = useConversationStore.getState().runsById["run-events"];
  store.applyStreamEvent(event);

  expect(useConversationStore.getState().runsById["run-events"]).toBe(firstRun);
});

it("applies a batch of stream events in order", () => {
  const store = useConversationStore.getState();
  store.loadConversation({
    id: "conv-batch",
    title: "Batch",
    datasource_id: "ds-1",
    context_tables: [],
    created_at: null,
    updated_at: null,
    messages: [
      {
        id: "assistant-batch",
        conversation_id: "conv-batch",
        role: "assistant",
        content: "",
        status: "streaming",
        sequence: 1,
        created_at: null,
        updated_at: null,
      },
    ],
    runs: [],
    artifacts: [],
    approvals: [],
  });

  store.applyStreamEvents([
    {
      event_id: "event-1",
      run_id: "run-batch",
      sequence: 1,
      created_at_ms: 1,
      type: "agent.progress.update",
      conversation_id: "conv-batch",
      assistant_message_id: "assistant-batch",
      step: { phase: "understanding", status: "running", summary: "理解问题" },
    },
    {
      event_id: "event-2",
      run_id: "run-batch",
      sequence: 2,
      created_at_ms: 2,
      type: "agent.answer.completed",
      conversation_id: "conv-batch",
      assistant_message_id: "assistant-batch",
      message_id: "assistant-batch",
      answer: {
        answer: "完成",
        key_findings: [],
        evidence: [],
        caveats: [],
        recommendations: [],
        follow_up_questions: [],
      },
    },
  ]);

  const state = useConversationStore.getState();
  expect(state.runsById["run-batch"].events).toHaveLength(2);
  expect(state.messagesById["assistant-batch"].content).toBe("完成");
});
```

Also extend `ConversationActions` in the test expectations by using `store.applyStreamEvents`; this fails until implemented.

- [ ] **Step 2: Run failing store tests**

Run:

```bash
cd desktop
npm run test -- --run src/stores/__tests__/conversationStore.test.ts
```

Expected: FAIL because `applyStreamEvents` does not exist and duplicate event currently replaces state.

- [ ] **Step 3: Implement state equality helpers**

In `conversationStore.ts`, update `ConversationActions`:

```ts
applyStreamEvents: (events: ConversationStreamEvent[]) => void;
```

Add helpers near `withRunEvent`:

```ts
function sameMessagePatch(current: ConversationMessage, patch: Partial<ConversationMessage>): boolean {
  return Object.entries(patch).every(([key, value]) => current[key as keyof ConversationMessage] === value);
}
```

Update `upsertMessage`:

```ts
if (sameMessagePatch(current, patch)) return state;
```

Update `upsertRun`:

```ts
const current = state.runsById[run.id];
if (current === run) return state;
```

In `applyStreamEvent`, when `withRunEvent` returns the same run and no approval/status/answer changes are present, leave `next` unchanged.

- [ ] **Step 4: Add batch action**

Refactor the body of `applyStreamEvent` into a pure local function:

```ts
function reduceStreamEvent(state: ConversationStore, event: ConversationStreamEvent): ConversationStore {
  let next = ensureStreamMessages(state, event);
  // move the current applyStreamEvent reducer body here
  return next;
}
```

Then implement:

```ts
applyStreamEvent: (event) => {
  set((state) => reduceStreamEvent(state, event));
},

applyStreamEvents: (events) => {
  if (events.length === 0) return;
  set((state) => events.reduce(reduceStreamEvent, state));
},
```

- [ ] **Step 5: Add requestAnimationFrame batcher**

Create `desktop/src/features/conversation/streamEventBatcher.ts`:

```ts
export function createStreamEventBatcher<T>(flush: (events: T[]) => void) {
  let queue: T[] = [];
  let scheduled = false;

  const schedule = typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
    ? window.requestAnimationFrame.bind(window)
    : (callback: FrameRequestCallback) => window.setTimeout(() => callback(Date.now()), 16);

  return (event: T) => {
    queue.push(event);
    if (scheduled) return;
    scheduled = true;
    schedule(() => {
      scheduled = false;
      const batch = queue;
      queue = [];
      flush(batch);
    });
  };
}
```

In `conversationStore.sendMessage`:

```ts
const batchEvent = createStreamEventBatcher<ConversationStreamEvent>((events) => get().applyStreamEvents(events));
await startConversationMessageStream(
  conversationId,
  request,
  { signal: abortController.signal, onEvent: batchEvent },
);
```

Import:

```ts
import { createStreamEventBatcher } from "../features/conversation/streamEventBatcher";
```

- [ ] **Step 6: Guard legacy `agentStore` timeline writes**

In `agentStore.ts`, update the handler:

```ts
const nextTimeline = appendAgentRuntimeEvent(timelineBox.list, event);
if (nextTimeline !== timelineBox.list) {
  timelineBox.list = nextTimeline;
  ws().patchTabTimeline(tabId, () => nextTimeline);
}
```

For artifact deltas:

```ts
const nextArtifacts = mergeArtifactDelta(artifactsBox.list, delta.artifact_id, delta.payload_merge);
if (nextArtifacts !== artifactsBox.list) {
  artifactsBox.list = nextArtifacts;
  ws().patchTab(tabId, { artifacts: toViewArtifacts(nextArtifacts) });
}
```

Wrap the handler with an RAF batcher if the existing tests can expose `makeAgentEventHandler`; otherwise keep the no-op guard in this task and add batching only to the conversation path, which is the primary route.

- [ ] **Step 7: Run store tests**

Run:

```bash
cd desktop
npm run test -- --run src/stores/__tests__/conversationStore.test.ts src/stores/__tests__/agentStore.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/conversation/streamEventBatcher.ts desktop/src/stores/conversationStore.ts desktop/src/stores/agentStore.ts desktop/src/stores/__tests__/conversationStore.test.ts desktop/src/stores/__tests__/agentStore.test.ts
git commit -m "perf: batch agent stream events"
```

---

### Task 5: Introduce ArtifactCard And Typed Renderer Registry

**Files:**
- Create: `desktop/src/features/workspace/artifacts/ArtifactCard.tsx`
- Modify: `desktop/src/features/workspace/artifacts/ArtifactRenderer.tsx`
- Modify: `desktop/src/features/workspace/artifacts/SqlArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/MarkdownArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`
- Modify: `desktop/src/App.css`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx`

- [ ] **Step 1: Add renderer registry test**

Add to `desktop/src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx` or create `ArtifactRenderer.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArtifactRenderer } from "../ArtifactRenderer";
import type { AgentArtifact } from "../../../../types/agentArtifact";

describe("ArtifactRenderer", () => {
  beforeEach(() => cleanup());

  it("renders supported artifact types through the registry", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "sql-1",
        type: "sql",
        title: "SQL",
        sql: "SELECT id FROM orders",
        purpose: "query",
        validationStatus: "passed",
      },
      {
        id: "markdown-1",
        type: "markdown",
        title: "分析",
        content: "订单上涨。",
      },
    ];

    render(
      <ArtifactRenderer
        artifacts={artifacts}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onToast={vi.fn()}
      />,
    );

    expect(screen.getByText("SQL")).toBeTruthy();
    expect(screen.getByText("分析")).toBeTruthy();
    expect(screen.getByText("订单上涨。")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run renderer test**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/ArtifactRenderer.test.tsx
```

Expected: FAIL if the file is new and not wired.

- [ ] **Step 3: Create ArtifactCard shell**

```tsx
import type { ReactNode } from "react";

type ArtifactTone = "default" | "sql" | "table" | "chart" | "insight" | "warning" | "danger";

interface ArtifactCardProps {
  icon?: ReactNode;
  title: string;
  badge: string;
  tone?: ArtifactTone;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  compact?: boolean;
}

export function ArtifactCard({
  icon,
  title,
  badge,
  tone = "default",
  description,
  meta,
  actions,
  children,
  compact = false,
}: ArtifactCardProps) {
  return (
    <section className={`artifact-card artifact-card-${tone} ${compact ? "is-compact" : ""}`}>
      <header className="artifact-card-header">
        <div className="artifact-card-title">
          {icon}
          <span>{title}</span>
        </div>
        <span className="artifact-card-badge">{badge}</span>
      </header>
      {description && <p className="artifact-card-desc">{description}</p>}
      {meta && <div className="artifact-card-meta">{meta}</div>}
      <div className="artifact-card-body">{children}</div>
      {actions && <footer className="artifact-card-actions">{actions}</footer>}
    </section>
  );
}
```

- [ ] **Step 4: Add ArtifactCard CSS**

In `App.css`:

```css
.artifact-card {
  border: 1px solid var(--agent-border);
  border-radius: var(--radius-card);
  background: var(--agent-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.artifact-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--agent-border);
  background: var(--agent-surface-muted);
}

.artifact-card-title {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  color: var(--agent-text);
  font-size: var(--ui-font-label);
  font-weight: 650;
}

.artifact-card-badge {
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  padding: 1px 8px;
  background: var(--agent-accent-soft);
  color: var(--agent-accent);
  font-size: var(--ui-font-micro);
  font-weight: 650;
}

.artifact-card-desc,
.artifact-card-meta,
.artifact-card-actions {
  padding-inline: 12px;
}

.artifact-card-desc {
  margin: 8px 0 0;
  color: var(--agent-text-muted);
  font-size: var(--ui-font-caption);
}

.artifact-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 8px;
}

.artifact-card-body {
  padding: 12px;
}

.artifact-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-bottom: 12px;
}
```

- [ ] **Step 5: Convert `ArtifactRenderer.tsx` to registry**

Use a narrow function map instead of component map because props differ:

```tsx
type ArtifactRendererMap = {
  chart: (artifact: Extract<AgentArtifact, { type: "chart" }>, props: ArtifactRendererProps) => JSX.Element;
  sql: (artifact: Extract<AgentArtifact, { type: "sql" }>, props: ArtifactRendererProps) => JSX.Element;
  sql_suggestion: (artifact: Extract<AgentArtifact, { type: "sql_suggestion" }>, props: ArtifactRendererProps) => JSX.Element;
  table: (artifact: Extract<AgentArtifact, { type: "table" }>, props: ArtifactRendererProps) => JSX.Element;
  result_view: (artifact: Extract<AgentArtifact, { type: "result_view" }>, props: ArtifactRendererProps) => JSX.Element;
  markdown: (artifact: Extract<AgentArtifact, { type: "markdown" }>, props: ArtifactRendererProps) => JSX.Element;
};

const ARTIFACT_RENDERERS: ArtifactRendererMap = {
  chart: (artifact, props) => <ChartArtifactView key={artifact.id} artifact={artifact} onToast={props.onToast} />,
  sql: (artifact, props) => <SqlArtifactView key={artifact.id} artifact={artifact} onOpenSqlConsole={props.onOpenSqlConsole} onToast={props.onToast} />,
  sql_suggestion: (artifact, props) => <SqlArtifactView key={artifact.id} artifact={artifact} onOpenSqlConsole={props.onOpenSqlConsole} onToast={props.onToast} />,
  table: (artifact, props) => <TableArtifactView key={artifact.id} artifact={artifact} onOpenResultTab={props.onOpenResultTab} onToast={props.onToast} />,
  result_view: (artifact, props) => <TableArtifactView key={artifact.id} artifact={artifact} onOpenResultTab={props.onOpenResultTab} onToast={props.onToast} />,
  markdown: (artifact, props) => <MarkdownArtifactView key={artifact.id} artifact={artifact} onToast={props.onToast} />,
};
```

Then:

```tsx
function renderArtifact(artifact: AgentArtifact, props: ArtifactRendererProps) {
  switch (artifact.type) {
    case "chart":
      return ARTIFACT_RENDERERS.chart(artifact, props);
    case "sql":
      return ARTIFACT_RENDERERS.sql(artifact, props);
    case "sql_suggestion":
      return ARTIFACT_RENDERERS.sql_suggestion(artifact, props);
    case "table":
      return ARTIFACT_RENDERERS.table(artifact, props);
    case "result_view":
      return ARTIFACT_RENDERERS.result_view(artifact, props);
    case "markdown":
      return ARTIFACT_RENDERERS.markdown(artifact, props);
    default:
      return <MarkdownArtifactView key={artifact.id} artifact={toFallbackMarkdownArtifact(artifact)} onToast={props.onToast} />;
  }
}

return (
  <>
    {artifacts.map((artifact) => {
      return renderArtifact(artifact, { artifacts, onOpenSqlConsole, onOpenResultTab, onToast });
    })}
  </>
);
```

Add this fallback helper for unsupported artifact types:

```tsx
function toFallbackMarkdownArtifact(artifact: AgentArtifact): MarkdownArtifact {
  return {
    id: artifact.id,
    type: "markdown",
    title: artifact.title || "Artifact",
    content: JSON.stringify(artifact, null, 2),
    description: "暂不支持的产物类型，已按原始 JSON 展示。",
  };
}
```

- [ ] **Step 6: Convert existing artifact views one at a time**

Start with `MarkdownArtifactView.tsx`:

```tsx
return (
  <ArtifactCard
    title={artifact.title}
    badge="分析"
    tone="insight"
    description={artifact.description}
    actions={(
      <button className="hifi-guide-btn-secondary hifi-artifact-action-btn flex items-center gap-1" onClick={handleCopy}>
        <Copy size={10} />
        复制
      </button>
    )}
  >
    <MarkdownContent content={artifact.content} />
  </ArtifactCard>
);
```

Then convert SQL, Table inline shell, and Chart shell while keeping body behavior unchanged.

- [ ] **Step 7: Run artifact tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/ArtifactRenderer.test.tsx src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/workspace/artifacts/ArtifactCard.tsx desktop/src/features/workspace/artifacts/ArtifactRenderer.tsx desktop/src/features/workspace/artifacts/SqlArtifactView.tsx desktop/src/features/workspace/artifacts/MarkdownArtifactView.tsx desktop/src/features/workspace/artifacts/TableArtifactView.tsx desktop/src/features/workspace/artifacts/ChartArtifactView.tsx desktop/src/App.css desktop/src/features/workspace/artifacts/__tests__
git commit -m "refactor: add shared artifact card shell"
```

---

### Task 6: Upgrade SQL Artifact To Read-Only Monaco

**Files:**
- Modify: `desktop/src/features/workspace/artifacts/SqlArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx`
- Modify: `desktop/src/App.css`

- [ ] **Step 1: Mock Monaco in SQL artifact tests**

In `SqlArtifactView.test.tsx`:

```tsx
vi.mock("@monaco-editor/react", () => ({
  default: ({ value, options }: { value: string; options: { readOnly?: boolean; fontSize?: number } }) => (
    <div data-testid="sql-monaco" data-readonly={String(options.readOnly)} data-font-size={String(options.fontSize)}>
      {value}
    </div>
  ),
}));
```

Add:

```tsx
it("renders SQL in a read-only Monaco editor", () => {
  render(<SqlArtifactView artifact={makeSqlArtifact()} onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

  const editor = screen.getByTestId("sql-monaco");
  expect(editor.textContent).toContain("SELECT");
  expect(editor.getAttribute("data-readonly")).toBe("true");
  expect(editor.getAttribute("data-font-size")).toBe("12");
});
```

- [ ] **Step 2: Run failing SQL test**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx
```

Expected: FAIL because SQL still renders as `<pre>`.

- [ ] **Step 3: Implement Monaco rendering**

In `SqlArtifactView.tsx`:

```tsx
import Editor from "@monaco-editor/react";
import { useTheme } from "../../../hooks/useTheme";
```

Inside component:

```tsx
const { theme } = useTheme();
```

Replace the SQL `<pre>` with:

```tsx
<div className="artifact-sql-editor">
  <Editor
    height="160px"
    defaultLanguage="sql"
    value={artifact.sql}
    theme={theme === "dark" ? "vs-dark" : "light"}
    options={{
      readOnly: true,
      minimap: { enabled: false },
      lineNumbers: "on",
      glyphMargin: false,
      folding: false,
      scrollBeyondLastLine: false,
      fontSize: 12,
      fontFamily: "var(--font-mono)",
      wordWrap: "on",
      renderLineHighlight: "none",
      overviewRulerLanes: 0,
    }}
  />
</div>
```

- [ ] **Step 4: Add CSS wrapper**

```css
.artifact-sql-editor {
  overflow: hidden;
  border: 1px solid var(--agent-border);
  border-radius: var(--radius-control);
  background: var(--agent-surface-elevated);
}
```

- [ ] **Step 5: Run SQL tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/features/workspace/artifacts/SqlArtifactView.tsx desktop/src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx desktop/src/App.css
git commit -m "feat: render sql artifacts with readonly editor"
```

---

### Task 7: Split Table Artifact And Improve DataGrid Feel

**Files:**
- Create: `desktop/src/features/workspace/artifacts/table/useArtifactTableData.ts`
- Create: `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx`
- Create: `desktop/src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx`
- Create: `desktop/src/features/workspace/artifacts/table/ArtifactTableFooter.tsx`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`
- Modify: `desktop/src/App.css`

- [ ] **Step 1: Add tests for table polish**

Add to `TableArtifactView.test.tsx`:

```tsx
it("marks numeric and null cells with data-grid classes", () => {
  render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

  expect(screen.getByText("10").closest("td")?.className).toContain("is-numeric");
  expect(screen.getByText("NULL").closest("td")?.className).toContain("is-null");
});

it("keeps warnings and notices in the meta area", () => {
  const { container } = render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

  const meta = container.querySelector(".artifact-table-meta");
  expect(meta?.textContent).toContain("仅展示前 10 行");
  expect(meta?.textContent).toContain("可继续筛选");
});
```

- [ ] **Step 2: Run failing table tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx
```

Expected: FAIL until the new classes/meta area exist.

- [ ] **Step 3: Extract `useArtifactTableData.ts`**

Move state and derived values from `TableArtifactView` into:

```ts
export interface ArtifactTableData {
  search: string;
  setSearch: (value: string) => void;
  sort: SortState | null;
  setSortColumn: (columnIndex: number) => void;
  page: number;
  setPage: (updater: number | ((page: number) => number)) => void;
  pageSize: number;
  setPageSize: (value: number) => void;
  visibleRows: string[][];
  filteredAndSortedRows: string[][];
  totalRows: number | undefined;
  returnedRows: number;
  previewCount: number;
  warnings: string[];
  notices: string[];
  latencyMs: number | undefined;
  isLoading: boolean;
  fetchError: string | null;
  isSqlBackedWorkspace: boolean;
  shouldUseWindow: boolean;
  expanded: boolean;
  setExpanded: (value: boolean | ((current: boolean) => boolean)) => void;
  csv: string;
}
```

Export:

```ts
export function useArtifactTableData(
  artifact: TableArtifact | ResultViewArtifact,
  mode: "inline" | "workspace",
): ArtifactTableData {
  // move existing TableArtifactView state/effects/memo here without changing behavior
}
```

- [ ] **Step 4: Extract `ArtifactTableGrid.tsx`**

```tsx
interface ArtifactTableGridProps {
  columns: string[];
  rows: string[][];
  sort: SortState | null;
  onSort: (columnIndex: number) => void;
  onCopyCell: (value: string) => void;
  emptyLabel: string;
}

export function ArtifactTableGrid({ columns, rows, sort, onSort, onCopyCell, emptyLabel }: ArtifactTableGridProps) {
  return (
    <table className="hifi-table artifact-table-grid min-w-full">
      <thead>
        <tr>
          {columns.map((column, columnIndex) => (
            <th key={`${column}-${columnIndex}`} className="artifact-table-head">
              <button type="button" className="artifact-table-head-button" onClick={() => onSort(columnIndex)}>
                <span>{column}</span>
                {sort?.columnIndex === columnIndex && (
                  <span className="hifi-artifact-sort-indicator">{sort.direction === "asc" ? "↑" : "↓"}</span>
                )}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length > 0 ? rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <td
                key={`${rowIndex}-${cellIndex}`}
                className={cellClassName(cell)}
                onClick={() => onCopyCell(cell)}
                title="点击复制单元格"
              >
                {cell === "NULL" ? <span className="artifact-table-null-pill">NULL</span> : cell}
              </td>
            ))}
          </tr>
        )) : (
          <tr>
            <td colSpan={columns.length} className="hifi-result-empty">{emptyLabel}</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function cellClassName(value: string): string {
  const classes = ["cursor-copy", "artifact-table-cell"];
  if (value === "NULL") classes.push("is-null");
  if (value.trim() !== "" && Number.isFinite(Number(value))) classes.push("is-numeric", "text-right", "tabular-nums");
  return classes.join(" ");
}
```

- [ ] **Step 5: Extract toolbar and footer**

Move the search/export/copy/pagination JSX into `ArtifactTableToolbar.tsx` and `ArtifactTableFooter.tsx`. Keep button labels exactly as they are now:

```tsx
刷新
筛选
排序
导出
复制
```

This keeps existing tests and user copy stable.

- [ ] **Step 6: Add DataGrid-style CSS**

```css
.artifact-table-grid tr {
  border-left: 2px solid transparent;
}

.artifact-table-grid tbody tr:hover {
  border-left-color: var(--agent-accent);
  background: var(--agent-surface-subtle);
}

.artifact-table-cell.is-numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.artifact-table-null-pill {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-pill);
  padding: 0 6px;
  background: var(--agent-surface-muted);
  color: var(--agent-text-muted);
  font-size: var(--ui-font-caption);
  font-style: italic;
}

.artifact-table-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/workspace/artifacts/TableArtifactView.tsx desktop/src/features/workspace/artifacts/table desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx desktop/src/App.css
git commit -m "refactor: split table artifact view"
```

---

### Task 8: Split Chart Option/Theme/Export And Add Focus Expansion

**Files:**
- Create: `desktop/src/features/workspace/artifacts/useChartTheme.ts`
- Create: `desktop/src/features/workspace/artifacts/useChartOption.ts`
- Create: `desktop/src/features/workspace/artifacts/useChartExport.ts`
- Modify: `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx`
- Modify: `desktop/src/App.css`

- [ ] **Step 1: Add chart expansion/export tests**

In `ChartArtifactView.test.tsx`, update the mock:

```tsx
import React, { useImperativeHandle } from "react";

const resizeMock = vi.fn();
const getDataURLMock = vi.fn(() => "data:image/png;base64,test");

vi.mock("echarts-for-react", () => ({
  default: React.forwardRef(({ option, style }: { option: unknown; style?: CSSProperties }, ref) => {
    echartsMock.options.push(option);
    useImperativeHandle(ref, () => ({
      getEchartsInstance: () => ({
        resize: resizeMock,
        getDataURL: getDataURLMock,
      }),
    }));
    return <div data-testid="echarts-mock" style={style} />;
  }),
}));
```

Add:

```tsx
it("can expand chart analysis height", () => {
  render(<ChartArtifactView artifact={makeChartArtifact("area")} onToast={vi.fn()} />);

  fireEvent.click(screen.getByRole("button", { name: "展开分析" }));

  expect(screen.getByTestId("echarts-mock").parentElement?.className).toContain("is-expanded");
  expect(resizeMock).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run failing chart test**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx
```

Expected: FAIL because the expand button/class does not exist.

- [ ] **Step 3: Extract chart theme**

Create `useChartTheme.ts`:

```ts
const CHART_COLOR_TOKENS = [
  "--agent-chart-1",
  "--agent-chart-2",
  "--agent-chart-3",
  "--agent-chart-4",
  "--agent-chart-5",
  "--agent-chart-6",
] as const;

function readToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function readFontSize(name: string, fallback: number): number {
  const parsed = Number.parseFloat(readToken(name, `${fallback}px`));
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function useChartTheme() {
  return {
    textColor: readToken("--color-text-primary", "currentColor"),
    textMuted: readToken("--color-text-muted", "currentColor"),
    textSecondary: readToken("--color-text-secondary", "currentColor"),
    borderColor: readToken("--color-border", "currentColor"),
    gridColor: readToken("--agent-chart-grid", "currentColor"),
    panelBg: readToken("--color-panel", "transparent"),
    tooltipShadow: readToken("--agent-chart-tooltip-shadow", "none"),
    areaStart: readToken("--agent-chart-area-start", "transparent"),
    areaEnd: readToken("--agent-chart-area-end", "transparent"),
    tooltipFontSize: readFontSize("--ui-font-control", 12),
    axisFontSize: readFontSize("--ui-font-caption", 10),
    chartColors: CHART_COLOR_TOKENS.map((token) => readToken(token, "currentColor")),
  };
}
```

- [ ] **Step 4: Extract option and export hooks**

Move option construction into:

```ts
export function useChartOption(
  artifact: ChartArtifact,
  chartType: ChartArtifactType,
  compact: boolean,
) {
  const theme = useChartTheme();
  return useMemo(() => buildChartOption(artifact, chartType, compact, theme), [artifact, chartType, compact, theme]);
}
```

Create export hook:

```ts
import type ReactECharts from "echarts-for-react";
import { copyText } from "./artifactActions";

export function useChartExport(
  chartRef: React.RefObject<ReactECharts | null>,
  artifactId: string,
  chartType: string,
  backgroundColor: string,
  onToast: (message: string) => void,
) {
  return () => {
    const chart = chartRef.current?.getEchartsInstance();
    if (!chart) {
      onToast("图表导出失败");
      return;
    }
    const url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor });
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${artifactId}-${chartType}.png`;
    anchor.click();
    onToast("已下载图表 PNG");
  };
}
```

Remove `document.querySelector` from `ChartArtifactView.tsx`.

- [ ] **Step 5: Add expansion UI**

In `ChartArtifactView.tsx`:

```tsx
const [expanded, setExpanded] = useState(false);
const chartRef = useRef<ReactECharts>(null);

useEffect(() => {
  chartRef.current?.getEchartsInstance()?.resize();
}, [expanded, compact]);
```

Add action:

```tsx
{!compact && (
  <button
    type="button"
    className="hifi-guide-btn-secondary hifi-artifact-action-btn-sm"
    onClick={() => setExpanded((value) => !value)}
  >
    {expanded ? "收起分析" : "展开分析"}
  </button>
)}
```

Render:

```tsx
<div className={`hifi-chart-body ${expanded ? "is-expanded" : ""}`} data-chart-id={artifact.id}>
  <ReactECharts ref={chartRef} option={option} style={{ height: "100%", width: "100%" }} />
</div>
```

- [ ] **Step 6: Add chart height CSS**

```css
.hifi-chart-body {
  height: 280px;
  transition: height 220ms cubic-bezier(0.16, 1, 0.3, 1);
}

.hifi-chart-card.is-compact .hifi-chart-body {
  height: 180px;
}

.hifi-chart-body.is-expanded {
  height: min(520px, 62vh);
}

@media (prefers-reduced-motion: reduce) {
  .hifi-chart-body {
    transition: none;
  }
}
```

- [ ] **Step 7: Run chart tests**

Run:

```bash
cd desktop
npm run test -- --run src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/workspace/artifacts/ChartArtifactView.tsx desktop/src/features/workspace/artifacts/useChartTheme.ts desktop/src/features/workspace/artifacts/useChartOption.ts desktop/src/features/workspace/artifacts/useChartExport.ts desktop/src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx desktop/src/App.css
git commit -m "feat: add focused chart analysis mode"
```

---

### Task 9: Finish Surface/Radius/Shadow Token Convergence

**Files:**
- Modify: `desktop/src/styles/tokens.css`
- Modify: `desktop/src/App.css`
- Modify: `desktop/src/features/conversation/workspace/conversationWorkspace.css`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/src/__tests__/agentVisualTokens.test.ts`

- [ ] **Step 1: Add token guard tests**

In `agentVisualTokens.test.ts`, extend token list:

```ts
for (const token of [
  "--surface-base",
  "--surface-panel",
  "--surface-card",
  "--surface-card-hover",
  "--border-subtle",
  "--border-strong",
  "--radius-sm",
  "--radius-md",
  "--radius-lg",
  "--radius-xl",
  "--radius-pill",
  "--shadow-card",
  "--shadow-card-hover",
]) {
  expect(tokens).toContain(token);
}
```

Add CSS guard:

```ts
it("keeps high-frequency UI surfaces behind tokens", () => {
  for (const relativePath of [
    "App.css",
    "features/conversation/workspace/conversationWorkspace.css",
    "components/data-grid/data-grid.css",
  ]) {
    const source = read(relativePath);
    expect(source, relativePath).not.toMatch(/background:\s*#(?:fff|ffffff|f8fafc|f1f5f9|fbfcfe)\b/i);
    expect(source, relativePath).not.toMatch(/border(?:-color)?:\s*#(?:e2e8f0|e8edf4|cbd5e1)\b/i);
  }
});
```

- [ ] **Step 2: Run failing token test**

Run:

```bash
cd desktop
npm run test -- --run src/__tests__/agentVisualTokens.test.ts
```

Expected: FAIL until aliases are defined and high-frequency hardcoded values are replaced.

- [ ] **Step 3: Define semantic aliases**

In `tokens.css` root and `.dark`:

```css
--surface-base: var(--color-bg);
--surface-panel: var(--color-panel);
--surface-panel-muted: var(--agent-surface-muted);
--surface-card: var(--agent-surface);
--surface-card-hover: var(--agent-surface-subtle);
--border-subtle: var(--agent-border);
--border-strong: var(--agent-border-strong);
--radius-sm: 6px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
--radius-pill: 999px;
--shadow-card: 0 1px 2px rgba(15, 23, 42, 0.04);
--shadow-card-hover: 0 8px 24px rgba(15, 23, 42, 0.08);
```

For `.dark`, use:

```css
--shadow-card: 0 1px 2px rgba(0, 0, 0, 0.22);
--shadow-card-hover: 0 10px 28px rgba(0, 0, 0, 0.32);
```

- [ ] **Step 4: Replace high-frequency hardcoded surfaces**

Replace only the high-frequency surfaces called out in the report:

```css
#FFFFFF -> var(--surface-card)
#F8FAFC -> var(--surface-panel-muted)
#F1F5F9 -> var(--surface-card-hover)
#FBFCFE -> var(--surface-card)
#E8EDF4 -> var(--border-subtle)
#CBD5E1 -> var(--agent-text-muted)
```

Do not replace semantic brand colors, trust colors, or chart colors in this task.

- [ ] **Step 5: Run token tests**

Run:

```bash
cd desktop
npm run test -- --run src/__tests__/agentVisualTokens.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/styles/tokens.css desktop/src/App.css desktop/src/features/conversation/workspace/conversationWorkspace.css desktop/src/components/data-grid/data-grid.css desktop/src/__tests__/agentVisualTokens.test.ts
git commit -m "style: converge desktop surface tokens"
```

---

### Task 10: Full Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run desktop tests**

```bash
cd desktop
npm run test -- --run
```

Expected: all Vitest files pass.

- [ ] **Step 2: Run lint**

```bash
cd desktop
npm run lint
```

Expected: exit code 0. Existing warnings are acceptable if unchanged; no new errors.

- [ ] **Step 3: Run build**

```bash
cd desktop
npm run build
```

Expected: exit code 0. Existing Vite chunk/dynamic import warnings are acceptable if unchanged.

- [ ] **Step 4: Run targeted backend guard**

This UI plan should not require backend edits, but run the agent API/architecture guard to catch accidental contract drift:

```bash
pytest engine/tests/test_agent_api.py engine/tests/test_architecture.py
```

Expected: PASS.

- [ ] **Step 5: Manual smoke check**

Start the desktop dev server:

```bash
cd desktop
npm run dev
```

Open the local URL shown by Vite and verify:

- Conversation stream starts without layout jumping when run completes.
- RunTracePanel progress strip advances and does not leave old completed stages as running.
- Manual trace expand/collapse works after run completion.
- Artifact Dock still opens SQL, result, chart, and safety artifacts.
- SQL artifact shows read-only editor and action buttons still work.
- Table inline preview shows 10 rows, workspace result tab keeps paging/search/sort.
- Chart expand/collapse changes height and PNG export still succeeds.
- Dark mode has no obvious local white blocks in table, toolbar, input, tab, or artifact surfaces.

- [ ] **Step 6: Commit any verification-only fixes**

If verification required source fixes, commit them:

```bash
git add desktop/src
git commit -m "fix: polish desktop ux verification issues"
```

If no fixes were needed, do not create an empty commit.

---

## Plan Self-Review

**Spec coverage:** The tasks cover every report priority: RunTrace status, controlled expansion, phase progress, conversation store selectors, message lookup maps, stream batching/no-op guards, ArtifactCard, registry, SQL Monaco, DataGrid table polish, chart focus mode, token convergence, and motion.

**Placeholder scan:** The plan contains no placeholder markers, no empty deferred sections, and no unqualified “write tests” instructions. Each task includes concrete files, test snippets, implementation snippets, commands, and expected outcomes.

**Type consistency:** The planned exported names are stable across tasks: `buildRunTraceModel`, `TimelineStage`, `TimelinePhase`, `PHASE_ORDER`, `PHASE_LABELS`, `useConversationViewModel`, `createStreamEventBatcher`, `ArtifactCard`, `useArtifactTableData`, `useChartTheme`, `useChartOption`, and `useChartExport`.

**Scope check:** The plan is large but sequential. Task 1 through Task 4 can ship as stability/performance work without the artifact visual work. Task 5 through Task 9 can ship independently after the stability tasks. Task 10 is verification only.

## Execution Options

1. **Subagent-Driven (recommended):** dispatch one fresh subagent per task, review after every task, commit each task separately.
2. **Inline Execution:** execute tasks in this session with checkpoints after Task 2, Task 4, Task 7, and Task 10.
