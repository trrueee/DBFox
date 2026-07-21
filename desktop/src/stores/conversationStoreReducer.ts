import type {
  ConversationActivity,
  ConversationArtifact,
  ConversationDetail,
  ConversationEvidence,
  ConversationMessage,
  ConversationQuestion,
  ConversationRun,
  ConversationStreamEvent,
  RuntimeEventEnvelope,
} from "../types/conversation";
import type { ConversationStore } from "./conversationStore";

export function upsertMessage(
  state: ConversationStore,
  messageId: string,
  patch: Partial<ConversationMessage>,
): ConversationStore {
  const current = state.messagesById[messageId];
  if (!current) return state;
  const next = { ...current, ...patch };
  const detail = state.detailById[current.conversation_id];
  return {
    ...state,
    messagesById: { ...state.messagesById, [messageId]: next },
    detailById: detail ? {
      ...state.detailById,
      [detail.id]: {
        ...detail,
        messages: detail.messages.map((item) => item.id === messageId ? next : item),
      },
    } : state.detailById,
  };
}

export function upsertRun(
  state: ConversationStore,
  conversationId: string,
  run: ConversationRun,
): ConversationStore {
  const detail = state.detailById[conversationId];
  return {
    ...state,
    runsById: { ...state.runsById, [run.id]: run },
    detailById: detail ? {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        runs: detail.runs.some((item) => item.id === run.id)
          ? detail.runs.map((item) => item.id === run.id ? run : item)
          : [...detail.runs, run],
      },
    } : state.detailById,
  };
}

export function reduceStreamEvent(state: ConversationStore, envelope: ConversationStreamEvent): ConversationStore {
  if (envelope.kind === "delta") return reduceLiveDelta(state, envelope.delta);
  return reduceCommittedEvent(state, envelope.event);
}

function reduceLiveDelta(
  state: ConversationStore,
  delta: Extract<ConversationStreamEvent, { kind: "delta" }>["delta"],
): ConversationStore {
  const currentRevision = state.liveRevisionById[delta.live_id] || 0;
  if (delta.operation === "replace") {
    if (delta.channel_revision < currentRevision) return state;
  } else if (delta.channel_revision !== currentRevision + 1) {
    return state;
  }
  state = {
    ...state,
    liveRevisionById: {
      ...state.liveRevisionById,
      [delta.live_id]: delta.channel_revision,
    },
  };
  const run = state.runsById[delta.run_id];
  if (!run) return state;
  if (delta.channel === "answer") {
    if (!run.assistant_message_id || delta.correlation_id !== run.assistant_message_id) return state;
    const current = state.messagesById[delta.correlation_id];
    if (!current) return state;
    return upsertMessage(state, current.id, {
      content: delta.operation === "replace" ? delta.content : current.content + delta.content,
      status: "streaming",
    });
  }
  if (delta.channel === "reasoning_summary") {
    return upsertActivity(state, run.conversation_id, {
      id: delta.correlation_id,
      run_id: delta.run_id,
      turn_id: delta.turn_id,
      kind: "analysis",
      title: "正在理解问题并规划分析",
      summary: delta.content,
      status: "running",
    }, false, delta.operation === "append");
  }
  if (delta.channel === "tool_progress") {
    const current = state.detailById[run.conversation_id]?.activities
      ?.findLast((item) => item.run_id === run.id && item.kind === "tool" && item.status === "running");
    return current ? upsertActivity(state, run.conversation_id, {
      ...current,
      summary: delta.content,
    }, false, delta.operation === "append") : state;
  }
  return state;
}

function reduceCommittedEvent(state: ConversationStore, event: RuntimeEventEnvelope): ConversationStore {
  const detail = state.detailById[event.session_id];
  if (!detail || event.sequence <= (detail.cursor || 0)) return state;
  let next = withCursor(state, detail, event.sequence);
  const run = event.run_id ? next.runsById[event.run_id] : undefined;
  const payload = event.payload;

  if (["run.created", "run.started", "run.cancelling"].includes(event.event_type) && run) {
    const status = event.event_type === "run.created"
      ? "queued"
      : event.event_type === "run.cancelling" ? "cancelling" : "running";
    next = upsertRun(next, event.session_id, {
      ...run,
      status,
      cancel_requested: event.event_type === "run.cancelling" ? true : run.cancel_requested,
      version: numberAt(payload, ["run", "version"], run.version || 0),
    });
  }
  if (event.event_type === "turn.started" && event.turn_id && event.run_id) {
    next = upsertActivity(next, event.session_id, {
      id: `activity:${event.turn_id}:analysis`,
      run_id: event.run_id,
      turn_id: event.turn_id,
      kind: "analysis",
      title: "正在理解问题并规划分析",
      status: "running",
      artifact_ids: [],
      started_at: event.timestamp,
    });
  }
  if (["run.completed", "run.failed", "run.cancelled"].includes(event.event_type) && run) {
    const status = event.event_type.slice(4) as ConversationRun["status"];
    const error = record(payload.error);
    const projectedRun = record(payload.run);
    next = upsertRun(next, event.session_id, {
      ...run,
      status,
      version: numberAt(payload, ["run", "version"], run.version || 0),
      completion_disposition: projectedRun.completion_disposition
        ? String(projectedRun.completion_disposition) as ConversationRun["completion_disposition"]
        : run.completion_disposition,
      limitation_codes: Array.isArray(projectedRun.limitation_codes)
        ? projectedRun.limitation_codes.map(String) as NonNullable<ConversationRun["limitation_codes"]>
        : run.limitation_codes,
      error_code: error.code ? String(error.code) : run.error_code,
      error_message: error.message ? String(error.message) : run.error_message,
    });
    next = settleRunActivities(next, event.session_id, run.id, status, event.timestamp);
    if (run.assistant_message_id) {
      next = upsertMessage(next, run.assistant_message_id, {
        status: status === "completed" ? "completed" : status === "cancelled" ? "cancelled" : "failed",
      });
    }
    next = clearLiveRevisions(next, `live:${event.session_id}:${run.id}:`);
  }
  if (event.event_type === "answer.completed" && run) {
    const response = record(payload.response);
    const answer = record(response.answer);
    const text = String(answer.text || "");
    if (run.assistant_message_id) {
      next = upsertMessage(next, run.assistant_message_id, { content: text, status: "completed" });
    }
    next = upsertRun(next, event.session_id, {
      ...next.runsById[run.id],
      completion_disposition: response.completion_disposition
        ? String(response.completion_disposition) as ConversationRun["completion_disposition"]
        : null,
      limitation_codes: Array.isArray(response.limitation_codes)
        ? response.limitation_codes.map(String) as NonNullable<ConversationRun["limitation_codes"]>
        : [],
      answer: {
        answer: text,
        evidence: Array.isArray(answer.evidence) ? answer.evidence as ConversationEvidence[] : [],
        key_findings: stringList(answer.key_findings),
        caveats: Array.isArray(answer.caveats) ? answer.caveats.map(String) : [],
        recommendations: stringList(answer.recommendations),
        follow_up_questions: stringList(answer.follow_up_questions),
      },
    });
  }
  if (["artifact.created", "artifact.updated"].includes(event.event_type)) {
    const artifact = normalizeEventArtifact(record(payload.artifact), event.session_id);
    if (artifact) next = upsertArtifact(next, event.session_id, artifact);
  }
  if (event.event_type === "artifact.selected") {
    const selection = record(payload.selection);
    const selectedId = typeof selection.artifact_id === "string" ? selection.artifact_id : null;
    const current = next.detailById[event.session_id];
    next = {
      ...next,
      detailById: { ...next.detailById, [event.session_id]: { ...current, selected_artifact_id: selectedId } },
    };
  }
  if (event.event_type === "turn.completed" && event.turn_id) {
    const turn = record(payload.turn);
    const summary = typeof turn.reasoning_summary === "string" ? turn.reasoning_summary.trim() : "";
    next = upsertActivity(next, event.session_id, {
      id: `activity:${event.turn_id}:analysis`, run_id: event.run_id || "",
      turn_id: event.turn_id, kind: "analysis",
      title: Number(turn.tool_call_count || 0) > 0
        ? "已确定下一步分析动作"
        : "已完成结果分析",
      summary: summary ? summary.slice(0, 280) : null,
      status: "completed",
      artifact_ids: [],
      completed_at: event.timestamp,
    });
    next = clearLiveRevisions(next, `live:${event.session_id}:${event.run_id}:${event.turn_id}:`);
  }
  if (event.event_type === "activity.updated") {
    const activity = record(payload.activity);
    const id = String(activity.id || "");
    if (id && event.run_id && event.turn_id) {
      next = upsertActivity(next, event.session_id, {
        id,
        run_id: event.run_id,
        turn_id: event.turn_id,
        kind: String(activity.kind || "analysis"),
        title: String(activity.title || "正在继续分析"),
        summary: activity.summary ? String(activity.summary) : null,
        status: String(activity.status || "running") as ConversationActivity["status"],
        tool_invocation_id: activity.tool_invocation_id ? String(activity.tool_invocation_id) : undefined,
        artifact_ids: Array.isArray(activity.artifact_ids) ? activity.artifact_ids.map(String) : [],
        started_at: activity.started_at ? String(activity.started_at) : event.timestamp,
        completed_at: activity.completed_at ? String(activity.completed_at) : null,
      });
    }
  }
  if (event.event_type === "plan.updated") {
    const plan = record(payload.plan);
    const id = String(plan.id || "");
    if (id && event.run_id && event.turn_id) {
      const steps = Array.isArray(plan.steps) ? plan.steps.map((value) => {
        const step = record(value);
        return {
          id: String(step.id || ""),
          title: String(step.title || ""),
          status: String(step.status || "pending") as NonNullable<ConversationActivity["steps"]>[number]["status"],
          evidence_required: Boolean(step.evidence_required),
          artifact_ids: Array.isArray(step.artifact_ids) ? step.artifact_ids.map(String) : [],
          note: step.note ? String(step.note) : null,
        };
      }) : [];
      const completed = steps.filter((step) => ["completed", "skipped"].includes(step.status)).length;
      const status = String(plan.status || "active");
      next = upsertActivity(next, event.session_id, {
        id: `activity:plan:${id}`,
        run_id: event.run_id,
        turn_id: event.turn_id,
        kind: "plan",
        title: String(plan.objective || "分析计划"),
        summary: plan.summary ? String(plan.summary) : `${completed}/${steps.length} 个步骤已完成`,
        status: status === "completed" ? "completed" : status === "blocked" ? "waiting" : "running",
        artifact_ids: Array.from(new Set(steps.flatMap((step) => step.artifact_ids))),
        steps,
        current_step_id: steps.find((step) => step.status === "in_progress")?.id || null,
        started_at: plan.created_at ? String(plan.created_at) : event.timestamp,
        completed_at: status === "completed" ? String(plan.updated_at || event.timestamp) : null,
      });
    }
  }
  if (event.event_type === "tool.requested") {
    const invocation = record(payload.tool_invocation);
    const id = String(invocation.id || "");
    if (id && event.turn_id && event.run_id) {
      next = upsertActivity(next, event.session_id, {
        id: `activity:${id}`, run_id: event.run_id, turn_id: event.turn_id,
        kind: "tool", title: toolLabel(String(invocation.tool_name || "")),
        status: String(invocation.status) === "waiting_approval" ? "waiting" : "pending",
        tool_invocation_id: id,
        artifact_ids: [],
        started_at: event.timestamp,
      });
    }
  }
  if (["tool.running", "tool.completed", "tool.failed"].includes(event.event_type)) {
    const invocationId = String(payload.tool_invocation_id || "");
    if (invocationId) {
      next = patchActivity(next, event.session_id, `activity:${invocationId}`, {
        status: event.event_type === "tool.running" ? "running" : event.event_type === "tool.completed" ? "completed" : "failed",
        completed_at: event.event_type === "tool.running" ? null : event.timestamp,
      });
    }
  }
  if (event.event_type === "observation.created") {
    const observation = record(payload.observation);
    const invocationId = String(observation.tool_invocation_id || "");
    if (invocationId) {
      next = patchActivity(next, event.session_id, `activity:${invocationId}`, {
        summary: observation.model_visible_summary ? String(observation.model_visible_summary) : null,
        artifact_ids: Array.isArray(observation.artifact_ids) ? observation.artifact_ids.map(String) : [],
      });
    }
  }
  if (event.event_type === "approval.requested" && run) {
    const approval = record(payload.approval) as unknown as NonNullable<ConversationRun["approval"]>;
    next = upsertRun(next, event.session_id, { ...run, status: "waiting_approval", approval });
    next = upsertApproval(next, event.session_id, approval);
  }
  if (event.event_type === "approval.resolved" && run) {
    const approval = record(payload.approval) as unknown as NonNullable<ConversationRun["approval"]>;
    next = upsertRun(next, event.session_id, { ...run, status: "running", approval });
    next = upsertApproval(next, event.session_id, approval);
  }
  if (event.event_type === "question.requested" && run) {
    const question = record(payload.question) as unknown as ConversationQuestion;
    next = upsertQuestion(next, event.session_id, question);
    next = upsertRun(next, event.session_id, { ...run, status: "waiting_input" });
  }
  if (event.event_type === "question.resolved" && run) {
    const question = record(payload.question) as unknown as ConversationQuestion;
    next = upsertQuestion(next, event.session_id, question);
    next = upsertRun(next, event.session_id, { ...run, status: "running" });
    const message = record(payload.user_message);
    if (message.id) {
      next = appendMessage(next, event.session_id, {
        id: String(message.id),
        conversation_id: event.session_id,
        role: "user",
        content: String(message.content || ""),
        status: "completed",
        sequence: Number(message.sequence || 0),
        created_at: event.timestamp,
        updated_at: event.timestamp,
      });
    }
  }
  return next;
}

function clearLiveRevisions(state: ConversationStore, prefix: string): ConversationStore {
  const entries = Object.entries(state.liveRevisionById).filter(([id]) => !id.startsWith(prefix));
  if (entries.length === Object.keys(state.liveRevisionById).length) return state;
  return { ...state, liveRevisionById: Object.fromEntries(entries) };
}

function withCursor(state: ConversationStore, detail: ConversationDetail, cursor: number): ConversationStore {
  return {
    ...state,
    detailById: { ...state.detailById, [detail.id]: { ...detail, cursor } },
  };
}

function upsertArtifact(state: ConversationStore, conversationId: string, artifact: ConversationArtifact): ConversationStore {
  const detail = state.detailById[conversationId];
  return {
    ...state,
    artifactsById: { ...state.artifactsById, [artifact.id]: artifact },
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        artifacts: detail.artifacts.some((item) => item.id === artifact.id)
          ? detail.artifacts.map((item) => item.id === artifact.id ? artifact : item)
          : [...detail.artifacts, artifact],
      },
    },
  };
}

function appendMessage(
  state: ConversationStore,
  conversationId: string,
  message: ConversationMessage,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail || state.messagesById[message.id]) return state;
  return {
    ...state,
    messagesById: { ...state.messagesById, [message.id]: message },
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        messages: [...detail.messages, message].sort((left, right) => left.sequence - right.sequence),
      },
    },
  };
}

function upsertQuestion(
  state: ConversationStore,
  conversationId: string,
  question: ConversationQuestion,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail || !question.id) return state;
  const questions = detail.questions || [];
  return {
    ...state,
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        questions: questions.some((item) => item.id === question.id)
          ? questions.map((item) => item.id === question.id ? question : item)
          : [...questions, question],
      },
    },
  };
}

function upsertApproval(
  state: ConversationStore,
  conversationId: string,
  approval: NonNullable<ConversationRun["approval"]>,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail || !approval.id) return state;
  return {
    ...state,
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        approvals: detail.approvals.some((item) => item.id === approval.id)
          ? detail.approvals.map((item) => item.id === approval.id ? approval : item)
          : [...detail.approvals, approval],
      },
    },
  };
}

function upsertActivity(
  state: ConversationStore,
  conversationId: string,
  activity: ConversationActivity,
  appendTitle = false,
  appendSummary = false,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail) return state;
  const activities = detail.activities || [];
  const existing = activities.find((item) => item.id === activity.id);
  const next = existing
    ? {
      ...existing,
      ...activity,
      title: appendTitle ? existing.title + activity.title : activity.title,
      summary: cleanActivitySummary(appendSummary
        ? `${existing.summary || ""}${activity.summary || ""}`
        : activity.summary),
    }
    : activity;
  return {
    ...state,
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        activities: existing
          ? activities.map((item) => item.id === activity.id ? next : item)
          : [...activities, next],
      },
    },
  };
}

function patchActivity(
  state: ConversationStore,
  conversationId: string,
  activityId: string,
  patch: Partial<ConversationActivity>,
): ConversationStore {
  const detail = state.detailById[conversationId];
  const current = detail?.activities?.find((item) => item.id === activityId);
  return current ? upsertActivity(state, conversationId, { ...current, ...patch }) : state;
}

function settleRunActivities(
  state: ConversationStore,
  conversationId: string,
  runId: string,
  runStatus: ConversationRun["status"],
  completedAt: string,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail?.activities) return state;
  const active = new Set(["pending", "running", "waiting"]);
  const terminalStatus: ConversationActivity["status"] = runStatus === "cancelled"
    ? "cancelled"
    : runStatus === "failed" ? "failed" : "completed";
  let changed = false;
  const activities = detail.activities.map((activity) => {
    if (activity.run_id !== runId || !active.has(activity.status)) return activity;
    changed = true;
    return { ...activity, status: terminalStatus, completed_at: completedAt };
  });
  if (!changed) return state;
  return {
    ...state,
    detailById: {
      ...state.detailById,
      [conversationId]: { ...detail, activities },
    },
  };
}

function normalizeEventArtifact(value: Record<string, unknown>, conversationId: string): ConversationArtifact | null {
  if (!value.id || !value.run_id || !value.type) return null;
  const relations: NonNullable<ConversationArtifact["relations"]> = Array.isArray(value.relations)
    ? value.relations as NonNullable<ConversationArtifact["relations"]>
    : [];
  return {
    id: String(value.id), conversation_id: conversationId, run_id: String(value.run_id),
    turn_id: value.turn_id ? String(value.turn_id) : null,
    semantic_id: value.semantic_key ? String(value.semantic_key) : null,
    version: Number(value.version || 1), type: String(value.type) as ConversationArtifact["type"],
    title: String(value.title || "工件"),
    status: String(value.status || "completed") as ConversationArtifact["status"],
    summary: value.summary ? String(value.summary) : null,
    payload: record(value.payload), payload_ref: value.payload_ref ? String(value.payload_ref) : null,
    provenance: record(value.provenance), relations,
    depends_on: relations.map((relation) => relation.artifact_id),
  };
}

function toolLabel(name: string): string {
  return ({
    "db.observe": "了解数据库结构", "db.search": "查找相关表和字段",
    "db.inspect": "检查表结构", "db.preview": "查看数据样例",
    "sql.validate": "验证分析 SQL", "sql.execute_readonly": "执行只读查询",
    "chart.suggest": "生成结果图表", "analysis.review": "复核分析覆盖度",
  } as Record<string, string>)[name] || `运行 ${name}`;
}

function cleanActivitySummary(value?: string | null): string | null {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) return null;
  return normalized.length > 280 ? `${normalized.slice(0, 277)}…` : normalized;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function numberAt(value: Record<string, unknown>, path: string[], fallback: number): number {
  let current: unknown = value;
  for (const key of path) current = record(current)[key];
  return typeof current === "number" ? current : fallback;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
