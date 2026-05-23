import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Award,
  BarChart3,
  Check,
  CircleDot,
  Copy,
  Download,
  History,
  PencilLine,
  Play,
  Plus,
  ShieldAlert,
  Table,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, QueryHistory } from "../lib/api";
import { SqlEditor } from "../components/SqlEditor";
import { ChartPanel } from "../components/ChartPanel";
import { DataTable } from "../components/DataTable";
import { AiQueryInput } from "../components/AiQueryInput";
import { StatusIndicator } from "../components/StatusIndicator";
import { ExplainVisualizer } from "../components/ExplainVisualizer";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { AiBenchmarkDrawer } from "../components/AiBenchmarkDrawer";
import { useQueryExecution } from "../hooks/useQueryExecution";

interface QueryPageProps {
  datasource: DataSource;
}

type ViewTab = "results" | "history";
type ResultViewMode = "table" | "chart" | "explain";

export const QueryPage = ({ datasource }: QueryPageProps) => {
  const [activeBottomTab, setActiveBottomTab] = useState<ViewTab>("results");
  const [resultViewMode, setResultViewMode] = useState<ResultViewMode>("table");
  const [history, setHistory] = useState<QueryHistory[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [showAiConfig, setShowAiConfig] = useState(false);
  const [aiConfig, setAiConfig] = useState({
    apiKey: "",
    apiBase: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    optimizeRag: true,
  });

  // Benchmark drawer states
  const [showBenchmarkDrawer, setShowBenchmarkDrawer] = useState(false);
  const [goldenPresetQuestion, setGoldenPresetQuestion] = useState("");
  const [goldenPresetSql, setGoldenPresetSql] = useState("");

  const fetchHistory = async () => {
    try {
      setHistoryLoading(true);
      setHistory(await api.listHistory(datasource.id));
    } catch (e) {
      console.error("Failed to load query history:", e);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Initialize custom hook
  const {
    tabs,
    activeEditorTab,
    setActiveEditorTabId,
    validating,
    renamingTabId,
    renameDraft,
    handleAddTab,
    handleCloseTab,
    startRenaming,
    commitRename,
    setRenameDraft,
    updateActiveTab,
    handleValidateSql,
    handleExecuteSql,
    handleCancelQuery,
  } = useQueryExecution(datasource, () => {
    void fetchHistory();
  });

  useEffect(() => {
    setActiveBottomTab("results");
    void fetchHistory();
  }, [datasource.id]);

  const isExplainQuery = useMemo(() => {
    if (!activeEditorTab?.queryResult) return false;
    const cols = activeEditorTab.queryResult.columns;
    return (
      cols.includes("select_type") ||
      cols.includes("table") ||
      cols.includes("detail") ||
      cols.includes("selectid")
    );
  }, [activeEditorTab?.queryResult]);

  const isDirty = (tab: any) => tab.sql !== tab.savedSql;

  const handleCopySql = async () => {
    if (!activeEditorTab) return;
    await navigator.clipboard.writeText(activeEditorTab.sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const handleExportCsv = () => {
    if (!activeEditorTab?.queryResult) return;
    const { columns, rows } = activeEditorTab.queryResult;
    const escapeCsv = (val: unknown): string => {
      if (val === null) return "";
      const s = String(val);
      if (s.includes(",") || s.includes('"') || s.includes("\n")) {
        return `"${s.replace(/"/g, '""')}"`;
      }
      return s;
    };
    const header = columns.map(escapeCsv).join(",");
    const body = rows.map((row) => columns.map((c) => escapeCsv(row[c])).join(",")).join("\n");
    const csv = "\uFEFF" + header + "\n" + body;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `databox_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleAiGenerate = async () => {
    const question = aiQuestion.trim();
    if (!question) return;
    try {
      setAiGenerating(true);
      updateActiveTab(() => ({ queryError: null, queryResult: null, schemaValidationWarnings: [] }));
      const result = await api.generateSql(datasource.id, question, {
        apiKey: aiConfig.apiKey || undefined,
        apiBase: aiConfig.apiBase || undefined,
        model: aiConfig.model || undefined,
        optimizeRag: aiConfig.optimizeRag,
      });
      updateActiveTab(() => ({
        sql: result.sql,
        guardrail: result.guardrail,
        schemaValidationWarnings: result.schemaValidationWarnings || [],
        queryResult: null,
      }));
      if (result.guardrail.result === "reject") {
        updateActiveTab(() => ({ queryError: result.guardrail.message }));
      }
      setAiQuestion("");
    } catch (error: any) {
      updateActiveTab(() => ({ queryError: error.message ?? "AI 生成 SQL 失败" }));
    } finally {
      setAiGenerating(false);
    }
  };

  return (
    <div
      className="animate-fade-in"
      style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%", overflow: "hidden" }}
    >
      {/* ── AI Query Input ── */}
      <ErrorBoundary title="AI 智能问数面板加载异常">
        <AiQueryInput
          value={aiQuestion}
          onChange={setAiQuestion}
          onSubmit={() => void handleAiGenerate()}
          loading={aiGenerating}
          onToggleConfig={() => setShowAiConfig((v) => !v)}
          isDemo={datasource.database_name === "databox_demo" || datasource.name.includes("Demo")}
        />
      </ErrorBoundary>

      {/* ── LLM Config ── */}
      {showAiConfig && (
        <div className="lab-card animate-slide-down" style={{ padding: "14px 18px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div>
              <label className="field-label">API Key</label>
              <input
                className="input-field input-field-sm"
                type="password"
                placeholder="留空使用离线模式"
                value={aiConfig.apiKey}
                onChange={(e) => setAiConfig((c) => ({ ...c, apiKey: e.target.value }))}
              />
            </div>
            <div>
              <label className="field-label">API Base URL</label>
              <input
                className="input-field input-field-sm"
                placeholder="https://api.openai.com/v1"
                value={aiConfig.apiBase}
                onChange={(e) => setAiConfig((c) => ({ ...c, apiBase: e.target.value }))}
              />
            </div>
            <div>
              <label className="field-label">Model</label>
              <input
                className="input-field input-field-sm"
                placeholder="gpt-4o-mini"
                value={aiConfig.model}
                onChange={(e) => setAiConfig((c) => ({ ...c, model: e.target.value }))}
              />
            </div>

            <div
              style={{
                gridColumn: "span 3",
                display: "flex",
                alignItems: "center",
                gap: 8,
                borderTop: "1px solid var(--border-light)",
                paddingTop: 10,
                marginTop: 4,
              }}
            >
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                  fontSize: "0.82rem",
                  color: "var(--text-secondary)",
                  fontWeight: 500,
                }}
              >
                <input
                  type="checkbox"
                  checked={aiConfig.optimizeRag}
                  onChange={(e) => setAiConfig((c) => ({ ...c, optimizeRag: e.target.checked }))}
                  style={{ width: 14, height: 14, accentColor: "var(--accent-indigo)", cursor: "pointer" }}
                />
                启用智能 RAG 表选择器 (过滤无关表结构，节省 Token 成本并提高 AI 准确率)
              </label>
            </div>
          </div>
        </div>
      )}

      {/* ── Main Content: Editor + Guardrail ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.5fr minmax(280px, 0.85fr)",
          gap: 14,
          flex: 1,
          overflow: "hidden",
          minHeight: 0,
        }}
      >
        {/* Left: Editor + Results */}
        <div style={{ display: "grid", gridTemplateRows: "minmax(200px, 1fr) auto", gap: 14, overflow: "hidden" }}>
          {/* SQL Editor */}
          <div className="lab-card" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {/* Tab bar */}
            <div
              style={{
                borderBottom: "1px solid var(--border-light)",
                padding: "6px 10px 0",
                background: "var(--bg-secondary)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 4, overflowX: "auto", paddingBottom: 6 }}>
                {tabs.map((tab) => {
                  const dirty = isDirty(tab);
                  const isActive = tab.id === activeEditorTab?.id;
                  const isRenaming = renamingTabId === tab.id;
                  return (
                    <div
                      key={tab.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        padding: "6px 10px",
                        borderRadius: "6px 6px 0 0",
                        border: "1px solid",
                        borderColor: isActive ? "var(--border-light)" : "transparent",
                        borderBottomColor: isActive ? "var(--bg-surface)" : "transparent",
                        background: isActive ? "var(--bg-surface)" : "transparent",
                        minWidth: "fit-content",
                      }}
                    >
                      <button
                        onClick={() => setActiveEditorTabId(tab.id)}
                        onDoubleClick={() => startRenaming(tab)}
                        style={{
                          border: "none",
                          background: "transparent",
                          color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                          cursor: "pointer",
                          fontSize: "0.8rem",
                          fontWeight: isActive ? 600 : 500,
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        {dirty && <CircleDot size={10} style={{ color: "var(--accent-amber)" }} />}
                        {isRenaming ? (
                          <input
                            className="input-field input-field-sm"
                            value={renameDraft}
                            autoFocus
                            onChange={(e) => setRenameDraft(e.target.value)}
                            onBlur={commitRename}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitRename();
                              if (e.key === "Escape") {
                                setRenameDraft("");
                              }
                            }}
                            style={{ width: 100 }}
                          />
                        ) : (
                          <span>{tab.title}</span>
                        )}
                      </button>
                      {!isRenaming && (
                        <button onClick={() => startRenaming(tab)} className="btn-ghost" style={{ padding: 1 }}>
                          <PencilLine size={11} />
                        </button>
                      )}
                      {tabs.length > 1 && (
                        <button onClick={() => handleCloseTab(tab.id)} className="btn-ghost" style={{ padding: 1 }}>
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  );
                })}
                <button className="btn-ghost" onClick={handleAddTab} style={{ padding: "4px 8px", flexShrink: 0 }}>
                  <Plus size={13} />
                </button>
              </div>
            </div>

            {/* Toolbar */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 14px",
                borderBottom: "1px solid var(--border-light)",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8rem", color: "var(--text-muted)" }}>
                <span className="text-mono" style={{ fontWeight: 500, color: "var(--text-secondary)" }}>
                  {datasource.database_name}
                </span>
                {activeEditorTab && isDirty(activeEditorTab) && (
                  <span style={{ color: "var(--accent-amber)" }}>· 未执行</span>
                )}
                {activeEditorTab?.status === "running" && (
                  <span className="animate-pulse" style={{ color: "var(--accent-indigo)", fontWeight: 600 }}>
                    · 正在执行中...
                  </span>
                )}
                {activeEditorTab?.status === "timeout" && (
                  <span style={{ color: "var(--accent-red)", fontWeight: 600 }}>· 查询超时 ⚠️</span>
                )}
                {activeEditorTab?.status === "cancelled" && (
                  <span style={{ color: "var(--text-muted)" }}>· 已取消 🛑</span>
                )}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  className="btn-secondary"
                  style={{
                    padding: "5px 10px",
                    fontSize: "0.8rem",
                    color: "var(--accent-indigo)",
                    borderColor: "rgba(74, 91, 192, 0.2)",
                  }}
                  onClick={() => {
                    setGoldenPresetQuestion("");
                    setGoldenPresetSql("");
                    setShowBenchmarkDrawer(true);
                  }}
                >
                  <Award size={13} />
                  黄金测试集
                </button>
                <button className="btn-ghost" onClick={handleCopySql}>
                  {copied ? <Check size={13} /> : <Copy size={13} />}
                  {copied ? "已复制" : "复制"}
                </button>
                <button
                  className="btn-secondary"
                  style={{ padding: "5px 10px", fontSize: "0.8rem" }}
                  onClick={handleValidateSql}
                  disabled={validating || !activeEditorTab || activeEditorTab.status === "running"}
                >
                  <ShieldAlert size={13} />
                  校验
                </button>

                {/* Cancellable Execution Button */}
                {activeEditorTab?.status === "running" ? (
                  <button
                    className="btn-secondary shadow-sm hover-lift animate-pulse"
                    style={{
                      padding: "5px 14px",
                      fontSize: "0.82rem",
                      color: "var(--accent-red)",
                      borderColor: "rgba(220, 38, 38, 0.2)",
                      fontWeight: 600,
                    }}
                    onClick={() => handleCancelQuery(activeEditorTab.id)}
                  >
                    <X size={13} />
                    取消执行
                  </button>
                ) : (
                  <button
                    className="btn-primary"
                    style={{ padding: "5px 14px", fontSize: "0.82rem" }}
                    onClick={() => handleExecuteSql(30000)} // Default to 30s timeout
                    disabled={!activeEditorTab}
                  >
                    <Play size={13} />
                    执行
                  </button>
                )}
              </div>
            </div>

            {/* Editor */}
            <div style={{ flex: 1, minHeight: 0 }}>
              <SqlEditor
                value={activeEditorTab?.sql ?? ""}
                onChange={(v) => updateActiveTab(() => ({ sql: v }))}
              />
            </div>
          </div>

          {/* Results / History */}
          <div
            className="lab-card"
            style={{ display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 180 }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 14px",
                borderBottom: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
              }}
            >
              <div className="pill-tabs">
                <button
                  className={`pill-tab ${activeBottomTab === "results" ? "active" : ""}`}
                  onClick={() => setActiveBottomTab("results")}
                >
                  <Table size={13} />
                  结果
                </button>
                <button
                  className={`pill-tab ${activeBottomTab === "history" ? "active" : ""}`}
                  onClick={() => setActiveBottomTab("history")}
                >
                  <History size={13} />
                  历史
                </button>
              </div>
              {activeEditorTab?.queryError && (
                <span
                  className="status-badge status-badge-error"
                  style={{
                    maxWidth: 320,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {activeEditorTab.queryError}
                </span>
              )}
            </div>

            <div style={{ flex: 1, overflow: "auto" }}>
              {activeBottomTab === "results" && (
                <>
                  {!activeEditorTab?.queryResult ? (
                    <div className="empty-state" style={{ padding: 36 }}>
                      <div className="empty-state-desc">
                        {activeEditorTab?.status === "running"
                          ? "SQL 正在安全执行中，请稍候..."
                          : "执行安全 SQL 后，这里会展示查询结果"}
                      </div>
                    </div>
                  ) : (
                    <div>
                      {/* Result meta bar */}
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "6px 16px",
                          borderBottom: "1px solid var(--border-light)",
                          fontSize: "0.78rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <div style={{ display: "flex", gap: 16 }}>
                          <span>
                            行数:{" "}
                            <strong style={{ color: "var(--text-primary)" }}>
                              {activeEditorTab.queryResult.rowCount}
                            </strong>
                          </span>
                          <span>
                            列数:{" "}
                            <strong style={{ color: "var(--text-primary)" }}>
                              {activeEditorTab.queryResult.columns.length}
                            </strong>
                          </span>
                          <span>
                            耗时:{" "}
                            <strong style={{ color: "var(--text-primary)" }}>
                              {activeEditorTab.queryResult.latencyMs}ms
                            </strong>
                          </span>
                        </div>
                        <div style={{ display: "flex", gap: 4 }}>
                          {isExplainQuery && (
                            <button
                              className={resultViewMode === "explain" ? "btn-primary" : "btn-secondary"}
                              style={{ padding: "3px 8px", fontSize: "0.74rem" }}
                              onClick={() => setResultViewMode("explain")}
                            >
                              <Activity size={12} /> 执行计划树
                            </button>
                          )}
                          <button
                            className={resultViewMode === "table" ? "btn-primary" : "btn-secondary"}
                            style={{ padding: "3px 8px", fontSize: "0.74rem" }}
                            onClick={() => setResultViewMode("table")}
                          >
                            <Table size={12} /> 表格
                          </button>
                          <button
                            className={resultViewMode === "chart" ? "btn-primary" : "btn-secondary"}
                            style={{ padding: "3px 8px", fontSize: "0.74rem" }}
                            onClick={() => setResultViewMode("chart")}
                          >
                            <BarChart3 size={12} /> 图表
                          </button>
                          <button
                            className="btn-ghost"
                            style={{ fontSize: "0.74rem" }}
                            onClick={handleExportCsv}
                          >
                            <Download size={12} /> CSV
                          </button>
                        </div>
                      </div>

                      {/* Performance Latency Breakdown Timeline */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "6px 16px",
                          background: "var(--bg-secondary)",
                          borderBottom: "1px solid var(--border-light)",
                          fontSize: "0.74rem",
                          gap: 12,
                          flexWrap: "wrap",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)" }}>
                          <span>⏱️ 耗时拆解:</span>
                          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                            <span>连接: <strong style={{ color: "var(--text-primary)" }}>{activeEditorTab.queryResult.connectMs ?? 0}ms</strong></span>
                            <span>安全过滤: <strong style={{ color: "var(--text-primary)" }}>{activeEditorTab.queryResult.guardrailMs ?? 0}ms</strong></span>
                            <span>引擎执行: <strong style={{ color: "var(--text-primary)" }}>{activeEditorTab.queryResult.executeMs ?? 0}ms</strong></span>
                            <span>拉取: <strong style={{ color: "var(--text-primary)" }}>{activeEditorTab.queryResult.fetchMs ?? 0}ms</strong></span>
                            <span>序列化: <strong style={{ color: "var(--text-primary)" }}>{activeEditorTab.queryResult.serializeMs ?? 0}ms</strong></span>
                          </div>
                        </div>
                        
                        {(() => {
                          const r = activeEditorTab.queryResult;
                          const c = r.connectMs ?? 0;
                          const g = r.guardrailMs ?? 0;
                          const e = r.executeMs ?? 0;
                          const f = r.fetchMs ?? 0;
                          const s = r.serializeMs ?? 0;
                          const total = Math.max(1, c + g + e + f + s);
                          const pc = (c / total) * 100;
                          const pg = (g / total) * 100;
                          const pe = (e / total) * 100;
                          const pf = (f / total) * 100;
                          const ps = (s / total) * 100;
                          return (
                            <div
                              style={{
                                display: "flex",
                                width: 140,
                                height: 6,
                                borderRadius: 3,
                                overflow: "hidden",
                                background: "rgba(0,0,0,0.1)",
                              }}
                              title={`总计耗时拆解 (连接: ${c}ms, 安全: ${g}ms, 执行: ${e}ms, 拉取: ${f}ms, 序列化: ${s}ms)`}
                            >
                              <div style={{ width: `${pc}%`, background: "#10B981" }} title={`连接: ${c}ms`} />
                              <div style={{ width: `${pg}%`, background: "#3B82F6" }} title={`安全: ${g}ms`} />
                              <div style={{ width: `${pe}%`, background: "#8B5CF6" }} title={`执行: ${e}ms`} />
                              <div style={{ width: `${pf}%`, background: "#F59E0B" }} title={`拉取: ${f}ms`} />
                              <div style={{ width: `${ps}%`, background: "#EF4444" }} title={`序列化: ${s}ms`} />
                            </div>
                          );
                        })()}
                      </div>

                      {/* Warnings Alert */}
                      {activeEditorTab.queryResult.warnings && activeEditorTab.queryResult.warnings.length > 0 && (
                        <div
                          className="animate-fade-in"
                          style={{
                            background: "rgba(245, 158, 11, 0.08)",
                            borderBottom: "1px dashed rgba(245, 158, 11, 0.2)",
                            padding: "8px 16px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 4,
                            fontSize: "0.78rem",
                            color: "var(--accent-amber)",
                          }}
                        >
                          {activeEditorTab.queryResult.warnings.map((warn, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{ fontSize: "10px" }}>⚠️</span>
                              <span>{warn}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {resultViewMode === "explain" && isExplainQuery ? (
                        <div style={{ padding: 12 }}>
                          <ErrorBoundary title="执行计划可视化解析异常">
                            <ExplainVisualizer
                              columns={activeEditorTab.queryResult.columns}
                              rows={activeEditorTab.queryResult.rows}
                            />
                          </ErrorBoundary>
                        </div>
                      ) : resultViewMode === "table" ? (
                        <ErrorBoundary title="数据网格 (DataTable) 渲染崩溃">
                          <DataTable
                            columns={activeEditorTab.queryResult.columns}
                            rows={activeEditorTab.queryResult.rows}
                            maxHeight="360px"
                          />
                        </ErrorBoundary>
                      ) : (
                        <div style={{ padding: 12 }}>
                          <ErrorBoundary title="数据分析图表 (ChartPanel) 渲染崩溃">
                            <ChartPanel
                              columns={activeEditorTab.queryResult.columns}
                              rows={activeEditorTab.queryResult.rows}
                            />
                          </ErrorBoundary>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}

              {activeBottomTab === "history" && (
                <>
                  {historyLoading ? (
                    <div style={{ padding: 24 }}>
                      {[1, 2, 3].map((i) => (
                        <div key={i} className="skeleton" style={{ height: 40, marginBottom: 6, borderRadius: 4 }} />
                      ))}
                    </div>
                  ) : history.length === 0 ? (
                    <div className="empty-state" style={{ padding: 36 }}>
                      <div className="empty-state-desc">还没有执行历史，执行一条 SQL 试试</div>
                    </div>
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>时间</th>
                          <th>SQL</th>
                          <th>审核</th>
                          <th>状态</th>
                          <th>行数</th>
                          <th>耗时</th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((item) => (
                          <tr key={item.id}>
                            <td style={{ whiteSpace: "nowrap", fontSize: "0.8rem" }}>
                              {new Date(item.created_at).toLocaleString("zh-CN", {
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </td>
                            <td
                              className="text-mono"
                              style={{
                                maxWidth: 240,
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                fontSize: "0.78rem",
                              }}
                            >
                              {item.executed_sql || item.safe_sql || item.submitted_sql}
                            </td>
                            <td>
                              <StatusIndicator
                                type={
                                  item.guardrail_result === "pass"
                                    ? "success"
                                    : item.guardrail_result === "warn"
                                    ? "warning"
                                    : "error"
                                }
                                size="sm"
                              />
                            </td>
                            <td>
                              <span
                                style={{
                                  color:
                                    item.execution_status === "success"
                                      ? "var(--accent-green)"
                                      : "var(--accent-red)",
                                  fontSize: "0.8rem",
                                }}
                              >
                                {item.execution_status}
                              </span>
                            </td>
                            <td className="cell-number">{item.rows_returned}</td>
                            <td className="cell-number">{item.execution_time_ms}ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right: Guardrail Panel */}
        <div className="lab-card" style={{ padding: 18, overflow: "auto" }}>
          <h3
            style={{
              fontSize: "0.92rem",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 16,
            }}
          >
            <ShieldAlert size={16} style={{ color: "var(--accent-indigo)" }} />
            Guardrail 安全审核
          </h3>

          {!activeEditorTab?.guardrail ? (
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", lineHeight: 1.7 }}>
              <p>点击「校验」或「执行」按钮后，这里会展示安全审核结果。</p>
              <div className="divider-spaced" />
              <p style={{ fontSize: "0.78rem" }}>
                Guardrail 会检查：危险语句、系统库访问、危险函数、多语句、无 LIMIT 等。
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Result badge */}
              <div>
                <StatusIndicator
                  type={
                    activeEditorTab.guardrail.result === "pass"
                      ? "success"
                      : activeEditorTab.guardrail.result === "warn"
                      ? "warning"
                      : "error"
                  }
                  label={
                    activeEditorTab.guardrail.result === "pass"
                      ? "通过"
                      : activeEditorTab.guardrail.result === "warn"
                      ? "警告"
                      : "拒绝"
                  }
                />
              </div>

              <p style={{ fontSize: "0.84rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                {activeEditorTab.guardrail.message}
              </p>

              {/* Safe SQL */}
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.8rem", marginBottom: 6, color: "var(--text-secondary)" }}>
                  安全 SQL
                </div>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    background: "var(--bg-secondary)",
                    padding: 12,
                    borderRadius: 6,
                    fontSize: "0.8rem",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-light)",
                    lineHeight: 1.6,
                  }}
                >
                  {activeEditorTab.guardrail.safeSql || "-"}
                </pre>
              </div>

              {/* Checks */}
              {activeEditorTab.guardrail.checks.length > 0 && (
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.8rem", marginBottom: 8, color: "var(--text-secondary)" }}>
                    检查项 ({activeEditorTab.guardrail.checks.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {activeEditorTab.guardrail.checks.map((item, i) => (
                      <div
                        key={`${item.rule}-${i}`}
                        className="lab-card-accent"
                        style={{
                          padding: "8px 12px",
                          borderLeftColor: item.level === "reject" ? "var(--accent-red)" : "var(--accent-amber)",
                          background: item.level === "reject" ? "var(--accent-red-light)" : "var(--accent-amber-light)",
                          fontSize: "0.78rem",
                        }}
                      >
                        <span style={{ fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: "0.72rem" }}>
                          {item.rule}
                        </span>
                        <span style={{ marginLeft: 6, color: "var(--text-secondary)" }}>{item.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Schema Validation Warnings */}
              {activeEditorTab.schemaValidationWarnings && activeEditorTab.schemaValidationWarnings.length > 0 && (
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.8rem", marginBottom: 8, color: "var(--accent-amber)", display: "flex", alignItems: "center", gap: 4 }}>
                    <ShieldAlert size={14} style={{ color: "var(--accent-amber)" }} />
                    AI 字段存在性校验警告 ({activeEditorTab.schemaValidationWarnings.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {activeEditorTab.schemaValidationWarnings.map((item, i) => (
                      <div
                        key={`schema-warn-${i}`}
                        className="lab-card-accent"
                        style={{
                          padding: "8px 12px",
                          borderLeftColor: "var(--accent-amber)",
                          background: "var(--accent-amber-light)",
                          fontSize: "0.78rem",
                          color: "var(--text-primary)",
                          borderRadius: 4,
                        }}
                      >
                        <span style={{ fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: "0.72rem", color: "var(--accent-amber)", marginRight: 6 }}>
                          hallucination
                        </span>
                        <span style={{ color: "var(--text-primary)" }}>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Save as Golden SQL Shortcut */}
              <div style={{ borderTop: "1px solid var(--border-light)", paddingTop: 12, marginTop: 4 }}>
                <button
                  className="btn-secondary"
                  style={{
                    width: "100%",
                    justifyContent: "center",
                    fontSize: "0.78rem",
                    padding: "6px 10px",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    color: "var(--accent-indigo)",
                    borderColor: "rgba(74, 91, 192, 0.2)",
                  }}
                  onClick={() => {
                    setGoldenPresetQuestion(activeEditorTab.title || "");
                    setGoldenPresetSql(activeEditorTab.sql);
                    setShowBenchmarkDrawer(true);
                  }}
                >
                  <Award size={13} />
                  另存为 Golden SQL (加入 Benchmark)
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Golden SQL Benchmark Drawer ── */}
      {showBenchmarkDrawer && (
        <AiBenchmarkDrawer
          datasource={datasource}
          aiConfig={aiConfig}
          initialQuestion={goldenPresetQuestion}
          initialSql={goldenPresetSql}
          onClose={() => setShowBenchmarkDrawer(false)}
        />
      )}
    </div>
  );
};
