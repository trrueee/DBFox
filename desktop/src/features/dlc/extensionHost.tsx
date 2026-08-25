import React from "react";
import ReactDOM from "react-dom";
import type {
  FrontendExtensionHost,
  DlcContributionSet,
} from "./types";
import type { ResourceConnectorContribution, ConnectorContext } from "../resources/types";
import type { DockViewContribution, DockRenderContext, DockViewContext } from "../dock/types";
import type {
  ArtifactRendererContribution,
  ArtifactEnvelope,
  ArtifactRendererContext,
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
import type { DlcOperationInvokeOptions } from "./types";
import type {
  CredentialEnrollmentBatchResult,
  CredentialEnrollmentInput,
} from "../../../../sdk/frontend/index";
import {
  addCurrentComposerContextResource,
  addCurrentConversationContextResource,
  getCurrentComposerContextSelection,
  getCurrentConversationContextSelection,
  removeCurrentComposerContextResource,
  removeCurrentConversationContextResource,
} from "../conversation/conversationContextSelection";

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

function DlcRenderCallback({ render }: { render: () => React.ReactNode }) {
  return <>{render()}</>;
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
  const artifactRenderers: ArtifactRendererContribution<unknown>[] = [];

  const host: FrontendExtensionHost = {
    dlcId,
    connectors: {
      register(contribution: ResourceConnectorContribution): void {
        if (!contribution || typeof contribution.id !== "string" || !contribution.id.trim()) {
          throw new Error(`[DLC ${dlcId}] Invalid connector registration: missing valid id`);
        }
        const safeContribution: ResourceConnectorContribution = {
          ...contribution,
          render(context: ConnectorContext) {
            return React.createElement(
              DlcErrorBoundary,
              { dlcId, componentName: `connector:${contribution.id}` },
              React.createElement(DlcRenderCallback, {
                render: () => contribution.render(context),
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
        };
        connectors.push(safeContribution);
      },
    },
    contextSelection: {
      isSelected: (ref) => getCurrentConversationContextSelection().some(
        (candidate) => candidate.kind === ref.kind && candidate.id === ref.id,
      ),
      list: () => getCurrentConversationContextSelection(),
      add: (ref) => addCurrentConversationContextResource(ref),
      remove: (ref) => removeCurrentConversationContextResource(ref),
    },
    composerContext: {
      isSelected: (ref) => getCurrentComposerContextSelection().some(
        (candidate) => candidate.kind === ref.kind && candidate.id === ref.id,
      ),
      list: () => getCurrentComposerContextSelection(),
      add: (ref) => addCurrentComposerContextResource(ref),
      remove: (ref) => removeCurrentComposerContextResource(ref),
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
    artifactRenderers: {
      register(contribution: ArtifactRendererContribution<unknown>): void {
        if (!contribution || typeof contribution.type !== "string" || !contribution.type.trim()) {
          throw new Error(
            `[DLC ${dlcId}] Invalid artifact renderer registration: missing valid type`,
          );
        }
        const safeContribution: ArtifactRendererContribution<unknown> = {
          ...contribution,
          render(artifact: ArtifactEnvelope<unknown>, context: ArtifactRendererContext) {
            return React.createElement(
              DlcErrorBoundary,
              { dlcId, componentName: `artifactRenderer:${contribution.type}` },
              React.createElement(DlcRenderCallback, {
                render: () => contribution.render(artifact, context),
              }),
            );
          },
        };
        artifactRenderers.push(safeContribution);
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
        artifactRenderers: Object.freeze([...artifactRenderers]),
      };
    },
  };
}
