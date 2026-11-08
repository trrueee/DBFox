import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "../../../components/ui";
import { useConversationStore } from "../../../stores/conversationStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { ConversationDetail } from "../../../types/conversation";
import { ProjectResourceSidebar } from "../ProjectResourceSidebar";
import type { ResourceConnectorContribution } from "../types";

vi.mock("../../projects/useProjectState", () => ({
  useProjectState: () => ({
    projects: [
      { id: "project-1", name: "DBFox", status: "active" },
      { id: "project-2", name: "Research", status: "active" },
    ],
    loadingProjects: false,
    projectError: "",
  }),
}));

const openConversation = vi.fn(async () => ({} as ConversationDetail));

describe("ProjectResourceSidebar", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      mainSurfaceByProject: { "project-1": { kind: "new-conversation" } },
    });
    useConversationStore.setState({
      detailById: {},
      summaries: [
        { id: "conv-1", project_id: "project-1", title: "重构产品界面", updated_at: "2026-08-15T08:00:00Z" },
        { id: "conv-2", project_id: "project-2", title: "其他项目", updated_at: "2026-08-16T08:00:00Z" },
      ],
      openConversation,
    });
  });

  it("nests only conversations under each folder project", () => {
    renderSidebar();

    expect(screen.getByRole("button", { name: "新任务" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主页" })).not.toBeInTheDocument();
    expect(screen.getByText("项目")).toBeInTheDocument();

    // The active project expands to conversations; capabilities open from its menu.
    expect(screen.getByRole("button", { name: /^重构产品界面/ })).toBeInTheDocument();
    expect(screen.queryByText("最近工作")).not.toBeInTheDocument();
    expect(screen.queryByText("对话")).not.toBeInTheDocument();
    expect(screen.queryByText("资源")).not.toBeInTheDocument();

    // Other projects stay collapsed: their conversations are not rendered.
    expect(screen.queryByRole("button", { name: /^其他项目/ })).not.toBeInTheDocument();
  });

  it("expands a project's conversation overflow through 显示更多", () => {
    const summaries = Array.from({ length: 7 }, (_, index) => ({
      id: `conv-${index}`,
      project_id: "project-1",
      title: `任务 ${index}`,
      updated_at: "2026-08-15T08:00:00Z",
    }));
    useConversationStore.setState({ summaries });

    renderSidebar();

    expect(screen.getByRole("button", { name: /^任务 4/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^任务 5/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /显示更多/ }));

    expect(screen.getByRole("button", { name: /^任务 5/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^任务 6/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "收起" }));
    expect(screen.queryByRole("button", { name: /^任务 5/ })).not.toBeInTheDocument();
  });

  it("keeps waiting and running threads reachable ahead of historical overflow", () => {
    useConversationStore.setState({ summaries: [
      ...Array.from({ length: 6 }, (_, index) => ({ id: `old-${index}`, project_id: "project-1", title: `历史 ${index}`, updated_at: null, run_status: "completed" as const })),
      { id: "waiting", project_id: "project-1", title: "需要确认的修改", updated_at: null, run_status: "waiting_approval" },
      { id: "running", project_id: "project-1", title: "长任务", updated_at: null, run_status: "running" },
    ] });
    renderSidebar();
    expect(screen.getByRole("button", { name: /^需要确认的修改/ })).toHaveAccessibleDescription("等待审批");
    expect(screen.getByRole("button", { name: /^长任务/ })).toHaveAccessibleDescription("运行中");
    expect(screen.getByRole("status", { name: "线程状态概览" })).toHaveTextContent("1 待介入");
    expect(screen.queryByRole("button", { name: /^历史 5/ })).not.toBeInTheDocument();
  });

  it("updates a beacon from the durable run without waiting for an index refresh", () => {
    useConversationStore.setState({ summaries: [{ id: "conv-1", project_id: "project-1", title: "正在修改", updated_at: null, run_status: "completed" }] });
    renderSidebar();
    expect(screen.getByRole("button", { name: /^正在修改/ })).toHaveAccessibleDescription("本轮已结束");
    act(() => useConversationStore.getState().loadConversation({
      protocol_version: 2, id: "conv-1", project_id: "project-1", title: "正在修改", resource_intents: [], items: [],
      runs: [{ id: "run-1", session_id: "conv-1", input_id: "input-1", session_sequence: 1, user_message_id: "message-1",
        question: "修改文件", status: "waiting_approval", version: 1, cancel_requested: false, result: {}, error: null }],
    }));
    expect(screen.getByRole("button", { name: /^正在修改/ })).toHaveAccessibleDescription("等待审批");
    expect(screen.getByRole("status", { name: "线程状态概览" })).toHaveTextContent("1 待介入");
    expect(useConversationStore.getState().summaries[0].run_status).toBe("completed");
  });

  it("keeps waiting threads accessible from the collapsed navigation", async () => {
    useConversationStore.setState({ summaries: [{ id: "conv-1", project_id: "project-1", title: "需要批准", updated_at: null, run_status: "waiting_approval" }] });
    renderSidebar({ collapsed: true });
    fireEvent.click(screen.getByRole("button", { name: "1 个对话待介入" }));
    await waitFor(() => expect(openConversation).toHaveBeenCalledWith("conv-1"));
    expect(useWorkspaceStore.getState().mainSurfaceByProject["project-1"]).toEqual({ kind: "conversation", conversationId: "conv-1" });
  });

  it("focuses a project on row click and toggles its group without forcing a surface", () => {
    renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: "Research" }));

    expect(useWorkspaceStore.getState().activeProjectId).toBe("project-2");
    expect(useWorkspaceStore.getState().mainSurfaceByProject["project-2"]).toBeUndefined();
    expect(screen.getByRole("button", { name: /^其他项目/ })).toBeInTheDocument();

    // Clicking the active project's row collapses its group.
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(screen.queryByRole("button", { name: /^其他项目/ })).not.toBeInTheDocument();
  });

  it("opens project settings through the visible project menu", async () => {
    renderSidebar();

    fireEvent.pointerDown(screen.getByRole("button", { name: "管理项目 Research" }), { button: 0, ctrlKey: false, pointerType: "mouse" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "项目设置" }));

    expect(useWorkspaceStore.getState().activeProjectId).toBe("project-2");
    expect(useWorkspaceStore.getState().mainSurfaceByProject["project-2"]).toEqual({
      kind: "project-overview",
    });
  });

  it("opens recent work through the existing conversation authority", async () => {
    renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: /^重构产品界面/ }));

    await waitFor(() => expect(openConversation).toHaveBeenCalledWith("conv-1"));
    expect(useWorkspaceStore.getState().mainSurfaceByProject["project-1"]).toEqual({
      kind: "conversation",
      conversationId: "conv-1",
    });
  });

  it.each([false, true])("invokes an owner's creation action without opening another workbench first (%s)", async (directWorkbench) => {
    const onAdd = vi.fn(async () => {});
    const onOpen = vi.fn();
    const openDock = vi.spyOn(useWorkspaceStore.getState(), "openDockTab").mockImplementation(() => {});
    try {
      renderSidebar({ connectors: [{
        id: "example.creation", title: "Studio", icon: null, render: () => null,
        addLabel: "创建作品", onAdd, ...(directWorkbench ? { onOpen } : {}),
      }] });
      fireEvent.pointerDown(screen.getByRole("button", { name: "管理项目 Research" }), { button: 0, ctrlKey: false, pointerType: "mouse" });
      fireEvent.click(await screen.findByRole("menuitem", { name: "创建作品" }));
      await waitFor(() => expect(onAdd).toHaveBeenCalledWith({ projectId: "project-2" }));
      expect(onOpen).not.toHaveBeenCalled();
      expect(openDock).not.toHaveBeenCalled();
    } finally { openDock.mockRestore(); }
  });

  it("routes Extensions and Settings through Core-owned destinations", () => {
    const onOpenExtensions = vi.fn();
    const onOpenSettings = vi.fn();
    renderSidebar({ onOpenExtensions, onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: "扩展" }));
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(onOpenExtensions).toHaveBeenCalledOnce();
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });

  it("keeps primary actions available in the 48px collapsed rail", () => {
    renderSidebar({ collapsed: true });

    expect(screen.getByRole("button", { name: "展开导航" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新任务" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主页" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "扩展" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "设置" })).toBeInTheDocument();
  });
});

function renderSidebar(overrides: {
  connectors?: ResourceConnectorContribution[];
  collapsed?: boolean;
  onOpenSettings?: () => void;
  onOpenExtensions?: () => void;
} = {}) {
  return render(
    <TooltipProvider>
      <ProjectResourceSidebar
        connectors={overrides.connectors ?? []}
        collapsed={overrides.collapsed ?? false}
        onToggleCollapse={vi.fn()}
        onNewProject={vi.fn()}
        onOpenSettings={overrides.onOpenSettings ?? vi.fn()}
        onOpenExtensions={overrides.onOpenExtensions ?? vi.fn()}
      />
    </TooltipProvider>,
  );
}
