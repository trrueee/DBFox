import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AssistantMessageItem,
  ConversationRun,
  UserMessageItem,
} from "../../../../types/conversation";
import { MessageList } from "../MessageList";

function run(id: string, sequence: number): ConversationRun {
  return {
    id,
    session_id: "session-1",
    input_id: `input-${sequence}`,
    session_sequence: sequence,
    user_message_id: `user-${sequence}`,
    question: `问题 ${sequence}`,
    status: "completed",
    version: 1,
    cancel_requested: false,
    result: {},
    error: null,
  };
}

function user(runId: string, sequence: number): UserMessageItem {
  return {
    id: `user-${sequence}`,
    type: "message",
    session_id: "session-1",
    run_id: runId,
    sequence: sequence * 2 - 1,
    revision: 1,
    status: "completed",
    created_at: `2026-07-26T00:00:0${sequence}Z`,
    payload: {
      role: "user",
      content: `问题 ${sequence}`,
      evidence: [],
      artifact_refs: [],
      limitation_codes: [],
    },
  };
}

function answer(runId: string, sequence: number): AssistantMessageItem {
  return {
    id: `message-${sequence}`,
    type: "message",
    session_id: "session-1",
    run_id: runId,
    turn_id: `turn-${sequence}`,
    sequence: sequence * 2,
    revision: 1,
    status: "completed",
    created_at: `2026-07-26T00:00:0${sequence}Z`,
    completed_at: `2026-07-26T00:01:0${sequence}Z`,
    payload: {
      role: "assistant",
      phase: "final_answer",
      content: `回答 ${sequence}`,
      evidence: [],
      artifact_refs: [],
      completion_disposition: "complete",
      limitation_codes: [],
    },
  };
}

describe("MessageList", () => {
  afterEach(cleanup);
  it("projects each run's user input and answer without cross-run leakage", () => {
    const runs = [run("run-1", 1), run("run-2", 2)];
    render(
      <MessageList
        runs={runs}
        items={[
          user("run-1", 1),
          answer("run-1", 1),
          user("run-2", 2),
          answer("run-2", 2),
        ]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.getByText("问题 1")).toBeTruthy();
    expect(screen.getByText("回答 1")).toBeTruthy();
    expect(screen.getByText("问题 2")).toBeTruthy();
    expect(screen.getByText("回答 2")).toBeTruthy();
  });

  it("shows the user question immediately while a run is queued", () => {
    const queued = run("run-queued", 1);
    queued.status = "queued";
    render(
      <MessageList
        runs={[queued]}
        items={[user("run-queued", 1)]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.getByText("问题 1")).toBeTruthy();
    expect(screen.getByText("正在理解问题")).toBeTruthy();
  });
});
