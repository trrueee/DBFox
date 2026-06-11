import { describe, expect, it } from "vitest";
import { createAgentRunDraft, reduceAgentRuntimeEvent } from "../agent";
import type { AgentRuntimeEvent } from "../types";

describe("reduceAgentRuntimeEvent", () => {
  it("stores streaming context summary", () => {
    const draft = createAgentRunDraft("Why did sales drop?");
    const event: AgentRuntimeEvent = {
      event_id: "ctx-1",
      run_id: "run-1",
      sequence: 2,
      created_at_ms: Date.now(),
      type: "agent.context.update",
      step: { summary: "Using 2 schema tables | Focus: Checking refunds" },
    };

    const next = reduceAgentRuntimeEvent(draft, event);
    expect(next.contextSummary).toBe("Using 2 schema tables | Focus: Checking refunds");
    expect(next.events).toHaveLength(1);
  });

  it("stores task lens from context update", () => {
    const draft = createAgentRunDraft("Why did sales drop?");
    const event: AgentRuntimeEvent = {
      event_id: "ctx-2",
      run_id: "run-1",
      sequence: 3,
      created_at_ms: Date.now(),
      type: "agent.context.update",
      step: {
        summary: "Using orders table",
        task_lens: {
          goal: "Analyze sales drop",
          current_focus: "Checking refund trend",
          next_likely: "Run grouped query",
          missing_evidence: ["refund rate"],
        },
      },
    };

    const next = reduceAgentRuntimeEvent(draft, event);
    expect(next.taskLens?.goal).toBe("Analyze sales drop");
    expect(next.taskLens?.current_focus).toBe("Checking refund trend");
    expect(next.taskLens?.missing_evidence).toEqual(["refund rate"]);
  });
});
