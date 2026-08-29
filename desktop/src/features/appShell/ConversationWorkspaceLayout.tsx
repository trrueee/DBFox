import { useLayoutEffect, type ReactNode } from "react";
import { usePanelRef } from "react-resizable-panels";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../../components/ui";

interface ConversationWorkspaceLayoutProps {
  dockOpen: boolean;
  conversation: ReactNode;
  dock: ReactNode;
}

/**
 * Owns the center/right workbench split at its real layout boundary. Panel
 * sizing and separator interaction are delegated to react-resizable-panels;
 * the durable Dock open state remains owned by workspaceStore.
 */
export function ConversationWorkspaceLayout({
  dockOpen,
  conversation,
  dock,
}: ConversationWorkspaceLayoutProps) {
  const dockPanelRef = usePanelRef();

  useLayoutEffect(() => {
    const panel = dockPanelRef.current;
    if (!panel) return;
    if (dockOpen) panel.expand();
    else panel.collapse();
  }, [dockOpen, dockPanelRef]);

  return (
    <ResizablePanelGroup
      id="conversation-workspace-split"
      direction="horizontal"
      className="app-v3-stage"
    >
      <ResizablePanel
        id="conversation-workspace-panel"
        className="app-conversation-panel"
        minSize={420}
      >
        {conversation}
      </ResizablePanel>

      {dockOpen && (
        <ResizableHandle
          aria-label="调整工作区宽度"
          className="app-dock-resize-handle"
          withGrip={false}
        />
      )}

      <ResizablePanel
        id="conversation-dock-panel"
        panelRef={dockPanelRef}
        className="app-dock-panel"
        defaultSize={dockOpen ? 440 : 44}
        minSize={320}
        maxSize="56%"
        collapsible
        collapsedSize={44}
        groupResizeBehavior="preserve-pixel-size"
      >
        {dock}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
