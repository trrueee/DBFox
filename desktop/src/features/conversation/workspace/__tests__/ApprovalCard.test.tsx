import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApprovalItem } from "../../../../types/conversation";
import { ApprovalCard } from "../ApprovalCard";

const approval: ApprovalItem = {
  id: "approval-1",
  type: "approval",
  session_id: "session-1",
  run_id: "run-1",
  turn_id: "turn-1",
  sequence: 1,
  revision: 1,
  status: "waiting",
  created_at: "2026-07-29T00:00:00Z",
  completed_at: null,
  payload: {
    version: 0,
    risk_level: "danger",
    reason: "该操作会修改数据",
    requested_action: {
      name: "db_execute",
      arguments: { sql: "UPDATE orders SET status = 'closed'" },
    },
  },
};

describe("ApprovalCard", () => {
  afterEach(cleanup);

  it("submits the exact approval identity and decision", () => {
    const onResolve = vi.fn();
    render(
      <ApprovalCard
        approval={approval}
        onOpenSqlConsole={vi.fn()}
        onResolve={onResolve}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "批准执行" }));

    expect(onResolve).toHaveBeenCalledWith("run-1", "approval-1", true);
  });

  it("prevents duplicate decisions and exposes submission failure", () => {
    render(
      <ApprovalCard
        approval={approval}
        onOpenSqlConsole={vi.fn()}
        onResolve={vi.fn()}
        submitting
        error="审批提交失败，请重试。"
      />,
    );

    expect(
      (screen.getByRole("button", { name: "正在提交…" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "拒绝" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByRole("alert").textContent).toBe("审批提交失败，请重试。");
  });
});
