import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../../components/ui";

const MIN_CONVERSATION_WIDTH = 520;
const MIN_DOCK_WIDTH = 340;
const RESIZE_HANDLE_WIDTH = 8;

/** A view's preferred width is a hint; the user's layout remains authoritative. */
export function initialDockWidth(stageWidth: number, preferredWidth: number, percent: number, savedWidth?: number): number {
  if (stageWidth < MIN_CONVERSATION_WIDTH + RESIZE_HANDLE_WIDTH + MIN_DOCK_WIDTH) return stageWidth;
  const requested = savedWidth ?? Math.min(preferredWidth, stageWidth * percent / 100);
  return Math.max(MIN_DOCK_WIDTH, Math.min(requested, stageWidth - MIN_CONVERSATION_WIDTH - RESIZE_HANDLE_WIDTH));
}

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
  defaultWidthPercent = 38,
  savedWidth,
  onWidthChange,
}: ConversationWorkspaceLayoutProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<PanelImperativeHandle>(null);
  const latestWidthRef = useRef(savedWidth ?? preferredWidth);
  const [stageWidth, setStageWidth] = useState(0);
  const compact = stageWidth > 0 && stageWidth < MIN_CONVERSATION_WIDTH + RESIZE_HANDLE_WIDTH + MIN_DOCK_WIDTH;

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
      dockRef.current?.resize(initialDockWidth(width, preferredWidth, defaultWidthPercent, savedWidth));
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
        minSize={compact ? 0 : MIN_CONVERSATION_WIDTH}
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
        defaultSize={dockOpen ? (savedWidth ?? `${defaultWidthPercent}%`) : 44}
        minSize={dockOpen ? (compact ? "100%" : MIN_DOCK_WIDTH) : 44}
        maxSize={dockOpen ? "100%" : 44}
        groupResizeBehavior="preserve-pixel-size"
        onResize={size => { if (dockOpen && !compact) latestWidthRef.current = size.inPixels; }}
      >
        {dock}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
