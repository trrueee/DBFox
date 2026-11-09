import type { WorkspaceDockTab } from "../../types/workspace";
import { coreDockViews } from "./coreDockViews";
import type { DockViewContext, DockViewContribution } from "./types";
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
  return coreDockViews;
}

export const DEFAULT_REGISTRY = createDockViewRegistry(productDockViews());

export function getDockView(
  viewType: string,
  registry: DockViewRegistry = DEFAULT_REGISTRY,
  dlcViews: readonly DockViewContribution[] = useDlcStore.getState().contributions.dockViews,
): DockViewContribution | null {
  return registry.get(viewType) ?? dlcViews.find((view) => view.viewType === viewType) ?? null;
}

export function visibleDockTabs(
  tabs: readonly WorkspaceDockTab[],
  context: DockViewContext,
  registry: DockViewRegistry = DEFAULT_REGISTRY,
  dlcViews: readonly DockViewContribution[] = useDlcStore.getState().contributions.dockViews,
): WorkspaceDockTab[] {
  // Keep unknown tabs visible so users can close them.
  return tabs.filter((tab) => getDockView(tab.viewType, registry, dlcViews)?.isVisible(tab, context) ?? true);
}

export function activeDockTab(tabs: readonly WorkspaceDockTab[], activeViewKey: string | null): WorkspaceDockTab | null {
  return tabs.find((tab) => tab.viewKey === activeViewKey) ?? tabs.at(-1) ?? null;
}

export function dockViewTitle(
  view: WorkspaceDockTab,
  registry: DockViewRegistry = DEFAULT_REGISTRY,
): string {
  return getDockView(view.viewType, registry)?.resolveTitle(view) ?? view.title;
}
