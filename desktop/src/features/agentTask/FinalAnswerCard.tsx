import { useMemo } from "react";
import {
  Lightbulb, AlertTriangle, CheckCircle2, FileText, ChevronRight, Terminal,
  Database, Hash, Target, Activity, Info,
} from "lucide-react";
import type { AgentAnswer, FollowUpSuggestion } from "../../lib/api/types";
import type { AgentArtifact } from "../../types/agentArtifact";
import type { AgentTabStatus } from "../../mock/dbfoxMock";
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

// ── Metric extraction from evidence ─────────────────────────────────────

function extractMetrics(answer: AgentAnswer): { label: string; value: string; icon: "count" | "rate" }[] {
  return (answer.evidence || [])
    .filter(ev => ev.value != null && ev.label)
    .map(ev => {
      const numVal = typeof ev.value === "number" ? ev.value : parseFloat(String(ev.value));
      return {
        label: ev.label,
        value: !isNaN(numVal) ? numVal.toLocaleString() : String(ev.value),
        icon: (ev.label.includes("率") || ev.label.includes("%") ? "rate" : "count") as "count" | "rate",
      };
    })
    .slice(0, 6);
}

// ── Main component ──────────────────────────────────────────────────────

export function FinalAnswerCard({
  answer, artifacts, suggestions, agentStatus, onSendFollowUp, onOpenSqlConsole, onToast,
}: FinalAnswerCardProps) {
  const hasFindings = answer?.key_findings && answer.key_findings.length > 0;
  const hasCaveats = answer?.caveats && answer.caveats.length > 0;
  const hasRecommendations = answer?.recommendations && answer.recommendations.length > 0;
  const hasFollowUp = answer?.follow_up_questions && answer.follow_up_questions.length > 0;

  const accentClass = useMemo(() => {
    if (agentStatus === "failed") return "task-answer-error";
    if (hasCaveats) return "task-answer-warn";
    return "task-answer-success";
  }, [agentStatus, hasCaveats]);

  const metrics = useMemo(() => (answer ? extractMetrics(answer) : []), [answer]);

  // Group artifacts: table → linked chart pairs
  const tableArtifacts = artifacts.filter(a => a.type === "table");
  const chartArtifacts = artifacts.filter(a => a.type === "chart");
  const sqlArtifacts = artifacts.filter(a => a.type === "sql");

  if (!answer || (!isRealAnswer(answer) && !hasFindings && !hasCaveats && metrics.length === 0)) {
    return null;
  }

  return (
    <div className={`task-answer-card ${accentClass} animate-slide-up`}>

      {/* ── Metric cards ── */}
      {metrics.length > 0 && (
        <div className="task-metrics-row">
          {metrics.map((m, i) => (
            <div key={i} className="task-metric-card">
              <span className="task-metric-value">{m.value}</span>
              <span className="task-metric-label">{m.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Answer body — rendered as Markdown (AI outputs ## headings, **bold**, lists) ── */}
      {answer.answer && isRealAnswer(answer) && (
        <div className="task-answer-markdown">
          <MarkdownContent content={answer.answer} />
        </div>
      )}

      {/* ── Key findings (fallback for non-markdown answers) ── */}
      {hasFindings && !isRealAnswer(answer) && (
        <div className="task-answer-findings">
          <div className="task-answer-section-title">
            <Lightbulb size={12} /><span>关键发现</span>
          </div>
          <ul className="task-answer-list">
            {answer.key_findings!.map((finding, i) => (
              <li key={i}><CheckCircle2 size={11} className="text-green-500 flex-shrink-0 mt-0.5" /><span>{finding}</span></li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Per-unit tables + charts ── */}
      {tableArtifacts.length > 0 && (
        <div className="task-answer-artifacts">
          <div className="task-answer-section-title">
            <Database size={12} /><span>查询结果</span>
          </div>
          <div className="task-artifacts-grid">
            {tableArtifacts.map((tableArt, ti) => {
              const tableSem = tableArt.semantic_id || tableArt.id;
              const linkedCharts = chartArtifacts.filter(
                c => (c.depends_on || []).some((d: string) =>
                  d === tableSem || d === "result_table" || tableSem.includes(d) || d.includes(tableSem),
                ),
              );
              return (
                <div key={tableArt.id} className="task-unit-card">
                  <div className="task-unit-table">
                    <div className="task-artifact-item-head">
                      <Database size={11} className="text-green-500" />
                      <span>结果表 {tableArtifacts.length > 1 ? `#${ti + 1}` : ""}</span>
                      <span className="text-[10px] text-slate-400 ml-auto">
                        {(tableArt.rows || []).length} 行 × {(tableArt.columns || []).length} 列
                      </span>
                    </div>
                    <div className="task-artifact-table-wrap">
                      <table className="task-artifact-table">
                        <thead><tr>
                          {(tableArt.columns || []).slice(0, 6).map((col: string, ci: number) => <th key={ci}>{col}</th>)}
                          {(tableArt.columns || []).length > 6 && <th>…</th>}
                        </tr></thead>
                        <tbody>
                          {(tableArt.rows || []).slice(0, 10).map((row: any[], ri: number) => (
                            <tr key={ri}>
                              {(tableArt.columns || []).slice(0, 6).map((col: string, ci: number) => (
                                <td key={ci}>{String(row?.[ci] ?? (row as Record<string, unknown>)?.[col] ?? "")}</td>
                              ))}
                              {(tableArt.columns || []).length > 6 && <td>…</td>}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {(tableArt.rows || []).length > 10 && (
                        <div className="task-artifact-table-more">仅显示前 10 行，共 {tableArt.rows.length} 行</div>
                      )}
                    </div>
                  </div>
                  {linkedCharts.map(chart => (
                    <div key={chart.id} className="task-unit-chart">
                      <div className="task-artifact-item-head">
                        <BarChartIcon size={11} className="text-purple-500" />
                        <span>{chart.title || "图表"}</span>
                      </div>
                      {chart.series && chart.series.length > 0 ? (
                        <div className="task-artifact-chart-bars">
                          {chart.series.map((s: any, si: number) => (
                            <div key={si} className="task-chart-bar-row">
                              <span className="task-chart-bar-label">{s.label}</span>
                              <div className="task-chart-bar-track">
                                <div className="task-chart-bar-fill" style={{
                                  width: `${Math.min(100, (s.value / (maxVal(chart.series) || 1)) * 100)}%`,
                                }} />
                              </div>
                              <span className="task-chart-bar-value">{Number(s.value).toLocaleString()}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-[11px] text-slate-400 p-2">暂无图表数据</div>
                      )}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── SQL artifacts ── */}
      {sqlArtifacts.length > 0 && (
        <div className="task-answer-artifacts">
          <div className="task-answer-section-title"><Terminal size={12} /><span>SQL</span></div>
          <div className="task-artifacts-grid">
            {sqlArtifacts.map(artifact => (
              <div key={artifact.id} className="task-artifact-item task-artifact-sql">
                <pre className="task-artifact-sql-pre">{artifact.sql}</pre>
                <div className="task-artifact-sql-actions">
                  <button className="task-artifact-btn" onClick={() => onOpenSqlConsole(artifact.sql)} type="button">在 SQL 控制台打开</button>
                  <button className="task-artifact-btn" onClick={() => { navigator.clipboard.writeText(artifact.sql).then(() => onToast("SQL 已复制"), () => onToast("复制失败")); }} type="button">复制</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Caveats ── */}
      {hasCaveats && (
        <div className="task-answer-caveats">
          <div className="task-answer-section-title"><AlertTriangle size={12} /><span>注意事项</span></div>
          <ul className="task-answer-list">
            {answer.caveats!.map((caveat, i) => (
              <li key={i}><AlertTriangle size={10} className="text-amber-500 flex-shrink-0 mt-0.5" /><span>{caveat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Recommendations ── */}
      {hasRecommendations && (
        <div className="task-answer-recommendations">
          <div className="task-answer-section-title"><Lightbulb size={12} /><span>建议</span></div>
          <ul className="task-answer-list">
            {answer.recommendations!.map((rec, i) => (<li key={i}>{rec}</li>))}
          </ul>
        </div>
      )}

      {/* ── Follow-up ── */}
      {hasFollowUp && (
        <div className="task-answer-followup">
          <div className="task-answer-section-title"><span>追问建议</span></div>
          <div className="task-followup-chips">
            {answer.follow_up_questions!.slice(0, 4).map((q, i) => (
              <button key={i} className="task-followup-chip" onClick={() => onSendFollowUp(q)} type="button"><span>{q}</span><ChevronRight size={11} /></button>
            ))}
          </div>
        </div>
      )}

      {suggestions && suggestions.length > 0 && !hasFollowUp && (
        <div className="task-answer-suggestions">
          <div className="task-answer-section-title"><span>你可能还想问</span></div>
          <div className="task-followup-chips">
            {suggestions.slice(0, 4).map((s, i) => (
              <button key={i} className="task-followup-chip" onClick={() => onSendFollowUp(s.question)} type="button"><span>{s.question}</span><ChevronRight size={11} /></button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function maxVal(series: Array<{ value: number }>): number {
  let max = 0; for (const s of series) { if (s.value > max) max = s.value; } return max;
}

function BarChartIcon({ size, className }: { size: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}
