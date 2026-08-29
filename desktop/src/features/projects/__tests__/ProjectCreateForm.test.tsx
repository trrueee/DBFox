import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../lib/api/client";
import { ProjectCreateForm } from "../ProjectCreateForm";

const projectState = vi.hoisted(() => ({
  createProject: vi.fn(),
}));

vi.mock("../useProjectState", () => ({
  useProjectState: () => ({ createProject: projectState.createProject }),
}));

describe("ProjectCreateForm", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    projectState.createProject.mockResolvedValue({ id: "project-new" });
  });

  it("creates an identity-only project without requiring a folder", async () => {
    const onCreated = vi.fn();
    render(<ProjectCreateForm onCreated={onCreated} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "orders" },
    });

    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() =>
      expect(projectState.createProject).toHaveBeenCalledWith({
        name: "orders",
        description: null,
      }),
    );
    expect(onCreated).toHaveBeenCalledWith("project-new");
  });

  it("requires only a project name", async () => {
    render(<ProjectCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "手工项目" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => expect(projectState.createProject).toHaveBeenCalledWith({
      name: "手工项目",
      description: null,
    }));
  });

  it("preserves an optional project description", async () => {
    render(<ProjectCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "保留名称" },
    });
    fireEvent.change(screen.getByPlaceholderText("这个项目主要分析什么？"), {
      target: { value: "  项目说明  " },
    });

    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() =>
      expect(projectState.createProject).toHaveBeenCalledWith(
        { name: "保留名称", description: "项目说明" },
      ),
    );
  });

  it("keeps create failures inline with safe correlation metadata", async () => {
    projectState.createProject.mockRejectedValueOnce(new ApiError(
      "database path C:\\private\\projects.db",
      503,
      "PROJECT_CREATE_UNAVAILABLE",
      [],
      { request_id: "project-request-7", secret: "must-not-render" },
    ));
    render(<ProjectCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("例如：电商经营分析"), {
      target: { value: "orders" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    expect(await screen.findByText("创建项目失败")).toBeTruthy();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("PROJECT_CREATE_UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("project-request-7")).toBeTruthy();
    expect(document.body.textContent).not.toContain("C:\\private\\projects.db");
    expect(document.body.textContent).not.toContain("must-not-render");
  });
});
