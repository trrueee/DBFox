import type {
  ArtifactRendererContribution,
  DockViewContribution,
  FrontendExtensionHost,
  RequestedResourceContributor,
  ResourceConnectorContribution,
} from "../../../../sdk/frontend/index";

export type {
  DlcOperationInvokeOptions,
  FrontendExtensionHost,
} from "../../../../sdk/frontend/index";

export interface ActiveDlcItem {
  dlc_id: string;
  package_version: string;
  package_digest: string;
  frontend_entrypoint?: string | null;
}

export interface RuntimeDlcActivationProjection {
  snapshot_id: string;
  active_dlcs: readonly ActiveDlcItem[];
}

export interface DlcContributionSet {
  readonly connectors: readonly ResourceConnectorContribution[];
  readonly requestedResources: readonly RequestedResourceContributor[];
  readonly dockViews: readonly DockViewContribution[];
  readonly artifactRenderers: readonly ArtifactRendererContribution<unknown>[];
}

export interface DlcModule {
  register?: (host: FrontendExtensionHost) => void | Promise<void>;
}

export type DlcLoadStatus = "unloaded" | "loading" | "loaded" | "error";

export interface DlcRegistrationRecord {
  readonly dlcId: string;
  readonly packageDigest: string;
  readonly status: DlcLoadStatus;
  readonly error?: string;
  readonly contributions: DlcContributionSet;
}
