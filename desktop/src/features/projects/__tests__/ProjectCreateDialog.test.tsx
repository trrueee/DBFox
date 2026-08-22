import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectCreateDialog } from "../ProjectCreateDialog";
import { useWorkspaceStore } from "../../../stores/workspaceStore";

const projectState = vi.hoisted(() => ({
  createProject: vi.fn(),
}));
const folderApi = vi.hoisted(() => ({
  pickProjectFolder: vi.fn(),
}));

vi.mock("../useProjectState", () => ({
  useProjectState: () => ({ createProject: projectState.createProject }),
}));
vi.mock("../../../lib/projectFolder", () => ({
  pickProjectFolder: folderApi.pickProjectFolder,
}));

describe("ProjectCreateDialog", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    folderApi.pickProjectFolder.mockResolvedValue(null);
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
    folderApi.pickProjectFolder.mockResolvedValue("D:/work/analytics");

    render(<ProjectCreateDialog />);
    expect(screen.getByText("新建项目")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "选择文件夹" }));
    await waitFor(() => expect(screen.getByDisplayValue("analytics")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => {
      expect(projectState.createProject).toHaveBeenCalledWith({
        name: "analytics",
        description: null,
        workspace_root: "D:/work/analytics",
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
