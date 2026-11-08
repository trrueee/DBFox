import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectCreateForm } from "../ProjectCreateForm";
import { useDlcStore } from "../../dlc/extensionStore";

const fixture = vi.hoisted(() => ({ createProject: vi.fn(), pick: vi.fn(), invoke: vi.fn(), listResources: vi.fn(), projects: [] as Array<{ id: string; name: string }> }));
vi.mock("../useProjectState", () => ({ useProjectState: () => ({ createProject: fixture.createProject, projects: fixture.projects, loadingProjects: false }) }));
vi.mock("../../../lib/desktopHost", () => ({ pickDesktopProjectFolder: fixture.pick }));
vi.mock("../../dlc/extensionHost", () => ({ invokeBoundDlcOperation: fixture.invoke }));

describe("folder-first project opening", () => {
  beforeEach(() => {
    vi.clearAllMocks(); fixture.projects = [];
    fixture.pick.mockResolvedValue("D:/work/orders");
    fixture.createProject.mockResolvedValue({ id: "project-new" });
    fixture.listResources.mockResolvedValue([]);
    fixture.invoke.mockImplementation(async (_owner, name) => name === "binding.get" ? { binding: null } : {});
    vi.stubGlobal("crypto", { subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) } });
    useDlcStore.setState({ contributions: { connectors: [{ id: "dbfox.workspace", title: "文件", icon: null, render: () => null, listResources: fixture.listResources }], dockViews: [], artifactViews: [] } });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("uses the folder name and binds it through the existing owner operation", async () => {
    const onCreated = vi.fn(); render(<ProjectCreateForm onCreated={onCreated} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "打开文件夹" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("project-new"));
    expect(fixture.createProject).toHaveBeenCalledWith(expect.objectContaining({ name: "orders", description: null, idempotency_key: expect.stringMatching(/^folder:[a-f0-9]{64}$/) }));
    expect(fixture.invoke).toHaveBeenCalledWith("dbfox.workspace", "binding.create", { root_path: "D:/work/orders" }, { projectId: "project-new" });
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("reopens a previously bound folder instead of creating another project", async () => {
    fixture.projects = [{ id: "existing", name: "orders" }];
    fixture.listResources.mockResolvedValue([{ id: "existing", kind: "dbfox.workspace.binding", name: "d:/WORK/orders" }]);
    const onCreated = vi.fn(); render(<ProjectCreateForm onCreated={onCreated} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "打开文件夹" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("existing"));
    expect(fixture.createProject).not.toHaveBeenCalled(); expect(fixture.invoke).not.toHaveBeenCalled();
  });

  it("does not create anything when the native picker is cancelled", async () => {
    fixture.pick.mockResolvedValue(null);
    render(<ProjectCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "打开文件夹" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "打开文件夹" })).not.toBeDisabled());
    expect(fixture.createProject).not.toHaveBeenCalled();
  });

  it("reconciles an uncertain binding result before an explicit retry", async () => {
    let reads = 0;
    fixture.invoke.mockImplementation(async (_owner, name) => {
      if (name === "binding.get") return { binding: ++reads === 1 ? null : { root_path: "D:/work/orders" } };
      throw new Error("connection interrupted");
    });
    const onCreated = vi.fn(); render(<ProjectCreateForm onCreated={onCreated} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "打开文件夹" }));
    expect(await screen.findByText("打开文件夹失败")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试打开" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("project-new"));
    expect(fixture.pick).toHaveBeenCalledOnce();
    expect(fixture.createProject.mock.calls[0][0]).toEqual(fixture.createProject.mock.calls[1][0]);
    expect(fixture.invoke.mock.calls.filter(call => call[1] === "binding.create")).toHaveLength(1);
  });
});
