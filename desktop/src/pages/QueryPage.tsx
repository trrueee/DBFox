import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, Award, Check, Copy, Play, ShieldAlert, Sparkles, X,
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, QueryHistory } from "../lib/api";
import { AiQueryInput } from "../components/AiQueryInput";
import { StatusIndicator } from "../components/StatusIndicator";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { AiBenchmarkDrawer } from "../components/AiBenchmarkDrawer";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useQueryExecution, type QueryTabState } from "../hooks/useQueryExecution";
import { actionRegistry, type ParsedAction, planHasErrors, planWarnings } from "../lib/queryActions";
import { ConsoleTranscript, type ConsoleBlock as ConsoleTranscriptBlock } from "../components/ConsoleTranscript";

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



function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export const QueryPage = ({ datasource, initialDraft, actionTrigger, onStateChange }: QueryPageProps) => {
  const [_activeBottomTab, setActiveBottomTab] = useState<ViewTab>("results");
  const [_resultViewMode, _setResultViewMode] = useState<ResultViewMode>("table");
  const [_history, setHistory] = useState<QueryHistory[]>([]);
  const [_historyLoading, setHistoryLoading] = useState(false);
  const [_historyMutating, setHistoryMutating] = useState(false);
  const [historySearch, _setHistorySearch] = useState("");
  const [historyStatus, _setHistoryStatus] = useState<"all" | "success" | "failed" | "timeout" | "cancelled">("all");
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
  const [consoleMode] = useState(true);
  const [consoleBlocks, setConsoleBlocks] = useState<ConsoleTranscriptBlock[]>([]);
  const handledActionNonceRef = useRef<number | undefined>(undefined);
  const [editorHeight] = useState(() => {
    const saved = localStorage.getItem("databox_editor_height");
    return saved ? Number(saved) : 320;
  });

  useEffect(() => {
    localStorage.setItem("databox_editor_height", String(editorHeight));
  }, [editorHeight]);


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
  const [_schemaTables, _setSchemaTables] = useState<Record<string,unknown>["nodes"]>([]);

  const _fetchSchemaMetadata = useCallback(async () => {
    try {
      const data = await api.getERDiagram(datasource.id);
      _setSchemaTables(data.nodes || []);
    } catch (e) {
      console.error("Failed to fetch schema metadata for autocomplete:", e);
      _setSchemaTables([]);
    }
  }, [datasource.id]);

  const initialDraftSql = initialDraft?.sql;
  const initialDraftTitle = initialDraft?.title;
  const initialDraftNonce = initialDraft?.nonce;
  const actionTriggerType = actionTrigger?.type;
  const actionTriggerNonce = actionTrigger?.nonce;

  useEffect(() => {
    setActiveBottomTab("results");
    void _fetchSchemaMetadata();
  }, [_fetchSchemaMetadata]);

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

  // ── Console mode execution — appends blocks to transcript ──

  const handleConsoleExecute = useCallback(() => {
    if (!activeEditorTab?.sql.trim() || activeEditorTab.status === "running") return;

    const sql = activeEditorTab.sql.trim();
    const inputBlock: ConsoleTranscriptBlock = {
      id: `in-${Date.now()}`,
      type: "input",
      sql,
      createdAt: Date.now(),
    };
    const runningBlock: ConsoleTranscriptBlock = {
      id: `run-${Date.now()}`,
      type: "running",
      sql,
      startedAt: Date.now(),
    };

    setConsoleBlocks((prev) => [...prev, inputBlock, runningBlock]);

    // Use directive pipeline
    const plan = actionRegistry.finalize(sql);
    if (planHasErrors(plan)) {
      const msg = plan.issues.filter((i) => i.level === "error").map((e) => `• ${e.message}`).join("\n");
      setConsoleBlocks((prev) => {
        const filtered = prev.filter((b) => b.id !== runningBlock.id);
        return [...filtered, {
          id: `err-${Date.now()}`,
          type: "error",
          sql,
          message: `查询动作配置错误:\n${msg}`,
        }];
      });
      return;
    }

    actionRegistry.applyPhase(plan, "beforeExecute");

    void handleExecuteSql(plan.context.timeoutMs, plan.compiledSql);
  }, [activeEditorTab, handleExecuteSql]);

  // Sync console blocks with execution results
  const prevResultRef = useRef(activeEditorTab?.queryResult);
  useEffect(() => {
    if (!consoleMode) return;
    const tab = activeEditorTab;
    if (!tab) return;

    // Remove old running block when result/error arrives
    if (tab.status !== "running" && prevResultRef.current !== tab.queryResult) {
      prevResultRef.current = tab.queryResult;

      if (tab.status === "success" && tab.queryResult) {
        setConsoleBlocks((prev) => {
          const withoutRunning = prev.filter((b) => b.type !== "running");
          return [...withoutRunning, {
            id: `res-${Date.now()}`,
            type: "result",
            sql: tab.sql,
            result: tab.queryResult!,
          }];
        });
      } else if (tab.status === "error" && tab.queryError) {
        setConsoleBlocks((prev) => {
          const withoutRunning = prev.filter((b) => b.type !== "running");
          return [...withoutRunning, {
            id: `err-${Date.now()}`,
            type: "error",
            sql: tab.sql,
            message: tab.queryError ?? "未知错误",
          }];
        });
      } else if (tab.status === "cancelled" || tab.status === "timeout") {
        setConsoleBlocks((prev) => prev.filter((b) => b.type !== "running"));
      }
    }
  }, [activeEditorTab?.status, activeEditorTab?.queryResult, activeEditorTab?.queryError, consoleMode]);

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


  const isDirty = (tab: QueryTabState) => tab.sql !== tab.savedSql;

  const handleCopySql = async () => {
    if (!activeEditorTab) return;
    await navigator.clipboard.writeText(activeEditorTab.sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };



  const [deleteConfirm, setDeleteConfirm] = useState<{ item: QueryHistory } | null>(null);
  const [clearConfirm, setClearConfirm] = useState(false);


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

          {/* Console Transcript */}
          <div style={{ flex: 1, minHeight: 0 }}>
            <ConsoleTranscript
              blocks={consoleBlocks}
              currentSql={activeEditorTab?.sql ?? ""}
              onSqlChange={(v) => updateActiveTab(() => ({ sql: v }))}
              onExecute={handleConsoleExecute}
              onFormat={handleFormatSql}
              onExplain={handleRunExplain}
              onInjectLimit={handleInjectLimit}
              onCancel={() => activeEditorTab && handleCancelQuery(activeEditorTab.id)}
              onClear={() => setConsoleBlocks([])}
              isRunning={activeEditorTab?.status === "running"}
              databaseName={datasource.database_name}
              engineLabel={datasource.db_type}
            />
          </div>
        </div>

      </div>

      {/* Sliding Detailed Guardrail Audit Drawer */}
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
