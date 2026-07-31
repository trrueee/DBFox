import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { QuestionItem } from "../../../../types/conversation";
import { QuestionCard } from "../QuestionCard";

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

describe("QuestionCard", () => {
  afterEach(cleanup);

  it("returns the exact selected business option", () => {
    const onRespond = vi.fn();
    render(<QuestionCard question={question("waiting")} onRespond={onRespond} />);
    fireEvent.click(screen.getByLabelText("财务月"));
    fireEvent.click(screen.getByRole("button", { name: "继续分析" }));
    expect(onRespond).toHaveBeenCalledWith({ selected_value: "fiscal" });
  });

  it("shows the resolved business answer", () => {
    render(
      <QuestionCard
        question={question("completed", {
          selected_value: "fiscal",
          text: "以结账日为准",
        })}
        onRespond={vi.fn()}
      />,
    );
    expect(screen.getByText("财务月 · 以结账日为准")).toBeTruthy();
  });

  it("locks the interaction and exposes the mutation error while submitting", () => {
    render(
      <QuestionCard
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
});
