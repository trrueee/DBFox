import { describe, expect, it } from "vitest";
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
});
