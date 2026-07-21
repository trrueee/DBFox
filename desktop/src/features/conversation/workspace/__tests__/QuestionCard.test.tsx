import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QuestionCard } from "../QuestionCard";

describe("QuestionCard", () => {
  it("returns the exact selected business option", () => {
    const onRespond = vi.fn();
    render(<QuestionCard question={{
      id: "question-1", run_id: "run-1", turn_id: "turn-1", status: "pending", version: 0,
      question: "按哪个月份口径？", reason: "财务月和自然月结果不同",
      options: [
        { value: "calendar", label: "自然月" },
        { value: "fiscal", label: "财务月" },
      ],
      allow_free_text: false,
    }} onRespond={onRespond} />);

    fireEvent.click(screen.getByLabelText("财务月"));
    fireEvent.click(screen.getByRole("button", { name: "继续分析" }));
    expect(onRespond).toHaveBeenCalledWith({ selected_value: "fiscal" });
  });

  it("shows the resolved business answer instead of a generic status", () => {
    render(<QuestionCard question={{
      id: "question-2", run_id: "run-1", turn_id: "turn-1", status: "answered", version: 1,
      question: "按哪个月份口径？", reason: "财务月和自然月结果不同",
      options: [{ value: "fiscal", label: "财务月" }],
      allow_free_text: true,
      response: { selected_value: "fiscal", text: "以结账日为准" },
    }} onRespond={vi.fn()} />);

    expect(screen.getByText("财务月 · 以结账日为准")).toBeTruthy();
  });
});
