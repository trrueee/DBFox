import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../../lib/api/client";
import { Composer } from "../Composer";

describe("Composer", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the shared composer in the conversation rail without unavailable actions", () => {
    const { container } = render(
      <Composer running={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(container.querySelector(".conv-composer-rail")).toBeTruthy();
    expect(container.querySelector(".dbfox-composer")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "继续提问" }).getAttribute("placeholder")).toBe("继续追问…");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "发送：立即执行" })).toBeTruthy();
  });

  it("sends trimmed text and clears the composer after admission succeeds", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);

    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "  分析订单趋势  " } });
    fireEvent.click(screen.getByRole("button", { name: "发送：立即执行" }));

    expect(onSend).toHaveBeenCalledWith("分析订单趋势", "queue", []);
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("preserves the draft when admission fails", async () => {
    const onSend = vi.fn().mockRejectedValue(new Error("network unavailable"));
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);

    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "保留这段问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送：立即执行" }));

    await waitFor(() => expect(onSend).toHaveBeenCalledOnce());
    expect(input.value).toBe("保留这段问题");
  });

  it("renders only safe Problem Details metadata for an admission failure", () => {
    const error = new ApiError(
      "private model endpoint",
      503,
      "AGENT_REQUEST_ERROR",
      [],
      { request_id: "composer-request-5", secret: "must-not-render" },
    );
    render(<Composer running={false} error={error} onSend={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText("服务暂时不可用，请稍后重试。")).toBeTruthy();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("AGENT_REQUEST_ERROR")).toBeTruthy();
    expect(screen.getByText("composer-request-5")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private model endpoint");
    expect(document.body.textContent).not.toContain("must-not-render");
  });

  it("renders multiple reference chips and clears them after send", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    const onClearReferences = vi.fn();
    const reference = {
      label: "orders (table)",
      authority: { kind: "dbfox.data.database", id: "creatorhub" },
      object: { kind: "dbfox.data.table", id: "orders" },
      locator: "table:orders",
    };
    render(
      <Composer
        running={false}
        onSend={onSend}
        onCancel={vi.fn()}
        references={[reference, { label: "分析结果", artifactId: "artifact_result" }]}
        onClearReferences={onClearReferences}
      />,
    );

    expect(screen.getByText("orders (table)")).toBeTruthy();
    expect(screen.getByText("dbfox.data.table")).toBeTruthy();
    const input = screen.getByRole("textbox", { name: "继续提问" });
    fireEvent.change(input, {
      target: { value: "统计总金额" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送：立即执行" }));

    expect(onSend).toHaveBeenCalledWith(
      "统计总金额",
      "queue",
      [reference, { label: "分析结果", artifactId: "artifact_result" }],
    );
    await waitFor(() => expect(onClearReferences).toHaveBeenCalledOnce());
  });

  it("turns the primary send action into the stop action while running", () => {
    const onCancel = vi.fn().mockResolvedValue(undefined);
    render(<Composer running={true} onSend={vi.fn()} onCancel={onCancel} />);

    expect(screen.queryByRole("button", { name: "发送：立即执行" })).toBeNull();
    const pause = screen.getByRole("button", { name: "停止当前任务" });

    fireEvent.click(pause);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("does not submit Enter while an IME composition session is active", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "分析中文输入" } });

    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(onSend).not.toHaveBeenCalled();
    expect(input.value).toBe("分析中文输入");

    fireEvent.keyDown(input, { key: "Enter", isComposing: false });

    await waitFor(() => expect(onSend).toHaveBeenCalledWith("分析中文输入", "queue", []));
  });

  it("keeps Shift+Enter available for multiline input", () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Composer running={false} onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "继续提问" });
    fireEvent.change(input, { target: { value: "第一行" } });

    fireEvent.keyDown(input, { key: "Enter", shiftKey: true, isComposing: false });

    expect(onSend).not.toHaveBeenCalled();
  });
});
