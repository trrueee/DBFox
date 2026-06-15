import { useMemo } from "react";
import { Lightbulb, AlertTriangle, CheckCircle2, FileText, ChevronRight, Terminal, Database } from "lucide-react";
import type { AgentAnswer, FollowUpSuggestion } from "../../lib/api/types";
import type { AgentArtifact } from "../../types/agentArtifact";
import type { AgentTabStatus } from "../../mock/databoxMock";
import { MarkdownContent } from "../workspace/queryResult/MarkdownContent";

interface FinalAnswerCardProps {
  answer: AgentAnswer | null | undefined;
  artifacts: AgentArtifact[];
  suggestions: FollowUpSuggestion[] | null | undefined;
  agentStatus: AgentTabStatus | "idle";
  onSendFollowUp: (text: string) => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

const BOILERPLATE = new Set([
  "i do not have a successful result set to analyze yet.",
  "the query returned no rows",
  "i could not complete the analysis",
]);

function isRealAnswer(answer: AgentAnswer): boolean {
  const text = (answer.answer || "").trim().toLowerCase();
  if (!text) return false;
  if (BOILERPLATE.has(text)) return false;
  return true;
}

export function FinalAnswerCard({
  answer,
  artifacts,
  suggestions,
  agentStatus,
  onSendFollowUp,
  onOpenSqlConsole,
  onToast,
}: FinalAnswerCardProps) {
  const hasFindings = answer?.key_findings && answer.key_findings.length > 0;
  const hasEvidence = answer?.evidence && answer.evidence.length > 0;
  const hasCaveats = answer?.caveats && answer.caveats.length > 0;
  const hasRecommendations = answer?.recommendations && answer.recommendations.length > 0;
  const hasFollowUp = answer?.follow_up_questions && answer.follow_up_questions.length > 0;

  const accentClass = useMemo(() => {
    if (agentStatus === "failed") return "task-answer-error";
    if (hasCaveats) return "task-answer-warn";
    return "task-answer-success";
  }, [agentStatus, hasCaveats]);

  if (!answer || (!isRealAnswer(answer) && !hasFindings && !hasCaveats && !hasEvidence && !hasRecommendations)) {
    return null;
  }

  return (
    <div className={`task-answer-card ${accentClass} animate-slide-up`}>

      {/* Main answer text */}
      {answer.answer && isRealAnswer(answer) && (
        <div className="task-answer-text">
          <MarkdownContent content={answer.answer} />
        </div>
      )}

      {/* Key findings */}
      {hasFindings && (
        <div className="task-answer-findings">
          <div className="task-answer-section-title">
            <Lightbulb size={12} />
            <span>关键发现</span>
          </div>
          <ul className="task-answer-list">
            {answer.key_findings!.map((finding, i) => (
              <li key={i}>
                <CheckCircle2 size={11} className="text-green-500 flex-shrink-0 mt-0.5" />
                <span>{finding}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Evidence */}
      {hasEvidence && (
        <div className="task-answer-evidence">
          <div className="task-answer-section-title">
            <FileText size={12} />
            <span>数据依据</span>
          </div>
          <ul className="task-answer-list">
            {answer.evidence!.map((ev, i) => (
              <li key={i}>
                <span className="task-evidence-label">{ev.label}</span>
                {ev.value != null && (
                  <>
                    <span className="task-evidence-sep">:</span>
                    <span className="task-evidence-value">{String(ev.value)}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Caveats */}
      {hasCaveats && (
        <div className="task-answer-caveats">
          <div className="task-answer-section-title">
            <AlertTriangle size={12} />
            <span>注意事项</span>
          </div>
          <ul className="task-answer-list">
            {answer.caveats!.map((caveat, i) => (
              <li key={i}>
                <AlertTriangle size={10} className="text-amber-500 flex-shrink-0 mt-0.5" />
                <span>{caveat}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendations */}
      {hasRecommendations && (
        <div className="task-answer-recommendations">
          <div className="task-answer-section-title">
            <Lightbulb size={12} />
            <span>建议</span>
          </div>
          <ul className="task-answer-list">
            {answer.recommendations!.map((rec, i) => (
              <li key={i}>{rec}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Follow-up questions from answer */}
      {hasFollowUp && (
        <div className="task-answer-followup">
          <div className="task-answer-section-title">
            <span>追问建议</span>
          </div>
          <div className="task-followup-chips">
            {answer.follow_up_questions!.slice(0, 4).map((q, i) => (
              <button
                key={i}
                className="task-followup-chip"
                onClick={() => onSendFollowUp(q)}
                type="button"
              >
                <span>{q}</span>
                <ChevronRight size={11} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Artifacts section */}
      {artifacts.length > 0 && (
        <div className="task-answer-artifacts">
          <div className="task-answer-section-title">
            <Database size={12} />
            <span>产出物</span>
          </div>
          <div className="task-artifacts-grid">
            {artifacts.map((artifact) => {
              if (artifact.type === "sql") {
                return (
                  <div key={artifact.id} className="task-artifact-item task-artifact-sql">
                    <div className="task-artifact-item-head">
                      <Terminal size={11} className="text-blue-500" />
                      <span>{artifact.title}</span>
                    </div>
                    <pre className="task-artifact-sql-pre">{artifact.sql}</pre>
                    <div className="task-artifact-sql-actions">
                      <button
                        className="task-artifact-btn"
                        onClick={() => {
                          onOpenSqlConsole(artifact.sql);
                        }}
                        type="button"
                      >
                        在 SQL 控制台打开
                      </button>
                      <button
                        className="task-artifact-btn"
                        onClick={() => {
                          navigator.clipboard.writeText(artifact.sql).then(
                            () => onToast("SQL 已复制"),
                            () => onToast("复制失败"),
                          );
                        }}
                        type="button"
                      >
                        复制
                      </button>
                    </div>
                  </div>
                );
              }
              if (artifact.type === "table") {
                return (
                  <div key={artifact.id} className="task-artifact-item task-artifact-table">
                    <div className="task-artifact-item-head">
                      <Database size={11} className="text-green-500" />
                      <span>{artifact.title}</span>
                      {artifact.description && (
                        <span className="text-[10px] text-slate-400 ml-auto">{artifact.description}</span>
                      )}
                    </div>
                    <div className="task-artifact-table-wrap">
                      <table className="task-artifact-table">
                        <thead>
                          <tr>
                            {artifact.columns.map((col, i) => (
                              <th key={i}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {artifact.rows.slice(0, 20).map((row, ri) => (
                            <tr key={ri}>
                              {row.map((cell, ci) => (
                                <td key={ci}>{cell}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {artifact.rows.length > 20 && (
                        <div className="task-artifact-table-more">
                          仅显示前 20 行，共 {artifact.rows.length} 行
                        </div>
                      )}
                    </div>
                  </div>
                );
              }
              if (artifact.type === "chart") {
                return (
                  <div key={artifact.id} className="task-artifact-item task-artifact-chart">
                    <div className="task-artifact-item-head">
                      <BarChartIcon size={11} className="text-purple-500" />
                      <span>{artifact.title}</span>
                      {artifact.description && (
                        <span className="text-[10px] text-slate-400 ml-auto">{artifact.description}</span>
                      )}
                    </div>
                    <div className="task-artifact-chart-bars">
                      {artifact.series.map((s, i) => (
                        <div key={i} className="task-chart-bar-row">
                          <span className="task-chart-bar-label">{s.label}</span>
                          <div className="task-chart-bar-track">
                            <div
                              className="task-chart-bar-fill"
                              style={{
                                width: `${Math.min(100, (s.value / (maxVal(artifact.series) || 1)) * 100)}%`,
                              }}
                            />
                          </div>
                          <span className="task-chart-bar-value">{s.value.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              }
              if (artifact.type === "markdown") {
                return (
                  <div key={artifact.id} className="task-artifact-item task-artifact-markdown">
                    <div className="task-artifact-item-head">
                      <FileText size={11} className="text-slate-500" />
                      <span>{artifact.title}</span>
                    </div>
                    <div className="task-artifact-markdown-body">
                      <MarkdownContent content={artifact.content} />
                    </div>
                  </div>
                );
              }
              return null;
            })}
          </div>
        </div>
      )}

      {/* Follow-up suggestion chips */}
      {suggestions && suggestions.length > 0 && !hasFollowUp && (
        <div className="task-answer-suggestions">
          <div className="task-answer-section-title">
            <span>你可能还想问</span>
          </div>
          <div className="task-followup-chips">
            {suggestions.slice(0, 4).map((s, i) => (
              <button
                key={i}
                className="task-followup-chip"
                onClick={() => onSendFollowUp(s.question)}
                type="button"
              >
                <span>{s.question}</span>
                <ChevronRight size={11} />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Small utility
function maxVal(series: Array<{ value: number }>): number {
  let max = 0;
  for (const s of series) {
    if (s.value > max) max = s.value;
  }
  return max;
}

function BarChartIcon({ size, className }: { size: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}
