import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  createStagedExtensionHost,
  initExtensionHostGlobalSdk,
} from "../extensionHost";
import type { ResourceConnectorContribution } from "../../resources/types";
import type { DockViewContribution } from "../../dock/types";
import type { ArtifactViewContribution } from "../../workspace/artifacts/types";

describe("FrontendExtensionHost", () => {
  it("initializes global window.__DBFOX_EXTENSION_HOST__ SDK", () => {
    initExtensionHostGlobalSdk();
    expect(window.__DBFOX_EXTENSION_HOST__).toBeDefined();
    expect(window.__DBFOX_EXTENSION_HOST__?.React).toBeDefined();
    expect(window.__DBFOX_EXTENSION_HOST__?.ReactDOM).toBeDefined();
    expect(window.__DBFOX_EXTENSION_HOST__?.version).toBe("1.0.0");
    expect("ui" in window.__DBFOX_EXTENSION_HOST__!).toBe(false);
  });

  it("exposes versioned UI primitives only on the scoped registration host", () => {
    const staged = createStagedExtensionHost("acme.ui_dlc");

    expect(staged.host.ui.version).toBe("1.0.0");
    expect(typeof staged.host.ui.Tree).toBe("function");
  });

  it("stages and collects valid contributions across all 3 seams", () => {
    const staged = createStagedExtensionHost("acme.test_dlc");

    // 1. Connector
    const mockConnector: ResourceConnectorContribution = {
      id: "acme.test_dlc.connector",
      title: "ACME Connector",
      icon: null,
      render: () => "Rendered Connector",
    };
    staged.host.connectors.register(mockConnector);

    // 2. Dock View
    const mockDockView: DockViewContribution = {
      viewType: "acme.test_dlc.view",
      icon: () => null,
      resolveTitle: () => "ACME View",
      isVisible: () => true,
      render: () => "Rendered Dock View",
    };
    staged.host.dockViews.register(mockDockView);

    // 3. Artifact View
    const mockView: ArtifactViewContribution<{ data: string }> = {
      id: "acme.test_dlc.artifact.default",
      title: "ACME Artifact",
      surfaces: ["inline", "workspace"],
      artifactTypes: [{ type: "acme.artifact", schemaVersions: [1] }],
      parsePayload: (val) => val as { data: string },
      render: () => "Rendered Artifact",
    };
    staged.host.artifactViews.register(mockView);

    const contribs = staged.getContributions();
    expect(contribs.connectors.length).toBe(1);
    expect(contribs.connectors[0].id).toBe("acme.test_dlc.connector");
    expect(contribs.dockViews.length).toBe(1);
    expect(contribs.dockViews[0].viewType).toBe("acme.test_dlc.view");
    expect(contribs.artifactViews.length).toBe(1);
    expect(contribs.artifactViews[0].id).toBe("acme.test_dlc.artifact.default");

    const { container } = render(contribs.connectors[0].render({ projectId: "project-1" }));
    expect(container.querySelector(".dlc-slot--connector")?.getAttribute("data-dlc-id"))
      .toBe("acme.test_dlc");
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
      staged.host.artifactViews.register({} as ArtifactViewContribution<unknown>);
    }).toThrow(/Invalid Artifact View registration/);

  });

  it("isolates synchronous render throws inside the DLC error boundary", () => {
    const staged = createStagedExtensionHost("acme.throwing_dlc");
    staged.host.connectors.register({
      id: "acme.throwing_dlc.connector",
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

  it("surfaces connector onAdd callback failures", async () => {
    const staged = createStagedExtensionHost("acme.throwing_dlc");
    staged.host.connectors.register({
      id: "acme.throwing_dlc.add",
      title: "Throwing",
      icon: null,
      render: () => null,
      onAdd: () => {
        throw new Error("add exploded");
      },
    });

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(
      staged.getContributions().connectors[0].onAdd?.({ projectId: "project-1" }),
    ).rejects.toThrow("add exploded");
    consoleError.mockRestore();
  });

  it("binds operation calls to the current DLC identity", async () => {
    const invokeOperationCalls = vi.fn();
    const invokeOperation = async <TOutput,>(
      dlcId: string,
      operationName: string,
      input: unknown,
      options?: {
        projectId?: string;
        credentialLeaseId?: string;
        signal?: AbortSignal;
      },
    ): Promise<TOutput> => {
      invokeOperationCalls(dlcId, operationName, input, options);
      return { ok: true } as TOutput;
    };
    const staged = createStagedExtensionHost("acme.bound", {
      invokeOperation,
      openDockTab: vi.fn(),
    });

    await expect(
      staged.host.operations.invoke(
        "list_bindings",
        { project_id: "p1" },
        { projectId: "p1", credentialLeaseId: "lease_credential_test" },
      ),
    ).resolves.toEqual({ ok: true });
    expect(invokeOperationCalls).toHaveBeenCalledWith(
      "acme.bound",
      "list_bindings",
      { project_id: "p1" },
      { projectId: "p1", credentialLeaseId: "lease_credential_test" },
    );
    await expect(staged.host.operations.invoke("../other", {})).rejects.toThrow(
      /Invalid DLC operation name/,
    );
  });

  it("binds credential enrollment to the current DLC identity", async () => {
    const enrollCredentials = vi.fn(async () => ({
      credentials: [{
        id: "cred_datasource_password_test",
        kind: "datasource_password",
      }],
      lease_id: "lease_test",
    }));
    const staged = createStagedExtensionHost("acme.bound", {
      invokeOperation: async <TOutput,>() => ({} as TOutput),
      openDockTab: vi.fn(),
      enrollCredentials,
    });

    await expect(staged.host.credentials.enrollBatch([{
      kind: "datasource_password",
      secret: "transient-only",
    }])).resolves.toEqual({
      credentials: [{
        id: "cred_datasource_password_test",
        kind: "datasource_password",
      }],
      lease_id: "lease_test",
    });
    expect(enrollCredentials).toHaveBeenCalledWith(
      "acme.bound",
      [{ kind: "datasource_password", secret: "transient-only" }],
      undefined,
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
