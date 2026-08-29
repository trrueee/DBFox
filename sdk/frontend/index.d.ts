import type * as React from "react";
import type * as ReactDOM from "react-dom";
import type { ReactNode } from "react";

export interface HostTreeItemRenderState {
  expanded: boolean;
  focused: boolean;
  selected: boolean;
  branch: boolean;
  loading: boolean;
  loadError?: Error;
}

export interface HostTreeProps<T> {
  rootItem: T;
  ariaLabel: string;
  getItemId(item: T): string;
  getItemLabel(item: T): string;
  getItemChildren(item: T): readonly T[] | undefined;
  getItemChildrenCount?: (item: T) => number | undefined;
  loadItemChildren?: (item: T, signal: AbortSignal) => Promise<readonly T[]>;
  renderItemIcon?: (item: T, state: HostTreeItemRenderState) => ReactNode;
  renderItemMeta?: (item: T, state: HostTreeItemRenderState) => ReactNode;
  renderItemActions?: (item: T, state: HostTreeItemRenderState) => ReactNode;
  renderBranchFooter?: (item: T, state: HostTreeItemRenderState) => ReactNode;
  defaultExpandedIds?: readonly string[];
  onExpandedIdsChange?: (ids: readonly string[]) => void;
  selectedIds?: readonly string[];
  onSelectedIdsChange?: (ids: readonly string[], items: readonly T[]) => void;
  onItemSelect?: (item: T) => void;
  className?: string;
}

export interface HostTreeComponent {
  <T>(props: HostTreeProps<T>): ReactNode;
}

export interface HostCodeArtifactProps {
  readonly title: string;
  readonly code: string;
  readonly language?: "sql" | "text";
  readonly badge?: string;
  readonly description?: string;
  readonly metadata?: readonly string[];
  readonly fileName: string;
  readonly mimeType?: string;
  readonly ariaLabel?: string;
  readonly onToast: (message: string) => void;
}

export interface HostCodeArtifactComponent {
  (props: HostCodeArtifactProps): ReactNode;
}

export interface HostUiPrimitives {
  readonly version: "1.0.0";
  readonly Tree: HostTreeComponent;
  /** Host-themed, accessible, read-only code Artifact with copy/download actions. */
  readonly CodeArtifact: HostCodeArtifactComponent;
}

export interface ConnectorContext {
  projectId: string;
}

/** One project-scoped resource a DLC has configured, surfaced in the
 * project management inventory. `kind` must be the same resource kind the
 * DLC registers as a resource provider. */
export interface ConnectorProjectResource {
  kind: string;
  id: string;
  name: string;
  detail?: string;
}

export interface ResourceConnectorContribution {
  id: string;
  title: string;
  icon: ReactNode;
  render(context: ConnectorContext): ReactNode;
  addLabel?: string;
  onAdd?: (context: ConnectorContext) => void | Promise<void>;
  /** List the resources this DLC has configured for the project. Enables the
   * management inventory in the project page; omit when the DLC has none. */
  listResources?: (context: ConnectorContext) => Promise<ConnectorProjectResource[]>;
  /** Remove a project-scoped resource previously returned by listResources. */
  removeResource?: (
    context: ConnectorContext,
    resource: ConnectorProjectResource,
  ) => void | Promise<void>;
}

export interface RequestedResourceRef {
  kind: string;
  id: string;
}

export interface ReferencedObject {
  kind: string;
  id: string;
  version?: string | number | null;
}

/**
 * A user-visible Workbench subject. `authority` is the only field that may
 * request execution authority; object/locator/artifact identify the subject.
 */
export interface WorkbenchReference {
  label: string;
  authority?: RequestedResourceRef;
  object?: ReferencedObject;
  locator?: string;
  artifactId?: string;
}

export interface WorkspaceDockTab {
  viewKey: string;
  viewType: string;
  title: string;
  closeable: boolean;
  projectId?: string;
  target?:
    | {
        type: "object";
        object: ReferencedObject;
        authority?: RequestedResourceRef;
        locator?: string;
      }
    | { type: "artifact"; id: string }
    | { type: "conversation"; id: string };
  stateKey?: string;
  /** Selected content view within this Tab; the Tab never owns domain payload. */
  selectedViewId?: string;
}

export type DockShowToast = (
  message: string,
  type?: "success" | "error" | "warning" | "info",
) => void;

export interface DockViewContext {
  activeProjectId: string;
  activeConversationId: string | null;
}

export interface DockRenderContext extends DockViewContext {
  showToast: DockShowToast;
  workbenchScopeId: string;
  onAsk(reference: WorkbenchReference): void;
}

export interface DockViewContribution {
  viewType: string;
  icon: (view: WorkspaceDockTab) => ReactNode;
  resolveTitle: (view: WorkspaceDockTab) => string;
  isVisible: (view: WorkspaceDockTab, context: DockViewContext) => boolean;
  render: (view: WorkspaceDockTab, context: DockRenderContext) => ReactNode;
}

export interface ArtifactEnvelope<TPayload = Record<string, unknown>> {
  id: string;
  type: string;
  schema_version?: number;
  title: string;
  summary?: string | null;
  payload?: TPayload | null;
  payload_ref?: string | null;
  resource_refs?: readonly RequestedResourceRef[];
  provenance?: Record<string, unknown>;
  relations?: Array<{ relation: string; artifact_id: string }>;
  status?: string;
  visibility?: string;
  version?: number;
}

export type ArtifactViewSurface = "inline" | "workspace";

export interface ArtifactRepresentationDescriptor {
  representation_type: string;
  version: number;
  operations: readonly {
    name: string;
    result_kind?: "json" | "stream";
    media_type?: string | null;
  }[];
}

export interface ArtifactRepresentationRequest {
  operation: string;
  parameters?: Record<string, unknown>;
}

export interface ArtifactRepresentationResult {
  representation_type: string;
  representation_version: number;
  operation: string;
  payload: unknown;
  consistency: "durable_snapshot" | "live_reexecution";
  original_observed_at?: string | null;
  read_at: string;
  read_id: string;
  source_version: string;
  source_fingerprint: string;
  warnings?: readonly string[];
  notices?: readonly string[];
}

/** Core-owned, authorization-preserving access to any Artifact Representation. */
export interface ArtifactRepresentationAccess {
  /** Representations already discovered for the Artifact being rendered. */
  readonly available: readonly ArtifactRepresentationDescriptor[];
  list(
    artifactId: string,
    signal?: AbortSignal,
  ): Promise<readonly ArtifactRepresentationDescriptor[]>;
  read(
    artifactId: string,
    representationType: string,
    request: ArtifactRepresentationRequest,
    signal?: AbortSignal,
  ): Promise<ArtifactRepresentationResult>;
  stream(
    artifactId: string,
    representationType: string,
    request: ArtifactRepresentationRequest,
    signal?: AbortSignal,
  ): Promise<Blob>;
}

export interface ArtifactViewContext {
  onToast: (message: string) => void;
  compact?: boolean;
  surface: ArtifactViewSurface;
  representations: ArtifactRepresentationAccess;
  /** Resolve another Artifact in the already-authorized local projection. */
  resolveArtifact?: (artifactId: string) => ArtifactEnvelope<unknown> | null;
  /** Open the same durable Artifact in the Core-owned Dock. */
  openArtifact?: (artifact: ArtifactEnvelope<unknown>) => void;
}

export interface ArtifactTypeSelector {
  type: string;
  schemaVersions?: readonly number[];
}

/** A named projection of an Artifact. Multiple Views may match one Artifact. */
export interface ArtifactViewContribution<TPayload> {
  id: string;
  title: string;
  priority?: number;
  surfaces: readonly ArtifactViewSurface[];
  artifactTypes?: readonly ArtifactTypeSelector[];
  representationTypes?: readonly string[];
  parsePayload(value: unknown): TPayload;
  render(
    artifact: ArtifactEnvelope<unknown>,
    payload: TPayload,
    context: ArtifactViewContext,
  ): ReactNode;
}

export interface DlcOperationInvokeOptions {
  readonly projectId?: string;
  /** Opaque server-issued lease used when this operation adopts new secrets. */
  readonly credentialLeaseId?: string;
  readonly signal?: AbortSignal;
}

export interface CredentialEnrollmentInput {
  readonly kind: string;
  readonly secret: string;
}

export interface CredentialEnrollmentBatchResult {
  readonly credentials: readonly {
    readonly id: string;
    readonly kind: string;
  }[];
  readonly lease_id: string;
}

export interface NativeFileSelection {
  readonly path: string;
  readonly name: string;
  readonly sizeBytes: number;
  readonly modifiedAtUnix: number;
}

export interface PickFileOptions {
  readonly title?: string;
  readonly accept?: readonly string[];
  readonly maxBytes?: number;
}

export interface FrontendExtensionHost {
  readonly dlcId: string;
  readonly ui: HostUiPrimitives;
  readonly connectors: {
    register(contribution: ResourceConnectorContribution): void;
  };
  readonly nativeDialogs: {
    /** Opens the Electron-owned folder picker. Returns null when cancelled. */
    pickFolder(): Promise<string | null>;
    /** Opens a bounded Electron-owned file picker. Extensions omit the leading dot. */
    pickFile(options?: PickFileOptions): Promise<NativeFileSelection | null>;
  };
  readonly nativeFiles: {
    /** Reads an unchanged file returned by pickFile once during this app process. */
    readPickedFile(path: string): Promise<Uint8Array>;
  };
  readonly credentials: {
    /** Enrolls transient secrets under this DLC's signed manifest permissions. */
    enrollBatch(
      credentials: readonly CredentialEnrollmentInput[],
      options?: { readonly signal?: AbortSignal },
    ): Promise<CredentialEnrollmentBatchResult>;
  };
  readonly dockViews: {
    register(contribution: DockViewContribution): void;
    open(view: WorkspaceDockTab, activate?: boolean): void;
  };
  readonly workbench: {
    /** Stable across draft-to-Conversation promotion; isolates capability view state. */
    currentScopeId(): string;
  };
  readonly artifactViews: {
    register(contribution: ArtifactViewContribution<unknown>): void;
  };
  readonly operations: {
    invoke<TOutput = unknown>(
      operationName: string,
      input?: unknown,
      options?: DlcOperationInvokeOptions,
    ): Promise<TOutput>;
  };
}

export interface DbfoxFrontendRuntimeSdk {
  React: typeof React;
  ReactDOM: typeof ReactDOM;
  version: string;
}

declare global {
  interface Window {
    __DBFOX_EXTENSION_HOST__?: DbfoxFrontendRuntimeSdk;
  }
}
