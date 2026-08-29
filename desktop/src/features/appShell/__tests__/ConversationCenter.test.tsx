import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../lib/api/client";
import { useConversationStore } from "../../../stores/conversationStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { ConversationCenter } from "../ConversationCenter";

const smartQueryProps = vi.hoisted(() => ({
  latest: null as Record<string, unknown> | null,
}));
const originalConversationActions = {
  createAndOpenConversation: useConversationStore.getState().createAndOpenConversation,
  sendMessage: useConversationStore.getState().sendMessage,
};

vi.mock("../../workspace/SmartQueryHome", () => ({
  SmartQueryHome: (props: Record<string, unknown>) => {
    smartQueryProps.latest = props;
    return <div data-testid="smart-query-home">{props.feedback as ReactNode}</div>;
  },
}));
vi.mock("../../conversation/workspace/ConversationWorkspace", () => ({
  ConversationWorkspace: () => (
    <div data-testid="conversation-workspace" data-main-surface="conversation" />
  ),
}));

describe("ConversationCenter", () => {
  beforeEach(() => {
    cleanup();
    smartQueryProps.latest = null;
    useWorkspaceStore.setState({
      activeProjectId: "",
      centerMode: "home",
      mainSurfaceByProject: {},
      pendingAsk: null,
      settingsOpen: false,
    });
    useConversationStore.setState(originalConversationActions);
  });

  it("gates on project existence, not on datasource", () => {
    render(<ConversationCenter onNewProject={vi.fn()} />);

    expect(screen.getByText("创建第一个项目")).toBeTruthy();
    expect(screen.getByRole("button", { name: /新建项目/ })).toBeTruthy();
    expect(screen.queryByTestId("smart-query-home")).toBeNull();
  });

  it("runs the conversation home with an active project even without any datasource", () => {
    useWorkspaceStore.setState({ activeProjectId: "project-1" });
    render(<ConversationCenter onNewProject={vi.fn()} />);

    expect(screen.getByTestId("smart-query-home")).toBeTruthy();
  });

  it("renders the ask home and carries a pending ask from the dock", () => {
    useWorkspaceStore.setState({ activeProjectId: "project-1", pendingAsk: "分析最近一周注册用户" });
    render(<ConversationCenter onNewProject={vi.fn()} />);

    expect(screen.getByTestId("smart-query-home")).toBeTruthy();
    expect(smartQueryProps.latest).toMatchObject({ askInputValue: "分析最近一周注册用户" });
  });

  it("renders only the conversation workspace when a conversation is active", async () => {
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      centerMode: "conversation",
      mainSurfaceByProject: {
        "project-1": { kind: "conversation", conversationId: "conv-1" },
      },
    });
    render(<ConversationCenter onNewProject={vi.fn()} />);

    expect(await screen.findByTestId("conversation-workspace")).toBeTruthy();
    expect(screen.queryByTestId("smart-query-home")).toBeNull();
    expect(screen.getByTestId("conversation-workspace").getAttribute("data-main-surface")).toBe("conversation");
  });

  it("opens project creation from the empty state action", async () => {
    const onNewProject = vi.fn();
    render(<ConversationCenter onNewProject={onNewProject} />);

    fireEvent.click(screen.getByRole("button", { name: /新建项目/ }));
    expect(onNewProject).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed task submission and safe correlation metadata on the ask surface", async () => {
    useWorkspaceStore.setState({ activeProjectId: "project-1" });
    useConversationStore.setState({
      createAndOpenConversation: vi.fn().mockRejectedValue(new ApiError(
        "private provider endpoint failed",
        503,
        "AGENT_REQUEST_ERROR",
        [],
        { request_id: "conversation-request-9", secret: "must-not-render" },
      )),
    });
    render(<ConversationCenter onNewProject={vi.fn()} />);

    (smartQueryProps.latest?.onAskInputChange as (value: string) => void)("分析订单");
    await waitFor(() => expect(smartQueryProps.latest?.askInputValue).toBe("分析订单"));
    (smartQueryProps.latest?.onSubmitAsk as () => void)();

    expect(await screen.findByText("无法开始任务")).toBeTruthy();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("AGENT_REQUEST_ERROR")).toBeTruthy();
    expect(screen.getByText("conversation-request-9")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private provider endpoint failed");
    expect(document.body.textContent).not.toContain("must-not-render");
    expect(smartQueryProps.latest?.askInputValue).toBe("分析订单");
  });

  it("retries a failed admission with the same conversation and idempotency key", async () => {
    useWorkspaceStore.setState({ activeProjectId: "project-1" });
    const createConversation = vi.fn().mockResolvedValue({ id: "conversation-retry" });
    const sendMessage = vi.fn()
      .mockRejectedValueOnce(new ApiError("admission failed", 503, "AGENT_REQUEST_ERROR"))
      .mockResolvedValueOnce(undefined);
    useConversationStore.setState({
      createAndOpenConversation: createConversation,
      sendMessage,
    });
    render(<ConversationCenter onNewProject={vi.fn()} />);

    (smartQueryProps.latest?.onAskInputChange as (value: string) => void)("分析订单");
    await waitFor(() => expect(smartQueryProps.latest?.askInputValue).toBe("分析订单"));
    (smartQueryProps.latest?.onSubmitAsk as () => void)();
    fireEvent.click(await screen.findByRole("button", { name: "重试发送" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2));
    expect(createConversation).toHaveBeenCalledTimes(1);
    expect(sendMessage.mock.calls[0][0]).toBe("conversation-retry");
    expect(sendMessage.mock.calls[1][0]).toBe("conversation-retry");
    expect(sendMessage.mock.calls[1][3]).toBe(sendMessage.mock.calls[0][3]);
  });
});
