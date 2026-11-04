import { beforeEach, describe, expect, it } from "vitest";
import { openWorkbenchReference } from "../openWorkbenchReference";
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

  it("keeps different authority, version, and conversation identities separate", () => {
    openWorkbenchReference(reference);
    const first = selectActiveDockTabs(useWorkspaceStore.getState())[0];
    useWorkspaceStore.getState().updateDockTab(first.viewKey, { preview: false });
    openWorkbenchReference({ ...reference, authority: { kind: "sample.files.root", id: "root-2" } });
    const second = selectActiveDockTabs(useWorkspaceStore.getState())[1];
    useWorkspaceStore.getState().updateDockTab(second.viewKey, { preview: false });
    openWorkbenchReference({ ...reference, object: { ...reference.object!, version: "v2" } });
    expect(new Set(selectActiveDockTabs(useWorkspaceStore.getState()).map(tab => tab.viewKey)).size).toBe(3);
    useWorkspaceStore.getState().setProjectActiveConversation("p1", "other-conversation");
    openWorkbenchReference(reference);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].viewKey).not.toBe(first.viewKey);
  });

  it("refuses missing or ambiguous resource viewers without changing the workbench", () => {
    useDlcStore.getState().setProjectionResult("test", {}, { connectors: [], artifactViews: [], dockViews: [view, { ...view, viewType: "sample.files.other" }] });
    expect(() => openWorkbenchReference(reference)).toThrow("多个扩展");
    useDlcStore.getState().reset();
    expect(() => openWorkbenchReference(reference)).toThrow("请启用");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(0);
  });

  it("rejects registration of another owner's object kinds", () => {
    const staged = createStagedExtensionHost("sample.files", { openDockTab: () => {}, invokeOperation: async <T,>() => ({} as T) });
    expect(() => staged.host.dockViews.register({ ...view, objectKinds: ["someone.else.file"] })).toThrow();
  });
});
