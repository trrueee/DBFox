import { Activity, BookOpen, CheckCircle2, Circle, Database, MessageSquare, Search, ShieldCheck, Tags, Wrench, XCircle } from "lucide-react";
import type { ConversationRun } from "../../../types/conversation";
import {
  buildRunTraceModel,
  eventSummary,
  eventTitle,
  type TimelinePhase,
  type TimelineStage,
} from "./runTraceModel";

export function RunTracePanel({ run }: { run: ConversationRun }) {
  const { stages, contextReferences, repairSummaries, summary } = buildRunTraceModel(run);

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
    </details>
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
