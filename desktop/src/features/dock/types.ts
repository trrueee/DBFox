import type { ReactNode } from "react";
import type { WorkspaceDockTab } from "../../types/workspace";

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
