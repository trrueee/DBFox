import { create } from "zustand";
import { useWorkspaceStore } from "./workspaceStore";
import { useDatasourceStore } from "./datasourceStore";
import { BASE_URL, ENGINE_TOKEN } from "../lib/api/client";
import {
  agentApi,
  mergeArtifactDelta,
  resolveAgentApproval,
  streamResumeAgentRun,
} from "../lib/api/agent";
import { getStoredApiConfig } from "../components/SettingsDialog";
import {
  appendAgentRuntimeEvent,
  createInitialAgentTimeline,
  timelineFromFinalResponse,
  type AgentTimelineItem,
} from "../features/workspace/agentTimeline";
import {
  buildAnswerText,
  buildSuggestionsText,
  describeRuntimeEvent,
  mergeApiArtifacts,
  toViewArtifacts,
} from "../features/workspace/agentBridge";
import type {
  AgentRunResponse,
  AgentRuntimeEvent,
  AgentArtifact as ApiAgentArtifact,
} from "../lib/api/types";

interface AgentState {
  _abortControllers: Map<string, AbortController>;
  _runIds: Map<string, string>;
  _cancelledTabs: Set<string>;
}

interface AgentActions {
  runAgentForTab: (
    tabId: string,
    question: string,
    opts?: { sessionId?: string; parentRunId?: string },
  ) => Promise<void>;
  handleApprovalDecision: (tabId: string, approved: boolean) => Promise<void>;
  sendFollowUp: (tabId: string, text: string) => void;
  cancelAgentRun: (tabId: string) => Promise<void>;
  regenerateAgentRun: (tabId: string) => void;
}

export type AgentStore = AgentState & AgentActions;

export const useAgentStore = create<AgentStore>()((set, get) => ({
  _abortControllers: new Map(),
  _runIds: new Map(),
  _cancelledTabs: new Set(),

  runAgentForTab: async (tabId, question, opts) => {
    const ws = useWorkspaceStore.getState();
    const ds = useDatasourceStore.getState();

    if (!ds.activeDatasourceId) {
      ws.appendTabMessages(tabId, [
        {
          id: ws._nextMsgId(),
          sender: "ai",
          text: "请先在左侧选择并连接一个数据源，然后重试。",
        },
      ]);
      ws.patchTab(tabId, { agentStatus: "failed" });
      ws.persistConversation({
        id: ws.tabs.find((t) => t.id === tabId)?.conversationId || `conv-${Date.now()}`,
        title: question,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        contextTables: ws.contextTables,
        messages: [],
        artifacts: [],
      });
      return;
    }

    const llm = getStoredApiConfig();
    if (!llm.apiKey?.trim()) {
      ws.appendTabMessages(tabId, [
        {
          id: ws._nextMsgId(),
          sender: "ai",
          text: "请先在右上角「设置 → LLM 配置」中填写 API Key 与模型，保存后重试。",
        },
      ]);
      ws.patchTab(tabId, { agentStatus: "failed" });
      return;
    }

    const progressId = ws._nextMsgId();
    ws.appendTabMessages(tabId, [{ id: progressId, sender: "ai", text: "思考中…" }]);
    ws.patchTab(tabId, {
      agentStatus: "running",
      agentApproval: null,
      agentTimeline: createInitialAgentTimeline(question),
      agentAnswer: null,
      agentSuggestions: null,
      artifacts: [],
    });

    const artifactsBox: { list: ApiAgentArtifact[] } = { list: [] };
    const timelineBox = { list: createInitialAgentTimeline(question) };
    const abortController = new AbortController();
    get()._abortControllers.set(tabId, abortController);
    const timeoutId = window.setTimeout(() => abortController.abort(), 300_000);

    try {
      const response = await agentApi.streamAgentQuery(
        ds.activeDatasourceId,
        question,
        {
          apiKey: llm.apiKey || undefined,
          apiBase: llm.apiBase || undefined,
          model: llm.modelName || undefined,
          sessionId: opts?.sessionId,
          parentRunId: opts?.parentRunId,
          workspaceContext: {
            datasource_id: ds.activeDatasourceId,
            selected_table_names: ws.contextTables,
          },
          execute: true,
        },
        {
          signal: abortController.signal,
          onEvent: makeAgentEventHandler(tabId, progressId, artifactsBox, timelineBox),
        },
      );
      finishAgentRun(tabId, progressId, response, artifactsBox.list, timelineBox.list);
    } catch (err) {
      const cancelled = get()._cancelledTabs.has(tabId);
      get()._cancelledTabs.delete(tabId);
      const ws2 = useWorkspaceStore.getState();
      ws2.updateTabMessage(tabId, progressId, `执行失败：${formatAgentError(err, cancelled)}`);
      ws2.patchTab(tabId, { agentStatus: "failed", agentApproval: null });
    } finally {
      window.clearTimeout(timeoutId);
      get()._abortControllers.delete(tabId);
    }
  },

  handleApprovalDecision: async (tabId, approved) => {
    const ws = useWorkspaceStore.getState();
    const tab = ws.tabs.find((t) => t.id === tabId);
    const approval = tab?.agentApproval;
    if (!approval) return;

    ws.patchTab(tabId, {
      agentApproval: null,
      agentStatus: approved ? "running" : "failed",
    });
    const progressId = ws._nextMsgId();
    ws.appendTabMessages(tabId, [
      {
        id: progressId,
        sender: "ai",
        text: approved ? "已确认，正在生成回答…" : "已拒绝执行操作。",
      },
    ]);

    let timeoutId: number | undefined;
    try {
      await resolveAgentApproval(
        approval.runId,
        approval.approvalId,
        approved ? "approved" : "rejected",
        approved ? "Approved in DBFox UI" : "Rejected in DBFox UI",
      );
      if (!approved) return;

      const artifactsBox: { list: ApiAgentArtifact[] } = { list: [] };
      const timelineBox = { list: tab.agentTimeline || [] };
      const abortController = new AbortController();
      get()._abortControllers.set(tabId, abortController);
      timeoutId = window.setTimeout(() => abortController.abort(), 300_000);
      const response = await streamResumeAgentRun(approval.runId, approval.approvalId, {
        signal: abortController.signal,
        onEvent: makeAgentEventHandler(tabId, progressId, artifactsBox, timelineBox),
      });
      finishAgentRun(tabId, progressId, response, artifactsBox.list, timelineBox.list);
    } catch (err) {
      const ws3 = useWorkspaceStore.getState();
      const message =
        err instanceof Error ? formatAgentError(err, get()._cancelledTabs.has(tabId)) : "审批处理失败";
      get()._cancelledTabs.delete(tabId);
      ws3.updateTabMessage(tabId, progressId, `审批处理失败：${message}`);
      ws3.patchTab(tabId, { agentStatus: "failed" });
    } finally {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      get()._abortControllers.delete(tabId);
    }
  },

  sendFollowUp: (tabId, text) => {
    const content = text.trim();
    if (!content) return;
    const ws = useWorkspaceStore.getState();
    const targetTab = ws.tabs.find((t) => t.id === tabId);
    if (targetTab?.agentStatus === "running" || targetTab?.agentStatus === "waiting_approval") return;
    ws.appendTabMessages(tabId, [{ id: ws._nextMsgId(), sender: "user", text: content }]);
    void get().runAgentForTab(tabId, content, {
      sessionId: targetTab?.agentSessionId,
      parentRunId: targetTab?.agentRunId,
    });
  },

  cancelAgentRun: async (tabId) => {
    get()._cancelledTabs.add(tabId);
    const ctrl = get()._abortControllers.get(tabId);
    if (ctrl) {
      ctrl.abort();
      get()._abortControllers.delete(tabId);
    }
    const runId = get()._runIds.get(tabId);
    if (runId) {
      get()._runIds.delete(tabId);
      try {
        await fetch(`${BASE_URL}/agent/runs/${encodeURIComponent(runId)}/cancel`, {
          method: "POST",
          headers: { "X-Local-Token": ENGINE_TOKEN },
        });
      } catch {
        // best-effort
      }
    }
    const ws = useWorkspaceStore.getState();
    const lastMsg = ws.tabs.find((t) => t.id === tabId)?.chatMessages?.slice(-1)?.[0];
    if (lastMsg) ws.updateTabMessage(tabId, lastMsg.id, "已取消。");
    ws.patchTab(tabId, { agentStatus: "failed", agentApproval: null });
  },

  regenerateAgentRun: (tabId) => {
    const ws = useWorkspaceStore.getState();
    const targetTab = ws.tabs.find((t) => t.id === tabId);
    if (!targetTab) return;
    const originalQuestion =
      targetTab.queryText ||
      targetTab.chatMessages?.find((m) => m.sender === "user")?.text ||
      "";
    if (!originalQuestion) return;
    void get().runAgentForTab(tabId, originalQuestion, {
      sessionId: targetTab.agentSessionId,
      parentRunId: targetTab.agentRunId,
    });
  },
}));

// --- Internal helpers (extracted from useAgentRunner) ---

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

function makeAgentEventHandler(
  tabId: string,
  progressId: number,
  artifactsBox: { list: ApiAgentArtifact[] },
  timelineBox: { list: AgentTimelineItem[] },
): (event: AgentRuntimeEvent) => void {
  const store = useAgentStore;
  const ws = () => useWorkspaceStore.getState();

  return (event: AgentRuntimeEvent) => {
    if (event.run_id && !store.getState()._runIds.has(tabId)) {
      store.getState()._runIds.set(tabId, event.run_id);
    }
    timelineBox.list = appendAgentRuntimeEvent(timelineBox.list, event);
    ws().patchTabTimeline(tabId, () => timelineBox.list);
    const progressText = describeRuntimeEvent(event);
    if (progressText) ws().updateTabMessage(tabId, progressId, progressText);
    if (event.type === "agent.artifact.created" && event.artifact) {
      artifactsBox.list = mergeApiArtifacts(artifactsBox.list, [event.artifact]);
      ws().patchTab(tabId, { artifacts: toViewArtifacts(artifactsBox.list) });
    }
    if (event.type === "agent.artifact.delta" && event.artifact_delta) {
      const delta = event.artifact_delta as {
        artifact_id?: string;
        payload_merge?: Record<string, unknown>;
      };
      if (delta.artifact_id && delta.payload_merge) {
        artifactsBox.list = mergeArtifactDelta(
          artifactsBox.list,
          delta.artifact_id,
          delta.payload_merge,
        );
        ws().patchTab(tabId, { artifacts: toViewArtifacts(artifactsBox.list) });
      }
    }
  };
}

function finishAgentRun(
  tabId: string,
  progressId: number,
  response: AgentRunResponse,
  apiArtifacts: ApiAgentArtifact[],
  timelineItems?: AgentTimelineItem[],
) {
  const ws = useWorkspaceStore.getState();

  if (response.run_id) {
    useAgentStore.getState()._runIds.set(tabId, response.run_id);
  }

  const merged = mergeApiArtifacts(apiArtifacts, response.artifacts || []);
  const viewArtifacts = toViewArtifacts(merged);
  const tab = ws.tabs.find((t) => t.id === tabId);
  const finalTimeline = timelineFromFinalResponse(
    timelineItems || tab?.agentTimeline || [],
    response,
  );

  if (response.status === "waiting_approval") {
    const approval = response.approval;
    const requestedAction = (approval?.requested_action || {}) as { args?: { sql?: unknown } };
    const approvalSql =
      typeof requestedAction.args?.sql === "string"
        ? requestedAction.args.sql
        : response.sql || undefined;
    ws.updateTabMessage(
      tabId,
      progressId,
      "该操作存在风险，需要你确认后才会继续执行。请在下方审批卡片中选择。",
    );
    ws.patchTab(tabId, {
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

  const succeeded =
    response.success || response.status === "success" || response.status === "completed";
  ws.updateTabMessage(
    tabId,
    progressId,
    succeeded
      ? buildAnswerText(response.answer, response.explanation)
      : `执行未完成：${response.error || "Agent 已停止。"}`,
  );
  const suggestionText = buildSuggestionsText(response.suggestions);
  if (succeeded && suggestionText) {
    ws.appendTabMessages(tabId, [{ id: ws._nextMsgId(), sender: "ai", text: suggestionText }]);
  }
  ws.patchTab(tabId, {
    artifacts: viewArtifacts,
    agentTimeline: finalTimeline,
    agentRunId: response.run_id,
    agentSessionId: response.session_id,
    agentStatus: succeeded ? "completed" : "failed",
    agentApproval: null,
    agentAnswer: response.answer || null,
    agentSuggestions: response.suggestions || null,
  });
}
