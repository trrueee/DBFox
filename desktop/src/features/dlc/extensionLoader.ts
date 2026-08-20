import type {
  DlcContributionSet,
  DlcModule,
  DlcRegistrationRecord,
  RuntimeDlcActivationProjection,
} from "./types";
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "./extensionHost";
import { EMPTY_CONTRIBUTIONS, useDlcStore } from "./extensionStore";
import { fetchEnginePath } from "../../lib/api/client";

export function normalizePackageDigest(digest: string): string {
  if (digest.startsWith("sha256:")) {
    return digest.slice(7).toLowerCase();
  }
  if (digest.startsWith("sha256-")) {
    return digest.slice(7).toLowerCase();
  }
  return digest.toLowerCase();
}

export function buildDlcAssetUrl(packageDigest: string, entrypoint: string): string {
  const normalizedDigest = normalizePackageDigest(packageDigest);
  const cleanEntrypoint = entrypoint.replace(/^\/+/, "").replace(/^frontend\//, "");
  return `dlc-asset://localhost/${normalizedDigest}/frontend/${cleanEntrypoint}`;
}

export type DynamicImportFn = (url: string) => Promise<DlcModule>;

const defaultDynamicImport: DynamicImportFn = async (url: string) => {
  // Use native dynamic import with vite-ignore
  return import(/* @vite-ignore */ url);
};

export async function loadActiveFrontendExtensions(
  projection: RuntimeDlcActivationProjection,
  dynamicImport: DynamicImportFn = defaultDynamicImport,
): Promise<{
  snapshotId: string;
  records: Record<string, DlcRegistrationRecord>;
  contributions: DlcContributionSet;
}> {
  initExtensionHostGlobalSdk();

  const store = useDlcStore.getState();
  store.setLoading(true);

  const records: Record<string, DlcRegistrationRecord> = {};
  const allConnectors = [];
  const allRequestedResources = [];
  const allDockViews = [];
  const allArtifactRenderers = [];

  const connectorIds = new Set<string>();
  const dockViewTypes = new Set<string>();
  const artifactTypes = new Set<string>();

  for (const dlc of projection.active_dlcs) {
    const dlcId = dlc.dlc_id;
    const digest = dlc.package_digest;

    if (!dlc.frontend_entrypoint) {
      records[dlcId] = {
        dlcId,
        packageDigest: digest,
        status: "loaded",
        contributions: EMPTY_CONTRIBUTIONS,
      };
      continue;
    }

    try {
      const assetUrl = buildDlcAssetUrl(digest, dlc.frontend_entrypoint);
      const staged = createStagedExtensionHost(dlcId);

      const module = await dynamicImport(assetUrl);
      if (typeof module.register === "function") {
        await module.register(staged.host);
      }

      const contribs = staged.getContributions();

      // Check for intra-DLC collisions with previously loaded DLCs
      for (const connector of contribs.connectors) {
        if (connectorIds.has(connector.id)) {
          throw new Error(
            `Duplicate connector ID "${connector.id}" registered by DLC "${dlcId}"`,
          );
        }
      }
      for (const dockView of contribs.dockViews) {
        if (dockViewTypes.has(dockView.viewType)) {
          throw new Error(
            `Duplicate dock view type "${dockView.viewType}" registered by DLC "${dlcId}"`,
          );
        }
      }
      for (const renderer of contribs.artifactRenderers) {
        if (artifactTypes.has(renderer.type)) {
          throw new Error(
            `Duplicate artifact renderer type "${renderer.type}" registered by DLC "${dlcId}"`,
          );
        }
      }

      // Record successful registrations
      for (const connector of contribs.connectors) {
        connectorIds.add(connector.id);
        allConnectors.push(connector);
      }
      for (const req of contribs.requestedResources) {
        allRequestedResources.push(req);
      }
      for (const dockView of contribs.dockViews) {
        dockViewTypes.add(dockView.viewType);
        allDockViews.push(dockView);
      }
      for (const renderer of contribs.artifactRenderers) {
        artifactTypes.add(renderer.type);
        allArtifactRenderers.push(renderer);
      }

      records[dlcId] = {
        dlcId,
        packageDigest: digest,
        status: "loaded",
        contributions: contribs,
      };
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.warn(
        `[DLC Host] Failed to load frontend extension for DLC "${dlcId}":`,
        errorMessage,
      );
      records[dlcId] = {
        dlcId,
        packageDigest: digest,
        status: "error",
        error: errorMessage,
        contributions: EMPTY_CONTRIBUTIONS,
      };
    }
  }

  const mergedContributions: DlcContributionSet = {
    connectors: Object.freeze(allConnectors),
    requestedResources: Object.freeze(allRequestedResources),
    dockViews: Object.freeze(allDockViews),
    artifactRenderers: Object.freeze(allArtifactRenderers),
  };

  store.setProjectionResult(
    projection.snapshot_id,
    records,
    mergedContributions,
  );

  return {
    snapshotId: projection.snapshot_id,
    records,
    contributions: mergedContributions,
  };
}

export async function fetchAndLoadActiveExtensions(
  dynamicImport?: DynamicImportFn,
): Promise<void> {
  const store = useDlcStore.getState();
  try {
    store.setLoading(true);
    const response = await fetchEnginePath("/dlcs/activation");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    const data = (await response.json()) as RuntimeDlcActivationProjection;
    await loadActiveFrontendExtensions(data, dynamicImport);
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error("[DLC Host] Failed to fetch and load active DLC projection:", errorMsg);
    // A failed projection cannot prove that any previous contribution remains active.
    store.reset();
    store.setError(errorMsg);
  }
}
