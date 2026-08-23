import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { clearCspVirtualLayout, setCspVirtualLayout } from "../../../lib/cspVirtualLayout";
import type {
  ConversationArtifact,
  ConversationRun,
  ConversationRunItem,
} from "../../../types/conversation";
import { AgentTimeline } from "./AgentTimeline";

const VIRTUALIZE_AFTER_RUNS = 40;
const BOTTOM_THRESHOLD_PX = 72;

interface MessageListProps {
  items: ConversationRunItem[];
  runs: ConversationRun[];
  artifacts: ConversationArtifact[];
  onOpenSqlConsole?: (sql?: string) => void;
  onSelectArtifact?: (artifactId: string) => void;
  resolvingQuestionId?: string | null;
  questionError?: string | null;
  onResolveQuestion?: (
    runId: string,
    questionId: string,
    response: { selected_value?: string; text?: string },
  ) => Promise<void> | void;
  onScrolledChange?: (scrolled: boolean) => void;
}

export function MessageList({
  items,
  runs,
  artifacts,
  onOpenSqlConsole,
  onSelectArtifact,
  resolvingQuestionId,
  questionError,
  onResolveQuestion,
  onScrolledChange,
}: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  const virtualLayoutId = `messages-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const pinnedToBottomRef = useRef(true);
  const previousRunCountRef = useRef(0);
  const scrolledStateRef = useRef(false);
  const orderedRuns = useMemo(
    () => [...runs].sort((left, right) => left.session_sequence - right.session_sequence),
    [runs],
  );
  const shouldVirtualize = orderedRuns.length > VIRTUALIZE_AFTER_RUNS;
  const itemsByRunId = useMemo(
    () => groupByRun(items),
    [items],
  );
  const artifactsByRunId = useMemo(
    () => groupArtifactsByRun(artifacts),
    [artifacts],
  );
  const latestRenderKey = useMemo(
    () => items.map((item) => `${item.id}:${item.revision}:${item.status}:${itemTextLength(item)}`).join("|"),
    [items],
  );

  // TanStack Virtual intentionally exposes imperative measurement functions.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: orderedRuns.length,
    enabled: shouldVirtualize,
    getScrollElement: () => ref.current,
    getItemKey: (index) => orderedRuns[index]?.id || index,
    estimateSize: () => 260,
    overscan: 5,
    initialRect: { width: 800, height: 720 },
  });
  const virtualRuns = virtualizer.getVirtualItems();

  useLayoutEffect(() => {
    if (!shouldVirtualize) {
      clearCspVirtualLayout(virtualLayoutId);
      return;
    }
    setCspVirtualLayout(
      virtualLayoutId,
      virtualizer.getTotalSize(),
      virtualRuns.map((item) => ({ index: item.index, start: item.start })),
    );
    return () => clearCspVirtualLayout(virtualLayoutId);
  }, [shouldVirtualize, virtualLayoutId, virtualRuns, virtualizer]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const node = ref.current;
    if (!node || orderedRuns.length === 0) return;
    if (shouldVirtualize) {
      virtualizer.scrollToIndex(orderedRuns.length - 1, { align: "end", behavior });
    } else if (typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior });
    } else {
      node.scrollTop = node.scrollHeight;
    }
  }, [orderedRuns.length, shouldVirtualize, virtualizer]);

  useEffect(() => {
    const addedRun = orderedRuns.length > previousRunCountRef.current;
    previousRunCountRef.current = orderedRuns.length;
    if (addedRun) pinnedToBottomRef.current = true;
    if (!pinnedToBottomRef.current) return;
    const frame = requestAnimationFrame(() => scrollToBottom(addedRun ? "auto" : "smooth"));
    return () => cancelAnimationFrame(frame);
  }, [artifacts.length, latestRenderKey, orderedRuns.length, scrollToBottom]);

  const emitScrolledState = useCallback(
    (scrolled: boolean) => {
      if (scrolledStateRef.current === scrolled) return;
      scrolledStateRef.current = scrolled;
      onScrolledChange?.(scrolled);
    },
    [onScrolledChange],
  );

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const updatePinnedState = () => {
      const distanceToBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
      pinnedToBottomRef.current = distanceToBottom <= BOTTOM_THRESHOLD_PX;
      emitScrolledState(distanceToBottom > BOTTOM_THRESHOLD_PX);
    };
    node.addEventListener("scroll", updatePinnedState, { passive: true });
    return () => node.removeEventListener("scroll", updatePinnedState);
  }, [emitScrolledState]);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinnedToBottomRef.current) scrollToBottom("auto");
    });
    observer.observe(node.firstElementChild || node);
    return () => observer.disconnect();
  }, [scrollToBottom]);

  const renderRun = (run: ConversationRun) => {
    const runItems = itemsByRunId.get(run.id) || [];
    return (
      <AgentTimeline
        run={run}
        items={runItems}
        artifacts={artifactsByRunId.get(run.id) || []}
        onOpenSqlConsole={onOpenSqlConsole}
        onSelectArtifact={onSelectArtifact}
        resolvingQuestionId={resolvingQuestionId}
        questionError={questionError}
        onResolveQuestion={onResolveQuestion}
      />
    );
  };

  return (
    <div className="conv-message-scroll" ref={ref}>
      <div
        className={`conv-message-column ${shouldVirtualize ? "is-virtualized" : ""}`}
        data-virtual-layout={shouldVirtualize ? virtualLayoutId : undefined}
      >
        {shouldVirtualize
          ? virtualRuns.map((virtualRun) => {
              const run = orderedRuns[virtualRun.index];
              return (
                <div
                  key={run.id}
                  className="conv-message-virtual-row"
                  data-index={virtualRun.index}
                  data-virtual-layout={virtualLayoutId}
                  ref={virtualizer.measureElement}
                >
                  {renderRun(run)}
                </div>
              );
            })
          : orderedRuns.map((run) => <div key={run.id}>{renderRun(run)}</div>)}
      </div>
    </div>
  );
}

function groupByRun(items: ConversationRunItem[]): Map<string, ConversationRunItem[]> {
  const grouped = new Map<string, ConversationRunItem[]>();
  for (const item of items) {
    const runItems = grouped.get(item.run_id);
    if (runItems) runItems.push(item);
    else grouped.set(item.run_id, [item]);
  }
  for (const values of grouped.values()) {
    values.sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id));
  }
  return grouped;
}

function groupArtifactsByRun(
  artifacts: ConversationArtifact[],
): Map<string, ConversationArtifact[]> {
  const grouped = new Map<string, ConversationArtifact[]>();
  for (const artifact of artifacts) {
    const runArtifacts = grouped.get(artifact.run_id);
    if (runArtifacts) runArtifacts.push(artifact);
    else grouped.set(artifact.run_id, [artifact]);
  }
  return grouped;
}

function itemTextLength(item: ConversationRunItem): number {
  if (item.type === "message") return item.payload.content.length;
  if (item.type === "function_call_output") return item.payload.summary.length;
  return 0;
}
