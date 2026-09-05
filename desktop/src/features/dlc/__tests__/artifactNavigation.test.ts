import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import type { ArtifactNavigationTarget, FrontendExtensionHost } from "../../../../../sdk/frontend/index";
import type { ConversationArtifact } from "../../../types/conversation";
import * as apiClient from "../../../lib/api/client";
import { selectActiveDockTabs, useWorkspaceStore } from "../../../stores/workspaceStore";
import { useConversationStore } from "../../../stores/conversationStore";
import { createStagedExtensionHost } from "../extensionHost";
import { invalidateActiveFrontendExtensions, loadActiveFrontendExtensions } from "../extensionLoader";
import { useDlcStore } from "../extensionStore";
import type { DlcModule } from "../types";
import { TooltipProvider } from "../../../components/ui";
import { WorkspaceDock } from "../../appShell/WorkspaceDock";
import { agentApi } from "../../../lib/api/agent";

const reads = vi.hoisted(() => ({ session: vi.fn(), artifacts: vi.fn() }));
vi.mock("../../../lib/api/generated/sdk.gen", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../lib/api/generated/sdk.gen")>(),
  getConversationApiV1ConversationsConversationIdGet: reads.session,
  getRunArtifactsApiV1ConversationsConversationIdRunsRunIdArtifactsGet: reads.artifacts,
}));

const target: ArtifactNavigationTarget = {
  projectId: "project-1", sessionId: "action-session", runId: "old-run", artifactId: "artifact-1",
};
const artifact: ConversationArtifact = {
  id: target.artifactId, session_id: target.sessionId, run_id: target.runId,
  type: "example.result", title: "Durable result", payload: { value: "server" },
  version: 1, status: "completed", visibility: "primary", provenance: {}, relations: [],
};
const snapshot = {
  protocol_version: 2,
  session: { id: target.sessionId, project_id: target.projectId, title: "Action session" },
  // The target run is older than the first page. The run-artifacts endpoint proves its membership.
  runs: [], items: [], cursor: 1,
  pagination: {
    items: { has_more: false }, runs: { has_more: true, next_before_sequence: 80 },
  },
};
const projection = {
  snapshot_id: "snapshot-1",
  active_dlcs: [{
    dlc_id: "example.navigation", package_version: "1.0.0",
    package_digest: "a".repeat(64), frontend_entrypoint: "frontend/index.js",
  }],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

async function activate(module?: DlcModule): Promise<FrontendExtensionHost> {
  let accepted!: FrontendExtensionHost;
  await loadActiveFrontendExtensions(projection, async () => module ?? {
    register(host) { accepted = host; },
  });
  return accepted;
}

function options(signal?: AbortSignal) {
  return { workbenchScopeId: useWorkspaceStore.getState().ensureActiveWorkbenchScope(), signal };
}

function expectNoNavigation() {
  expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([]);
  expect(useConversationStore.getState().artifactsById).toEqual({});
}

describe("Host Artifact navigation through the canonical repository and store", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    reads.session.mockReset().mockResolvedValue({ data: snapshot });
    reads.artifacts.mockReset().mockResolvedValue({ data: [artifact] });
    invalidateActiveFrontendExtensions();
    useWorkspaceStore.setState({
      activeProjectId: target.projectId,
      mainSurfaceByProject: { [target.projectId]: { kind: "conversation", conversationId: "chat-session" } },
      workbenchByConversation: {},
    });
    useConversationStore.setState({ detailById: {}, artifactsById: {} });
  });

  afterEach(() => { cleanup(); invalidateActiveFrontendExtensions(); vi.restoreAllMocks(); });

  it.each([null, "chat-session"])("renders the actual Action Run artifact view from scope %s", async (conversationId) => {
    if (!conversationId) useWorkspaceStore.getState().setProjectMainSurface(target.projectId, { kind: "new-conversation" });
    vi.spyOn(agentApi, "listArtifactRepresentations").mockResolvedValue([]);
    let host!: FrontendExtensionHost;
    await activate({ register(value) {
      host = value;
      value.artifactViews.register({
        id: "example.navigation.result", title: "Result viewer", surfaces: ["workspace"],
        artifactTypes: [{ type: artifact.type, schemaVersions: [1] }],
        parsePayload: (payload) => payload,
        render: (envelope) => createElement("div", { "data-testid": "actual-result-view" }, envelope.title),
      });
    } });
    const initialSurface = useWorkspaceStore.getState().mainSurfaceByProject[target.projectId];
    await host.workbench.openArtifact!(target, options());
    render(createElement(TooltipProvider, null,
      createElement(WorkspaceDock, { activeConversationId: conversationId, showToast: vi.fn() })));
    expect((await screen.findByRole("tab", { name: artifact.title })).getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByTestId("actual-result-view")).toBeTruthy();
    expect(useWorkspaceStore.getState().mainSurfaceByProject[target.projectId]).toEqual(initialSurface);
    act(() => { useWorkspaceStore.getState().setActiveProject("another-project"); });
    expect(screen.queryByRole("tab", { name: artifact.title })).toBeNull();
    expect(screen.queryByTestId("actual-result-view")).toBeNull();
    act(() => { useWorkspaceStore.getState().setActiveProject(target.projectId); });
    expect(await screen.findByRole("tab", { name: artifact.title })).toBeTruthy();
    expect(await screen.findByTestId("actual-result-view")).toBeTruthy();
  });

  it("opens an older Action Run from another session with the server's identity and payload", async () => {
    const host = await activate();
    const scope = options();
    const writes = vi.spyOn(globalThis, "fetch");
    await host.workbench.openArtifact!(target, scope);

    expect(reads.session).toHaveBeenCalledOnce();
    expect(reads.session.mock.calls[0][0]).toMatchObject({ path: { conversation_id: target.sessionId } });
    expect(reads.artifacts.mock.calls[0][0]).toMatchObject({
      path: { conversation_id: target.sessionId, run_id: target.runId },
    });
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([expect.objectContaining({
      viewType: "core.artifact", title: artifact.title, target: { type: "artifact", id: artifact.id },
    })]);
    expect(useConversationStore.getState().artifactsById[artifact.id].payload).toEqual(artifact.payload);
    expect(useConversationStore.getState().detailById).toEqual({});
    expect(writes).not.toHaveBeenCalled(); // No admission, export, selection, follow, or other write.
  });

  it("uses only captured identity fields when the caller mutates its object while reading", async () => {
    const pending = deferred<{ data: typeof snapshot }>();
    reads.session.mockReturnValueOnce(pending.promise);
    const host = await activate();
    const input = { ...target, title: "Forged", payload: { value: "forged" }, viewType: "foreign.view" };
    const scope = options();
    const navigation = host.workbench.openArtifact!(input, scope);
    input.artifactId = "changed";
    scope.workbenchScopeId = "changed";
    pending.resolve({ data: snapshot });
    await navigation;
    expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].title).toBe(artifact.title);
  });

  it.each(["projectId", "sessionId", "runId", "artifactId"] as const)("rejects an empty %s before reading", async (key) => {
    const host = await activate();
    await expect(host.workbench.openArtifact!({ ...target, [key]: " " }, options())).rejects.toThrow();
    expect(reads.session).not.toHaveBeenCalled();
    expectNoNavigation();
  });

  it("rejects a cross-project target before reading", async () => {
    const host = await activate();
    await expect(host.workbench.openArtifact!({ ...target, projectId: "other" }, options())).rejects.toThrow();
    expect(reads.session).not.toHaveBeenCalled();
    expectNoNavigation();
  });

  it.each([
    { id: "wrong-session", project_id: target.projectId },
    { id: target.sessionId, project_id: "other-project" },
    { id: target.sessionId, project_id: null },
  ])("rejects a fresh session with invalid identity %j", async (session) => {
    reads.session.mockResolvedValue({ data: { ...snapshot, session: { ...snapshot.session, ...session } } });
    const host = await activate();
    await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow();
    expect(reads.artifacts).not.toHaveBeenCalled();
    expectNoNavigation();
  });

  it.each([
    [],
    [{ ...artifact, id: "another" }],
    [{ ...artifact, session_id: "wrong-session" }],
    [{ ...artifact, run_id: "wrong-run" }],
    [artifact, artifact],
    [artifact, { ...artifact, id: "other", run_id: "foreign" }],
    [{ ...artifact, type: "" }],
  ])("rejects absent, ambiguous, malformed, or mismatched response %j", async (...values) => {
    // it.each spreads an array row into arguments; recover the intended response list.
    reads.artifacts.mockResolvedValue({ data: values });
    const host = await activate();
    await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow();
    expectNoNavigation();
  });

  it.each(["creating", "failed", "stale"] as const)("preserves the existing view contract for %s artifacts", async (status) => {
    reads.artifacts.mockResolvedValue({ data: [{ ...artifact, status }] });
    const host = await activate();
    await host.workbench.openArtifact!(target, options());
    expect(useConversationStore.getState().artifactsById[artifact.id].status).toBe(status);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
  });

  it.each(["session", "artifacts"] as const)("does not publish when the %s read fails", async (key) => {
    reads[key].mockRejectedValue(new Error("not found"));
    const host = await activate();
    await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow("Unable to open");
    expectNoNavigation();
  });

  it("does not trust a correct cached artifact or session when the server now rejects the project", async () => {
    const host = await activate();
    await host.workbench.openArtifact!(target, options());
    useWorkspaceStore.getState().closeDockTab(`core.artifact:${artifact.id}`);
    reads.session.mockResolvedValue({ data: { ...snapshot, session: { ...snapshot.session, project_id: "other" } } });
    await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow();
    expect(reads.session).toHaveBeenCalledTimes(2);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([]);
  });

  it("rejects a conflicting cache identity without overwriting it", async () => {
    const polluted = { ...artifact, session_id: "foreign-session", run_id: "foreign-run" };
    useConversationStore.setState({ artifactsById: { [artifact.id]: polluted } });
    const host = await activate();
    await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow("Unable to open");
    expect(reads.artifacts).toHaveBeenCalledOnce();
    expect(useConversationStore.getState().artifactsById[artifact.id]).toBe(polluted);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([]);
  });

  it("never uses a cached ID to authorize a different run", async () => {
    useConversationStore.setState({ artifactsById: { [artifact.id]: artifact } });
    reads.artifacts.mockRejectedValue(new Error("RUN_NOT_FOUND"));
    const host = await activate();
    await expect(host.workbench.openArtifact!({ ...target, runId: "foreign-run" }, options())).rejects.toThrow();
    expect(reads.artifacts).toHaveBeenCalledOnce();
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([]);
  });

  it("rejects pre-abort and an old scope captured before export", async () => {
    const host = await activate();
    const aborted = new AbortController(); aborted.abort();
    await expect(host.workbench.openArtifact!(target, options(aborted.signal))).rejects.toThrow();
    const oldScope = options();
    useWorkspaceStore.getState().setProjectActiveConversation(target.projectId, "new-chat");
    await expect(host.workbench.openArtifact!(target, oldScope)).rejects.toThrow();
    expect(reads.session).not.toHaveBeenCalled();
    expectNoNavigation();
  });

  it.each(["abort", "project", "workbench", "leave-and-return", "generation", "deactivate"])(
    "discards a late read after %s and releases the workspace listener", async (change) => {
      const host = await activate();
      const scope = options();
      const controller = new AbortController();
      const pending = deferred<{ data: ConversationArtifact[] }>();
      reads.artifacts.mockReturnValueOnce(pending.promise);
      const originalSubscribe = useWorkspaceStore.subscribe;
      const unsubscribe = vi.fn();
      vi.spyOn(useWorkspaceStore, "subscribe").mockImplementation((listener) => {
        const stop = originalSubscribe(listener);
        return () => { unsubscribe(); stop(); };
      });
      const navigation = host.workbench.openArtifact!(target, { ...scope, signal: controller.signal });
      const result = expect(navigation).rejects.toThrow();
      await vi.waitFor(() => expect(reads.artifacts).toHaveBeenCalledOnce());
      if (change === "abort") controller.abort();
      if (change === "project" || change === "leave-and-return") useWorkspaceStore.getState().setActiveProject("other");
      if (change === "leave-and-return") useWorkspaceStore.getState().setActiveProject(target.projectId);
      if (change === "workbench") useWorkspaceStore.getState().setProjectActiveConversation(target.projectId, "other-chat");
      if (change === "generation") vi.spyOn(apiClient, "getRuntimeSession").mockReturnValue({ ...apiClient.getRuntimeSession(), generation: 99 });
      if (change === "deactivate") invalidateActiveFrontendExtensions();
      pending.resolve({ data: [artifact] });
      await result;
      expect(unsubscribe).toHaveBeenCalledOnce();
      expectNoNavigation();
    },
  );

  it("checks cancellation after parsing and before publishing", async () => {
    const controller = new AbortController();
    reads.artifacts.mockResolvedValue({ data: [{
      ...artifact,
      get payload() { controller.abort(); return artifact.payload; },
    }] });
    const host = await activate();
    await expect(host.workbench.openArtifact!(target, options(controller.signal))).rejects.toThrow();
    expectNoNavigation();
  });

  it("rechecks scope when a synchronous projection subscriber changes projects", async () => {
    const host = await activate();
    const stop = useConversationStore.subscribe((state) => {
      if (state.artifactsById[artifact.id]) useWorkspaceStore.getState().setActiveProject("other");
    });
    try {
      await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow();
      expect(selectActiveDockTabs(useWorkspaceStore.getState())).toEqual([]);
    } finally { stop(); }
  });

  it("keeps a cancelled navigation independent from a timeline read and a later navigation", async () => {
    const host = await activate();
    const timelineRead = deferred<{ data: ConversationArtifact[] }>();
    const cancelledRead = deferred<{ data: ConversationArtifact[] }>();
    reads.artifacts.mockReturnValueOnce(timelineRead.promise).mockReturnValueOnce(cancelledRead.promise);
    const timeline = useConversationStore.getState().loadRunArtifacts(target.sessionId, target.runId, [artifact.id]);
    const controller = new AbortController();
    const cancelled = host.workbench.openArtifact!(target, options(controller.signal));
    const rejected = expect(cancelled).rejects.toThrow();
    await vi.waitFor(() => expect(reads.artifacts).toHaveBeenCalledTimes(2));
    controller.abort();
    await host.workbench.openArtifact!(target, options());
    cancelledRead.resolve({ data: [{ ...artifact, title: "Late cancelled response" }] });
    await rejected;
    expect(useConversationStore.getState().artifactsById[artifact.id].title).toBe(artifact.title);
    timelineRead.resolve({ data: [artifact] });
    await timeline;
    expect(reads.artifacts).toHaveBeenCalledTimes(3);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
  });

  it("revokes old references when the same ESM module and digest register again", async () => {
    const hosts: FrontendExtensionHost[] = [];
    const module: DlcModule = { register(host) { hosts.push(host); } };
    await activate(module);
    const pending = deferred<{ data: ConversationArtifact[] }>();
    reads.artifacts.mockReturnValueOnce(pending.promise);
    const old = hosts[0].workbench.openArtifact!(target, options());
    const rejected = expect(old).rejects.toThrow();
    await vi.waitFor(() => expect(reads.artifacts).toHaveBeenCalledOnce());
    await activate(module);
    await expect(hosts[0].workbench.openArtifact!(target, options())).rejects.toThrow();
    pending.resolve({ data: [{ ...artifact, title: "Old activation" }] });
    await rejected;
    expectNoNavigation();
    await hosts[1].workbench.openArtifact!(target, options());
    expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].title).toBe(artifact.title);
  });

  it("does not let a late import overwrite the Host retained by the current ESM", async () => {
    let retained!: FrontendExtensionHost;
    const register = vi.fn((host: FrontendExtensionHost) => { retained = host; });
    const module: DlcModule = { register };
    const pending = deferred<DlcModule>();
    const old = loadActiveFrontendExtensions(projection, () => pending.promise);
    await loadActiveFrontendExtensions({ ...projection, snapshot_id: "current" }, async () => module);
    const current = retained;
    pending.resolve(module);
    await old;
    expect(register).toHaveBeenCalledOnce();
    expect(retained).toBe(current);
    expect(useDlcStore.getState().activeSnapshotId).toBe("current");
    await retained.workbench.openArtifact!(target, options());
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
  });

  it("finishes stale async registration and its cleanup before registering the same ESM again", async () => {
    const pending = deferred<void>();
    const order: string[] = [];
    let count = 0;
    let retained!: FrontendExtensionHost;
    const hosts: FrontendExtensionHost[] = [];
    const module: DlcModule = {
      async register(host) {
        const number = ++count;
        order.push(`start-${number}`);
        hosts.push(host);
        if (number === 1) await pending.promise;
        retained = host;
        order.push(`finish-${number}`);
      },
      deactivate() { order.push("deactivate"); },
    };
    const old = loadActiveFrontendExtensions(projection, async () => module);
    await vi.waitFor(() => expect(count).toBe(1));
    const current = loadActiveFrontendExtensions({ ...projection, snapshot_id: "current" }, async () => module);
    await Promise.resolve();
    expect(count).toBe(1);
    pending.resolve();
    await Promise.all([old, current]);
    expect(order).toEqual(["start-1", "finish-1", "deactivate", "start-2", "finish-2"]);
    expect(retained).toBe(hosts[1]);
    await expect(hosts[0].workbench.openArtifact!(target, options())).rejects.toThrow();
    await retained.workbench.openArtifact!(target, options());
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
  });

  it("skips remaining registrations after invalidation during an async register", async () => {
    const pending = deferred<void>();
    const first = vi.fn(async () => { await pending.promise; });
    const second = vi.fn();
    const deactivate = vi.fn();
    const two = { ...projection, active_dlcs: [...projection.active_dlcs, {
      ...projection.active_dlcs[0], dlc_id: "example.other", package_digest: "b".repeat(64),
    }] };
    const loading = loadActiveFrontendExtensions(two, async (url) => url.includes("b".repeat(64))
      ? { register: second } : { register: first, deactivate });
    await vi.waitFor(() => expect(first).toHaveBeenCalledOnce());
    invalidateActiveFrontendExtensions();
    pending.resolve();
    await loading;
    expect(second).not.toHaveBeenCalled();
    expect(deactivate).toHaveBeenCalledOnce();
    expect(useDlcStore.getState().activeSnapshotId).toBeNull();
    expectNoNavigation();
  });

  it("never activates staging, failed registration, or explicitly revoked hosts", async () => {
    const staged = createStagedExtensionHost("example.navigation");
    await expect(staged.host.workbench.openArtifact!(target, options())).rejects.toThrow();
    staged.revokeNavigation(); staged.activateNavigation();
    await expect(staged.host.workbench.openArtifact!(target, options())).rejects.toThrow();
    let failed!: FrontendExtensionHost;
    await activate({ register(host) { failed = host; throw new Error("registration failed"); } });
    await expect(failed.workbench.openArtifact!(target, options())).rejects.toThrow();
    expect(reads.session).not.toHaveBeenCalled();
  });

  it("does not resurrect leases invalidated by synchronous projection subscribers", async () => {
    let host!: FrontendExtensionHost;
    const stop = useDlcStore.subscribe((state) => {
      if (state.activeSnapshotId === projection.snapshot_id) invalidateActiveFrontendExtensions();
    });
    try {
      await activate({ register(value) { host = value; } });
      await expect(host.workbench.openArtifact!(target, options())).rejects.toThrow();
      expect(reads.session).not.toHaveBeenCalled();
    } finally { stop(); }
  });

  it("keeps the API v2 member optional and rejects incomplete public types", () => {
    const staged = createStagedExtensionHost("example.navigation");
    const legacy: FrontendExtensionHost = {
      ...staged.host, workbench: { currentScopeId: () => "legacy-scope" },
    };
    expect(legacy.workbench.openArtifact).toBeUndefined();
    expect(() => legacy.dockViews.open({
      viewKey: "forged", viewType: "core.artifact", title: "Forged", closeable: true,
    })).toThrow("unregistered");
    const compileOnly = () => {
      // @ts-expect-error Every persistent identity field is required.
      void staged.host.workbench.openArtifact!({ artifactId: "id" }, { workbenchScopeId: "scope" });
      // @ts-expect-error The originating scope is required.
      void staged.host.workbench.openArtifact!(target, {});
      // @ts-expect-error An envelope is not a navigation target.
      void staged.host.workbench.openArtifact!(artifact, { workbenchScopeId: "scope" });
      // @ts-expect-error No arbitrary Core view or payload is exposed.
      void staged.host.workbench.openArtifact!({ ...target, viewType: "core.artifact" }, { workbenchScopeId: "scope" });
    };
    void compileOnly;
  });
});
