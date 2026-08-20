import React from "react";
import ReactDOM from "react-dom";
import type {
  FrontendExtensionHost,
  DlcContributionSet,
} from "./types";
import type { ResourceConnectorContribution, ConnectorContext } from "../resources/types";
import type { RequestedResourceContributor } from "../resources/requestedResourceComposition";
import type { DockViewContribution, DockRenderContext, DockViewContext } from "../dock/types";
import type {
  ArtifactRendererContribution,
  ArtifactEnvelope,
  ArtifactRendererContext,
} from "../workspace/artifacts/types";
import { DlcErrorBoundary } from "./DlcErrorBoundary";
import type { WorkspaceDockTab } from "../../types/workspace";

declare global {
  interface Window {
    __DBFOX_EXTENSION_HOST__?: {
      React: typeof React;
      ReactDOM: typeof ReactDOM;
      version: string;
    };
  }
}

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

function DlcRenderCallback({ render }: { render: () => React.ReactNode }) {
  return <>{render()}</>;
}

function reportCallbackFailure(dlcId: string, callback: string, error: unknown): void {
  console.error(`[DLC Host] ${dlcId} ${callback} callback failed:`, error);
}

/**
 * Creates an isolated, transactional staging host for a DLC registration.
 */
export function createStagedExtensionHost(dlcId: string): StagedExtensionHostResult {
  const connectors: ResourceConnectorContribution[] = [];
  const requestedResources: RequestedResourceContributor[] = [];
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
            ? (context: ConnectorContext) => {
              try {
                contribution.onAdd?.(context);
              } catch (error) {
                reportCallbackFailure(dlcId, `connector:${contribution.id}:onAdd`, error);
              }
            }
            : undefined,
        };
        connectors.push(safeContribution);
      },
    },
    requestedResources: {
      register(contributor: RequestedResourceContributor): void {
        if (typeof contributor !== "function") {
          throw new Error(
            `[DLC ${dlcId}] Invalid requested resource contributor: must be a function`,
          );
        }
        requestedResources.push((context) => {
          try {
            return contributor(context);
          } catch (error) {
            reportCallbackFailure(dlcId, "requestedResources", error);
            return { complete: false };
          }
        });
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
  };

  return {
    host,
    getContributions(): DlcContributionSet {
      return {
        connectors: Object.freeze([...connectors]),
        requestedResources: Object.freeze([...requestedResources]),
        dockViews: Object.freeze([...dockViews]),
        artifactRenderers: Object.freeze([...artifactRenderers]),
      };
    },
  };
}
