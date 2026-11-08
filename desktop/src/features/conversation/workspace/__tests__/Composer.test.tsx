import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../../lib/api/client";
import { useWorkspaceStore } from "../../../../stores/workspaceStore";
import { Composer } from "../Composer";

describe("Composer", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({ activeProjectId: "p1", mainSurfaceByProject: {}, workbenchByConversation: {} });
  });
  afterEach(() => {
    cleanup();
  });

  it("renders the shared composer in the conversation rail without unavailable actions", () => {
    const { container } = render(
      <Composer running={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(container.querySelector(".conv-composer-rail")).toBeTruthy();
    expect(container.querySelector(".dbfox-composer")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "继续提问" }).getAttribute("placeholder")).toBe("");
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

  it("restores separate conversation drafts after navigation unmounts the input", () => {
    const props = { running: false, onSend: vi.fn(), onCancel: vi.fn() };
    const first = render(<Composer {...props} conversationId="c1" />);
    fireEvent.change(screen.getByRole("textbox", { name: "继续提问" }), { target: { value: "项目一的未发送问题" } });
    first.unmount();
    const second = render(<Composer {...props} conversationId="c2" />);
    const secondInput = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    expect(secondInput.value).toBe("");
    fireEvent.change(secondInput, { target: { value: "项目二的未发送问题" } });
    second.unmount();
    const restored = render(<Composer {...props} conversationId="c1" />);
    expect((screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement).value).toBe("项目一的未发送问题");
    restored.unmount();
    render(<Composer {...props} conversationId="c2" />);
    expect((screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement).value).toBe("项目二的未发送问题");
  });

  it("does not clear a newer draft when an earlier admission finishes after navigation", async () => {
    let resolve!: () => void;
    const onSend = vi.fn(() => new Promise<void>(done => { resolve = done; }));
    const first = render(<Composer running={false} conversationId="c1" onSend={onSend} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "继续提问" }), { target: { value: "正在发送的问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送：立即执行" }));
    first.unmount();
    render(<Composer running={false} conversationId="c1" onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "接着写的新草稿" } });
    resolve();
    await waitFor(() => expect(onSend).toHaveResolved());
    expect(input.value).toBe("接着写的新草稿");
  });

  it.each([true, false])("settles admission in its original conversation after switching (accepted=%s)", async accepted => {
    let resolve!: () => void;
    let reject!: (error: Error) => void;
    const onSend = vi.fn(() => new Promise<void>((done, fail) => { resolve = done; reject = fail; }));
    const originalRef = { label: "原始引用", artifactId: "a1" };
    const nextRef = { label: "新项目引用", artifactId: "a2" };
    const workspace = useWorkspaceStore.getState();
    workspace.setProjectActiveConversation("p1", "c1");
    workspace.addWorkbenchReference(originalRef);
    const first = render(<Composer running={false} conversationId="c1" onSend={onSend} onCancel={vi.fn()}
      references={[originalRef]} onClearReferences={() => workspace.clearWorkbenchReferences("c1")} />);
    fireEvent.change(screen.getByRole("textbox", { name: "继续提问" }), { target: { value: "原始问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送：立即执行" }));
    first.unmount();

    workspace.setActiveProject("p2");
    workspace.setProjectActiveConversation("p2", "c2");
    workspace.addWorkbenchReference(nextRef);
    render(<Composer running={false} conversationId="c2" onSend={vi.fn()} onCancel={vi.fn()} references={[nextRef]} />);
    const input = screen.getByRole("textbox", { name: "继续提问" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "新项目的问题" } });
    await act(async () => {
      if (accepted) resolve(); else reject(new Error("admission failed"));
      await onSend.mock.results[0].value.catch(() => undefined);
    });

    expect(input.value).toBe("新项目的问题");
    expect(useWorkspaceStore.getState().workbenchByConversation.c2.references).toEqual([nextRef]);
    expect(useWorkspaceStore.getState().workbenchByConversation.c1.draftInput).toBe(accepted ? "" : "原始问题");
    expect(useWorkspaceStore.getState().workbenchByConversation.c1.references).toEqual(accepted ? [] : [originalRef]);
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
    expect(screen.getByRole("button", { name: "orders (table)" }).getAttribute("aria-description")).toBe("数据表");
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
