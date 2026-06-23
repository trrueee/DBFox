import { useEffect, useRef, useState } from "react";
import { Activity, BookOpen, CheckCircle2, Circle, Database, MessageSquare, Search, ShieldCheck, Tags, Wrench, XCircle } from "lucide-react";
import type { AgentRuntimeEvent } from "../../../lib/api/types";
import type { ConversationRun } from "../../../types/conversation";
import {
  buildRunTraceModel,
  eventSummary,
  eventTitle,
  type TimelinePhase,
  type TimelineStage,
} from "./runTraceModel";
import { RunPhaseStepper } from "./RunPhaseStepper";

type RunStatusKind = "idle" | "model" | "tool" | "repair" | "success" | "failed" | "waiting";

interface RunStatusNode {
  title: string;
  detail: string;
  kind: RunStatusKind;
}

export function RunTracePanel({ run }: { run: ConversationRun }) {
  const { events, stages, contextReferences, repairSummaries, summary } = buildRunTraceModel(run);
  const [expanded, setExpanded] = useState(false);
  const userToggledRef = useRef(false);
  const previousRunIdRef = useRef(run.id);
  const statusNode = buildRunStatusNode(run, events, stages);

  useEffect(() => {
    if (previousRunIdRef.current !== run.id) {
      previousRunIdRef.current = run.id;
      userToggledRef.current = false;
      setExpanded(false);
    }
  }, [run.id]);

  const toggleExpanded = () => {
    userToggledRef.current = true;
    setExpanded((value) => !value);
  };

  return (
    <section className="conv-run-trace" data-expanded={expanded ? "true" : "false"}>
      <button
        type="button"
        className={`conv-run-status-node is-${statusNode.kind}`}
        aria-expanded={expanded}
        onClick={toggleExpanded}
      >
        <span className="conv-run-status-icon">{statusIcon(statusNode.kind)}</span>
        <span className="conv-run-status-copy">
          <strong>{statusNode.title}</strong>
          {statusNode.detail && <span>{statusNode.detail}</span>}
        </span>
        {stages.length > 0 && <span className="conv-run-count">{stages.length}</span>}
      </button>
      {expanded && (
        <div className="conv-run-trace-body">
          <div className="conv-run-debug-summary">{summary}</div>
          <RunPhaseStepper stages={stages} />
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
          {repairSummaries.length > 0 && (
            <div className="conv-repair-summaries">
              {repairSummaries.map((repair) => (
                <section className="conv-repair-summary" key={repair.key}>
                  <header>
                    <strong>
                      <Wrench size={12} />
                      SQL 修复
                    </strong>
                    {repair.attemptLabel && <span>{repair.attemptLabel}</span>}
                    {repair.errorClass && <code>{repair.errorClass}</code>}
                  </header>
                  {repair.update && <p>{repair.update}</p>}
                  {repair.failedSql && (
                    <div className="conv-repair-failed-sql">
                      <b>失败 SQL</b>
                      <pre>{repair.failedSql}</pre>
                    </div>
                  )}
                  {(repair.rootCause || repair.recoveryStrategy) && (
                    <div className="conv-repair-detail-grid">
                      {repair.rootCause && (
                        <span>
                          <b>根因</b>
                          <small>{repair.rootCause}</small>
                        </span>
                      )}
                      {repair.recoveryStrategy && (
                        <span>
                          <b>修复策略</b>
                          <small>{repair.recoveryStrategy}</small>
                        </span>
                      )}
                    </div>
                  )}
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
      )}
    </section>
  );
}

function buildRunStatusNode(
  run: ConversationRun,
  events: AgentRuntimeEvent[],
  stages: TimelineStage[],
): RunStatusNode {
  const stage = currentStage(stages);
  const event = latestStageEvent(stage) || events[events.length - 1];
  const detail = run.error_message || (event ? eventSummary(event) : "") || stage?.summary || "";

  if (run.status === "completed") {
    return { title: "已完成", detail: completedRunDetail(events, detail), kind: "success" };
  }
  if (run.status === "failed") return { title: "执行失败", detail, kind: "failed" };
  if (run.status === "waiting_approval") return { title: "等待确认", detail, kind: "waiting" };
  if (stage?.phase === "repairing") return { title: "SQL 修复中", detail, kind: "repair" };

  if (stage && isToolPhase(stage.phase, event)) {
    return { title: "正在执行工具", detail, kind: "tool" };
  }

  if (stage) {
    return { title: "正在调用模型", detail, kind: "model" };
  }

  return { title: "待执行", detail, kind: "idle" };
}

function currentStage(stages: TimelineStage[]): TimelineStage | undefined {
  return findStageByStatus(stages, "failed") || findStageByStatus(stages, "running") || stages[stages.length - 1];
}

function findStageByStatus(
  stages: TimelineStage[],
  status: TimelineStage["status"],
): TimelineStage | undefined {
  for (let index = stages.length - 1; index >= 0; index -= 1) {
    if (stages[index].status === status) return stages[index];
  }
  return undefined;
}

function latestStageEvent(stage?: TimelineStage): AgentRuntimeEvent | undefined {
  return stage?.events[stage.events.length - 1];
}

function isToolPhase(phase: TimelinePhase, event?: AgentRuntimeEvent): boolean {
  if (toolName(event)) return true;
  return (
    phase === "searching_schema" ||
    phase === "inspecting" ||
    phase === "generating_sql" ||
    phase === "validating" ||
    phase === "executing" ||
    phase === "approval"
  );
}

function toolName(event?: AgentRuntimeEvent): string {
  const value = event?.step?.tool_name || event?.step?.tool;
  return typeof value === "string" ? value : "";
}

function completedRunDetail(events: AgentRuntimeEvent[], fallback: string): string {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === "agent.run.completed") return eventSummary(event) || "任务完成。";
  }
  return fallback;
}

function statusIcon(kind: RunStatusKind) {
  if (kind === "failed") return <XCircle size={14} />;
  if (kind === "repair") return <Wrench size={14} />;
  if (kind === "tool") return <Database size={14} />;
  if (kind === "model") return <MessageSquare size={14} />;
  if (kind === "success") return <CheckCircle2 size={14} />;
  if (kind === "waiting") return <ShieldCheck size={14} />;
  return <Activity size={14} />;
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
