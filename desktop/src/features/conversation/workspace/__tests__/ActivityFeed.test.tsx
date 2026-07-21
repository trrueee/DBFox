import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ActivityFeed } from "../ActivityFeed";

describe("ActivityFeed", () => {
  it("shows a safe product summary and expands durable activities", () => {
    render(<ActivityFeed activities={[
      {
        id: "activity-1", run_id: "run-1", turn_id: "turn-1", kind: "analysis",
        title: "正在确认订单口径", status: "completed",
      },
      {
        id: "activity-2", run_id: "run-1", turn_id: "turn-1", kind: "tool",
        title: "执行只读查询", summary: "返回 24 行", status: "running",
      },
    ]} />);

    const current = screen.getByRole("button", { name: /执行只读查询/ });
    expect(current.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(current);
    expect(screen.getByText("正在确认订单口径")).toBeTruthy();
    expect(screen.getAllByText("返回 24 行").length).toBeGreaterThan(0);
  });

  it("renders dynamic plan steps without exposing chain-of-thought", () => {
    render(<ActivityFeed activities={[{
      id: "activity-plan", run_id: "run-1", turn_id: "turn-1", kind: "plan",
      title: "分析订单增长", summary: "1/2 个步骤已完成", status: "running",
      steps: [
        { id: "trend", title: "确认增长趋势", status: "completed", evidence_required: true, artifact_ids: ["artifact-1"] },
        { id: "cause", title: "定位异常原因", status: "in_progress", evidence_required: true, artifact_ids: [] },
      ],
    }]} />);

    fireEvent.click(screen.getByRole("button", { name: /分析订单增长/ }));
    expect(screen.getByText("确认增长趋势")).toBeTruthy();
    expect(screen.getByText("定位异常原因")).toBeTruthy();
  });
});
