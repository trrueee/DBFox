import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConversationArtifact, PlanItem } from "../../../types/conversation";
import { AgentPlan } from "../AgentPlan";

afterEach(cleanup);

describe("AgentPlan", () => {
  it("keeps one quiet header: status glyph, objective, and progress", () => {
    render(<AgentPlan item={plan("failed", ["completed", "blocked", "pending"])} />);

    expect(screen.getByText("核对订单异常")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.queryByText(/plan-1\.md/)).not.toBeInTheDocument();
    expect(screen.queryByText("计划状态图例")).not.toBeInTheDocument();
  });

  it("marks the active step with semantic current-step state", () => {
    const { container } = render(<AgentPlan item={plan("in_progress", ["completed", "in_progress", "pending"])} />);

    expect(container.querySelector('li[data-status="in_progress"]')).toHaveAttribute("aria-current", "step");
  });

  it("keeps completed steps struck through in the expanded checklist", () => {
    const { container } = render(<AgentPlan item={plan("in_progress", ["completed", "in_progress"])} />);

    const completedTitle = screen.getByText("步骤 1");
    expect(completedTitle).toHaveClass("line-through");
    expect(container.querySelector('li[data-status="completed"]')).toBeInTheDocument();
  });

  it("opens a completed step artifact through the existing selection action", () => {
    const item = plan("completed", ["completed"]);
    item.payload.steps[0].evidence_required = true;
    item.payload.steps[0].artifact_ids = ["artifact-1"];
    const onSelectArtifact = vi.fn();
    render(<AgentPlan item={item} artifacts={[artifact()]} onSelectArtifact={onSelectArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: /核对订单异常/ }));
    fireEvent.click(screen.getByRole("button", { name: "打开完成证据：渠道转化结果" }));

    expect(onSelectArtifact).toHaveBeenCalledWith("artifact-1");
  });

  it("makes required but unavailable completion evidence explicit", () => {
    const item = plan("completed", ["completed"]);
    item.payload.steps[0].evidence_required = true;
    item.payload.steps[0].artifact_ids = ["artifact-missing"];
    render(<AgentPlan item={item} artifacts={[]} onSelectArtifact={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /核对订单异常/ }));
    expect(screen.getByText("完成证据暂不可用")).toBeInTheDocument();
  });

  it("preserves a manual collapse across streaming revisions of the same status", () => {
    const item = plan("in_progress", ["completed", "in_progress"]);
    const view = render(<AgentPlan item={item} />);
    fireEvent.click(screen.getByRole("button", { name: /核对订单异常/ }));

    view.rerender(<AgentPlan item={{ ...item, revision: 2 }} />);

    expect(screen.getByRole("button", { name: /核对订单异常/ })).toHaveAttribute("aria-expanded", "false");
  });
});

function plan(
  status: PlanItem["status"],
  statuses: readonly PlanItem["payload"]["steps"][number]["status"][],
): PlanItem {
  return {
    id: "plan-1",
    type: "plan",
    session_id: "session-1",
    run_id: "run-1",
    turn_id: "turn-1",
    sequence: 1,
    revision: 1,
    status,
    created_at: "2026-08-27T00:00:00Z",
    payload: {
      objective: "核对订单异常",
      steps: statuses.map((stepStatus, index) => ({
        id: `step-${index + 1}`,
        title: `步骤 ${index + 1}`,
        status: stepStatus,
      })),
    },
  };
}

function artifact(): ConversationArtifact {
  return {
    id: "artifact-1",
    session_id: "session-1",
    run_id: "run-1",
    turn_id: "turn-1",
    version: 1,
    type: "markdown",
    title: "渠道转化结果",
    status: "completed",
    visibility: "supporting",
    payload: { content: "已核对" },
    provenance: {},
    relations: [],
  };
}
