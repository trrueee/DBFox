import type { WorkspaceDockTab } from "../../types/workspace";
import { coreDockViews } from "./coreDockViews";
import { dataDockViews } from "./dataDockViews";
import type { DockViewContribution } from "./types";
import { workspaceDockViews } from "./workspaceDockViews";
import { useDlcStore } from "../dlc/extensionStore";

export interface DockViewRegistry {
  get: (viewType: string) => DockViewContribution | null;
  all: () => readonly DockViewContribution[];
}

export function createDockViewRegistry(
  contributions: readonly DockViewContribution[],
): DockViewRegistry {
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

export const DEFAULT_REGISTRY = createDockViewRegistry(productDockViews());

export function getDockView(
  viewType: string,
  registry: DockViewRegistry = DEFAULT_REGISTRY,
): DockViewContribution | null {
  const view = registry.get(viewType);
  if (view) return view;

  const dlcViews = useDlcStore.getState().contributions.dockViews;
  return dlcViews.find((v) => v.viewType === viewType) ?? null;
}

export function dockViewTitle(
  view: WorkspaceDockTab,
  registry: DockViewRegistry = DEFAULT_REGISTRY,
): string {
  return getDockView(view.viewType, registry)?.resolveTitle(view) ?? view.title;
}
