import type {
  DlcContributionSet,
  DlcModule,
  DlcRegistrationRecord,
  RuntimeDlcActivationProjection,
} from "./types";
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "./extensionHost";
import { EMPTY_CONTRIBUTIONS, useDlcStore } from "./extensionStore";
import { fetchEnginePath } from "../../lib/api/client";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { CORE_ARTIFACT_VIEW_IDS, CORE_DOCK_VIEW_TYPES } from "./coreContributionIds";

const CORE_DOCK_TYPES = Object.freeze(Object.values(CORE_DOCK_VIEW_TYPES));
const CORE_ARTIFACT_IDS = Object.freeze(Object.values(CORE_ARTIFACT_VIEW_IDS));

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

interface ActiveFrontendModule {
  readonly packageDigest: string;
  readonly module: DlcModule;
}

let projectionEpoch = 0;
let activeFrontendModules = new Map<string, ActiveFrontendModule>();
let lifecycleBarrier: Promise<void> = Promise.resolve();

function reserveProjectionEpoch(): number {
  projectionEpoch += 1;
  return projectionEpoch;
}

async function deactivateModule(dlcId: string, module: DlcModule): Promise<void> {
  if (typeof module.deactivate !== "function") return;
  try {
    await module.deactivate();
  } catch (error) {
    console.warn(`[DLC Host] Failed to deactivate frontend extension "${dlcId}":`, error);
  }
}

function retireModules(modules: ReadonlyMap<string, ActiveFrontendModule>): Promise<void> {
  lifecycleBarrier = lifecycleBarrier.then(async () => {
    for (const [dlcId, active] of modules) {
      await deactivateModule(dlcId, active.module);
    }
  });
  return lifecycleBarrier;
}

/** Invalidates every in-flight projection before clearing its committed projection. */
export function invalidateActiveFrontendExtensions(): void {
  reserveProjectionEpoch();
  const retired = activeFrontendModules;
  activeFrontendModules = new Map();
  useDlcStore.getState().reset();
  useWorkspaceStore.getState().reconcileDockViewTypes(
    CORE_DOCK_TYPES,
  );
  void retireModules(retired);
}

export async function loadActiveFrontendExtensions(
  projection: RuntimeDlcActivationProjection,
  dynamicImport: DynamicImportFn = defaultDynamicImport,
): Promise<{
  snapshotId: string;
  records: Record<string, DlcRegistrationRecord>;
  contributions: DlcContributionSet;
}> {
  const epoch = reserveProjectionEpoch();
  return loadFrontendProjection(projection, dynamicImport, epoch);
}

async function loadFrontendProjection(
  projection: RuntimeDlcActivationProjection,
  dynamicImport: DynamicImportFn,
  epoch: number,
): Promise<{
  snapshotId: string;
  records: Record<string, DlcRegistrationRecord>;
  contributions: DlcContributionSet;
}> {
  await lifecycleBarrier;
  initExtensionHostGlobalSdk();

  const store = useDlcStore.getState();
  store.setLoading(true);

  const records: Record<string, DlcRegistrationRecord> = {};
  const allConnectors = [];
  const allDockViews = [];
  const allArtifactViews = [];

  const connectorIds = new Set<string>();
  const dockViewTypes = new Set<string>(CORE_DOCK_TYPES);
  const artifactViewIds = new Set<string>(CORE_ARTIFACT_IDS);
  const stagedModules = new Map<string, ActiveFrontendModule>();

  for (const dlc of projection.active_dlcs) {
    const dlcId = dlc.dlc_id;
    const digest = dlc.package_digest;
    let importedModule: DlcModule | null = null;

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
      importedModule = module;
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
      for (const view of contribs.artifactViews) {
        if (artifactViewIds.has(view.id)) {
          throw new Error(
            `Duplicate Artifact View id "${view.id}" registered by DLC "${dlcId}"`,
          );
        }
      }

      // Record successful registrations
      for (const connector of contribs.connectors) {
        connectorIds.add(connector.id);
        allConnectors.push(connector);
      }
      for (const dockView of contribs.dockViews) {
        dockViewTypes.add(dockView.viewType);
        allDockViews.push(dockView);
      }
      for (const view of contribs.artifactViews) {
        artifactViewIds.add(view.id);
        allArtifactViews.push(view);
      }

      records[dlcId] = {
        dlcId,
        packageDigest: digest,
        status: "loaded",
        contributions: contribs,
      };
      stagedModules.set(dlcId, { packageDigest: digest, module });
    } catch (err: unknown) {
      if (
        importedModule
        && activeFrontendModules.get(dlcId)?.module !== importedModule
      ) {
        await deactivateModule(dlcId, importedModule);
      }
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
    dockViews: Object.freeze(allDockViews),
    artifactViews: Object.freeze(allArtifactViews),
  };

  // A newer engine generation, fetch, or explicit invalidation owns the store.
  // Stale async imports may finish, but can never repopulate the projection.
  if (epoch !== projectionEpoch) {
    const staleModules = new Map<string, ActiveFrontendModule>();
    for (const [dlcId, staged] of stagedModules) {
      if (activeFrontendModules.get(dlcId)?.module !== staged.module) {
        staleModules.set(dlcId, staged);
      }
    }
    await retireModules(staleModules);
    return {
      snapshotId: projection.snapshot_id,
      records,
      contributions: mergedContributions,
    };
  }

  store.setProjectionResult(
    projection.snapshot_id,
    records,
    mergedContributions,
  );
  useWorkspaceStore.getState().reconcileDockViewTypes([
    ...CORE_DOCK_TYPES,
    ...mergedContributions.dockViews.map((view) => view.viewType),
  ]);

  const retired = activeFrontendModules;
  activeFrontendModules = stagedModules;
  const deactivated = new Map<string, ActiveFrontendModule>();
  for (const [dlcId, active] of retired) {
    if (stagedModules.get(dlcId)?.module !== active.module) {
      deactivated.set(dlcId, active);
    }
  }
  await retireModules(deactivated);

  return {
    snapshotId: projection.snapshot_id,
    records,
    contributions: mergedContributions,
  };
}

export async function fetchAndLoadActiveExtensions(
  dynamicImport?: DynamicImportFn,
): Promise<void> {
  const epoch = reserveProjectionEpoch();
  const store = useDlcStore.getState();
  try {
    store.setLoading(true);
    const response = await fetchEnginePath("/dlcs/activation");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    const data = (await response.json()) as RuntimeDlcActivationProjection;
    await loadFrontendProjection(data, dynamicImport ?? defaultDynamicImport, epoch);
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error("[DLC Host] Failed to fetch and load active DLC projection:", errorMsg);
    if (epoch === projectionEpoch) {
      // A failed projection cannot prove that any previous contribution remains active.
      invalidateActiveFrontendExtensions();
      useDlcStore.getState().setError(errorMsg);
    }
  }
}
