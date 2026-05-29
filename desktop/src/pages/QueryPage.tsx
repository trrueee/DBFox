import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Award,
  BarChart3,
  Check,
  Copy,
  Database,
  Download,
  History,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
  Sparkles,
  Table,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, ERDiagramData, QueryHistory } from "../lib/api";
import { SqlEditor } from "../components/SqlEditor";
import { DataTable } from "../components/DataTable";
import { AiQueryInput } from "../components/AiQueryInput";
import { StatusIndicator } from "../components/StatusIndicator";
import { ExplainVisualizer } from "../components/ExplainVisualizer";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { AiBenchmarkDrawer } from "../components/AiBenchmarkDrawer";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useQueryExecution, type QueryTabState } from "../hooks/useQueryExecution";
import { actionRegistry, type ParsedAction, planHasErrors, planWarnings } from "../lib/queryActions";

interface QueryPageProps {
  datasource: DataSource;
  initialDraft?: {
    sql: string;
    title?: string;
    nonce: number;
  } | null;
  actionTrigger?: {
    type: "execute" | "stop" | "validate" | "export" | "format";
    nonce: number;
  };
  onStateChange?: (state: {
    resultState?: "idle" | "running" | "success" | "error" | "cancelled" | "timeout";
    sqlDraft?: string;
    dirty?: boolean;
  }) => void;
}

type ViewTab = "results" | "history";
type ResultViewMode = "table" | "chart" | "explain";

const ChartPanel = lazy(() =>
  import("../components/ChartPanel").then((module) => ({ default: module.ChartPanel })),
);

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export const QueryPage = ({ datasource, initialDraft, actionTrigger, onStateChange }: QueryPageProps) => {
  const [activeBottomTab, setActiveBottomTab] = useState<ViewTab>("results");
  const [resultViewMode, setResultViewMode] = useState<ResultViewMode>("table");
  const [history, setHistory] = useState<QueryHistory[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyMutating, setHistoryMutating] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [historyStatus, setHistoryStatus] = useState<"all" | "success" | "failed" | "timeout" | "cancelled">("all");
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

  const [showAiInput, setShowAiInput] = useState(false);
  const [showGuardrailDrawer, setShowGuardrailDrawer] = useState(false);
  const handledActionNonceRef = useRef<number | undefined>(undefined);
  const [editorHeight, setEditorHeight] = useState(() => {
    const saved = localStorage.getItem("databox_editor_height");
    return saved ? Number(saved) : 320;
  });

  useEffect(() => {
    localStorage.setItem("databox_editor_height", String(editorHeight));
  }, [editorHeight]);

  const handleHeightDragMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.pageY;
    const startHeight = editorHeight;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.pageY - startY;
      setEditorHeight(Math.max(120, Math.min(800, startHeight + deltaY)));
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

  const fetchHistory = useCallback(async () => {
    try {
      setHistoryLoading(true);
      setHistory(
        await api.listHistory(datasource.id, {
          search: historySearch.trim() || undefined,
          status: historyStatus,
          limit: 100,
        }),
      );
    } catch (e) {
      console.error("Failed to load query history:", e);
    } finally {
      setHistoryLoading(false);
    }
  }, [datasource.id, historySearch, historyStatus]);

  // Initialize custom hook
  const {
    activeEditorTab,
    validating,
    handleAddTab,
    handleCloseTab,
    updateActiveTab,
    openSqlDraft,
    handleValidateSql,
    handleExecuteSql,
    handleCancelQuery,
    confirmRequest,
    resolveConfirm,
  } = useQueryExecution(datasource, () => {
    void fetchHistory();
  });

  const toast = useToast();
  const [schemaTables, setSchemaTables] = useState<ERDiagramData["nodes"]>([]);

  const fetchSchemaMetadata = useCallback(async () => {
    try {
      const data = await api.getERDiagram(datasource.id);
      setSchemaTables(data.nodes || []);
    } catch (e) {
      console.error("Failed to fetch schema metadata for autocomplete:", e);
      setSchemaTables([]);
    }
  }, [datasource.id]);

  const initialDraftSql = initialDraft?.sql;
  const initialDraftTitle = initialDraft?.title;
  const initialDraftNonce = initialDraft?.nonce;
  const actionTriggerType = actionTrigger?.type;
  const actionTriggerNonce = actionTrigger?.nonce;

  useEffect(() => {
    setActiveBottomTab("results");
    void fetchSchemaMetadata();
  }, [fetchSchemaMetadata]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchHistory();
    }, 220);
    return () => window.clearTimeout(timer);
  }, [fetchHistory]);

  useEffect(() => {
    if (!initialDraftSql) return;
    openSqlDraft(initialDraftSql, initialDraftTitle);
    setActiveBottomTab("results");
  }, [initialDraftNonce, initialDraftSql, initialDraftTitle, openSqlDraft]);

  // Synchronize state with parent Tab Bar
  useEffect(() => {
    if (activeEditorTab && onStateChange) {
      onStateChange({
        resultState: activeEditorTab.status,
        sqlDraft: activeEditorTab.sql,
        dirty: activeEditorTab.sql !== activeEditorTab.savedSql
      });
    }
  }, [activeEditorTab, onStateChange]);

  const handleExportCsv = useCallback(() => {
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
  }, [activeEditorTab?.queryResult]);

  // Handle parent toolbar trigger nonces
  useEffect(() => {
    if (!actionTriggerType || actionTriggerNonce === undefined) return;
    if (handledActionNonceRef.current === actionTriggerNonce) return;
    handledActionNonceRef.current = actionTriggerNonce;
    const executeAction = async () => {
      if (actionTriggerType === "execute") {
        handleExecuteWithDirectives(30000);
      } else if (actionTriggerType === "stop") {
        if (activeEditorTab) {
          handleCancelQuery(activeEditorTab.id);
        }
      } else if (actionTriggerType === "validate") {
        await handleValidateSql();
      } else if (actionTriggerType === "export") {
        handleExportCsv();
      } else if (actionTriggerType === "format") {
        if (activeEditorTab) {
          const sqlKeywords = [
            "select", "from", "where", "join", "left", "right", "inner", "on", "group by", "order by", "limit",
            "insert", "update", "delete", "create", "drop", "alter", "table", "and", "or", "not", "null", "as",
            "having", "in", "like", "between", "exists", "union", "all", "is", "into", "values", "set"
          ];
          let formatted = activeEditorTab.sql;
          sqlKeywords.forEach(kw => {
            const regex = new RegExp(`\\b${kw}\\b`, 'gi');
            formatted = formatted.replace(regex, kw.toUpperCase());
          });
          updateActiveTab(() => ({ sql: formatted }));
        }
      }
    };
    void executeAction();
  }, [
    actionTriggerNonce,
    actionTriggerType,
    activeEditorTab,
    handleCancelQuery,
    handleExecuteSql,
    handleExportCsv,
    handleValidateSql,
    updateActiveTab,
  ]);
  const handleAiOptimizeSql = async () => {
    if (!activeEditorTab?.sql.trim()) return;
    try {
      setAiGenerating(true);
      updateActiveTab(() => ({ queryError: null }));
      const prompt = `针对以下 SQL 进行性能优化分析，并只返回优化后的标准 SQL 语句，同时说明优化点：\n\n${activeEditorTab.sql}`;
      const result = await api.generateSql(datasource.id, prompt);
      if (result.sql) {
        updateActiveTab(() => ({ sql: result.sql }));
        toast.toast("SQL 优化完成，已应用到编辑器", "success");
      } else {
        toast.toast("AI 未返回优化后的 SQL", "warning");
      }
    } catch (e: unknown) {
      toast.toast(`优化失败: ${getErrorMessage(e, "AI SQL optimization failed")}`, "error");
    } finally {
      setAiGenerating(false);
    }
  };

  const handleAiExplainSql = async () => {
    if (!activeEditorTab?.sql.trim()) return;
    try {
      setAiGenerating(true);
      updateActiveTab(() => ({ queryError: null }));
      const prompt = `请用中文解释以下 SQL 的查询意图、关联字段逻辑以及运行过程：\n\n${activeEditorTab.sql}`;
      const result = await api.generateSql(datasource.id, prompt);
      if (result.sql || (result.guardrail && result.guardrail.message)) {
        updateActiveTab(() => ({
          queryError: `【AI 解释 SQL】\n${result.guardrail?.message || "无安全问题"}\n\n【逻辑流程分析】\n${result.sql || "已完成逻辑解释"}`
        }));
        toast.toast("SQL 解释生成成功", "success");
      }
    } catch (e: unknown) {
      toast.toast(`解释失败: ${getErrorMessage(e, "AI SQL explanation failed")}`, "error");
    } finally {
      setAiGenerating(false);
    }
  };

  const handleInjectLimit = () => {
    if (!activeEditorTab?.sql.trim()) return;
    let sql = activeEditorTab.sql.trim();
    if (/limit\s+\d+/i.test(sql)) {
      toast.toast("SQL 已包含 LIMIT 限制", "info");
      return;
    }
    if (sql.endsWith(";")) {
      sql = sql.slice(0, -1);
    }
    sql += " LIMIT 100;";
    updateActiveTab(() => ({ sql }));
    toast.toast("已成功注入 LIMIT 100 保护", "success");
  };

  const handleFormatSql = () => {
    if (!activeEditorTab?.sql.trim()) return;
    const sqlKeywords = [
      "select", "from", "where", "join", "left", "right", "inner", "on", "group by", "order by", "limit",
      "insert", "update", "delete", "create", "drop", "alter", "table", "and", "or", "not", "null", "as",
      "having", "in", "like", "between", "exists", "union", "all", "is", "into", "values", "set",
    ];
    let formatted = activeEditorTab.sql;
    sqlKeywords.forEach((kw) => {
      const regex = new RegExp(`\\b${kw}\\b`, "gi");
      formatted = formatted.replace(regex, kw.toUpperCase());
    });
    updateActiveTab(() => ({ sql: formatted }));
    toast.toast("SQL 关键字已格式化", "success");
  };

  const handleRunExplain = async () => {
    if (!activeEditorTab?.sql.trim()) return;
    const sql = activeEditorTab.sql.trim();
    if (/^\s*explain\s/i.test(sql)) {
      toast.toast("SQL 已是 EXPLAIN 查询，直接执行即可", "info");
      return;
    }
    updateActiveTab(() => ({ sql: `EXPLAIN ${sql}` }));
    // Auto-execute after a brief delay to let the editor update
    setTimeout(() => {
      handleExecuteSql(30000);
    }, 100);
  };

  const handleCopyResultJson = () => {
    if (!activeEditorTab?.queryResult) return;
    const { columns, rows } = activeEditorTab.queryResult;
    const json = JSON.stringify(rows.map((row) => {
      const obj: Record<string, unknown> = {};
      columns.forEach((c) => { obj[c] = row[c] ?? null; });
      return obj;
    }), null, 2);
    navigator.clipboard.writeText(json).then(() => {
      toast.toast(`已复制 ${rows.length} 行 JSON`, "success");
    }).catch(() => toast.toast("复制失败", "error"));
  };

  const handleCopyResultInsert = () => {
    if (!activeEditorTab?.queryResult) return;
    const { columns, rows } = activeEditorTab.queryResult;
    const tableName = "table_name";
    const inserts = rows.map((row) => {
      const vals = columns.map((c) => {
        const v = row[c];
        if (v === null || v === undefined) return "NULL";
        if (typeof v === "number" || typeof v === "bigint") return String(v);
        if (typeof v === "boolean") return v ? "1" : "0";
        const s = String(v).replace(/\\/g, "\\\\").replace(/'/g, "''");
        return `'${s}'`;
      });
      return `INSERT INTO \`${tableName}\` (${columns.map((c) => `\`${c}\``).join(", ")})\nVALUES (${vals.join(", ")});`;
    }).join("\n\n");
    navigator.clipboard.writeText(inserts).then(() => {
      toast.toast(`已复制 ${rows.length} 行 INSERT`, "success");
    }).catch(() => toast.toast("复制失败", "error"));
  };

  // ── @ 查询动作（ExecutionPlan 架构：sourceText 永不污染，只改 compiledSql）──

  const activeDirectives = useMemo<ParsedAction[]>(() => {
    if (!activeEditorTab?.sql) return [];
    return actionRegistry.parseAll(activeEditorTab.sql).actions;
  }, [activeEditorTab?.sql]);

  const handleExecuteWithDirectives = useCallback(
    (_timeoutMs: number = 30000) => {
      if (!activeEditorTab?.sql.trim()) return;

      const plan = actionRegistry.finalize(activeEditorTab.sql);

      // 致命错误 → 阻止执行，展示给用户
      if (planHasErrors(plan)) {
        const msg = plan.issues
          .filter((i) => i.level === "error")
          .map((e) => `• [${e.code}] ${e.message}`)
          .join("\n");
        updateActiveTab(() => ({
          queryError: `查询动作配置错误:\n${msg}`,
          queryResult: null,
        }));
        return;
      }

      // 警告 → toast 提示，不阻止执行
      for (const w of planWarnings(plan)) {
        toast.toast(`[${w.code}] ${w.message}`, "warning");
      }

      // beforeExecute 阶段（如 @timeout 设置超时）
      actionRegistry.applyPhase(plan, "beforeExecute");

      // 执行：传入 compiledSql，不修改编辑器源码
      void handleExecuteSql(plan.context.timeoutMs, plan.compiledSql);
    },
    [activeEditorTab, updateActiveTab, handleExecuteSql, toast],
  );

  const handleRemoveDirective = useCallback(
    (index: number) => {
      if (!activeEditorTab) return;
      const lines = activeEditorTab.sql.split("\n");
      let dirIdx = 0;
      const newLines = lines.filter((line) => {
        if (/^\s*@\w+/.test(line.trim())) {
          if (dirIdx === index) {
            dirIdx++;
            return false;
          }
          dirIdx++;
        }
        return true;
      });
      updateActiveTab(() => ({ sql: newLines.join("\n") }));
    },
    [activeEditorTab, updateActiveTab],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;

      if (e.key === "Enter") {
        e.preventDefault();
        if (e.shiftKey) {
          void handleValidateSql();
        } else {
          void handleExecuteWithDirectives(30000);
        }
        return;
      }

      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        handleAddTab();
        return;
      }

      if (e.key === "w" || e.key === "W") {
        e.preventDefault();
        if (activeEditorTab) {
          void handleCloseTab(activeEditorTab.id);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeEditorTab, handleValidateSql, handleExecuteWithDirectives, handleAddTab, handleCloseTab]);

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

  const isDirty = (tab: QueryTabState) => tab.sql !== tab.savedSql;

  const handleCopySql = async () => {
    if (!activeEditorTab) return;
    await navigator.clipboard.writeText(activeEditorTab.sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const getHistorySql = (item: QueryHistory) =>
    item.executed_sql || item.safe_sql || item.generated_sql || item.submitted_sql || "";

  const handleReuseHistory = (item: QueryHistory) => {
    const sql = getHistorySql(item);
    if (!sql) return;
    openSqlDraft(sql, item.question || "历史查询");
    setActiveBottomTab("results");
  };

  const [deleteConfirm, setDeleteConfirm] = useState<{ item: QueryHistory } | null>(null);
  const [clearConfirm, setClearConfirm] = useState(false);

  const handleDeleteHistory = async (item: QueryHistory) => {
    setDeleteConfirm({ item });
  };

  const doDeleteHistory = async () => {
    const item = deleteConfirm?.item;
    if (!item) return;
    setDeleteConfirm(null);
    try {
      setHistoryMutating(true);
      await api.deleteHistory(item.id);
      setHistory((prev) => prev.filter((h) => h.id !== item.id));
      toast.toast("查询历史已删除", "success");
    } catch (e: unknown) {
      toast.toast(getErrorMessage(e, "删除查询历史失败"), "error");
    } finally {
      setHistoryMutating(false);
    }
  };

  const doClearHistory = async () => {
    setClearConfirm(false);
    try {
      setHistoryMutating(true);
      await api.clearHistory(datasource.id);
      setHistory([]);
      toast.toast("查询历史已清空", "success");
    } catch (e: unknown) {
      toast.toast(getErrorMessage(e, "清空查询历史失败"), "error");
    } finally {
      setHistoryMutating(false);
    }
  };

  const formatHistoryStatus = (status: QueryHistory["execution_status"] | string) => {
    switch (status) {
      case "success":
        return "成功";
      case "failed":
        return "失败";
      case "timeout":
        return "超时";
      case "cancelled":
        return "已取消";
      default:
        return status || "-";
    }
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
    } catch (error: unknown) {
      updateActiveTab(() => ({ queryError: getErrorMessage(error, "AI 生成 SQL 失败") }));
    } finally {
      setAiGenerating(false);
    }
  };

  return (
    <div
      className="animate-fade-in"
      style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%", overflow: "hidden" }}
    >
      <style>{`
        .row-splitter {
          transition: background 0.15s, border-color 0.15s;
          border-top: 1px solid var(--border-light);
          border-bottom: 1px solid var(--border-light);
        }
        .row-splitter:hover {
          background: var(--bg-secondary) !important;
        }
        .row-splitter:hover div {
          background: var(--accent-indigo) !important;
        }
        .animate-slide-left {
          animation: slideLeft 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes slideLeft {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
      `}</style>

      {/* 鈹€鈹€ Collapsible AI Query Input 鈹€鈹€ */}
      {showAiInput && (
        <ErrorBoundary title="AI 智能问数面板加载异常">
          <div className="animate-slide-down">
            <AiQueryInput
              value={aiQuestion}
              onChange={setAiQuestion}
              onSubmit={() => void handleAiGenerate()}
              loading={aiGenerating}
              onToggleConfig={() => setShowAiConfig((v) => !v)}
              isDemo={datasource.database_name === "databox_demo" || datasource.name.includes("Demo")}
            />
          </div>
        </ErrorBoundary>
      )}

      {/* 鈹€鈹€ LLM Config 鈹€鈹€ */}
      {showAiConfig && showAiInput && (
        <div className="lab-card animate-slide-down" style={{ padding: "14px 18px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div>
              <label className="field-label">API Key</label>
              <input
                className="input-field input-field-sm"
                type="password"
                placeholder="鐣欑┖浣跨敤绂荤嚎妯″紡"
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
                启用智能 RAG 表选择器（过滤无关表结构，节省 Token 成本并提高 AI 准确率）
              </label>
            </div>
          </div>
        </div>
      )}

      {/* 鈹€鈹€ Main Content: SQL Workspace with Collapsible splits 鈹€鈹€ */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          overflow: "hidden",
          minHeight: 0,
        }}
      >
        {/* SQL Editor (Draggable height) */}
        <div
          className="lab-card"
          style={{
            height: editorHeight,
            minHeight: 120,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >


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
                <span style={{ color: "var(--accent-amber)" }}>• 未执行</span>
              )}
              {activeEditorTab?.status === "running" && (
                <span className="animate-pulse" style={{ color: "var(--accent-indigo)", fontWeight: 600 }}>
                  • 正在执行中...
                </span>
              )}
              {activeEditorTab?.status === "timeout" && (
                <span style={{ color: "var(--accent-red)", fontWeight: 600 }}>• 查询超时</span>
              )}
              {activeEditorTab?.status === "cancelled" && (
                <span style={{ color: "var(--text-muted)" }}>• 已取消</span>
              )}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className={`btn-secondary ${showAiInput ? "active" : ""}`}
                style={{
                  padding: "5px 10px",
                  fontSize: "0.8rem",
                  color: showAiInput ? "var(--accent-indigo)" : "var(--text-secondary)",
                  borderColor: showAiInput ? "var(--accent-indigo)" : "var(--border-light)",
                  background: showAiInput ? "var(--bg-active)" : "var(--bg-surface)",
                }}
                onClick={() => setShowAiInput(!showAiInput)}
              >
                <Sparkles size={13} style={{ color: "var(--accent-indigo)" }} />
                AI 智能问数
              </button>
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

              {/* Inline Editor AI Actions */}
              <button
                className="btn-secondary"
                style={{ padding: "5px 10px", fontSize: "0.8rem", color: "var(--accent-indigo)", borderColor: "rgba(74, 91, 192, 0.2)", background: "rgba(74, 91, 192, 0.02)" }}
                onClick={handleAiExplainSql}
                disabled={aiGenerating || !activeEditorTab || activeEditorTab.status === "running"}
                title="AI 智能解释当前 SQL 意图"
              >
                <Sparkles size={12} style={{ color: "var(--accent-indigo)" }} />
                解释 SQL
              </button>

              <button
                className="btn-secondary"
                style={{ padding: "5px 10px", fontSize: "0.8rem", color: "var(--accent-indigo)", borderColor: "rgba(74, 91, 192, 0.2)", background: "rgba(74, 91, 192, 0.02)" }}
                onClick={handleAiOptimizeSql}
                disabled={aiGenerating || !activeEditorTab || activeEditorTab.status === "running"}
                title="AI 智能优化并重写 SQL"
              >
                <ShieldAlert size={12} style={{ color: "var(--accent-indigo)" }} />
                优化 SQL
              </button>

              <button
                className="btn-secondary"
                style={{ padding: "5px 10px", fontSize: "0.8rem", color: "var(--text-secondary)", borderColor: "var(--border-light)" }}
                onClick={handleInjectLimit}
                disabled={!activeEditorTab || activeEditorTab.status === "running"}
                title="自动在 SQL 尾部追加 LIMIT 100，防止大结果集拖慢执行"
              >
                注入 LIMIT
              </button>

              <button
                className="btn-ghost"
                style={{ padding: "5px 8px", fontSize: "0.8rem" }}
                onClick={handleFormatSql}
                disabled={!activeEditorTab?.sql.trim() || activeEditorTab.status === "running"}
                title="格式化 SQL 关键字为大写"
              >
                格式化
              </button>

              <button
                className="btn-secondary"
                style={{ padding: "5px 10px", fontSize: "0.8rem", color: "var(--text-secondary)", borderColor: "var(--border-light)" }}
                onClick={handleRunExplain}
                disabled={!activeEditorTab?.sql.trim() || activeEditorTab.status === "running"}
                title="执行 EXPLAIN 查看查询计划"
              >
                <Activity size={12} />
                Explain
              </button>

              <button
                className="btn-secondary"
                style={{ padding: "5px 10px", fontSize: "0.8rem" }}
                onClick={handleValidateSql}
                disabled={validating || !activeEditorTab || activeEditorTab.status === "running"}
                title="校验 SQL 安全性 (Ctrl+Shift+Enter)"
              >
                <ShieldAlert size={13} />
                安全检查
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
                  onClick={() => handleExecuteWithDirectives(30000)}
                  disabled={!activeEditorTab}
                  title="执行 SQL 查询 (Ctrl+Enter) — @ 查询动作将在执行前自动剥离"
                >
                  <Play size={13} />
                  执行
                </button>
              )}
            </div>
          </div>

          {/* Guardrail Status Strip */}
          {activeEditorTab?.guardrail && (
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "6px 14px",
              background: activeEditorTab.guardrail.result === "pass" ? "rgba(16, 185, 129, 0.06)" : activeEditorTab.guardrail.result === "warn" ? "rgba(245, 158, 11, 0.06)" : "rgba(239, 68, 68, 0.06)",
              borderBottom: "1px solid var(--border-light)",
              fontSize: "0.78rem",
              lineHeight: "1.4",
              flexShrink: 0,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, color: activeEditorTab.guardrail.result === "pass" ? "var(--accent-green)" : activeEditorTab.guardrail.result === "warn" ? "var(--accent-amber)" : "var(--accent-red)" }}>
                <ShieldAlert size={13} />
                <span><strong>Guardrail:</strong> {activeEditorTab.guardrail.message}</span>
                {activeEditorTab.schemaValidationWarnings && activeEditorTab.schemaValidationWarnings.length > 0 && (
                  <span style={{
                    marginLeft: 8,
                    background: "rgba(245, 158, 11, 0.1)",
                    color: "var(--accent-amber)",
                    padding: "1px 5px",
                    borderRadius: 3,
                    fontSize: "0.7rem",
                    fontWeight: 600,
                  }}>
                    ⚠️ 架构告警 ({activeEditorTab.schemaValidationWarnings.length})
                  </span>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {activeEditorTab.guardrail.safeSql && (
                  <span style={{ color: "var(--text-muted)", fontSize: "0.7rem", fontFamily: "var(--font-mono)" }}>
                    [自动注入 LIMIT]
                  </span>
                )}
                <button
                  onClick={() => setShowGuardrailDrawer(true)}
                  className="btn-ghost"
                  style={{
                    padding: "2px 8px",
                    fontSize: "0.72rem",
                    fontWeight: 600,
                    color: "var(--accent-indigo)",
                  }}
                >
                  查看审计报告 🔍
                </button>
              </div>
            </div>
          )}

          {/* @ Query Action Directive Capsules */}
          {activeDirectives.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 14px",
                borderBottom: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
                flexWrap: "wrap",
              }}
            >
              <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600, marginRight: 2 }}>
                查询动作:
              </span>
              {activeDirectives.map((d, i) => (
                <span
                  key={i}
                  title="点击移除该查询动作"
                  onClick={() => handleRemoveDirective(i)}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "1px 8px",
                    borderRadius: 3,
                    fontSize: "0.66rem",
                    fontFamily: "var(--font-mono)",
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "1px solid",
                    ...(d.type === "export"
                      ? { background: "rgba(16,185,129,0.08)", color: "var(--accent-green)", borderColor: "rgba(16,185,129,0.2)" }
                      : d.type === "limit"
                        ? { background: "rgba(59,130,246,0.08)", color: "#2563EB", borderColor: "rgba(59,130,246,0.2)" }
                        : d.type === "timeout"
                          ? { background: "rgba(245,158,11,0.08)", color: "var(--accent-amber)", borderColor: "rgba(245,158,11,0.2)" }
                          : d.type === "explain"
                            ? { background: "rgba(139,92,246,0.08)", color: "#7C3AED", borderColor: "rgba(139,92,246,0.2)" }
                            : d.type === "chart"
                              ? { background: "rgba(236,72,153,0.08)", color: "#DB2777", borderColor: "rgba(236,72,153,0.2)" }
                              : { background: "var(--bg-hover)", color: "var(--text-secondary)", borderColor: "var(--border-light)" }),
                  }}
                >
                  @{d.label}
                  <X size={9} style={{ opacity: 0.5 }} />
                </span>
              ))}
              <span style={{ fontSize: "0.62rem", color: "var(--text-muted)", marginLeft: "auto" }}>点击胶囊移除</span>
            </div>
          )}

          {/* Editor */}
          <div style={{ flex: 1, minHeight: 0 }}>
            <SqlEditor
              value={activeEditorTab?.sql ?? ""}
              onChange={(v) => updateActiveTab(() => ({ sql: v }))}
              schemaTables={schemaTables}
            />
          </div>
        </div>

        {/* Draggable Row Height Splitter */}
        <div
          onMouseDown={handleHeightDragMouseDown}
          style={{
            height: 8,
            cursor: "row-resize",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "transparent",
            userSelect: "none",
            flexShrink: 0,
          }}
          className="row-splitter"
          title="上下拖动调整编辑器与结果集高度"
        >
          <div style={{ width: 40, height: 4, borderRadius: 2, background: "var(--border-medium)" }} />
        </div>

        {/* Results / History */}
        <div
          className="lab-card"
          style={{ display: "flex", flexDirection: "column", overflow: "hidden", flex: 1, minHeight: 120 }}
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
            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
              {activeBottomTab === "history" && (
                <>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      minWidth: 180,
                      maxWidth: 240,
                      padding: "4px 8px",
                      border: "1px solid var(--border-light)",
                      borderRadius: 6,
                      background: "var(--bg-surface)",
                    }}
                  >
                    <Search size={13} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                    <input
                      value={historySearch}
                      onChange={(e) => setHistorySearch(e.target.value)}
                      placeholder="搜索问题或 SQL"
                      style={{
                        border: "none",
                        outline: "none",
                        background: "transparent",
                        width: "100%",
                        minWidth: 0,
                        color: "var(--text-primary)",
                        fontSize: "0.78rem",
                      }}
                    />
                  </label>
                  <select
                    className="input-field input-field-sm"
                    value={historyStatus}
                    onChange={(e) => setHistoryStatus(e.target.value as typeof historyStatus)}
                    style={{ width: 104, height: 30, fontSize: "0.78rem" }}
                  >
                    <option value="all">全部状态</option>
                    <option value="success">成功</option>
                    <option value="failed">失败</option>
                    <option value="timeout">超时</option>
                    <option value="cancelled">已取消</option>
                  </select>
                  <button
                    className="btn-ghost"
                    onClick={() => void fetchHistory()}
                    disabled={historyLoading}
                    title="刷新历史"
                    style={{ padding: "5px 8px" }}
                  >
                    <RefreshCw size={13} />
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={() => setClearConfirm(true)}
                    disabled={historyMutating || history.length === 0}
                    title="清空当前数据源历史"
                    style={{ padding: "5px 8px", color: "var(--accent-red)" }}
                  >
                    <Trash2 size={13} />
                    清空
                  </button>
                </>
              )}
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
          </div>

          <div style={{ flex: 1, overflow: "auto" }}>
            {activeBottomTab === "results" && (
              <>
                {!activeEditorTab?.queryResult ? (
                  <div className="empty-state" style={{ padding: 36 }}>
                    {activeEditorTab?.status === "running" ? (
                      <>
                        <div className="empty-state-desc">SQL 正在安全执行中，请稍候...</div>
                        <div style={{ marginTop: 8, width: 120, height: 3, background: "var(--accent-indigo-light)", borderRadius: 2, overflow: "hidden" }}>
                          <div className="progress-bar-glow" style={{ height: "100%", width: "60%", background: "var(--accent-indigo)", borderRadius: 2 }} />
                        </div>
                      </>
                    ) : (
                      <>
                        <Play size={28} className="empty-state-icon" style={{ color: "var(--accent-indigo)" }} />
                        <div className="empty-state-desc">在编辑器中编写 SQL，点击「执行」或按 <strong>Ctrl+Enter</strong></div>
                        <div style={{ marginTop: 12, fontSize: "0.78rem", color: "var(--text-muted)" }}>
                          也可通过 AI 智能问数自动生成 SQL
                        </div>
                      </>
                    )}
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
                            <Activity size={12} /> 执行计划
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
                          onClick={handleCopyResultJson}
                          title="复制结果为 JSON 数组"
                        >
                          <Copy size={11} /> JSON
                        </button>
                        <button
                          className="btn-ghost"
                          style={{ fontSize: "0.74rem" }}
                          onClick={handleCopyResultInsert}
                          title="复制结果为 INSERT 语句"
                        >
                          <Database size={11} /> INSERT
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
                        <span>耗时拆解:</span>
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
                            <span style={{ fontSize: "10px" }}>!</span>
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
                          maxHeight="100%"
                        />
                      </ErrorBoundary>
                    ) : (
                      <div style={{ padding: 12 }}>
                        <ErrorBoundary title="数据分析图表 (ChartPanel) 渲染崩溃">
                          <Suspense fallback={<div className="skeleton" style={{ height: 260, borderRadius: 8 }} />}>
                            <ChartPanel
                              columns={activeEditorTab.queryResult.columns}
                              rows={activeEditorTab.queryResult.rows}
                            />
                          </Suspense>
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
                    <div className="empty-state-desc">
                      {historySearch.trim() || historyStatus !== "all"
                        ? "没有匹配的查询历史"
                        : "还没有执行历史，执行一条 SQL 试试"}
                    </div>
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>操作</th>
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
                          <td style={{ whiteSpace: "nowrap" }}>
                            <button
                              className="btn-ghost"
                              onClick={() => handleReuseHistory(item)}
                              disabled={!getHistorySql(item)}
                              title="复用 SQL"
                              style={{ padding: "3px 7px", fontSize: "0.74rem" }}
                            >
                              <RotateCcw size={12} />
                              复用
                            </button>
                            <button
                              className="btn-ghost"
                              onClick={() => handleDeleteHistory(item)}
                              disabled={historyMutating}
                              title="删除历史"
                              style={{ padding: "3px 7px", color: "var(--accent-red)" }}
                            >
                              <Trash2 size={12} />
                            </button>
                          </td>
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
                            title={getHistorySql(item)}
                          >
                            {getHistorySql(item) || "-"}
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
                              {formatHistoryStatus(item.execution_status)}
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

      {/* 鈹€鈹€ Sliding Detailed Guardrail Audit Drawer 鈹€鈹€ */}
      {showGuardrailDrawer && activeEditorTab?.guardrail && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.4)",
            backdropFilter: "blur(4px)",
            display: "flex",
            justifyContent: "flex-end",
            zIndex: 9999,
          }}
          onClick={() => setShowGuardrailDrawer(false)}
        >
          <div
            className="animate-slide-left"
            style={{
              width: 440,
              height: "100%",
              background: "var(--bg-surface)",
              borderLeft: "1px solid var(--border-medium)",
              boxShadow: "var(--shadow-xl)",
              display: "flex",
              flexDirection: "column",
              padding: 24,
              overflowY: "auto",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
                <ShieldAlert size={18} style={{ color: "var(--accent-indigo)" }} />
                Guardrail 安全审计报告
              </h3>
              <button onClick={() => setShowGuardrailDrawer(false)} className="btn-ghost" style={{ padding: 4 }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <label style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "block", marginBottom: 6 }}>审核结论</label>
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
                      ? "安全评估通过"
                      : activeEditorTab.guardrail.result === "warn"
                      ? "存在合规性警告"
                      : "拒绝执行（阻断）"
                  }
                />
              </div>

              <div>
                <label style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "block", marginBottom: 4 }}>详情说明</label>
                <p style={{ fontSize: "0.84rem", color: "var(--text-secondary)", lineHeight: 1.6, margin: 0 }}>
                  {activeEditorTab.guardrail.message}
                </p>
              </div>

              {/* Safe SQL */}
              <div>
                <label style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "block", marginBottom: 6 }}>安全 SQL 备份</label>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                    background: "var(--bg-secondary)",
                    padding: 12,
                    borderRadius: 6,
                    fontSize: "0.78rem",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-light)",
                    margin: 0,
                    lineHeight: 1.5,
                  }}
                >
                  {activeEditorTab.guardrail.safeSql || activeEditorTab.sql}
                </pre>
              </div>

              {/* Checks */}
              {activeEditorTab.guardrail.checks.length > 0 && (
                <div>
                  <label style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "block", marginBottom: 8 }}>命中安全规则</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {activeEditorTab.guardrail.checks.map((item, i) => (
                      <div
                        key={`${item.rule}-${i}`}
                        style={{
                          padding: "8px 12px",
                          borderLeft: "3px solid",
                          borderLeftColor: item.level === "reject" ? "var(--accent-red)" : "var(--accent-amber)",
                          background: "var(--bg-secondary)",
                          borderRadius: "0 6px 6px 0",
                          fontSize: "0.78rem",
                        }}
                      >
                        <div style={{ fontWeight: 700, fontFamily: "var(--font-mono)", fontSize: "0.72rem", marginBottom: 2 }}>
                          {item.rule}
                        </div>
                        <div style={{ color: "var(--text-secondary)" }}>{item.message}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Schema Validation Warnings */}
              {activeEditorTab.schemaValidationWarnings && activeEditorTab.schemaValidationWarnings.length > 0 && (
                <div>
                  <label style={{ fontSize: "0.76rem", color: "var(--accent-amber)", display: "block", marginBottom: 8 }}>AI 字段校验警告</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {activeEditorTab.schemaValidationWarnings.map((item, i) => (
                      <div
                        key={`schema-warn-${i}`}
                        style={{
                          padding: "8px 12px",
                          borderLeft: "3px solid var(--accent-amber)",
                          background: "var(--bg-secondary)",
                          fontSize: "0.76rem",
                          color: "var(--text-primary)",
                          borderRadius: "0 6px 6px 0",
                        }}
                      >
                        <span style={{ fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: "0.72rem", color: "var(--accent-amber)", marginRight: 6 }}>
                          hallucination
                        </span>
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ borderTop: "1px solid var(--border-light)", paddingTop: 18, marginTop: 10 }}>
                <button
                  className="btn-secondary"
                  style={{
                    width: "100%",
                    justifyContent: "center",
                    fontSize: "0.8rem",
                    padding: "8px 12px",
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
                    setShowGuardrailDrawer(false);
                  }}
                >
                  <Award size={14} />
                  另存为 Golden SQL（加入 Benchmark）
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 鈹€鈹€ Golden SQL Benchmark Drawer 鈹€鈹€ */}
      {showBenchmarkDrawer && (
        <AiBenchmarkDrawer
          datasource={datasource}
          aiConfig={aiConfig}
          initialQuestion={goldenPresetQuestion}
          initialSql={goldenPresetSql}
          onClose={() => setShowBenchmarkDrawer(false)}
        />
      )}

      {/* Confirm dialogs */}
      <ConfirmDialog
        open={confirmRequest !== null}
        title={confirmRequest?.title ?? ""}
        message={confirmRequest?.message ?? ""}
        variant={confirmRequest?.variant ?? "info"}
        onConfirm={() => resolveConfirm(true)}
        onCancel={() => resolveConfirm(false)}
      />

      <ConfirmDialog
        open={deleteConfirm !== null}
        title="删除查询历史"
        message={`确认删除这条查询历史吗？\n\nSQL: ${deleteConfirm?.item ? (deleteConfirm.item.executed_sql || deleteConfirm.item.safe_sql || "").slice(0, 100) : ""}`}
        variant="danger"
        onConfirm={doDeleteHistory}
        onCancel={() => setDeleteConfirm(null)}
      />

      <ConfirmDialog
        open={clearConfirm}
        title="清空查询历史"
        message={`确认清空数据源「${datasource.name}」的全部查询历史吗？此操作不可撤销。`}
        variant="danger"
        onConfirm={doClearHistory}
        onCancel={() => setClearConfirm(false)}
      />
    </div>
  );
};
