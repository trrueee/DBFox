import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectCreateForm } from "../ProjectCreateForm";

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

describe("ProjectCreateForm", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    folderApi.pickProjectFolder.mockResolvedValue(null);
    projectState.createProject.mockResolvedValue({ id: "project-new" });
  });

  it("selects a local folder, derives the default name, and sends workspace_root", async () => {
    folderApi.pickProjectFolder.mockResolvedValue("C:/demo/orders");
    const onCreated = vi.fn();
    render(<ProjectCreateForm onCreated={onCreated} onCancel={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "选择文件夹" }));
    await waitFor(() => expect(screen.getByDisplayValue("orders")).toBeInTheDocument());
    expect(screen.getByText("C:/demo/orders")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() =>
      expect(projectState.createProject).toHaveBeenCalledWith({
        name: "orders",
        description: null,
        workspace_root: "C:/demo/orders",
      }),
    );
    expect(onCreated).toHaveBeenCalledWith("project-new");
  });

  it("requires a folder before submitting", async () => {
    render(<ProjectCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "手工项目" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    expect(await screen.findByText("请先选择项目文件夹。")).toBeInTheDocument();
    expect(projectState.createProject).not.toHaveBeenCalled();
  });

  it("keeps a user-entered name when the folder picker returns", async () => {
    folderApi.pickProjectFolder.mockResolvedValue("D:/work/project-x");
    render(<ProjectCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "保留名称" },
    });
    fireEvent.click(screen.getByRole("button", { name: "选择文件夹" }));
    await waitFor(() => expect(screen.getByDisplayValue("保留名称")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() =>
      expect(projectState.createProject).toHaveBeenCalledWith(
        expect.objectContaining({ name: "保留名称", workspace_root: "D:/work/project-x" }),
      ),
    );
  });
});
