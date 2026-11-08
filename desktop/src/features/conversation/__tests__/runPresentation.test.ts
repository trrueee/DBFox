import { expect, it } from "vitest";
import { threadRunStatus, runPresentation } from "../runPresentation";
import type { ConversationRun } from "../../../types/conversation";

it("keeps approval, input, queueing and cancellation distinct from execution", () => {
  expect(runPresentation("waiting_approval").label).toBe("等待审批");
  expect(runPresentation("waiting_input").label).toBe("等待答复");
  expect(runPresentation("queued").label).toBe("排队中");
  expect(runPresentation("cancelling").label).toBe("正在停止");
  expect(runPresentation("completed").label).toBe("本轮已结束");
  expect(runPresentation("completed").tone).toBe("quiet");
});

const run = (status: ConversationRun["status"], sequence = 1): ConversationRun => ({
  id: `run-${sequence}`, session_id: "session", input_id: `input-${sequence}`, session_sequence: sequence,
  user_message_id: `message-${sequence}`, question: "task", status, version: 1,
  cancel_requested: false, result: {}, error: null,
});

it("uses the newest durable projection, including across different runs", () => {
  expect(threadRunStatus({ runs: [run("waiting_approval")], cursor: 8 }, { run_status: "completed", cursor: 7 })).toBe("waiting_approval");
  expect(threadRunStatus({ runs: [run("completed")], cursor: 8 }, { run_status: "running", cursor: 12 })).toBe("running");
  expect(threadRunStatus(undefined, { run_status: "running", cursor: 12 })).toBe("running");
  expect(threadRunStatus({ runs: [], cursor: 0 }, { run_status: null, cursor: 0 })).toBeNull();
  expect(runPresentation(null).label).toBe("尚未运行");
});

it("keeps the active intervention visible ahead of queued follow-ups", () => {
  expect(threadRunStatus({ runs: [run("completed"), run("waiting_approval", 2), run("queued", 3)], cursor: 9 })).toBe("waiting_approval");
  expect(threadRunStatus({ runs: [run("completed")], cursor: 8 }, { run_status: "waiting_approval", cursor: 8 })).toBe("waiting_approval");
});
