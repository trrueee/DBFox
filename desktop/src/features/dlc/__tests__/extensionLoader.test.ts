import { describe, expect, it } from "vitest";
import {
  buildDlcAssetUrl,
  loadActiveFrontendExtensions,
  normalizePackageDigest,
} from "../extensionLoader";
import type { FrontendExtensionHost, RuntimeDlcActivationProjection } from "../types";
import { useDlcStore } from "../extensionStore";

describe("extensionLoader", () => {
  it("normalizes package digests and constructs canonical dlc-asset URLs", () => {
    const rawDigest = "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF";
    const normalized = normalizePackageDigest(`sha256:${rawDigest}`);
    expect(normalized).toBe(rawDigest.toLowerCase());

    const url = buildDlcAssetUrl(rawDigest, "frontend/index.js");
    expect(url).toBe(`dlc-asset://localhost/${rawDigest.toLowerCase()}/frontend/index.js`);

    const url2 = buildDlcAssetUrl(`sha256-${rawDigest}`, "/index.js");
    expect(url2).toBe(`dlc-asset://localhost/${rawDigest.toLowerCase()}/frontend/index.js`);
  });

  it("loads valid DLC modules and promotes contributions into store", async () => {
    const digest = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
    const projection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_test_123",
      active_dlcs: [
        {
          dlc_id: "acme.analytics",
          package_version: "1.0.0",
          package_digest: digest,
          frontend_entrypoint: "frontend/index.js",
        },
      ],
    };

    const mockImport = async () => ({
      register: (host: FrontendExtensionHost) => {
        host.dockViews.register({
          viewType: "acme.analytics.dashboard",
          icon: () => null,
          resolveTitle: () => "Analytics",
          isVisible: () => true,
          render: () => "Analytics View",
        });
      },
    });

    const result = await loadActiveFrontendExtensions(projection, mockImport);

    expect(result.snapshotId).toBe("snap_test_123");
    expect(result.records["acme.analytics"].status).toBe("loaded");
    expect(result.contributions.dockViews.length).toBe(1);
    expect(result.contributions.dockViews[0].viewType).toBe("acme.analytics.dashboard");

    const store = useDlcStore.getState();
    expect(store.activeSnapshotId).toBe("snap_test_123");
    expect(store.contributions.dockViews.length).toBe(1);
  });

  it("isolates broken DLCs without crashing or contaminating other DLCs", async () => {
    const digest1 = "1111111111111111111111111111111111111111111111111111111111111111";
    const digest2 = "2222222222222222222222222222222222222222222222222222222222222222";

    const projection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_fault_test",
      active_dlcs: [
        {
          dlc_id: "broken.dlc",
          package_version: "1.0.0",
          package_digest: digest1,
          frontend_entrypoint: "frontend/bad.js",
        },
        {
          dlc_id: "healthy.dlc",
          package_version: "1.0.0",
          package_digest: digest2,
          frontend_entrypoint: "frontend/good.js",
        },
      ],
    };

    const mockImport = async (url: string) => {
      if (url.includes(digest1)) {
        throw new Error("SyntaxError: Unexpected token in bad.js");
      }
      return {
        register: (host: FrontendExtensionHost) => {
          host.connectors.register({
            id: "healthy.connector",
            title: "Healthy",
            icon: null,
            render: () => "Healthy Connector",
          });
        },
      };
    };

    const result = await loadActiveFrontendExtensions(projection, mockImport);

    expect(result.records["broken.dlc"].status).toBe("error");
    expect(result.records["broken.dlc"].error).toContain("SyntaxError");
    expect(result.records["healthy.dlc"].status).toBe("loaded");

    // Only healthy contributions are present
    expect(result.contributions.connectors.length).toBe(1);
    expect(result.contributions.connectors[0].id).toBe("healthy.connector");
  });

  it("handles duplicate contribution collision between DLCs by failing the colliding DLC", async () => {
    const digest1 = "3333333333333333333333333333333333333333333333333333333333333333";
    const digest2 = "4444444444444444444444444444444444444444444444444444444444444444";

    const projection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_collision_test",
      active_dlcs: [
        {
          dlc_id: "first.dlc",
          package_version: "1.0.0",
          package_digest: digest1,
          frontend_entrypoint: "frontend/index.js",
        },
        {
          dlc_id: "second.dlc",
          package_version: "1.0.0",
          package_digest: digest2,
          frontend_entrypoint: "frontend/index.js",
        },
      ],
    };

    const mockImport = async () => ({
      register: (host: FrontendExtensionHost) => {
        host.dockViews.register({
          viewType: "shared.duplicate.view",
          icon: () => null,
          resolveTitle: () => "Duplicate",
          isVisible: () => true,
          render: () => "Duplicate View",
        });
      },
    });

    const result = await loadActiveFrontendExtensions(projection, mockImport);

    expect(result.records["first.dlc"].status).toBe("loaded");
    expect(result.records["second.dlc"].status).toBe("error");
    expect(result.records["second.dlc"].error).toContain("Duplicate dock view type");
    expect(result.contributions.dockViews.length).toBe(1);
  });
});
