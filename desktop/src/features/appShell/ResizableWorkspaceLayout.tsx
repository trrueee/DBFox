import type { ReactNode } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../../components/ui";

interface ResizableWorkspaceLayoutProps {
  sidebarCollapsed: boolean;
  settingsOpen: boolean;
  sidebar: ReactNode;
  workspace: ReactNode;
}

export function ResizableWorkspaceLayout({
  sidebarCollapsed,
  settingsOpen,
  sidebar,
  workspace,
}: ResizableWorkspaceLayoutProps) {
  return (
    <ResizablePanelGroup
      id="app-body-split"
      direction="horizontal"
      className="app-body-split"
    >
      <ResizablePanel
        id="app-sidebar-panel"
        className={`app-sidebar-panel ${sidebarCollapsed ? "app-sidebar-panel--collapsed" : ""}`}
        defaultSize={sidebarCollapsed ? 36 : settingsOpen ? 248 : 260}
        minSize={sidebarCollapsed ? 36 : 220}
        maxSize={sidebarCollapsed ? 36 : settingsOpen ? 320 : 420}
        disabled={sidebarCollapsed}
        groupResizeBehavior="preserve-pixel-size"
      >
        {sidebar}
      </ResizablePanel>

      {!sidebarCollapsed && (
        <ResizableHandle
          aria-label="Resize datasource sidebar"
          className="app-sidebar-resize-handle"
        />
      )}

      <ResizablePanel
        id="app-workspace-panel"
        className="app-workspace-panel"
        minSize={420}
      >
        {workspace}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
