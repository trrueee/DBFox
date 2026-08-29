import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildDlcAssetUrl,
  invalidateActiveFrontendExtensions,
  loadActiveFrontendExtensions,
  normalizePackageDigest,
} from "../extensionLoader";
import type { FrontendExtensionHost, RuntimeDlcActivationProjection } from "../types";
import { useDlcStore } from "../extensionStore";

describe("extensionLoader", () => {
  beforeEach(() => {
    invalidateActiveFrontendExtensions();
  });
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
            id: "healthy.dlc.connector",
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
    expect(result.contributions.connectors[0].id).toBe("healthy.dlc.connector");
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
          dlc_id: "first",
          package_version: "1.0.0",
          package_digest: digest2,
          frontend_entrypoint: "frontend/index.js",
        },
      ],
    };

    const mockImport = async () => ({
      register: (host: FrontendExtensionHost) => {
        host.dockViews.register({
          viewType: "first.dlc.shared",
          icon: () => null,
          resolveTitle: () => "Duplicate",
          isVisible: () => true,
          render: () => "Duplicate View",
        });
      },
    });

    const result = await loadActiveFrontendExtensions(projection, mockImport);

    expect(result.records["first.dlc"].status).toBe("loaded");
    expect(result.records.first.status).toBe("error");
    expect(result.records.first.error).toContain("Duplicate dock view type");
    expect(result.contributions.dockViews.length).toBe(1);
  });

  it("rejects IDs outside the owning DLC namespace and duplicate local registrations", async () => {
    const projection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_admission",
      active_dlcs: [{
        dlc_id: "acme.analytics",
        package_version: "1.0.0",
        package_digest: "5".repeat(64),
        frontend_entrypoint: "frontend/index.js",
      }],
    };

    const outside = await loadActiveFrontendExtensions(projection, async () => ({
      register(host) {
        host.connectors.register({
          id: "another.owner",
          title: "Invalid",
          icon: null,
          render: () => null,
        });
      },
    }));
    expect(outside.records["acme.analytics"].status).toBe("error");
    expect(outside.records["acme.analytics"].error).toContain("must be owned by namespace");

    const duplicate = await loadActiveFrontendExtensions(
      { ...projection, snapshot_id: "snap_duplicate" },
      async () => ({
        register(host) {
          const contribution = {
            id: "acme.analytics.connector",
            title: "Analytics",
            icon: null,
            render: () => null,
          };
          host.connectors.register(contribution);
          host.connectors.register(contribution);
        },
      }),
    );
    expect(duplicate.records["acme.analytics"].status).toBe("error");
    expect(duplicate.records["acme.analytics"].error).toContain("Duplicate connector id");
  });

  it("reserves Core contribution identities", async () => {
    const projection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_core_collision",
      active_dlcs: [{
        dlc_id: "core",
        package_version: "1.0.0",
        package_digest: "6".repeat(64),
        frontend_entrypoint: "frontend/index.js",
      }],
    };
    const result = await loadActiveFrontendExtensions(projection, async () => ({
      register(host) {
        host.dockViews.register({
          viewType: "core.artifacts",
          icon: () => null,
          resolveTitle: () => "Invalid",
          isVisible: () => true,
          render: () => null,
        });
      },
    }));

    expect(result.records.core.status).toBe("error");
    expect(result.records.core.error).toContain("Duplicate dock view type");
    expect(result.contributions.dockViews).toHaveLength(0);
  });

  it("fences a slower stale projection from a newer committed snapshot", async () => {
    let resolveOld!: (module: { register(host: FrontendExtensionHost): void }) => void;
    const oldModule = new Promise<{ register(host: FrontendExtensionHost): void }>((resolve) => {
      resolveOld = resolve;
    });
    const oldProjection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_old",
      active_dlcs: [{
        dlc_id: "acme.old",
        package_version: "1.0.0",
        package_digest: "7".repeat(64),
        frontend_entrypoint: "frontend/index.js",
      }],
    };
    const newProjection: RuntimeDlcActivationProjection = {
      snapshot_id: "snap_new",
      active_dlcs: [{
        dlc_id: "acme.new",
        package_version: "1.0.0",
        package_digest: "8".repeat(64),
        frontend_entrypoint: "frontend/index.js",
      }],
    };

    const staleLoad = loadActiveFrontendExtensions(oldProjection, () => oldModule);
    await loadActiveFrontendExtensions(newProjection, async () => ({
      register(host) {
        host.connectors.register({
          id: "acme.new.connector",
          title: "New",
          icon: null,
          render: () => null,
        });
      },
    }));
    resolveOld({
      register(host) {
        host.connectors.register({
          id: "acme.old.connector",
          title: "Old",
          icon: null,
          render: () => null,
        });
      },
    });
    await staleLoad;

    expect(useDlcStore.getState().activeSnapshotId).toBe("snap_new");
    expect(useDlcStore.getState().contributions.connectors[0].id).toBe("acme.new.connector");
  });

  it("deactivates retired DLC modules", async () => {
    const deactivate = vi.fn();
    await loadActiveFrontendExtensions({
      snapshot_id: "snap_active",
      active_dlcs: [{
        dlc_id: "acme.lifecycle",
        package_version: "1.0.0",
        package_digest: "9".repeat(64),
        frontend_entrypoint: "frontend/index.js",
      }],
    }, async () => ({ register: () => undefined, deactivate }));

    await loadActiveFrontendExtensions({ snapshot_id: "snap_empty", active_dlcs: [] });
    expect(deactivate).toHaveBeenCalledOnce();
  });
});
