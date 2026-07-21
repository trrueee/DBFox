import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer } from "../Composer";

describe("Composer", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders a Codex-style composer card in the conversation rail without an attachment action", () => {
    const { container } = render(
      <Composer running={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(container.querySelector(".conv-composer-rail")).toBeTruthy();
    expect(container.querySelector(".conv-composer-card")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "继续提问" }).getAttribute("placeholder")).toBe("继续追问…");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "发送" })).toBeTruthy();
  });

  it("sends trimmed text and clears the composer", () => {
    const onSend = vi.fn();
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);

    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "  分析订单趋势  " } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSend).toHaveBeenCalledWith("分析订单趋势", "queue");
    expect(input.value).toBe("");
  });

  it("shows a pause control while running", () => {
    const onCancel = vi.fn();
    render(<Composer running={true} onSend={vi.fn()} onCancel={onCancel} />);

    expect(screen.getByRole("button", { name: "发送" })).toBeTruthy();
    const pause = screen.getByRole("button", { name: "停止当前任务" });

    fireEvent.click(pause);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
