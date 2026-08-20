import type { ResourceConnectorContribution } from "../resources/types";
import type { RequestedResourceContributor } from "../resources/requestedResourceComposition";
import type { DockViewContribution } from "../dock/types";
import type { ArtifactRendererContribution } from "../workspace/artifacts/types";

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

export interface FrontendExtensionHost {
  readonly dlcId: string;
  readonly connectors: {
    register(contribution: ResourceConnectorContribution): void;
  };
  readonly requestedResources: {
    register(contributor: RequestedResourceContributor): void;
  };
  readonly dockViews: {
    register(contribution: DockViewContribution): void;
  };
  readonly artifactRenderers: {
    register(contribution: ArtifactRendererContribution<unknown>): void;
  };
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
