import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "../../../components/ui";
import { useConversationStore } from "../../../stores/conversationStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { ConversationDetail } from "../../../types/conversation";
import { ProjectResourceSidebar } from "../ProjectResourceSidebar";

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
      summaries: [
        { id: "conv-1", project_id: "project-1", title: "重构产品界面", updated_at: "2026-08-15T08:00:00Z" },
        { id: "conv-2", project_id: "project-2", title: "其他项目", updated_at: "2026-08-16T08:00:00Z" },
      ],
      openConversation,
    });
  });

  it("nests each project's conversations and resources directly under its row", () => {
    renderSidebar();

    expect(screen.getByRole("button", { name: "新任务" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "主页" })).toBeInTheDocument();
    expect(screen.getByText("项目")).toBeInTheDocument();

    // The active project's group auto-expands: conversations and resource sections
    // sit directly under the project row — no chevron, no sub-group headers.
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

  it("opens project management through the row's hover action", () => {
    renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: "管理项目 Research" }));

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
  collapsed?: boolean;
  onOpenSettings?: () => void;
  onOpenExtensions?: () => void;
} = {}) {
  return render(
    <TooltipProvider>
      <ProjectResourceSidebar
        connectors={[]}
        collapsed={overrides.collapsed ?? false}
        onToggleCollapse={vi.fn()}
        onNewProject={vi.fn()}
        onOpenSettings={overrides.onOpenSettings ?? vi.fn()}
        onOpenExtensions={overrides.onOpenExtensions ?? vi.fn()}
      />
    </TooltipProvider>,
  );
}
