import React from "react";
import ReactDOM from "react-dom";
import type {
  FrontendExtensionHost,
  DlcContributionSet,
} from "./types";
import type { ResourceConnectorContribution, ConnectorContext } from "../resources/types";
import type { RequestedResourceContributor } from "../resources/requestedResourceComposition";
import type { DockViewContribution, DockRenderContext } from "../dock/types";
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
              contribution.render(context),
            );
          },
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
        requestedResources.push(contributor);
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
          render(view: WorkspaceDockTab, context: DockRenderContext) {
            return React.createElement(
              DlcErrorBoundary,
              { dlcId, componentName: `dockView:${contribution.viewType}` },
              contribution.render(view, context),
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
              contribution.render(artifact, context),
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
