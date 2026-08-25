import type * as React from "react";
import type * as ReactDOM from "react-dom";
import type { ReactNode } from "react";

export interface ConnectorContext {
  projectId: string;
}

export interface ResourceConnectorContribution {
  id: string;
  title: string;
  icon: ReactNode;
  render(context: ConnectorContext): ReactNode;
  addLabel?: string;
  onAdd?: (context: ConnectorContext) => void | Promise<void>;
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
    | { type: "resource"; kind: string; id: string; version?: string | number | null }
    | { type: "artifact"; id: string }
    | { type: "conversation"; id: string };
  stateKey?: string;
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

export interface ArtifactRendererContext {
  onToast: (message: string) => void;
  compact?: boolean;
  mode?: "inline" | "workspace";
}

export interface ArtifactRendererContribution<TPayload> {
  type: string;
  supportedSchemaVersions: readonly number[];
  parsePayload(value: unknown): TPayload;
  render(artifact: ArtifactEnvelope<TPayload>, context: ArtifactRendererContext): ReactNode;
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
  readonly artifactRenderers: {
    register(contribution: ArtifactRendererContribution<unknown>): void;
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
