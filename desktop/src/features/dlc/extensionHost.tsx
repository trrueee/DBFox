import React from "react";
import ReactDOM from "react-dom";
import type {
  FrontendExtensionHost,
  DlcContributionSet,
} from "./types";
import type { ResourceConnectorContribution, ConnectorContext } from "../resources/types";
import type { DockViewContribution, DockRenderContext, DockViewContext } from "../dock/types";
import type {
  ArtifactViewContribution,
  ArtifactEnvelope,
  ArtifactViewContext,
} from "../workspace/artifacts/types";
import { DlcErrorBoundary } from "./DlcErrorBoundary";
import type { WorkspaceDockTab } from "../../types/workspace";
import { fetchEnginePath } from "../../lib/api/client";
import {
  pickDesktopFile,
  pickDesktopProjectFolder,
  readDesktopPickedFile,
} from "../../lib/desktopHost";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { Tree } from "../../components/ui";
import { CodeArtifactView } from "../workspace/artifacts/CodeArtifactView";
import type { DlcOperationInvokeOptions } from "./types";
import type {
  CredentialEnrollmentBatchResult,
  CredentialEnrollmentInput,
} from "./types";
import "./extension-host.css";

/**
 * Ensures global SDK object is mounted on window for dynamic DLC scripts.
 */
export function initExtensionHostGlobalSdk(): void {
  if (typeof window !== "undefined") {
    window.__DBFOX_EXTENSION_HOST__ = {
      React,
      ReactDOM,
      version: "1.0.0",
    };
  }
}

export interface StagedExtensionHostResult {
  host: FrontendExtensionHost;
  getContributions(): DlcContributionSet;
}

interface ExtensionHostServices {
  invokeOperation<TOutput>(
    dlcId: string,
    operationName: string,
    input: unknown,
    options?: DlcOperationInvokeOptions,
  ): Promise<TOutput>;
  openDockTab(view: WorkspaceDockTab, activate?: boolean): void;
  pickFolder?(): Promise<string | null>;
  pickFile?(options?: { title?: string; accept?: readonly string[]; maxBytes?: number }): Promise<{
    path: string; name: string; sizeBytes: number; modifiedAtUnix: number;
  } | null>;
  readPickedFile?(path: string): Promise<Uint8Array>;
  enrollCredentials?(
    dlcId: string,
    credentials: readonly CredentialEnrollmentInput[],
    signal?: AbortSignal,
  ): Promise<CredentialEnrollmentBatchResult>;
}

async function invokeBoundDlcOperation<TOutput>(
  dlcId: string,
  operationName: string,
  input: unknown,
  options?: DlcOperationInvokeOptions,
): Promise<TOutput> {
  const query = options?.projectId
    ? `?project_id=${encodeURIComponent(options.projectId)}`
    : "";
  const response = await fetchEnginePath(
    `/dlcs/${encodeURIComponent(dlcId)}/operations/${encodeURIComponent(operationName)}${query}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options?.credentialLeaseId
          ? { "X-Credential-Lease-Id": options.credentialLeaseId }
          : {}),
      },
      body: JSON.stringify(input ?? {}),
      signal: options?.signal,
    },
  );
  if (!response.ok) {
    let message = `DLC operation failed with HTTP ${response.status}`;
    try {
      const payload = await response.json() as {
        detail?: string | { message?: string };
      };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail?.message) {
        message = payload.detail.message;
      }
    } catch {
      // Keep the bounded status-only fallback; never expose local auth material.
    }
    throw new Error(message);
  }
  return await response.json() as TOutput;
}

async function enrollBoundDlcCredentials(
  dlcId: string,
  credentials: readonly CredentialEnrollmentInput[],
  signal?: AbortSignal,
): Promise<CredentialEnrollmentBatchResult> {
  const response = await fetchEnginePath(
    `/dlcs/${encodeURIComponent(dlcId)}/credentials/batch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credentials }),
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(`DLC credential enrollment failed with HTTP ${response.status}`);
  }
  return await response.json() as CredentialEnrollmentBatchResult;
}

const DEFAULT_EXTENSION_HOST_SERVICES: ExtensionHostServices = {
  invokeOperation: invokeBoundDlcOperation,
  openDockTab: (view, activate) => {
    useWorkspaceStore.getState().openDockTab(view, activate);
  },
  pickFolder: pickDesktopProjectFolder,
  pickFile: (options) => pickDesktopFile({
    title: options?.title,
    filters: options?.accept?.length
      ? [{ name: "Allowed files", extensions: [...options.accept] }]
      : undefined,
    maxBytes: options?.maxBytes,
  }),
  readPickedFile: readDesktopPickedFile,
  enrollCredentials: enrollBoundDlcCredentials,
};

function DlcRenderCallback({
  render,
  dlcId,
  surface,
}: {
  render: () => React.ReactNode;
  dlcId: string;
  surface: "connector" | "dock" | "artifact";
}) {
  return (
    <div className={`dlc-slot dlc-slot--${surface}`} data-dlc-id={dlcId}>
      {render()}
    </div>
  );
}

function reportCallbackFailure(dlcId: string, callback: string, error: unknown): void {
  console.error(`[DLC Host] ${dlcId} ${callback} callback failed:`, error);
}

/**
 * Creates a same-realm transactional staging host for trusted DLC registration.
 * Callback failure isolation is not a DOM, process, network, or native-bridge
 * sandbox; R8A deliberately keeps untrusted frontend code disabled.
 */
export function createStagedExtensionHost(
  dlcId: string,
  services: ExtensionHostServices = DEFAULT_EXTENSION_HOST_SERVICES,
): StagedExtensionHostResult {
  const connectors: ResourceConnectorContribution[] = [];
  const dockViews: DockViewContribution[] = [];
  const artifactViews: ArtifactViewContribution<unknown>[] = [];
  const connectorIds = new Set<string>();
  const dockViewTypes = new Set<string>();
  const artifactViewIds = new Set<string>();

  const admitOwnedId = (id: string, kind: string, registered: Set<string>): void => {
    if (id !== dlcId && !id.startsWith(`${dlcId}.`)) {
      throw new Error(
        `[DLC ${dlcId}] ${kind} id "${id}" must be owned by namespace "${dlcId}"`,
      );
    }
    if (registered.has(id)) {
      throw new Error(`[DLC ${dlcId}] Duplicate ${kind} id "${id}"`);
    }
    registered.add(id);
  };

  const host: FrontendExtensionHost = {
    dlcId,
    ui: {
      version: "1.0.0",
      Tree,
      CodeArtifact: CodeArtifactView,
    },
    connectors: {
      register(contribution: ResourceConnectorContribution): void {
        if (!contribution || typeof contribution.id !== "string" || !contribution.id.trim()) {
          throw new Error(`[DLC ${dlcId}] Invalid connector registration: missing valid id`);
        }
        admitOwnedId(contribution.id, "connector", connectorIds);
        const safeContribution: ResourceConnectorContribution = {
          ...contribution,
          render(context: ConnectorContext) {
            return React.createElement(
              DlcErrorBoundary,
              { dlcId, componentName: `connector:${contribution.id}` },
              React.createElement(DlcRenderCallback, {
                render: () => contribution.render(context),
                dlcId,
                surface: "connector",
              }),
            );
          },
          onAdd: contribution.onAdd
            ? async (context: ConnectorContext) => {
              try {
                await contribution.onAdd?.(context);
              } catch (error) {
                reportCallbackFailure(dlcId, `connector:${contribution.id}:onAdd`, error);
                throw error;
              }
            }
            : undefined,
          listResources: contribution.listResources
            ? async (context: ConnectorContext) => {
              try {
                return (await contribution.listResources?.(context)) ?? [];
              } catch (error) {
                reportCallbackFailure(dlcId, `connector:${contribution.id}:listResources`, error);
                throw error;
              }
            }
            : undefined,
          removeResource: contribution.removeResource
            ? async (context: ConnectorContext, resource) => {
              try {
                await contribution.removeResource?.(context, resource);
              } catch (error) {
                reportCallbackFailure(dlcId, `connector:${contribution.id}:removeResource`, error);
                throw error;
              }
            }
            : undefined,
        };
        connectors.push(safeContribution);
      },
    },
    nativeDialogs: {
      pickFolder: () => (services.pickFolder ?? pickDesktopProjectFolder)(),
      pickFile: (options) => (services.pickFile ?? DEFAULT_EXTENSION_HOST_SERVICES.pickFile!)(options),
    },
    nativeFiles: {
      readPickedFile: (path) => (
        services.readPickedFile ?? readDesktopPickedFile
      )(path),
    },
    credentials: {
      enrollBatch(credentials, options) {
        return (services.enrollCredentials ?? enrollBoundDlcCredentials)(
          dlcId,
          credentials,
          options?.signal,
        );
      },
    },
    dockViews: {
      register(contribution: DockViewContribution): void {
        if (
          !contribution ||
          typeof contribution.viewType !== "string" ||
          !contribution.viewType.trim()
        ) {
          throw new Error(`[DLC ${dlcId}] Invalid dock view registration: missing valid viewType`);
        }
        admitOwnedId(contribution.viewType, "dock view", dockViewTypes);
        const safeContribution: DockViewContribution = {
          ...contribution,
          icon(view: WorkspaceDockTab) {
            try {
              return contribution.icon(view);
            } catch (error) {
              reportCallbackFailure(dlcId, `dockView:${contribution.viewType}:icon`, error);
              return null;
            }
          },
          resolveTitle(view: WorkspaceDockTab) {
            try {
              return contribution.resolveTitle(view);
            } catch (error) {
              reportCallbackFailure(dlcId, `dockView:${contribution.viewType}:resolveTitle`, error);
              return view.title;
            }
          },
          isVisible(view: WorkspaceDockTab, context: DockViewContext) {
            try {
              return contribution.isVisible(view, context);
            } catch (error) {
              reportCallbackFailure(dlcId, `dockView:${contribution.viewType}:isVisible`, error);
              return false;
            }
          },
          render(view: WorkspaceDockTab, context: DockRenderContext) {
            return React.createElement(
              DlcErrorBoundary,
              { dlcId, componentName: `dockView:${contribution.viewType}` },
              React.createElement(DlcRenderCallback, {
                render: () => contribution.render(view, context),
                dlcId,
                surface: "dock",
              }),
            );
          },
        };
        dockViews.push(safeContribution);
      },
      open(view: WorkspaceDockTab, activate = true): void {
        if (!view || !dockViews.some((candidate) => candidate.viewType === view.viewType)) {
          throw new Error(
            `[DLC ${dlcId}] Cannot open unregistered Dock viewType "${view?.viewType ?? ""}"`,
          );
        }
        services.openDockTab({ ...view }, activate);
      },
    },
    workbench: {
      currentScopeId(): string {
        return useWorkspaceStore.getState().ensureActiveWorkbenchScope();
      },
    },
    artifactViews: {
      register(contribution: ArtifactViewContribution<unknown>): void {
        if (!contribution || typeof contribution.id !== "string" || !contribution.id.trim()) {
          throw new Error(
            `[DLC ${dlcId}] Invalid Artifact View registration: missing valid id`,
          );
        }
        admitOwnedId(contribution.id, "Artifact View", artifactViewIds);
        if (!contribution.artifactTypes?.length && !contribution.representationTypes?.length) {
          throw new Error(`[DLC ${dlcId}] Invalid Artifact View registration: missing selector`);
        }
        const safeContribution: ArtifactViewContribution<unknown> = {
          ...contribution,
          render(
            artifact: ArtifactEnvelope<unknown>,
            payload: unknown,
            context: ArtifactViewContext,
          ) {
            return React.createElement(
              DlcErrorBoundary,
              { dlcId, componentName: `artifactView:${contribution.id}` },
              React.createElement(DlcRenderCallback, {
                render: () => contribution.render(artifact, payload, context),
                dlcId,
                surface: "artifact",
              }),
            );
          },
        };
        artifactViews.push(safeContribution);
      },
    },
    operations: {
      invoke<TOutput = unknown>(
        operationName: string,
        input: unknown = {},
        options?: DlcOperationInvokeOptions,
      ): Promise<TOutput> {
        if (!/^[a-z0-9_.-]{1,64}$/.test(operationName)) {
          return Promise.reject(
            new Error(`Invalid DLC operation name: "${operationName}"`),
          );
        }
        return services.invokeOperation<TOutput>(dlcId, operationName, input, options);
      },
    },
  };

  return {
    host,
    getContributions(): DlcContributionSet {
      return {
        connectors: Object.freeze([...connectors]),
        dockViews: Object.freeze([...dockViews]),
        artifactViews: Object.freeze([...artifactViews]),
      };
    },
  };
}
