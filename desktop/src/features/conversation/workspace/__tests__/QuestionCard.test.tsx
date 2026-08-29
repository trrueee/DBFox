import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentQuestion } from "../../../../components/agent-elements/AgentQuestion";
import type { QuestionItem } from "../../../../types/conversation";

function question(status: QuestionItem["status"], response?: Record<string, unknown>): QuestionItem {
  return {
    id: "question-1",
    type: "question",
    session_id: "session-1",
    run_id: "run-1",
    turn_id: "turn-1",
    sequence: 1,
    revision: 1,
    status,
    created_at: "2026-07-26T00:00:00Z",
    completed_at: status === "completed" ? "2026-07-26T00:01:00Z" : null,
    payload: {
      version: status === "completed" ? 1 : 0,
      question: "按哪个月份口径？",
      reason: "财务月和自然月结果不同",
      options: [
        { value: "calendar", label: "自然月" },
        { value: "fiscal", label: "财务月" },
      ],
      allow_free_text: true,
      response,
    },
  };
}

describe("AgentQuestion", () => {
  afterEach(cleanup);

  it("returns the exact selected business option", () => {
    const onRespond = vi.fn();
    render(<AgentQuestion question={question("waiting")} onRespond={onRespond} />);
    fireEvent.click(screen.getByLabelText("财务月"));
    fireEvent.click(screen.getByRole("button", { name: "继续任务" }));
    expect(onRespond).toHaveBeenCalledWith({ selected_value: "fiscal" });
  });

  it("shows the resolved business answer", () => {
    render(
      <AgentQuestion
        question={question("completed", {
          selected_value: "fiscal",
          text: "以结账日为准",
        })}
        onRespond={vi.fn()}
      />,
    );
    expect(screen.getByText("财务月 · 以结账日为准")).toBeTruthy();
  });

  it("submits free text without inventing an option value", () => {
    const onRespond = vi.fn();
    render(<AgentQuestion question={question("waiting")} onRespond={onRespond} />);

    fireEvent.change(screen.getByLabelText("补充说明"), { target: { value: "按最近一次结账日" } });
    fireEvent.click(screen.getByRole("button", { name: "继续任务" }));

    expect(onRespond).toHaveBeenCalledWith({ text: "按最近一次结账日" });
  });

  it("locks the interaction and exposes the mutation error while submitting", () => {
    render(
      <AgentQuestion
        question={question("waiting")}
        onRespond={vi.fn()}
        submitting
        error="回答提交失败，请重试。"
      />,
    );

    expect(
      (screen.getByRole("button", { name: "正在提交…" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByRole("alert").textContent).toBe("回答提交失败，请重试。");
  });

  it("renders an expired question as a locked terminal state", () => {
    render(<AgentQuestion question={question("expired")} onRespond={vi.fn()} />);

    expect(screen.getByText("问题已过期")).toBeInTheDocument();
    expect(screen.getByText(/回答期限已结束/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "继续任务" })).toBeNull();
  });

  it("keeps cancellation distinct from expiration", () => {
    render(<AgentQuestion question={question("cancelled")} onRespond={vi.fn()} />);

    expect(screen.getByText("问题已取消")).toBeInTheDocument();
    expect(screen.getByText(/已随任务停止/)).toBeInTheDocument();
    expect(screen.queryByText("问题已过期")).toBeNull();
  });
});
