import { useMemo } from "react";
import {
  Lightbulb, AlertTriangle, CheckCircle2, FileText, ChevronRight, Terminal,
  Database, TrendingUp, BarChart3, PieChart, Hash, Target, Activity, Info,
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

// ── Report section parsing ──────────────────────────────────────────────

interface ReportSection {
  type: "conclusion" | "metrics" | "breakdown" | "trend" | "diagnosis" | "recommendation" | "scope" | "general";
  title: string;
  content: string;
}

const SECTION_PATTERNS: { pattern: RegExp; type: ReportSection["type"]; title: string }[] = [
  { pattern: /^#{1,3}\s*结论/i, type: "conclusion", title: "结论" },
  { pattern: /^#{1,3}\s*(关键|核心).{0,4}(指标|数据)/i, type: "metrics", title: "关键指标" },
  { pattern: /^#{1,3}\s*(维度|分布|分组|状态|平台).{0,4}(分析|分布)/i, type: "breakdown", title: "维度分析" },
  { pattern: /^#{1,3}\s*(趋势|变化|时间)/i, type: "trend", title: "趋势分析" },
  { pattern: /^#{1,3}\s*(异常|风险|问题|诊断)/i, type: "diagnosis", title: "异常与风险" },
  { pattern: /^#{1,3}\s*(建议|推荐|后续|下一步)/i, type: "recommendation", title: "建议" },
  { pattern: /^#{1,3}\s*(数据|口径|来源|范围|覆盖)/i, type: "scope", title: "数据口径" },
  // Fallback: Chinese patterns anywhere in line (for non-markdown output)
  { pattern: /结论[：:]/i, type: "conclusion", title: "结论" },
  { pattern: /关键指标|核心指标|指标总览/i, type: "metrics", title: "关键指标" },
  { pattern: /维度分析|分布|分组|状态分布|平台分布/i, type: "breakdown", title: "维度分析" },
  { pattern: /趋势|变化|时间/i, type: "trend", title: "趋势分析" },
  { pattern: /异常|风险|问题|诊断/i, type: "diagnosis", title: "异常与风险" },
  { pattern: /建议|推荐|后续|下一步/i, type: "recommendation", title: "建议" },
  { pattern: /数据口径|数据来源|分析范围|覆盖/i, type: "scope", title: "数据口径" },
];

function parseReportSections(text: string): ReportSection[] {
  // Find section boundaries by looking for numbered/标记 patterns
  const lines = text.split("\n");
  const sections: ReportSection[] = [];
  let currentType: ReportSection["type"] = "general";
  let currentTitle = "";
  let currentLines: string[] = [];
  let hasStructured = false;

  for (const line of lines) {
    let matched: ReportSection["type"] | null = null;
    let matchedTitle = "";
    for (const { pattern, type, title } of SECTION_PATTERNS) {
      if (pattern.test(line)) {
        matched = type;
        matchedTitle = title;
        hasStructured = true;
        break;
      }
    }

    if (matched) {
      if (currentLines.length > 0 || currentTitle) {
        sections.push({
          type: currentType,
          title: currentTitle || "分析",
          content: currentLines.join("\n").trim(),
        });
      }
      currentType = matched;
      currentTitle = matchedTitle;
      currentLines = [line];
    } else {
      currentLines.push(line);
    }
  }

  // Last section
  if (currentLines.length > 0) {
    sections.push({
      type: currentType,
      title: currentTitle || (hasStructured ? "" : ""),
      content: currentLines.join("\n").trim(),
    });
  }

  // If no structured sections detected, treat whole text as one
  if (!hasStructured) {
    return [{ type: "general", title: "", content: text.trim() }];
  }

  return sections.filter(s => s.content.length > 0);
}

// ── Metric extraction ───────────────────────────────────────────────────

interface MetricCard {
  label: string;
  value: string | number;
  sub?: string;
  icon: "count" | "rate" | "amount" | "trend";
}

function extractMetrics(
  answer: AgentAnswer,
  sections: ReportSection[],
): MetricCard[] {
  const metrics: MetricCard[] = [];

  // From evidence
  for (const ev of answer.evidence || []) {
    if (ev.value != null && ev.label) {
      const numVal = typeof ev.value === "number" ? ev.value : parseFloat(String(ev.value));
      if (!isNaN(numVal)) {
        metrics.push({
          label: ev.label,
          value: numVal.toLocaleString(),
          icon: ev.label.includes("率") || ev.label.includes("%") ? "rate"
            : ev.label.includes("行") || ev.label.includes("数") ? "count"
            : "amount",
        });
      }
    }
  }

  // Try to extract numbers from metrics section
  for (const s of sections) {
    if (s.type === "metrics") {
      const percentMatches = s.content.match(/([0-9]+(?:\.[0-9]+)?)[%％]/g);
      if (percentMatches) {
        for (const m of percentMatches.slice(0, 2)) {
          metrics.push({ label: "", value: m, icon: "rate" });
        }
      }
    }
  }

  return metrics.slice(0, 6);
}

// ── Section icon ────────────────────────────────────────────────────────

function sectionIcon(type: ReportSection["type"]) {
  const cls = "flex-shrink-0";
  switch (type) {
    case "conclusion": return <Target size={14} className={cls + " text-blue-500"} />;
    case "metrics": return <Hash size={14} className={cls + " text-green-500"} />;
    case "breakdown": return <PieChart size={14} className={cls + " text-purple-500"} />;
    case "trend": return <TrendingUp size={14} className={cls + " text-orange-500"} />;
    case "diagnosis": return <AlertTriangle size={14} className={cls + " text-amber-500"} />;
    case "recommendation": return <Lightbulb size={14} className={cls + " text-yellow-500"} />;
    case "scope": return <Info size={14} className={cls + " text-slate-400"} />;
    default: return <FileText size={14} className={cls + " text-slate-400"} />;
  }
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

  const sections = useMemo(
    () => (answer?.answer ? parseReportSections(answer.answer) : []),
    [answer?.answer],
  );

  const metrics = useMemo(
    () => (answer ? extractMetrics(answer, sections) : []),
    [answer, sections],
  );

  // Group artifacts: tables grouped by semantic_id prefix, charts linked to tables
  const tableArtifacts = artifacts.filter(a => a.type === "table");
  const chartArtifacts = artifacts.filter(a => a.type === "chart");
  const sqlArtifacts = artifacts.filter(a => a.type === "sql");

  if (!answer || (!isRealAnswer(answer) && !hasFindings && !hasCaveats && metrics.length === 0)) {
    return null;
  }

  return (
    <div className={`task-answer-card ${accentClass} animate-slide-up`}>

      {/* ── Metric cards row ── */}
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

      {/* ── Structured report sections ── */}
      {sections.length > 0 && (
        <div className="task-report-sections">
          {sections.map((s, i) => (
            <div key={i} className={`task-report-section task-section-${s.type}`}>
              {s.title && (
                <div className="task-report-section-head">
                  {sectionIcon(s.type)}
                  <span className="task-report-section-title">{s.title}</span>
                </div>
              )}
              <div className="task-report-section-body">
                <MarkdownContent content={s.content} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Key findings (when no structured sections) ── */}
      {hasFindings && sections.length === 0 && (
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

      {/* ── Per-unit artifacts: table + chart pairs ── */}
      {tableArtifacts.length > 0 && (
        <div className="task-answer-artifacts">
          <div className="task-answer-section-title">
            <Database size={12} /><span>查询结果</span>
          </div>
          <div className="task-artifacts-grid">
            {tableArtifacts.map((tableArt, ti) => {
              // Find chart that depends on this table
              const tableSem = tableArt.semantic_id || tableArt.id;
              const linkedCharts = chartArtifacts.filter(
                c => (c.depends_on || []).some((d: string) =>
                  d === tableSem || d === "result_table" || tableSem.includes(d) || d.includes(tableSem),
                ),
              );
              return (
                <div key={tableArt.id} className="task-unit-card">
                  {/* Table */}
                  <div className="task-unit-table">
                    <div className="task-artifact-item-head">
                      <Database size={11} className="text-green-500" />
                      <span>结果表 {tableArtifacts.length > 1 ? `#${ti + 1}` : ""}</span>
                      <span className="text-[10px] text-slate-400 ml-auto">
                        {tableArt.rows?.length || 0} 行 × {(tableArt.columns || []).length} 列
                      </span>
                    </div>
                    <div className="task-artifact-table-wrap">
                      <table className="task-artifact-table">
                        <thead>
                          <tr>
                            {(tableArt.columns || []).slice(0, 6).map((col: string, ci: number) => (
                              <th key={ci}>{col}</th>
                            ))}
                            {(tableArt.columns || []).length > 6 && <th>…</th>}
                          </tr>
                        </thead>
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
                        <div className="task-artifact-table-more">
                          仅显示前 10 行，共 {tableArt.rows.length} 行
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Linked chart */}
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
          <div className="task-answer-section-title">
            <Terminal size={12} /><span>SQL</span>
          </div>
          <div className="task-artifacts-grid">
            {sqlArtifacts.map(artifact => (
              <div key={artifact.id} className="task-artifact-item task-artifact-sql">
                <pre className="task-artifact-sql-pre">{artifact.sql}</pre>
                <div className="task-artifact-sql-actions">
                  <button className="task-artifact-btn" onClick={() => onOpenSqlConsole(artifact.sql)} type="button">
                    在 SQL 控制台打开
                  </button>
                  <button className="task-artifact-btn" onClick={() => {
                    navigator.clipboard.writeText(artifact.sql).then(() => onToast("SQL 已复制"), () => onToast("复制失败"));
                  }} type="button">
                    复制
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Caveats ── */}
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

      {/* ── Recommendations ── */}
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

      {/* ── Follow-up ── */}
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

      {/* ── Suggestion chips from run ── */}
      {suggestions && suggestions.length > 0 && !hasFollowUp && (
        <div className="task-answer-suggestions">
          <div className="task-answer-section-title"><span>你可能还想问</span></div>
          <div className="task-followup-chips">
            {suggestions.slice(0, 4).map((s, i) => (
              <button key={i} className="task-followup-chip" onClick={() => onSendFollowUp(s.question)} type="button">
                <span>{s.question}</span><ChevronRight size={11} />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function maxVal(series: Array<{ value: number }>): number {
  let max = 0;
  for (const s of series) { if (s.value > max) max = s.value; }
  return max;
}

function BarChartIcon({ size, className }: { size: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}
