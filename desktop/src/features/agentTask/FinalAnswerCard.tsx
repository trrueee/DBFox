import { useMemo } from "react";
import {
  Lightbulb, AlertTriangle, ChevronRight, Database, Terminal,
} from "lucide-react";
import type { AgentAnswer } from "../../lib/api/types";
import type { AgentArtifact } from "../../types/agentArtifact";
import type { AgentTabStatus } from "../../mock/dbfoxMock";
import { MarkdownContent } from "../workspace/queryResult/MarkdownContent";

interface FinalAnswerCardProps {
  answer: AgentAnswer | null | undefined;
  artifacts: AgentArtifact[];
  agentStatus: AgentTabStatus | "idle";
  onSendFollowUp: (text: string) => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

function isRealAnswer(answer: AgentAnswer): boolean {
  const text = (answer.answer || "").trim();
  return text.length > 0;
}

// Evidence artifact types — only table / chart / sql are user-visible data products
const EVIDENCE_TYPES = new Set(["table", "chart", "sql"]);

function getEvidenceArtifacts(all: AgentArtifact[]): AgentArtifact[] {
  return all.filter(a => EVIDENCE_TYPES.has(a.type));
}

export function FinalAnswerCard({
  answer, artifacts, agentStatus, onSendFollowUp, onOpenSqlConsole, onToast,
}: FinalAnswerCardProps) {
  const hasCaveats = answer?.caveats && answer.caveats.length > 0;
  const hasRecommendations = answer?.recommendations && answer.recommendations.length > 0;
  const hasFollowUp = answer?.follow_up_questions && answer.follow_up_questions.length > 0;

  const evidenceArtifacts = useMemo(
    () => getEvidenceArtifacts(artifacts),
    [artifacts],
  );

  const tableArts = evidenceArtifacts.filter(a => a.type === "table");
  const chartArts = evidenceArtifacts.filter(a => a.type === "chart");
  const sqlArts = evidenceArtifacts.filter(a => a.type === "sql");

  const accentClass = agentStatus === "failed"
    ? "task-answer-error"
    : hasCaveats ? "task-answer-warn" : "task-answer-success";

  if (!answer || !isRealAnswer(answer)) return null;

  return (
    <div className={`task-answer-card ${accentClass}`}>

      {/* Answer body — Markdown, always visible */}
      <div className="task-answer-markdown">
        <MarkdownContent content={answer.answer} />
      </div>

      {/* Evidence artifacts — collapsible */}
      {evidenceArtifacts.length > 0 && (
        <details className="task-answer-evidence-details">
          <summary className="task-answer-section-title">
            <Database size={12} />
            <span>支撑数据</span>
            <span className="text-[10px] text-slate-400 ml-2">
              ({tableArts.length} 表, {chartArts.length} 图, {sqlArts.length} SQL)
            </span>
          </summary>

          <div className="task-evidence-body">
            {/* Tables — columns/rows are at artifact top level */}
            {tableArts.map(t => {
              const cols: string[] = (t as any).columns || [];
              const rows: any[][] = (t as any).rows || [];
              return (
                <div key={t.id} className="task-evidence-table">
                  <div className="task-evidence-head">
                    <Database size={11} className="text-green-500" />
                    <span>{t.title || "结果表"}</span>
                    <span className="text-[10px] text-slate-400 ml-auto">
                      {rows.length} 行 × {cols.length} 列
                    </span>
                  </div>
                  <div className="task-artifact-table-wrap">
                    <table className="task-artifact-table">
                      <thead><tr>
                        {cols.slice(0, 6).map((col: string, ci: number) => (
                          <th key={ci}>{col}</th>
                        ))}
                      </tr></thead>
                      <tbody>
                        {rows.slice(0, 10).map((row: any[], ri: number) => (
                          <tr key={ri}>
                            {cols.slice(0, 6).map((col: string, ci: number) => (
                              <td key={ci}>{String(row?.[ci] ?? (row as Record<string, unknown>)?.[col] ?? "")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {rows.length > 10 && (
                      <div className="task-artifact-table-more">
                        仅显示前 10 行，共 {rows.length} 行
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* SQL — sql string is at artifact top level */}
            {sqlArts.map(s => {
              const sqlText: string = (s as any).sql || "";
              return (
                <div key={s.id} className="task-evidence-sql">
                  <div className="task-evidence-head">
                    <Terminal size={11} className="text-blue-500" />
                    <span>SQL</span>
                  </div>
                  <pre className="task-artifact-sql-pre">{sqlText}</pre>
                  <button
                    className="task-artifact-btn"
                    onClick={() => onOpenSqlConsole(sqlText)}
                    type="button"
                  >
                    在 SQL 控制台打开
                  </button>
                </div>
              );
            })}
          </div>
        </details>
      )}

      {/* Caveats */}
      {hasCaveats && (
        <div className="task-answer-caveats">
          <div className="task-answer-section-title">
            <AlertTriangle size={12} /><span>注意事项</span>
          </div>
          <ul className="task-answer-list">
            {answer.caveats!.map((caveat, i) => (
              <li key={i}><AlertTriangle size={10} className="text-amber-500 flex-shrink-0 mt-0.5" /><span>{caveat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendations */}
      {hasRecommendations && (
        <div className="task-answer-recommendations">
          <div className="task-answer-section-title">
            <Lightbulb size={12} /><span>建议</span>
          </div>
          <ul className="task-answer-list">
            {answer.recommendations!.map((rec, i) => (<li key={i}>{rec}</li>))}
          </ul>
        </div>
      )}

      {/* Follow-up questions */}
      {hasFollowUp && (
        <div className="task-answer-followup">
          <div className="task-answer-section-title"><span>追问建议</span></div>
          <div className="task-followup-chips">
            {answer.follow_up_questions!.slice(0, 4).map((q, i) => (
              <button key={i} className="task-followup-chip" onClick={() => onSendFollowUp(q)} type="button">
                <span>{q}</span><ChevronRight size={11} />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
