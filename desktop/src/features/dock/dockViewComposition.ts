import type { WorkspaceDockTab } from "../../types/workspace";
import { coreDockViews } from "./coreDockViews";
import { dataDockViews } from "./dataDockViews";
import type { DockViewContribution } from "./types";
import { workspaceDockViews } from "./workspaceDockViews";

export function createDockViewRegistry(
  contributions: readonly DockViewContribution[],
): {
  get: (viewType: string) => DockViewContribution | null;
  all: () => readonly DockViewContribution[];
} {
  const map = new Map<string, DockViewContribution>();
  for (const contribution of contributions) {
    if (map.has(contribution.viewType)) {
      throw new Error(
        `Duplicate Dock viewType contribution detected: "${contribution.viewType}". Registration must fail closed.`,
      );
    }
    map.set(contribution.viewType, contribution);
  }
  return {
    get: (viewType: string) => map.get(viewType) ?? null,
    all: () => contributions,
  };
}

export function productDockViews(): readonly DockViewContribution[] {
  return [
    ...coreDockViews,
    ...dataDockViews,
    ...workspaceDockViews,
  ];
}

const DEFAULT_REGISTRY = createDockViewRegistry(productDockViews());

export function getDockView(viewType: string): DockViewContribution | null {
  return DEFAULT_REGISTRY.get(viewType);
}

export function dockViewTitle(view: WorkspaceDockTab): string {
  return getDockView(view.viewType)?.resolveTitle(view) ?? view.title;
}
