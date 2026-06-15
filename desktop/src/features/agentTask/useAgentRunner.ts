import { useCallback, useEffect, useRef } from "react";
import type { Conversation, ConversationMessage } from "../../types/conversation";
import type { WorkspaceTab } from "../../mock/databoxMock";
import type { AgentArtifact as ApiAgentArtifact, AgentRunResponse, AgentRuntimeEvent } from "../../lib/api/types";
import { BASE_URL, ENGINE_TOKEN } from "../../lib/api/client";
import { agentApi, mergeArtifactDelta, resolveAgentApproval, streamResumeAgentRun } from "../../lib/api/agent";
import { getStoredApiConfig } from "../../components/SettingsDialog";
import { appendAgentRuntimeEvent, createInitialAgentTimeline, timelineFromFinalResponse, type AgentTimelineItem } from "../workspace/agentTimeline";
import {
  buildAnswerText,
  buildSuggestionsText,
  describeRuntimeEvent,
  mergeApiArtifacts,
  toViewArtifacts,
} from "../workspace/agentBridge";

type ChatMessages = NonNullable<WorkspaceTab["chatMessages"]>;
type TimelineItems = NonNullable<WorkspaceTab["agentTimeline"]>;

type UseAgentRunnerOptions = {
  tabs: WorkspaceTab[];
  conversations: Conversation[];
  activeDatasourceId: string;
  contextTables: string[];
  appendTabMessages: (tabId: string, messages: ChatMessages) => void;
  updateTabMessage: (tabId: string, messageId: number, text: string) => void;
  patchTab: (tabId: string, patch: Partial<WorkspaceTab>) => void;
  patchTabTimeline: (tabId: string, updater: (items: TimelineItems) => TimelineItems) => void;
  persistConversation: (conversation: Conversation) => Promise<void>;
  showToast: (message: string) => void;
  nextMsgId: () => number;
};

export function useAgentRunner({
  tabs,
  conversations,
  activeDatasourceId,
  contextTables,
  appendTabMessages,
  updateTabMessage,
  patchTab,
  patchTabTimeline,
  persistConversation,
  showToast,
  nextMsgId,
}: UseAgentRunnerOptions) {
  const tabsRef = useRef<WorkspaceTab[]>(tabs);
  const conversationsRef = useRef<Conversation[]>(conversations);
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  const runIdsRef = useRef<Map<string, string>>(new Map());
  const cancelledTabsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    tabsRef.current = tabs;
  }, [tabs]);

  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  // Defers persistence to the next event-loop tick so that the tab ref
  // (updated via useEffect after render) reflects the latest state.
  const scheduleAfterStateFlush = (callback: () => void) => {
    window.setTimeout(callback, 0);
  };

  const persistTabConversation = useCallback((tabId: string) => {
    scheduleAfterStateFlush(() => {
      const tab = tabsRef.current.find((item) => item.id === tabId);
      if (!tab?.conversationId) return;
      const origin = conversationsRef.current.find((item) => item.id === tab.conversationId);
      const now = Date.now();
      void persistConversation({
        id: tab.conversationId,
        title: origin?.title || tab.queryText || "未命名问答",
        createdAt: origin?.createdAt || now,
        updatedAt: now,
        contextTables: origin?.contextTables || contextTables,
        messages: tabMessagesToConversationMessages(tab.chatMessages || []),
        artifacts: tab.artifacts || [],
      });
    });
  }, [contextTables, persistConversation]);

  const makeAgentEventHandler = useCallback((
    tabId: string,
    progressId: number,
    artifactsBox: { list: ApiAgentArtifact[] },
    timelineBox: { list: AgentTimelineItem[] },
  ) => {
    return (event: AgentRuntimeEvent) => {
      // Capture run_id from the first event so cancel can reach the backend
      if (event.run_id && !runIdsRef.current.has(tabId)) {
        runIdsRef.current.set(tabId, event.run_id);
      }
      timelineBox.list = appendAgentRuntimeEvent(timelineBox.list, event);
      patchTabTimeline(tabId, () => timelineBox.list);
      const progressText = describeRuntimeEvent(event);
      if (progressText) updateTabMessage(tabId, progressId, progressText);
      if (event.type === "agent.artifact.created" && event.artifact) {
        artifactsBox.list = mergeApiArtifacts(artifactsBox.list, [event.artifact]);
        patchTab(tabId, { artifacts: toViewArtifacts(artifactsBox.list) });
      }
      if (event.type === "agent.artifact.delta" && event.artifact_delta) {
        const delta = event.artifact_delta as { artifact_id?: string; payload_merge?: Record<string, unknown> };
        const artifactId = delta.artifact_id;
        const payloadMerge = delta.payload_merge;
        if (artifactId && payloadMerge) {
          artifactsBox.list = mergeArtifactDelta(artifactsBox.list, artifactId, payloadMerge);
          patchTab(tabId, { artifacts: toViewArtifacts(artifactsBox.list) });
        }
      }
    };
  }, [patchTab, patchTabTimeline, updateTabMessage]);

  const finishAgentRun = useCallback((
    tabId: string,
    progressId: number,
    response: AgentRunResponse,
    apiArtifacts: ApiAgentArtifact[],
    timelineItems?: AgentTimelineItem[],
  ) => {
    if (response.run_id) {
      runIdsRef.current.set(tabId, response.run_id);
    }
    const merged = mergeApiArtifacts(apiArtifacts, response.artifacts || []);
    const viewArtifacts = toViewArtifacts(merged);
    const finalTimeline = timelineFromFinalResponse(
      timelineItems || tabsRef.current.find((item) => item.id === tabId)?.agentTimeline || [],
      response,
    );

    if (response.status === "waiting_approval") {
      const approval = response.approval;
      const requestedAction = (approval?.requested_action || {}) as { args?: { sql?: unknown } };
      const approvalSql = typeof requestedAction.args?.sql === "string" ? requestedAction.args.sql : response.sql || undefined;
      updateTabMessage(tabId, progressId, "该操作存在风险，需要你确认后才会继续执行。请在下方审批卡片中选择。");
      patchTab(tabId, {
        artifacts: viewArtifacts,
        agentTimeline: finalTimeline,
        agentRunId: response.run_id,
        agentSessionId: response.session_id,
        agentStatus: "waiting_approval",
        agentApproval: approval
          ? {
              runId: response.run_id,
              approvalId: approval.id,
              stepName: approval.step_name,
              riskLevel: approval.risk_level,
              reason: approval.reason || undefined,
              sql: approvalSql,
            }
          : null,
      });
      return;
    }

    const succeeded = response.success || response.status === "success" || response.status === "completed";
    updateTabMessage(
      tabId,
      progressId,
      succeeded ? buildAnswerText(response.answer, response.explanation) : `执行未完成：${response.error || "Agent 已停止。"}`,
    );
    const suggestionText = buildSuggestionsText(response.suggestions);
    if (succeeded && suggestionText) {
      appendTabMessages(tabId, [{ id: nextMsgId(), sender: "ai", text: suggestionText }]);
    }
    patchTab(tabId, {
      artifacts: viewArtifacts,
      agentTimeline: finalTimeline,
      agentRunId: response.run_id,
      agentSessionId: response.session_id,
      agentStatus: succeeded ? "completed" : "failed",
      agentApproval: null,
      agentAnswer: response.answer || null,
      agentSuggestions: response.suggestions || null,
    });
    persistTabConversation(tabId);
  }, [appendTabMessages, nextMsgId, patchTab, persistTabConversation, updateTabMessage]);

  const runAgentForTab = useCallback(async (
    tabId: string,
    question: string,
    opts?: { sessionId?: string; parentRunId?: string },
  ) => {
    if (!activeDatasourceId) {
      appendTabMessages(tabId, [{ id: nextMsgId(), sender: "ai", text: "请先在左侧选择并连接一个数据源，然后重试。" }]);
      patchTab(tabId, { agentStatus: "failed" });
      persistTabConversation(tabId);
      return;
    }
    const llm = getStoredApiConfig();
    if (!llm.apiKey?.trim()) {
      appendTabMessages(tabId, [{
        id: nextMsgId(),
        sender: "ai",
        text: "请先在右上角「设置 → LLM 配置」中填写 API Key 与模型，保存后重试。",
      }]);
      patchTab(tabId, { agentStatus: "failed" });
      persistTabConversation(tabId);
      return;
    }
    const progressId = nextMsgId();
    appendTabMessages(tabId, [{ id: progressId, sender: "ai", text: "思考中…" }]);
    patchTab(tabId, {
      agentStatus: "running",
      agentApproval: null,
      agentTimeline: createInitialAgentTimeline(question),
    });

    const artifactsBox: { list: ApiAgentArtifact[] } = { list: [] };
    const timelineBox = { list: createInitialAgentTimeline(question) };
    const abortController = new AbortController();
    abortControllersRef.current.set(tabId, abortController);
    const timeoutId = window.setTimeout(() => abortController.abort(), 300_000);
    try {
      const response = await agentApi.streamAgentQuery(
        activeDatasourceId,
        question,
        {
          apiKey: llm.apiKey || undefined,
          apiBase: llm.apiBase || undefined,
          model: llm.modelName || undefined,
          sessionId: opts?.sessionId,
          parentRunId: opts?.parentRunId,
          workspaceContext: { datasource_id: activeDatasourceId, selected_table_names: contextTables },
          execute: true,
        },
        { signal: abortController.signal, onEvent: makeAgentEventHandler(tabId, progressId, artifactsBox, timelineBox) },
      );
      finishAgentRun(tabId, progressId, response, artifactsBox.list, timelineBox.list);
    } catch (err) {
      const cancelled = cancelledTabsRef.current.has(tabId);
      cancelledTabsRef.current.delete(tabId);
      updateTabMessage(tabId, progressId, `执行失败：${formatAgentError(err, cancelled)}`);
      patchTab(tabId, { agentStatus: "failed", agentApproval: null });
      persistTabConversation(tabId);
    } finally {
      window.clearTimeout(timeoutId);
      abortControllersRef.current.delete(tabId);
    }
  }, [
    activeDatasourceId,
    appendTabMessages,
    contextTables,
    finishAgentRun,
    makeAgentEventHandler,
    nextMsgId,
    patchTab,
    persistTabConversation,
    updateTabMessage,
  ]);

  const handleApprovalDecision = useCallback(async (tabId: string, approve: boolean) => {
    const tab = tabsRef.current.find((item) => item.id === tabId);
    const approval = tab?.agentApproval;
    if (!approval) return;

    patchTab(tabId, { agentApproval: null, agentStatus: approve ? "running" : "failed" });
    const progressId = nextMsgId();
    appendTabMessages(tabId, [{ id: progressId, sender: "ai", text: approve ? "已确认，正在生成回答…" : "已拒绝执行操作。" }]);

    let timeoutId: number | undefined;
    try {
      await resolveAgentApproval(
        approval.runId,
        approval.approvalId,
        approve ? "approved" : "rejected",
        approve ? "Approved in DataBox UI" : "Rejected in DataBox UI",
      );
      if (!approve) {
        persistTabConversation(tabId);
        return;
      }
      const artifactsBox: { list: ApiAgentArtifact[] } = { list: [] };
      const timelineBox = { list: tab.agentTimeline || [] };
      const abortController = new AbortController();
      abortControllersRef.current.set(tabId, abortController);
      timeoutId = window.setTimeout(() => abortController.abort(), 300_000);
      const response = await streamResumeAgentRun(approval.runId, approval.approvalId, {
        signal: abortController.signal,
        onEvent: makeAgentEventHandler(tabId, progressId, artifactsBox, timelineBox),
      });
      finishAgentRun(tabId, progressId, response, artifactsBox.list, timelineBox.list);
    } catch (err) {
      const message = err instanceof Error ? formatAgentError(err, cancelledTabsRef.current.has(tabId)) : "审批处理失败";
      cancelledTabsRef.current.delete(tabId);
      updateTabMessage(tabId, progressId, `审批处理失败：${message}`);
      patchTab(tabId, { agentStatus: "failed" });
    } finally {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      abortControllersRef.current.delete(tabId);
    }
  }, [appendTabMessages, finishAgentRun, makeAgentEventHandler, nextMsgId, patchTab, persistTabConversation, updateTabMessage]);

  const sendFollowUp = useCallback((tabId: string, text: string) => {
    const content = text.trim();
    if (!content) return;
    const targetTab = tabsRef.current.find((tab) => tab.id === tabId);
    if (targetTab?.agentStatus === "running") {
      showToast("AI 正在生成回答，请稍候");
      return;
    }
    if (targetTab?.agentStatus === "waiting_approval") {
      showToast("请先处理待审批的操作");
      return;
    }
    appendTabMessages(tabId, [{ id: nextMsgId(), sender: "user", text: content }]);
    void runAgentForTab(tabId, content, {
      sessionId: targetTab?.agentSessionId,
      parentRunId: targetTab?.agentRunId,
    });
  }, [appendTabMessages, nextMsgId, runAgentForTab, showToast]);

  const cancelAgentRun = useCallback(async (tabId: string) => {
    // 1. Abort the in-flight fetch immediately — unblocks the UI
    cancelledTabsRef.current.add(tabId);
    const ctrl = abortControllersRef.current.get(tabId);
    if (ctrl) {
      ctrl.abort();
      abortControllersRef.current.delete(tabId);
    }
    // 2. Best-effort backend cancellation (run_id captured from first SSE event)
    const runId = runIdsRef.current.get(tabId);
    if (runId) {
      runIdsRef.current.delete(tabId);
      try {
        await fetch(`${BASE_URL}/agent/runs/${encodeURIComponent(runId)}/cancel`, {
          method: "POST",
          headers: { "X-Local-Token": ENGINE_TOKEN },
        });
      } catch {
        // best-effort; local state already reflects cancellation
      }
    }
    // 3. Update UI regardless of whether we had a run_id
    const lastMsg = tabsRef.current.find((t) => t.id === tabId)?.chatMessages?.slice(-1)?.[0];
    if (lastMsg) {
      updateTabMessage(tabId, lastMsg.id, "已取消。");
    }
    patchTab(tabId, { agentStatus: "failed", agentApproval: null });
    persistTabConversation(tabId);
  }, [patchTab, persistTabConversation, updateTabMessage]);

  const regenerateAgentRun = useCallback((tabId: string) => {
    const targetTab = tabsRef.current.find((tab) => tab.id === tabId);
    if (!targetTab) return;
    const originalQuestion = targetTab.queryText || targetTab.chatMessages?.find((message) => message.sender === "user")?.text || "";
    if (!originalQuestion) return;
    void runAgentForTab(tabId, originalQuestion, {
      sessionId: targetTab.agentSessionId,
      parentRunId: targetTab.agentRunId,
    });
  }, [runAgentForTab]);

  return {
    runAgentForTab,
    handleApprovalDecision,
    sendFollowUp,
    cancelAgentRun,
    regenerateAgentRun,
  };
}

function formatAgentError(err: unknown, cancelled = false): string {
  if (!(err instanceof Error)) return "AI 分析失败";
  const coded = err as Error & { code?: string };
  if (coded.code === "NO_LLM_KEY") {
    return "请先在右上角「设置 → LLM 配置」中填写 API Key 与模型，保存后重试。";
  }
  if (err.name === "AbortError") {
    return cancelled ? "已取消。" : "请求超时：LLM 响应过慢或网络异常，请检查 API Key、模型与网络后重试。";
  }
  return err.message.replace(/agent\s*runtime\s*failed:?/i, "服务请求出错:");
}

function tabMessagesToConversationMessages(messages: ChatMessages): ConversationMessage[] {
  return messages.map((message, index) => ({
    id: `message-${message.id || index}`,
    role: message.sender === "user" ? "user" : "assistant",
    content: message.text,
    createdAt: Number(message.id) || Date.now(),
  }));
}
