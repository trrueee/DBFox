import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectCreateDialog } from "../ProjectCreateDialog";
import { useWorkspaceStore } from "../../../stores/workspaceStore";

const projectState = vi.hoisted(() => ({
  createProject: vi.fn(),
}));

vi.mock("../useProjectState", () => ({
  useProjectState: () => ({ createProject: projectState.createProject }),
}));

describe("ProjectCreateDialog", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    projectState.createProject.mockResolvedValue({ id: "project-abc" });
    useWorkspaceStore.setState({
      activeProjectId: "",
      projectCreateOpen: false,
      centerMode: "conversation",
    });
  });

  it("does not render modal content when projectCreateOpen is false", () => {
    render(<ProjectCreateDialog />);
    expect(screen.queryByText("新建项目")).not.toBeInTheDocument();
  });

  it("renders modal and creates project, switching active project and closing modal", async () => {
    useWorkspaceStore.setState({ projectCreateOpen: true });
    render(<ProjectCreateDialog />);
    expect(screen.getByText("新建项目")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "analytics" },
    });

    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => {
      expect(projectState.createProject).toHaveBeenCalledWith({
        name: "analytics",
        description: null,
      });
    });

    expect(useWorkspaceStore.getState().activeProjectId).toBe("project-abc");
    expect(useWorkspaceStore.getState().projectCreateOpen).toBe(false);
  });

  it("closes dialog on Cancel button click", () => {
    useWorkspaceStore.setState({ projectCreateOpen: true });
    render(<ProjectCreateDialog />);

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(useWorkspaceStore.getState().projectCreateOpen).toBe(false);
  });
});
