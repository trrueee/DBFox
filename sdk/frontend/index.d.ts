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
  onAdd?: (context: ConnectorContext) => void;
}

export interface RequestedResourceRef {
  kind: string;
  id: string;
  version?: string | number | null;
}

export interface ConversationSendResourceContext {
  projectId: string;
  conversationId: string;
  datasourceId?: string | null;
}

export interface RequestedResourceContributionResult {
  complete: boolean;
  refs?: readonly RequestedResourceRef[];
}

export type RequestedResourceContributor = (
  context: ConversationSendResourceContext,
) => RequestedResourceContributionResult;

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
  activeDatasourceId: string;
  activeConversationId: string | null;
}

export interface DockRenderContext extends DockViewContext {
  showToast: DockShowToast;
  onOpenQueryResult: (queryText: string) => void;
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
  readonly signal?: AbortSignal;
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
    open(view: WorkspaceDockTab, activate?: boolean): void;
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
