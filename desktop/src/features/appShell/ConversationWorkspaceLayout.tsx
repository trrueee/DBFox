import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

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
  const stageRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);

  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    // Measure the actual stage: navigation changes its width without a window
    // resize. Keep the same panels mounted so layout changes retain drafts.
    const measure = () => {
      const width = stage.getBoundingClientRect().width;
      if (width > 0) setCompact(width < 420 + 8 + 320);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);
  const conversationHidden = compact && dockOpen;

  return (
    <ResizablePanelGroup
      id="conversation-workspace-split"
      ref={stageRef}
      data-compact={compact ? "true" : undefined}
      direction="horizontal"
      className="app-v3-stage"
    >
      <ResizablePanel
        id="conversation-workspace-panel"
        className="app-conversation-panel"
        minSize={compact ? 0 : 420}
        maxSize={conversationHidden ? 0 : "100%"}
        inert={conversationHidden}
        aria-hidden={conversationHidden || undefined}
      >
        {conversation}
      </ResizablePanel>

      {dockOpen && !compact && (
        <ResizableHandle
          aria-label="调整工作区宽度"
          className="app-dock-resize-handle"
          withGrip={false}
        />
      )}

      <ResizablePanel
        id="conversation-dock-panel"
        className="app-dock-panel"
        defaultSize={dockOpen ? 440 : 44}
        minSize={dockOpen ? (compact ? "100%" : 320) : 44}
        maxSize={dockOpen ? (compact ? "100%" : "56%") : 44}
        groupResizeBehavior="preserve-pixel-size"
      >
        {dock}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
