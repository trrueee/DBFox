import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectCreateDialog } from "../ProjectCreateDialog";
import { useWorkspaceStore } from "../../../stores/workspaceStore";

vi.mock("../ProjectCreateForm", () => ({
  ProjectCreateForm: ({ onCreated, onCancel }: { onCreated: (id: string) => void; onCancel: () => void }) => <div><button onClick={() => onCreated("project-abc")}>选择文件夹</button><button onClick={onCancel}>取消</button></div>,
}));

describe("ProjectCreateDialog", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      activeProjectId: "",
      projectCreateOpen: false,
      centerMode: "conversation",
    });
  });

  it("does not render modal content when projectCreateOpen is false", () => {
    render(<ProjectCreateDialog />);
    expect(screen.queryByText("打开文件夹")).not.toBeInTheDocument();
  });

  it("renders modal and creates project, switching active project and closing modal", async () => {
    useWorkspaceStore.setState({ projectCreateOpen: true });
    render(<ProjectCreateDialog />);
    expect(screen.getByText("打开文件夹")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "选择文件夹" }));
    await waitFor(() => expect(useWorkspaceStore.getState().activeProjectId).toBe("project-abc"));

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
