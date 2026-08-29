import type {
  ArtifactViewContribution,
  DockViewContribution,
  FrontendExtensionHost,
  ResourceConnectorContribution,
} from "../../../../sdk/frontend/index";

export type {
  CredentialEnrollmentBatchResult,
  CredentialEnrollmentInput,
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
  readonly dockViews: readonly DockViewContribution[];
  readonly artifactViews: readonly ArtifactViewContribution<unknown>[];
}

export interface DlcModule {
  register?: (host: FrontendExtensionHost) => void | Promise<void>;
  deactivate?: () => void | Promise<void>;
}

export type DlcLoadStatus = "unloaded" | "loading" | "loaded" | "error";

export interface DlcRegistrationRecord {
  readonly dlcId: string;
  readonly packageDigest: string;
  readonly status: DlcLoadStatus;
  readonly error?: string;
  readonly contributions: DlcContributionSet;
}
