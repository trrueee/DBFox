import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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

  it("sends trimmed text and clears the composer after admission succeeds", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);

    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "  分析订单趋势  " } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSend).toHaveBeenCalledWith("分析订单趋势", "queue", []);
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("preserves the draft when admission fails", async () => {
    const onSend = vi.fn().mockRejectedValue(new Error("network unavailable"));
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);

    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "保留这段问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(onSend).toHaveBeenCalledOnce());
    expect(input.value).toBe("保留这段问题");
  });

  it("renders reference context and clears reference on send", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    const onClearReference = vi.fn();
    const reference = {
      label: "orders (table)",
      kind: "Table",
    };
    render(
      <Composer
        running={false}
        onSend={onSend}
        onCancel={vi.fn()}
        reference={reference}
        onClearReference={onClearReference}
      />,
    );

    expect(screen.getByText("orders (table)")).toBeTruthy();
    expect(screen.getByText("Table")).toBeTruthy();
    const input = screen.getByRole("textbox", { name: "继续提问" });
    fireEvent.change(input, {
      target: { value: "统计总金额" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSend).toHaveBeenCalledWith("统计总金额", "queue", []);
    await waitFor(() => expect(onClearReference).toHaveBeenCalledOnce());
  });

  it("shows a pause control while running", () => {
    const onCancel = vi.fn().mockResolvedValue(undefined);
    render(<Composer running={true} onSend={vi.fn()} onCancel={onCancel} />);

    expect(screen.getByRole("button", { name: "发送" })).toBeTruthy();
    const pause = screen.getByRole("button", { name: "停止当前任务" });

    fireEvent.click(pause);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
