import { beforeEach, describe, expect, it } from "vitest";
import { openWorkbenchReference } from "../openWorkbenchReference";
import { captureWorkbenchInput } from "../workbenchInput";
import { useDlcStore } from "../../dlc/extensionStore";
import { createStagedExtensionHost } from "../../dlc/extensionHost";
import { selectActiveDockTabs, useWorkspaceStore } from "../../../stores/workspaceStore";
import type { WorkbenchReference } from "../../../types/workspace";

const reference: WorkbenchReference = { label: "README.md", authority: { kind: "sample.files.root", id: "root-1" },
  object: { kind: "sample.files.file", id: "README.md", version: "v1" }, locator: "README.md" };
const view = { viewType: "sample.files.viewer", objectKinds: ["sample.files.file"], icon: () => null, resolveTitle: () => "file", isVisible: () => true, render: () => null };

describe("exact reference navigation", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({ activeProjectId: "p1", mainSurfaceByProject: {}, workbenchByConversation: {} });
    useDlcStore.getState().setProjectionResult("test", {}, { connectors: [], artifactViews: [], dockViews: [view] });
  });

  it("reuses an exact resource tab and keeps it pinned", () => {
    openWorkbenchReference(reference);
    const tab = selectActiveDockTabs(useWorkspaceStore.getState())[0];
    useWorkspaceStore.getState().updateDockTab(tab.viewKey, { preview: false });
    openWorkbenchReference(reference);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([{ ...tab, preview: false }]);
  });

  it("captures the visible object and locator without inheriting its authority", () => {
    useWorkspaceStore.getState().setProjectActiveConversation("p1", "conversation-1");
    openWorkbenchReference(reference);
    expect(captureWorkbenchInput([], "conversation-1")).toEqual([{
      label: "当前查看 · README.md", object: reference.object, locator: "README.md",
    }]);
    expect(captureWorkbenchInput([reference], "conversation-1")).toEqual([reference]);
    expect(captureWorkbenchInput([], "another-conversation")).toEqual([]);
    useWorkspaceStore.getState().setDockOpen(false);
    expect(captureWorkbenchInput([], "conversation-1")).toEqual([]);
  });

  it("keeps different authority, version, and conversation identities separate", () => {
    openWorkbenchReference(reference);
    const first = selectActiveDockTabs(useWorkspaceStore.getState())[0];
    useWorkspaceStore.getState().updateDockTab(first.viewKey, { preview: false });
    openWorkbenchReference({ ...reference, authority: { kind: "sample.files.root", id: "root-2" } });
    const second = selectActiveDockTabs(useWorkspaceStore.getState())[1];
    useWorkspaceStore.getState().updateDockTab(second.viewKey, { preview: false });
    expect(() => openWorkbenchReference({ ...reference, authority: undefined })).toThrow("多个页签");
    openWorkbenchReference({ ...reference, object: { ...reference.object!, version: "v2" } });
    expect(new Set(selectActiveDockTabs(useWorkspaceStore.getState()).map(tab => tab.viewKey)).size).toBe(3);
    useWorkspaceStore.getState().setProjectActiveConversation("p1", "other-conversation");
    openWorkbenchReference(reference);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].viewKey).not.toBe(first.viewKey);
  });

  it("captures the displayed tab when a contribution hides the stored active tab", () => {
    useDlcStore.getState().setProjectionResult("test", {}, { connectors: [], artifactViews: [], dockViews: [
      view, { ...view, viewType: "sample.files.hidden", objectKinds: ["sample.files.hidden"], isVisible: () => false },
    ] });
    const workspace = useWorkspaceStore.getState();
    workspace.setProjectActiveConversation("p1", "chat");
    openWorkbenchReference(reference);
    workspace.openDockTab({
      viewKey: "hidden", viewType: "sample.files.hidden", title: "Hidden", closeable: true,
      target: { type: "object", object: { kind: "sample.files.hidden", id: "hidden.md" } },
    });
    expect(captureWorkbenchInput([], "chat")).toEqual([{
      label: "当前查看 · README.md", object: reference.object, locator: reference.locator,
    }]);
  });

  it("leaves input valid when an extension tab locator exceeds the reference contract", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "long", viewType: view.viewType, title: "Long", closeable: true,
      target: { type: "object", object: reference.object!, locator: "x".repeat(1001) },
    });
    expect(captureWorkbenchInput([], null)).toEqual([]);
  });

  it("refuses missing or ambiguous resource viewers without changing the workbench", () => {
    useDlcStore.getState().setProjectionResult("test", {}, { connectors: [], artifactViews: [], dockViews: [view, { ...view, viewType: "sample.files.other" }] });
    expect(() => openWorkbenchReference(reference)).toThrow("多个扩展");
    useDlcStore.getState().reset();
    expect(() => openWorkbenchReference(reference)).toThrow("支持此对象的扩展");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(0);
  });

  it("rejects registration of another owner's object kinds", () => {
    const staged = createStagedExtensionHost("sample.files", { openDockTab: () => {}, invokeOperation: async <T,>() => ({} as T) });
    expect(() => staged.host.dockViews.register({ ...view, objectKinds: ["someone.else.file"] })).toThrow();
  });
});
