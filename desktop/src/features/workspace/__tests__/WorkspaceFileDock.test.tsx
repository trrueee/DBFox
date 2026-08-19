import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceDockTab } from "../../../types/workspace";
import { useWorkspaceFileStore } from "../../../stores/workspaceFileStore";
import { WorkspaceFileDockContent } from "../WorkspaceFileDock";

const projectFolderApi = vi.hoisted(() => ({
  readProjectFile: vi.fn(),
}));

vi.mock("../../../lib/projectFolder", () => ({
  readProjectFile: projectFolderApi.readProjectFile,
}));

function tab(): WorkspaceDockTab {
  return {
    viewKey: "dbfox.workspace.file:project-1:C:/demo/blob.bin",
    viewType: "dbfox.workspace.file",
    title: "blob.bin",
    closeable: true,
    projectId: "project-1",
    stateKey: "dbfox.workspace.file:project-1:C:/demo/blob.bin",
    target: { type: "resource", kind: "workspace", id: "project-1" },
  };
}

describe("WorkspaceFileDockContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceFileStore.setState({
      fileStateByKey: {
        "dbfox.workspace.file:project-1:C:/demo/blob.bin": {
          projectId: "project-1",
          filePath: "C:/demo/blob.bin",
          fileName: "blob.bin",
        },
      },
    });
    projectFolderApi.readProjectFile.mockResolvedValue({
      path: "C:/demo/blob.bin",
      name: "blob.bin",
      content: null,
      binary: true,
      size: 4,
      error: "二进制文件不支持预览",
    });
  });

  it("shows a retryable error state for binary or unreadable files", async () => {
    render(<WorkspaceFileDockContent tab={tab()} />);

    expect(screen.getByText("正在读取文件…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("无法预览文件")).toBeInTheDocument());
    expect(screen.getByText("二进制文件不支持预览")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    await waitFor(() => expect(projectFolderApi.readProjectFile).toHaveBeenCalledTimes(2));
  });
});
