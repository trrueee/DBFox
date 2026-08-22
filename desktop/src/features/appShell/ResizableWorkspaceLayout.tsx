import { useRef, type ReactNode } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../../components/ui";
import { useTheme } from "../../hooks/themeContext";

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
  const { appearance, updateAppearance } = useTheme();
  const latestSidebarWidthRef = useRef(appearance.sidebarWidth);
  const sidebarDefaultWidth = settingsOpen
    ? Math.min(appearance.sidebarWidth, 320)
    : appearance.sidebarWidth;

  return (
    <ResizablePanelGroup
      id="app-body-split"
      direction="horizontal"
      className="app-body-split"
      onLayoutChanged={(_layout, meta) => {
        if (
          meta.isUserInteraction
          && !sidebarCollapsed
          && latestSidebarWidthRef.current !== appearance.sidebarWidth
        ) {
          updateAppearance({ sidebarWidth: latestSidebarWidthRef.current });
        }
      }}
    >
      <ResizablePanel
        id="app-sidebar-panel"
        className={`app-sidebar-panel ${sidebarCollapsed ? "app-sidebar-panel--collapsed" : ""}`}
        defaultSize={sidebarCollapsed ? 36 : sidebarDefaultWidth}
        minSize={sidebarCollapsed ? 36 : 248}
        maxSize={sidebarCollapsed ? 36 : settingsOpen ? 320 : 420}
        disabled={sidebarCollapsed}
        groupResizeBehavior="preserve-pixel-size"
        onResize={(size) => {
          if (!sidebarCollapsed) latestSidebarWidthRef.current = Math.round(size.inPixels);
        }}
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
