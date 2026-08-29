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

    expect(icon?.classList.contains("lucide-arrow-up")).toBe(true);
    expect(queryByRole("button", { name: "添加上下文" })).toBeNull();
    expect(container.querySelector(".dbfox-composer__context")).toBeNull();
  });

  it("uses one primary action slot for send and stop", () => {
    const { getByRole, onCancel, queryByRole, rerender } = renderComposer("", { running: true });
    const stop = getByRole("button", { name: "停止当前任务" });

    expect(queryByRole("button", { name: /发送：/ })).toBeNull();
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
    expect(stop.isSameNode(send)).toBe(true);
    expect(queryByRole("button", { name: "停止当前任务" })).toBeNull();
  });

  it("supports Escape as keyboard parity for the active stop action", () => {
    const { getByRole, onCancel } = renderComposer("draft", { running: true });
    fireEvent.keyDown(getByRole("textbox", { name: "Composer" }), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
