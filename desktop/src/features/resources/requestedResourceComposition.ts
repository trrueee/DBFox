import type { RequestedResourceRef } from "../../lib/api/generated/types.gen";

export interface RequestedResourceContext {
  projectId: string;
  datasourceId?: string | null;
  workspaceRoot?: string | null;
  githubBindingId?: string | null;
  activeGithubBindingId?: string | null;
}

export type RequestedResourceCollector = (
  context: RequestedResourceContext,
) => readonly RequestedResourceRef[] | undefined;

export const dataRequestedResourceCollector: RequestedResourceCollector = (context) => {
  if (!context.datasourceId) return undefined;
  return [{ kind: "database", id: context.datasourceId }];
};

export const workspaceRequestedResourceCollector: RequestedResourceCollector = (context) => {
  if (!context.workspaceRoot || !context.projectId) return undefined;
  return [{ kind: "workspace", id: context.projectId }];
};

export const githubRequestedResourceCollector: RequestedResourceCollector = (context) => {
  const bindingId = context.githubBindingId || context.activeGithubBindingId;
  if (!bindingId) return undefined;
  return [{ kind: "github.repository", id: bindingId }];
};

export const PRODUCT_REQUESTED_RESOURCE_COLLECTORS: readonly RequestedResourceCollector[] = [
  dataRequestedResourceCollector,
  workspaceRequestedResourceCollector,
  githubRequestedResourceCollector,
];

export function collectProductRequestedResources(
  context: RequestedResourceContext,
  collectors: readonly RequestedResourceCollector[] = PRODUCT_REQUESTED_RESOURCE_COLLECTORS,
): readonly RequestedResourceRef[] | undefined {
  // If workspace authority is unproven (undefined), fail safe by omitting requested_resources
  // so the server preserves full legacy session authority without dropping workspace tools.
  if (context.projectId && context.workspaceRoot === undefined) {
    return undefined;
  }

  const refs: RequestedResourceRef[] = [];
  const seen = new Set<string>();

  for (const collector of collectors) {
    const collected = collector(context);
    if (!collected) continue;
    for (const ref of collected) {
      const key = `${ref.kind}:${ref.id}`;
      if (!seen.has(key)) {
        seen.add(key);
        refs.push(ref);
      }
    }
  }

  return refs.length > 0 ? refs : undefined;
}
