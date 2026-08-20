import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  createStagedExtensionHost,
  initExtensionHostGlobalSdk,
} from "../extensionHost";
import type { ResourceConnectorContribution } from "../../resources/types";
import type { DockViewContribution } from "../../dock/types";
import type { ArtifactRendererContribution } from "../../workspace/artifacts/types";

describe("FrontendExtensionHost", () => {
  it("initializes global window.__DBFOX_EXTENSION_HOST__ SDK", () => {
    initExtensionHostGlobalSdk();
    expect(window.__DBFOX_EXTENSION_HOST__).toBeDefined();
    expect(window.__DBFOX_EXTENSION_HOST__?.React).toBeDefined();
    expect(window.__DBFOX_EXTENSION_HOST__?.ReactDOM).toBeDefined();
    expect(window.__DBFOX_EXTENSION_HOST__?.version).toBe("1.0.0");
  });

  it("stages and collects valid contributions across all 4 seams", () => {
    const staged = createStagedExtensionHost("acme.test_dlc");

    // 1. Connector
    const mockConnector: ResourceConnectorContribution = {
      id: "acme.test_connector",
      title: "ACME Connector",
      icon: null,
      render: () => "Rendered Connector",
    };
    staged.host.connectors.register(mockConnector);

    // 2. Requested Resource
    staged.host.requestedResources.register((context) => ({
      complete: true,
      refs: [{ kind: "acme.resource", id: context.projectId }],
    }));

    // 3. Dock View
    const mockDockView: DockViewContribution = {
      viewType: "acme.test_view",
      icon: () => null,
      resolveTitle: () => "ACME View",
      isVisible: () => true,
      render: () => "Rendered Dock View",
    };
    staged.host.dockViews.register(mockDockView);

    // 4. Artifact Renderer
    const mockRenderer: ArtifactRendererContribution<{ data: string }> = {
      type: "acme.artifact",
      supportedSchemaVersions: [1],
      parsePayload: (val) => val as { data: string },
      render: () => "Rendered Artifact",
    };
    staged.host.artifactRenderers.register(mockRenderer);

    const contribs = staged.getContributions();
    expect(contribs.connectors.length).toBe(1);
    expect(contribs.connectors[0].id).toBe("acme.test_connector");
    expect(contribs.requestedResources.length).toBe(1);
    expect(contribs.dockViews.length).toBe(1);
    expect(contribs.dockViews[0].viewType).toBe("acme.test_view");
    expect(contribs.artifactRenderers.length).toBe(1);
    expect(contribs.artifactRenderers[0].type).toBe("acme.artifact");
  });

  it("rejects invalid registrations fail-closed", () => {
    const staged = createStagedExtensionHost("acme.invalid_dlc");

    expect(() => {
      staged.host.connectors.register({} as ResourceConnectorContribution);
    }).toThrow(/Invalid connector registration/);

    expect(() => {
      staged.host.dockViews.register({} as DockViewContribution);
    }).toThrow(/Invalid dock view registration/);

    expect(() => {
      staged.host.artifactRenderers.register({} as ArtifactRendererContribution<unknown>);
    }).toThrow(/Invalid artifact renderer registration/);

    expect(() => {
      // @ts-expect-error test invalid type
      staged.host.requestedResources.register(null);
    }).toThrow(/Invalid requested resource contributor/);
  });

  it("isolates synchronous render throws inside the DLC error boundary", () => {
    const staged = createStagedExtensionHost("acme.throwing_dlc");
    staged.host.connectors.register({
      id: "acme.throwing_connector",
      title: "Throwing",
      icon: null,
      render: () => {
        throw new Error("render exploded");
      },
    });

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(staged.getContributions().connectors[0].render({ projectId: "project-1" }));
    expect(screen.getByText(/扩展组件加载或渲染失败/)).toBeTruthy();
    consoleError.mockRestore();
  });

  it("fails closed when a requested-resource contributor throws", () => {
    const staged = createStagedExtensionHost("acme.throwing_dlc");
    staged.host.requestedResources.register(() => {
      throw new Error("authority unavailable");
    });

    expect(staged.getContributions().requestedResources[0]({
      projectId: "project-1",
      conversationId: "conversation-1",
    })).toEqual({ complete: false });
  });

  it("contains connector onAdd callback failures", () => {
    const staged = createStagedExtensionHost("acme.throwing_dlc");
    staged.host.connectors.register({
      id: "acme.throwing_add",
      title: "Throwing",
      icon: null,
      render: () => null,
      onAdd: () => {
        throw new Error("add exploded");
      },
    });

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => staged.getContributions().connectors[0].onAdd?.({ projectId: "project-1" })).not.toThrow();
    consoleError.mockRestore();
  });

  it("binds operation calls to the current DLC identity", async () => {
    const invokeOperationCalls = vi.fn();
    const invokeOperation = async <TOutput,>(
      dlcId: string,
      operationName: string,
      input: unknown,
      options?: { projectId?: string; signal?: AbortSignal },
    ): Promise<TOutput> => {
      invokeOperationCalls(dlcId, operationName, input, options);
      return { ok: true } as TOutput;
    };
    const staged = createStagedExtensionHost("acme.bound", {
      invokeOperation,
      openDockTab: vi.fn(),
    });

    await expect(
      staged.host.operations.invoke("list_bindings", { project_id: "p1" }, { projectId: "p1" }),
    ).resolves.toEqual({ ok: true });
    expect(invokeOperationCalls).toHaveBeenCalledWith(
      "acme.bound",
      "list_bindings",
      { project_id: "p1" },
      { projectId: "p1" },
    );
    await expect(staged.host.operations.invoke("../other", {})).rejects.toThrow(
      /Invalid DLC operation name/,
    );
  });

  it("opens only Dock view types registered by the same DLC", () => {
    const openDockTab = vi.fn();
    const staged = createStagedExtensionHost("acme.bound", {
      invokeOperation: async <TOutput,>() => ({} as TOutput),
      openDockTab,
    });
    staged.host.dockViews.register({
      viewType: "acme.bound.file",
      icon: () => null,
      resolveTitle: (view) => view.title,
      isVisible: () => true,
      render: () => null,
    });

    staged.host.dockViews.open({
      viewKey: "acme.bound.file:1",
      viewType: "acme.bound.file",
      title: "File",
      closeable: true,
    });
    expect(openDockTab).toHaveBeenCalledOnce();
    expect(() => staged.host.dockViews.open({
      viewKey: "dbfox.core.settings",
      viewType: "dbfox.core.settings",
      title: "Settings",
      closeable: true,
    })).toThrow(/Cannot open unregistered Dock viewType/);
  });
});
