import { useCallback, useEffect, useId, useInsertionEffect, useMemo, useRef, useState } from "react";
import { ArrowDownIcon } from "@/components/icons";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Button, ErrorDetails } from "../../../components/ui";
import { clearCspVirtualLayout, setCspVirtualLayout } from "../../../lib/cspVirtualLayout";
import { getUserErrorMessage } from "../../../lib/api/client";
import type {
  ConversationArtifact,
  ConversationEvidence,
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
  hasOlderHistory?: boolean;
  loadingOlderHistory?: boolean;
  olderHistoryLoaded?: boolean;
  historyLoadError?: unknown;
  onLoadOlderHistory?: () => Promise<unknown> | void;
  onOpenSqlConsole?: (sql?: string) => void;
  onSelectArtifact?: (artifactId: string) => void;
  onOpenEvidence?: (evidence: ConversationEvidence) => void;
  pinnedActionId?: string;
  onFocusAction?: () => void;
  resolvingQuestionId?: string | null;
  questionError?: unknown;
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
  hasOlderHistory = false,
  loadingOlderHistory = false,
  olderHistoryLoaded = false,
  historyLoadError,
  onLoadOlderHistory,
  onOpenSqlConsole,
  onSelectArtifact,
  onOpenEvidence,
  pinnedActionId,
  onFocusAction,
  resolvingQuestionId,
  questionError,
  onResolveQuestion,
  onScrolledChange,
}: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  const columnRef = useRef<HTMLDivElement>(null);
  const virtualLayoutId = `messages-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const pinnedToBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);
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
    anchorTo: "end",
    followOnAppend: "auto",
    scrollEndThreshold: BOTTOM_THRESHOLD_PX,
    useFlushSync: false,
  });
  const virtualRuns = virtualizer.getVirtualItems();
  const historyStatusId = `${virtualLayoutId}-history-status`;
  const showHistoryControl = hasOlderHistory || Boolean(historyLoadError) || olderHistoryLoaded;

  // CSSOM sizing must land before TanStack Virtual's layout effect synchronizes
  // an end-anchored prepend to the browser scroll position.
  useInsertionEffect(() => {
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
      virtualizer.scrollToEnd({ behavior });
    } else if (typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior });
    } else {
      node.scrollTop = node.scrollHeight;
    }
  }, [orderedRuns.length, shouldVirtualize, virtualizer]);

  useEffect(() => {
    if (!pinnedToBottomRef.current) return;
    const frame = requestAnimationFrame(() => scrollToBottom("auto"));
    return () => cancelAnimationFrame(frame);
  }, [artifacts.length, latestRenderKey, orderedRuns.length, scrollToBottom]);

  const emitScrolledState = useCallback(
    (scrolled: boolean) => {
      if (scrolledStateRef.current === scrolled) return;
      scrolledStateRef.current = scrolled;
      setShowJump(scrolled);
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
      else emitScrolledState(node.scrollHeight - node.scrollTop - node.clientHeight > BOTTOM_THRESHOLD_PX);
    });
    observer.observe(node);
    if (columnRef.current) observer.observe(columnRef.current);
    return () => observer.disconnect();
  }, [scrollToBottom, emitScrolledState]);

  const renderRun = (run: ConversationRun) => {
    const runItems = itemsByRunId.get(run.id) || [];
    return (
      <AgentTimeline
        run={run}
        items={runItems}
        artifacts={artifactsByRunId.get(run.id) || []}
        onOpenSqlConsole={onOpenSqlConsole}
        onSelectArtifact={onSelectArtifact ? artifactId => {
          pinnedToBottomRef.current = false;
          onSelectArtifact(artifactId);
        } : undefined}
        onOpenEvidence={onOpenEvidence ? evidence => {
          pinnedToBottomRef.current = false;
          onOpenEvidence(evidence);
        } : undefined}
        pinnedActionId={pinnedActionId}
        onFocusAction={onFocusAction}
        resolvingQuestionId={resolvingQuestionId}
        questionError={questionError}
        onResolveQuestion={onResolveQuestion}
      />
    );
  };

  return (
    <div className="conv-message-list">
    <div className="conv-message-scroll" ref={ref}>
      {showHistoryControl && (
        <div className="conv-history-control">
          {hasOlderHistory || historyLoadError ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={loadingOlderHistory || !onLoadOlderHistory}
              aria-describedby={historyLoadError ? historyStatusId : undefined}
              onClick={() => {
                void Promise.resolve(onLoadOlderHistory?.()).catch(() => undefined);
              }}
            >
              {loadingOlderHistory
                ? "正在载入更早消息…"
                : historyLoadError
                  ? "重试载入更早消息"
                  : "载入更早消息"}
            </Button>
          ) : (
            <span role="status">已载入全部消息</span>
          )}
          {Boolean(historyLoadError) && (
            <div id={historyStatusId} role="alert" className="conv-history-error">
              <span>{typeof historyLoadError === "string"
                ? historyLoadError
                : getUserErrorMessage(historyLoadError, "更早的对话记录载入失败，请重试。")}</span>
              <ErrorDetails error={historyLoadError} />
            </div>
          )}
        </div>
      )}
      <div
        ref={columnRef}
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
    {showJump ? <Button type="button" variant="outline" size="sm" className="conv-jump-latest"
      onClick={() => { pinnedToBottomRef.current = true; scrollToBottom(); emitScrolledState(false); }}>
      <ArrowDownIcon size={16} aria-hidden="true" />回到最新
    </Button> : null}
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
