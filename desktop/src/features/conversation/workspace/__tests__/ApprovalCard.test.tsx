import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApprovalItem } from "../../../../types/conversation";
import { ApprovalAuditCard, ApprovalCard } from "../ApprovalCard";

afterEach(cleanup);

const approval: ApprovalItem = {
  id: "approval-1",
  type: "approval",
  session_id: "session-1",
  run_id: "run-1",
  sequence: 1,
  revision: 1,
  status: "waiting",
  created_at: "2026-08-26T08:00:00Z",
  payload: {
    version: 1,
    risk_level: "warning",
    reason: "该操作会向项目目录写入文件。",
    requested_action: {
      name: "workspace.write_file",
      arguments: { path: "reports/summary.md" },
    },
  },
};

describe("ApprovalCard", () => {
  it("shows risk, reason and operation before the decision actions", () => {
    render(<ApprovalCard approval={approval} onResolve={vi.fn()} />);

    expect(screen.getByText("需要你的批准")).toBeInTheDocument();
    expect(screen.getByText("该操作会向项目目录写入文件。")).toBeInTheDocument();
    expect(screen.getByText("workspace.write_file")).toBeInTheDocument();
    const actions = screen.getAllByRole("button");
    expect(actions[0]).toHaveTextContent("拒绝");
    expect(actions[1]).toHaveTextContent("批准执行");
    expect(actions[0]).toHaveFocus();
  });

  it("resolves reject and approve decisions through the same Core component", () => {
    const onResolve = vi.fn();
    render(<ApprovalCard approval={approval} onResolve={onResolve} />);

    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    fireEvent.click(screen.getByRole("button", { name: "批准执行" }));

    expect(onResolve).toHaveBeenNthCalledWith(1, "run-1", "approval-1", false);
    expect(onResolve).toHaveBeenNthCalledWith(2, "run-1", "approval-1", true);
  });

  it("locks both decisions and exposes a recoverable mutation error", () => {
    render(<ApprovalCard approval={approval} onResolve={vi.fn()} submitting error="审批提交失败，请重试。" />);

    expect(screen.getByLabelText("需要批准")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "拒绝" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "正在提交…" })).toBeDisabled();
    expect(screen.getByLabelText("需要批准")).toHaveTextContent("审批提交失败，请重试。");
  });

  it("renders the durable approved decision through the adopted confirmation state", () => {
    render(<ApprovalAuditCard approval={{
      ...approval,
      status: "completed",
      payload: { ...approval.payload, decision: "approved", decision_note: "已由项目负责人确认" },
    }} />);

    expect(screen.getByLabelText("批准记录")).toHaveAttribute("role", "status");
    expect(screen.getByText("已批准")).toBeInTheDocument();
    expect(screen.queryByText("已拒绝")).not.toBeInTheDocument();
  });

  it.each([
    ["expired", "expired", "批准请求已过期", "请求到期后未执行该操作"],
    ["cancelled", "cancelled", "批准请求已取消", "请求已随任务停止"],
  ] as const)("keeps %s distinct from a rejected decision", (status, decision, title, message) => {
    render(<ApprovalAuditCard approval={{
      ...approval,
      status,
      payload: { ...approval.payload, decision },
    }} />);

    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(message))).toBeInTheDocument();
    expect(screen.queryByText("已拒绝")).not.toBeInTheDocument();
  });
});
