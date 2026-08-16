import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceDockTab } from "../../../types/workspace";
import { WorkspaceFileDockContent } from "../WorkspaceFileDock";

const projectFolderApi = vi.hoisted(() => ({
  readProjectFile: vi.fn(),
}));

vi.mock("../../../lib/projectFolder", () => ({
  readProjectFile: projectFolderApi.readProjectFile,
}));

function tab(): WorkspaceDockTab {
  return {
    id: "file-project-1-C:/demo/blob.bin",
    kind: "file",
    title: "blob.bin",
    closeable: true,
    projectId: "project-1",
    filePath: "C:/demo/blob.bin",
    fileName: "blob.bin",
  };
}

describe("WorkspaceFileDockContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
