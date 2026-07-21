import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { clearCspVirtualLayout, setCspVirtualLayout } from "../../../lib/cspVirtualLayout";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
import type {
  ConversationArtifact,
  ConversationActivity,
  ConversationMessage,
  ConversationQuestion,
  ConversationRun,
} from "../../../types/conversation";
import { MessageBubble } from "./MessageBubble";

const VIRTUALIZE_AFTER_MESSAGES = 50;
const BOTTOM_THRESHOLD_PX = 72;

interface MessageListProps {
  messages: ConversationMessage[];
  runs: ConversationRun[];
  artifacts: ConversationArtifact[];
  activities?: ConversationActivity[];
  questions?: ConversationQuestion[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab: (artifact: ResultViewArtifact) => void;
  onSelectArtifact?: (artifactId: string) => void;
  onResolveQuestion?: (
    runId: string,
    questionId: string,
    response: { selected_value?: string; text?: string },
  ) => void;
}

export function MessageList({
  messages,
  runs,
  artifacts,
  activities = [],
  questions = [],
  onOpenSqlConsole,
  onOpenResultTab,
  onSelectArtifact,
  onResolveQuestion,
}: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  const virtualLayoutId = `messages-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const pinnedToBottomRef = useRef(true);
  const previousMessageCountRef = useRef(0);
  const shouldVirtualize = messages.length > VIRTUALIZE_AFTER_MESSAGES;
  const runsByAssistantMessageId = useMemo(
    () => new Map(runs.map((run) => [run.assistant_message_id, run])),
    [runs],
  );
  const artifactsByRunId = useMemo(() => {
    const map = new Map<string, ConversationArtifact[]>();
    for (const artifact of artifacts) {
      const key = artifact.run_id;
      const existing = map.get(key);
      if (existing) {
        existing.push(artifact);
      } else {
        map.set(key, [artifact]);
      }
    }
    return map;
  }, [artifacts]);
  const activitiesByRunId = useMemo(() => {
    const map = new Map<string, ConversationActivity[]>();
    for (const activity of activities) map.set(activity.run_id, [...(map.get(activity.run_id) || []), activity]);
    return map;
  }, [activities]);
  const questionsByRunId = useMemo(() => {
    const map = new Map<string, ConversationQuestion>();
    for (const question of questions) map.set(question.run_id, question);
    return map;
  }, [questions]);
  const latestMessageScrollKey = useMemo(() => {
    const latest = messages[messages.length - 1];
    return latest ? `${latest.id}:${latest.status}:${latest.content}` : "";
  }, [messages]);

  // TanStack Virtual intentionally exposes imperative measurement functions.
  // eslint-disable-next-line react-hooks/incompatible-library
  const messageVirtualizer = useVirtualizer({
    count: messages.length,
    enabled: shouldVirtualize,
    getScrollElement: () => ref.current,
    getItemKey: (index) => messages[index]?.id || index,
    estimateSize: () => 180,
    overscan: 6,
    initialRect: { width: 800, height: 720 },
  });
  const virtualMessages = messageVirtualizer.getVirtualItems();

  useLayoutEffect(() => {
    if (!shouldVirtualize) {
      clearCspVirtualLayout(virtualLayoutId);
      return;
    }
    setCspVirtualLayout(
      virtualLayoutId,
      messageVirtualizer.getTotalSize(),
      virtualMessages.map((item) => ({ index: item.index, start: item.start })),
    );
    return () => clearCspVirtualLayout(virtualLayoutId);
  }, [messageVirtualizer, shouldVirtualize, virtualLayoutId, virtualMessages]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const node = ref.current;
    if (!node || messages.length === 0) return;
    if (shouldVirtualize) {
      messageVirtualizer.scrollToIndex(messages.length - 1, { align: "end", behavior });
    } else {
      node.scrollTo({ top: node.scrollHeight, behavior });
    }
  }, [messageVirtualizer, messages.length, shouldVirtualize]);

  useEffect(() => {
    const addedMessage = messages.length > previousMessageCountRef.current;
    previousMessageCountRef.current = messages.length;
    if (addedMessage) pinnedToBottomRef.current = true;
    if (!pinnedToBottomRef.current) return;
    const frame = requestAnimationFrame(() => scrollToBottom(addedMessage ? "auto" : "smooth"));
    return () => cancelAnimationFrame(frame);
  }, [messages.length, artifacts.length, latestMessageScrollKey, scrollToBottom]);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const updatePinnedState = () => {
      pinnedToBottomRef.current = node.scrollHeight - node.scrollTop - node.clientHeight <= BOTTOM_THRESHOLD_PX;
    };
    node.addEventListener("scroll", updatePinnedState, { passive: true });
    return () => node.removeEventListener("scroll", updatePinnedState);
  }, []);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinnedToBottomRef.current) scrollToBottom("auto");
    });
    const content = node.firstElementChild;
    observer.observe(content || node);
    return () => observer.disconnect();
  }, [scrollToBottom]);

  const renderMessage = (message: ConversationMessage) => {
    const run = runsByAssistantMessageId.get(message.id);
    const messageArtifacts = run ? artifactsByRunId.get(run.id) || [] : [];
    const messageActivities = run ? activitiesByRunId.get(run.id) || [] : [];
    const question = run ? questionsByRunId.get(run.id) : undefined;
    return (
      <MessageBubble
        message={message}
        run={run}
        artifacts={messageArtifacts}
        activities={messageActivities}
        question={question}
        onOpenSqlConsole={onOpenSqlConsole}
        onOpenResultTab={onOpenResultTab}
        onSelectArtifact={onSelectArtifact}
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
        {shouldVirtualize ? virtualMessages.map((virtualMessage) => {
          const message = messages[virtualMessage.index];
          return (
            <div
              key={message.id}
              className="conv-message-virtual-row"
              data-index={virtualMessage.index}
              data-virtual-layout={virtualLayoutId}
              ref={messageVirtualizer.measureElement}
            >
              {renderMessage(message)}
            </div>
          );
        }) : messages.map((message) => <div key={message.id}>{renderMessage(message)}</div>)}
      </div>
    </div>
  );
}
