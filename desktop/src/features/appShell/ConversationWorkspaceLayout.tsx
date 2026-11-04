import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../../components/ui";

interface ConversationWorkspaceLayoutProps {
  dockOpen: boolean;
  conversation: ReactNode;
  dock: ReactNode;
  preferredWidth?: number;
  defaultWidthPercent?: number;
  savedWidth?: number;
  onWidthChange?: (width: number) => void;
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
  preferredWidth = 480,
  defaultWidthPercent = 28,
  savedWidth,
  onWidthChange,
}: ConversationWorkspaceLayoutProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<PanelImperativeHandle>(null);
  const latestWidthRef = useRef(savedWidth ?? preferredWidth);
  const [stageWidth, setStageWidth] = useState(0);
  const compact = stageWidth > 0 && stageWidth < 420 + 8 + 320;

  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    // Measure the actual stage: navigation changes its width without a window
    // resize. Keep the same panels mounted so layout changes retain drafts.
    const measure = () => {
      const width = stage.getBoundingClientRect().width;
      if (width > 0) setStageWidth(Math.round(width));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);
  const conversationHidden = compact && dockOpen;

  useLayoutEffect(() => {
    if (!dockOpen) return;
    // Panel registers its changed min/max constraints in a nested layout
    // commit. Resize once that commit has settled, using its public API.
    const frame = requestAnimationFrame(() => {
      const width = stageRef.current?.getBoundingClientRect().width ?? 0;
      if (!width) return;
      if (compact) { dockRef.current?.resize("100%"); return; }
      const desiredWidth = savedWidth ?? Math.max(preferredWidth, width * defaultWidthPercent / 100);
      dockRef.current?.resize(Math.max(320, Math.min(desiredWidth, width - 428)));
    });
    return () => cancelAnimationFrame(frame);
  }, [dockOpen, compact, stageWidth, preferredWidth, defaultWidthPercent, savedWidth]);

  return (
    <ResizablePanelGroup
      id="conversation-workspace-split"
      ref={stageRef}
      data-compact={compact ? "true" : undefined}
      direction="horizontal"
      className="app-v3-stage"
      onLayoutChanged={(_layout, meta) => {
        if (meta.isUserInteraction && dockOpen && !compact) onWidthChange?.(latestWidthRef.current);
      }}
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
        panelRef={dockRef}
        defaultSize={dockOpen ? (savedWidth ?? preferredWidth) : 44}
        minSize={dockOpen ? (compact ? "100%" : 320) : 44}
        maxSize={dockOpen ? "100%" : 44}
        groupResizeBehavior="preserve-pixel-size"
        onResize={size => { if (dockOpen && !compact) latestWidthRef.current = size.inPixels; }}
      >
        {dock}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
