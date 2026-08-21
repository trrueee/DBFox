import type { RequestedResourceRef } from "../../lib/api/generated/types.gen";
import { queryClient } from "../../lib/queryClient";
import { projectQueryKeys } from "../projects/useProjectState";
import type { ProjectResponse } from "../../lib/api/generated/types.gen";
import { useDlcStore } from "../dlc/extensionStore";

export interface ConversationSendResourceContext {
  projectId: string;
  conversationId: string;
  datasourceId?: string | null;
}

export interface RequestedResourceContributionResult {
  /**
   * Whether this capability was able to prove a complete and definite authority decision.
   * If false, the overall snapshot cannot be proven complete -> omit requested_resources (fallback).
   */
  complete: boolean;
  /**
   * The requested resources for this capability (empty if none selected/active).
   */
  refs?: readonly RequestedResourceRef[];
}

export type RequestedResourceContributor = (
  context: ConversationSendResourceContext,
) => RequestedResourceContributionResult;

export const dataRequestedResourceContributor: RequestedResourceContributor = (context) => {
  if (!context.datasourceId) {
    return { complete: true, refs: [] };
  }
  return { complete: true, refs: [{ kind: "database", id: context.datasourceId }] };
};

export const workspaceRequestedResourceContributor: RequestedResourceContributor = (context) => {
  if (!context.projectId) {
    return { complete: true, refs: [] };
  }
  const projects = queryClient.getQueryData<ProjectResponse[]>(projectQueryKeys.all);
  if (!projects) {
    // Project state not yet cached in client: unproven complete authority
    return { complete: false };
  }
  const project = projects.find((p) => p.id === context.projectId);
  if (!project) {
    return { complete: false };
  }
  const workspaceRoot = project.workspace_root?.trim();
  if (!workspaceRoot) {
    // Proven: project exists and explicitly has no local workspace
    return { complete: true, refs: [] };
  }
  return { complete: true, refs: [{ kind: "workspace", id: context.projectId }] };
};

export const PRODUCT_REQUESTED_RESOURCE_CONTRIBUTORS: readonly RequestedResourceContributor[] = [
  dataRequestedResourceContributor,
  workspaceRequestedResourceContributor,
];

export interface ProductRequestedResourcesSnapshot {
  complete: boolean;
  refs: readonly RequestedResourceRef[];
}

export function getEffectiveRequestedResourceContributors(): readonly RequestedResourceContributor[] {
  const dlcContributors = useDlcStore.getState().contributions.requestedResources;
  return [...PRODUCT_REQUESTED_RESOURCE_CONTRIBUTORS, ...dlcContributors];
}

export function collectProductRequestedResources(
  context: ConversationSendResourceContext,
  contributors?: readonly RequestedResourceContributor[],
): ProductRequestedResourcesSnapshot {
  const activeContributors =
    contributors ?? getEffectiveRequestedResourceContributors();
  const refs: RequestedResourceRef[] = [];
  const seen = new Set<string>();

  for (const contributor of activeContributors) {
    const result = contributor(context);
    if (!result.complete) {
      return { complete: false, refs: [] };
    }
    if (result.refs) {
      for (const ref of result.refs) {
        const key = `${ref.kind}:${ref.id}`;
        if (!seen.has(key)) {
          seen.add(key);
          refs.push(ref);
        }
      }
    }
  }

  return { complete: true, refs };
}
