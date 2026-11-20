import { cleanup, fireEvent, render } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnifiedComposer } from "../UnifiedComposer";

afterEach(cleanup);

function renderComposer(value = "hello", props: Partial<ComponentProps<typeof UnifiedComposer>> = {}) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <UnifiedComposer
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      placeholder="Describe the work"
      ariaLabel="Composer"
      onCancel={onCancel}
      {...props}
    />,
  );
  return { ...view, onCancel, onChange, onSubmit };
}

describe("UnifiedComposer", () => {
  it("keeps typing available during file upload without adding status text", () => {
    const { getByRole, queryByText, onSubmit } = renderComposer("draft", { attachmentBusy: true, onAddAttachment: vi.fn() });
    expect(getByRole("textbox").hasAttribute("disabled")).toBe(false);
    expect(queryByText("正在添加文件…")).toBeNull();
    expect(getByRole("button", { name: "添加本地文件" }).getAttribute("aria-busy")).toBe("true");
    fireEvent.keyDown(getByRole("textbox"), { key: "Enter" });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("opens and removes the exact reference without focusing the textarea", () => {
    const reference = { label: "培养方案.xlsx", object: { kind: "dbfox.core.attachment", id: "att-1" } };
    const onOpenReference = vi.fn();
    const onRemoveReference = vi.fn();
    const { getByRole } = renderComposer("", { references: [reference], onOpenReference, onRemoveReference });
    fireEvent.click(getByRole("button", { name: "培养方案.xlsx" }));
    expect(onOpenReference).toHaveBeenCalledWith(reference);
    fireEvent.click(getByRole("button", { name: "移除上下文：培养方案.xlsx" }));
    expect(onRemoveReference).toHaveBeenCalledWith(reference);
    expect(document.activeElement).not.toBe(getByRole("textbox"));
  });
  it("focuses the textarea when the Prompt Kit surface is clicked", () => {
    const { container, getByRole } = renderComposer();
    const composer = container.querySelector(".dbfox-composer__prompt-input");
    const textarea = getByRole("textbox", { name: "Composer" });

    expect(composer).not.toBeNull();
    fireEvent.click(composer!);

    expect(document.activeElement).toBe(textarea);
  });

  it("submits on Enter, preserves Shift+Enter, and ignores IME composition", () => {
    const { onSubmit, getByRole } = renderComposer();
    const textarea = getByRole("textbox", { name: "Composer" });

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    fireEvent.keyDown(textarea, { key: "Enter", isComposing: true });
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("renders an upward send arrow and no context button", () => {
    const { container, getByRole, queryByRole } = renderComposer("hello");
    const send = getByRole("button", { name: /发送：/ });
    const icon = send.querySelector("svg");

    expect(icon?.querySelector("use")?.getAttribute("href")).toContain("#arrow-up-regular");
    expect(queryByRole("button", { name: "添加上下文" })).toBeNull();
    expect(container.querySelector(".dbfox-composer__context")).toBeNull();
  });

  it("keeps Stop independent from Send while drafting a follow-up", () => {
    const { getByRole, onCancel, queryByRole, rerender } = renderComposer("", { running: true });
    const stop = getByRole("button", { name: "停止当前任务" });

    expect(getByRole("button", { name: /发送：/ }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(stop);
    expect(onCancel).toHaveBeenCalledTimes(1);

    rerender(
      <UnifiedComposer
        value="follow up"
        onChange={() => undefined}
        onSubmit={() => undefined}
        onCancel={onCancel}
        placeholder="Describe the work"
        ariaLabel="Composer"
        running
      />,
    );

    const send = getByRole("button", { name: "发送：排队执行" });
    expect(stop.isSameNode(getByRole("button", { name: "停止当前任务" }))).toBe(true);
    expect(send.hasAttribute("disabled")).toBe(false);
    expect(queryByRole("button", { name: "停止当前任务" })).not.toBeNull();
  });

  it("waits for cancellation confirmation and preserves an editable draft", () => {
    const { getByRole, onCancel, onSubmit } = renderComposer("follow up", { running: true, cancelling: true });
    expect(getByRole("button", { name: "正在停止当前任务" }).hasAttribute("disabled")).toBe(true);
    expect(getByRole("textbox").hasAttribute("disabled")).toBe(false);
    fireEvent.keyDown(getByRole("textbox"), { key: "Escape" });
    fireEvent.keyDown(getByRole("textbox"), { key: "Enter" });
    expect(onCancel).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("allows a new draft during admission and ignores Escape from an IME", () => {
    const { getByRole, onChange, onCancel } = renderComposer("draft", { running: true, submitting: true });
    fireEvent.change(getByRole("textbox"), { target: { value: "next draft" } });
    expect(onChange).toHaveBeenCalledWith("next draft");
    fireEvent.keyDown(getByRole("textbox"), { key: "Escape", isComposing: true });
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("supports Escape as keyboard parity for the active stop action", () => {
    const { getByRole, onCancel } = renderComposer("draft", { running: true });
    fireEvent.keyDown(getByRole("textbox", { name: "Composer" }), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed stop request distinct from a confirmed stop", async () => {
    const onCancel = vi.fn().mockRejectedValue(new Error("connection lost"));
    const { getByRole, getByText } = renderComposer("保留草稿", { running: true, onCancel, cancelError: new Error("connection lost") });
    fireEvent.click(getByRole("button", { name: "停止当前任务" }));
    await Promise.resolve();
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(getByText("停止请求未确认，任务可能仍在运行。")).toBeTruthy();
    expect((getByRole("textbox") as HTMLTextAreaElement).value).toBe("保留草稿");
    expect(getByRole("button", { name: /发送：/ }).querySelector("use")?.getAttribute("href")).toContain("#arrow-up-regular");
  });
});
