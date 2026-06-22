import { Activity, BookOpen, CheckCircle2, Circle, Database, MessageSquare, Search, ShieldCheck, Tags, Wrench, XCircle } from "lucide-react";
import type { AgentRuntimeEvent } from "../../../lib/api/types";
import type { ConversationRun } from "../../../types/conversation";

const TOOL_LABELS: Record<string, string> = {
  "db.observe": "浏览数据库结构",
  "db.search": "搜索相关表和字段",
  "db.inspect": "检查表结构",
  "db.preview": "预览样例数据",
  "sql.validate": "校验 SQL 安全性",
  "sql.execute_readonly": "执行只读查询",
  "chart.suggest": "生成图表建议",
  "answer.synthesize": "整理最终答案",
};

const EVENT_LABELS: Record<string, string> = {
  "agent.run.started": "开始执行任务",
  "agent.run.completed": "任务完成",
  "agent.run.failed": "执行失败",
  "agent.run.cancelled": "执行已取消",
  "agent.run.waiting_approval": "等待确认",
  "agent.approval.required": "需要确认",
  "agent.approval.resolved": "确认已处理",
  "agent.artifact.created": "生成数据产物",
  "agent.answer.completed": "整理最终答案",
};

const PHASE_ORDER = [
  "understanding",
  "searching_schema",
  "inspecting",
  "generating_sql",
  "validating",
  "executing",
  "repairing",
  "synthesizing",
  "completed",
] as const;

type TimelinePhase = (typeof PHASE_ORDER)[number] | "approval";

const PHASE_LABELS: Record<TimelinePhase, string> = {
  understanding: "理解问题",
  searching_schema: "搜索结构",
  inspecting: "检查数据",
  generating_sql: "生成 SQL",
  validating: "安全校验",
  executing: "执行查询",
  repairing: "自动修复",
  synthesizing: "整理回答",
  completed: "完成",
  approval: "等待确认",
};

interface TimelineStage {
  phase: TimelinePhase;
  label: string;
  status: "running" | "success" | "failed";
  summary: string;
  events: AgentRuntimeEvent[];
}

interface ContextReference {
  label: string;
  summary: string;
  source: string;
}

export function RunTracePanel({ run }: { run: ConversationRun }) {
  const events = (run.events || []).filter((event) => String(event.type) !== "agent.answer.delta");
  const stages = buildTimelineStages(run, events);
  const contextReferences = contextReferenceCards(events);
  const summary = runSummary(run, events, stages);

  return (
    <details className="conv-run-trace" open={run.status === "running" || run.status === "failed"}>
      <summary>
        {run.status === "failed" ? <XCircle size={14} /> : <Activity size={14} />}
        <span>{summary}</span>
        {stages.length > 0 && <span className="conv-run-count">{stages.length}</span>}
      </summary>
      <div className="conv-run-trace-body">
        {contextReferences.length > 0 && (
          <div className="conv-context-reference-groups">
            {contextReferences.map((group) => (
              <section className="conv-context-reference-group" key={group.kind}>
                <strong>
                  {group.kind === "memory" ? <BookOpen size={12} /> : <Tags size={12} />}
                  {group.title}
                </strong>
                <div>
                  {group.items.map((item) => (
                    <span className="conv-context-reference" key={`${group.kind}-${item.label}-${item.summary}`}>
                      <b>{item.label}</b>
                      {item.summary && <small>{item.summary}</small>}
                    </span>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
        {stages.length > 0 ? (
          <ol className="conv-run-events conv-run-stages">
            {stages.map((stage) => (
              <li className={`conv-run-stage conv-run-stage-${stage.status}`} key={stage.phase}>
                <span className="conv-run-event-icon">{phaseIcon(stage.phase, stage.status)}</span>
                <span className="conv-run-event-copy">
                  <strong>{stage.label}</strong>
                  {stage.summary && <span>{stage.summary}</span>}
                  {stage.events.length > 0 && (
                    <details className="conv-run-stage-debug">
                      <summary>调试细节</summary>
                      <ol>
                        {stage.events.map((event) => (
                          <li key={event.event_id || `${event.type}-${event.sequence}`}>
                            <strong>{eventTitle(event)}</strong>
                            {eventSummary(event) && <span>{eventSummary(event)}</span>}
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <div className="conv-run-empty">Waiting for runtime events...</div>
        )}
        {run.error_message && <div>{run.error_message}</div>}
      </div>
    </details>
  );
}

function contextReferenceCards(events: AgentRuntimeEvent[]): Array<{ kind: "memory" | "semantic"; title: string; items: ContextReference[] }> {
  const memory = dedupeReferences(events.flatMap((event) => taskLensReferences(event, "memory_references")));
  const semantic = dedupeReferences(events.flatMap((event) => taskLensReferences(event, "semantic_references")));
  const groups: Array<{ kind: "memory" | "semantic"; title: string; items: ContextReference[] }> = [];
  if (memory.length > 0) groups.push({ kind: "memory", title: "参考业务记忆", items: memory });
  if (semantic.length > 0) groups.push({ kind: "semantic", title: "字段理解", items: semantic });
  return groups;
}

function taskLensReferences(event: AgentRuntimeEvent, key: "memory_references" | "semantic_references"): ContextReference[] {
  const taskLens = event.step?.task_lens;
  if (!taskLens || typeof taskLens !== "object") return [];
  const raw = (taskLens as Record<string, unknown>)[key];
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const label = typeof record.label === "string" ? record.label.trim() : "";
    if (!label) return [];
    return [{
      label,
      summary: typeof record.summary === "string" ? record.summary.trim() : "",
      source: typeof record.source === "string" ? record.source.trim() : "",
    }];
  });
}

function dedupeReferences(items: ContextReference[]): ContextReference[] {
  const seen = new Set<string>();
  const result: ContextReference[] = [];
  for (const item of items) {
    const key = `${item.label}|${item.summary}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result.slice(0, 5);
}

function runSummary(
  run: ConversationRun,
  events: AgentRuntimeEvent[],
  stages: TimelineStage[],
): string {
  const lastStage = stages[stages.length - 1];
  if (run.status === "running") return lastStage ? lastStage.label : "DBFox 正在分析...";
  if (run.status === "failed") return "执行失败";
  if (run.status === "cancelled") return "执行已取消";
  if (run.status === "waiting_approval") return "等待确认";
  if (run.status !== "completed") return "执行过程";

  const sqlCount = events.filter((event) => toolName(event) === "sql.execute_readonly").length;
  const rowCount = sumNumeric(events, ["rowCount", "row_count", "rows"]);
  const durationMs = sumNumeric(events, ["durationMs", "duration_ms", "latencyMs", "latency_ms"]);
  const parts = [`执行过程`, `${stages.length || events.length} 阶段`];
  if (sqlCount > 0) parts.push(`${sqlCount} 条 SQL`);
  if (rowCount > 0) parts.push(`${rowCount} 行`);
  if (durationMs > 0) parts.push(`${durationMs}ms`);
  return parts.join(" · ");
}

function stepValue(event: AgentRuntimeEvent, key: string): string {
  const value = event.step?.[key];
  return typeof value === "string" ? value : "";
}

function stepNumber(event: AgentRuntimeEvent, key: string): number {
  const value = event.step?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return 0;
}

function outputNumber(event: AgentRuntimeEvent, key: string): number {
  const output = event.step?.output;
  if (!output || typeof output !== "object") return 0;
  const value = (output as Record<string, unknown>)[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return 0;
}

function sumNumeric(events: AgentRuntimeEvent[], keys: string[]): number {
  return events.reduce((total, event) => {
    for (const key of keys) {
      const value = stepNumber(event, key) || outputNumber(event, key);
      if (value > 0) return total + value;
    }
    return total;
  }, 0);
}

function toolName(event: AgentRuntimeEvent): string {
  return stepValue(event, "tool_name") || stepValue(event, "tool");
}

function buildTimelineStages(run: ConversationRun, events: AgentRuntimeEvent[]): TimelineStage[] {
  const byPhase = new Map<TimelinePhase, TimelineStage>();
  for (const event of events) {
    const phase = phaseForEvent(event);
    const current = byPhase.get(phase);
    const status = eventStatus(event);
    const summary = eventSummary(event);
    if (!current) {
      byPhase.set(phase, {
        phase,
        label: PHASE_LABELS[phase],
        status,
        summary,
        events: [event],
      });
      continue;
    }
    current.events.push(event);
    current.status = mergeStageStatus(current.status, status);
    if (summary) current.summary = summary;
  }

  if (run.status === "waiting_approval" && !byPhase.has("approval")) {
    byPhase.set("approval", {
      phase: "approval",
      label: PHASE_LABELS.approval,
      status: "running",
      summary: run.error_message || "",
      events: [],
    });
  }

  return Array.from(byPhase.values()).sort((left, right) => phaseSort(left.phase) - phaseSort(right.phase));
}

function phaseSort(phase: TimelinePhase): number {
  if (phase === "approval") return PHASE_ORDER.indexOf("validating") + 0.5;
  const index = PHASE_ORDER.indexOf(phase as (typeof PHASE_ORDER)[number]);
  return index === -1 ? PHASE_ORDER.length : index;
}

function phaseForEvent(event: AgentRuntimeEvent): TimelinePhase {
  const explicit = stepValue(event, "phase");
  if (isTimelinePhase(explicit)) return explicit;
  const type = String(event.type);
  if (type.includes("approval") || type.includes("waiting_approval")) return "approval";
  if (type.includes("completed") && type === "agent.run.completed") return "completed";
  if (type === "agent.answer.completed") return "synthesizing";
  if (type.includes("failed")) return "repairing";
  return phaseForTool(toolName(event), stepValue(event, "name"));
}

function isTimelinePhase(value: string): value is TimelinePhase {
  return value === "approval" || (PHASE_ORDER as readonly string[]).includes(value);
}

function phaseForTool(tool: string, name: string): TimelinePhase {
  const value = `${tool} ${name}`.toLowerCase();
  if (value.includes("repair")) return "repairing";
  if (value.includes("db.search") || (value.includes("schema") && !value.includes("inspect"))) return "searching_schema";
  if (value.includes("db.inspect") || value.includes("db.preview") || value.includes("inspect")) return "inspecting";
  if (value.includes("sql.validate") || value.includes("safety") || value.includes("guardrail")) return "validating";
  if (value.includes("sql.execute") || value.includes("readonly") || value.includes("db.query")) return "executing";
  if (value.includes("chart") || value.includes("answer") || value.includes("memory")) return "synthesizing";
  if (value.includes("sql")) return "generating_sql";
  return "understanding";
}

function eventStatus(event: AgentRuntimeEvent): TimelineStage["status"] {
  const rawType = String(event.type);
  const status = stepValue(event, "status").toLowerCase();
  if (rawType.includes("failed") || status === "failed" || status === "error") return "failed";
  if (rawType.includes("started") || status === "running") return "running";
  return "success";
}

function mergeStageStatus(current: TimelineStage["status"], next: TimelineStage["status"]): TimelineStage["status"] {
  if (current === "failed" || next === "failed") return "failed";
  if (current === "running" || next === "running") return "running";
  return "success";
}

function eventTitle(event: AgentRuntimeEvent): string {
  const tool = toolName(event);
  if (tool) return TOOL_LABELS[tool] || tool;
  const name = stepValue(event, "name") || stepValue(event, "step_name");
  if (name) return name;
  if (event.type === "agent.artifact.created") return event.artifact?.title || "Artifact created";
  return EVENT_LABELS[String(event.type)] || String(event.type).replace("agent.", "").replaceAll(".", " ");
}

function eventSummary(event: AgentRuntimeEvent): string {
  return (
    stepValue(event, "summary") ||
    stepValue(event, "message") ||
    stepValue(event, "status") ||
    event.error ||
    ""
  );
}

function phaseIcon(phase: TimelinePhase, status: TimelineStage["status"]) {
  if (status === "failed") return <XCircle size={13} />;
  if (phase === "searching_schema") return <Search size={13} />;
  if (phase === "inspecting" || phase === "executing") return <Database size={13} />;
  if (phase === "validating" || phase === "approval") return <ShieldCheck size={13} />;
  if (phase === "repairing") return <Wrench size={13} />;
  if (phase === "synthesizing") return <MessageSquare size={13} />;
  if (status === "success") return <CheckCircle2 size={13} />;
  return <Circle size={13} />;
}
