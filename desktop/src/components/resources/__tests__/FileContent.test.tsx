import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileContent } from "../FileContent";

afterEach(cleanup);

describe("read-only file viewing", () => {
  it("opens Markdown as a document and switches the same content to source and split", () => {
    render(<FileContent name="docs/guide.md" content={'# 项目说明\n\n这里是 **正文**。'} />);
    expect(screen.getByRole("heading", { name: "项目说明" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "源码" }));
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByText("# 项目说明")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "分栏" }));
    expect(screen.getByRole("heading", { name: "项目说明" })).toBeTruthy();
    expect(screen.getByText("# 项目说明")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("highlights Python with the official grammar and forwards the context action", async () => {
    const onAsk = vi.fn();
    const view = render(<FileContent name="main.py" content={'def greet():\n    return "hello"'} onAsk={onAsk} />);
    await waitFor(() => expect(view.container.querySelector(".tok-keyword")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入对话" }));
    expect(onAsk).toHaveBeenCalledOnce();
    expect(view.container.querySelector("[contenteditable]" )).toBeNull();
  });

  it("keeps file HTML as inert source text", () => {
    const view = render(<FileContent name="page.html" content={'<script>window.fileExecuted = true</script><h1>文件标题</h1>'} />);
    expect(view.container.querySelector("script")).toBeNull();
    expect(screen.queryByRole("heading")).toBeNull();
  });
});
