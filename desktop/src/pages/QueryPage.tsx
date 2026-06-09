import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import type { DataSource, QueryResult } from "../lib/api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useQueryExecution } from "../hooks/useQueryExecution";
import { actionRegistry, planHasErrors, planWarnings } from "../lib/query-actions";
import type { QueryExecutionPlan } from "../lib/query-actions/types";
import { ConsoleTranscript, type ConsoleBlock } from "../components/ConsoleTranscript";

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
    lastQueryResultPreview?: QueryResult | null;
    lastError?: string | null;
  }) => void;
}

interface PendingConsoleRun {
  runningBlockId: string;
  sourceSql: string;
  plan: QueryExecutionPlan;
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function makeConsoleId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function keywordFormat(sql: string) {
  const sqlKeywords = [
    "select",
    "from",
    "where",
    "join",
    "left",
    "right",
    "inner",
    "on",
    "group by",
    "order by",
    "limit",
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "table",
    "and",
    "or",
    "not",
    "null",
    "as",
    "having",
    "in",
    "like",
    "between",
    "exists",
    "union",
    "all",
    "is",
    "into",
    "values",
    "set",
  ];

  return sqlKeywords.reduce((formatted, keyword) => {
    const regex = new RegExp(`\\b${keyword}\\b`, "gi");
    return formatted.replace(regex, keyword.toUpperCase());
  }, sql);
}

export const QueryPage = ({ datasource, initialDraft, actionTrigger, onStateChange }: QueryPageProps) => {
  const toast = useToast();
  const [consoleBlocks, setConsoleBlocks] = useState<ConsoleBlock[]>([]);
  const handledActionNonceRef = useRef<number | undefined>(undefined);
  const pendingRunRef = useRef<PendingConsoleRun | null>(null);

  const aiConfig = useMemo(
    () => ({
      apiKey: "",
      apiBase: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
      optimizeRag: true,
    }),
    [],
  );

  const {
    activeEditorTab,
    updateActiveTab,
    openSqlDraft,
    handleValidateSql,
    handleExecuteSql,
    handleCancelQuery,
    confirmRequest,
    resolveConfirm,
  } = useQueryExecution(datasource);

  useEffect(() => {
    if (!initialDraft?.sql) return;
    openSqlDraft(initialDraft.sql, initialDraft.title);
  }, [initialDraft?.nonce, initialDraft?.sql, initialDraft?.title, openSqlDraft]);

  useEffect(() => {
    if (!activeEditorTab || !onStateChange) return;
    onStateChange({
      resultState: activeEditorTab.status,
      sqlDraft: activeEditorTab.sql,
      dirty: activeEditorTab.sql !== activeEditorTab.savedSql,
      lastQueryResultPreview: activeEditorTab.queryResult ?? null,
      lastError: activeEditorTab.queryError ?? null,
    });
  }, [activeEditorTab, onStateChange]);

  const handleExportCsv = useCallback(() => {
    if (!activeEditorTab?.queryResult) return;
    const { columns, rows } = activeEditorTab.queryResult;
    const escapeCsv = (value: unknown): string => {
      if (value === null || value === undefined) return "";
      const text = String(value);
      return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const header = columns.map(escapeCsv).join(",");
    const body = rows.map((row) => columns.map((column) => escapeCsv(row[column])).join(",")).join("\n");
    downloadText(
      `databox_export_${new Date().toISOString().slice(0, 10)}.csv`,
      `\uFEFF${header}\n${body}`,
      "text/csv;charset=utf-8",
    );
  }, [activeEditorTab]);

  const executeConsoleSql = useCallback(
    (sqlOverride?: string) => {
      const sql = (sqlOverride ?? activeEditorTab?.sql ?? "").trim();
      if (!sql || activeEditorTab?.status === "running") return;

      const plan = actionRegistry.finalize(sql);
      const inputBlock: ConsoleBlock = {
        id: makeConsoleId("in"),
        type: "input",
        sql,
        createdAt: Date.now(),
      };

      if (planHasErrors(plan)) {
        const message = plan.issues
          .filter((issue) => issue.level === "error")
          .map((issue) => `• [${issue.code}] ${issue.message}`)
          .join("\n");
        setConsoleBlocks((prev) => [
          ...prev,
          inputBlock,
          {
            id: makeConsoleId("err"),
            type: "error",
            sql,
            message: `查询动作配置错误:\n${message}`,
            createdAt: Date.now(),
          },
        ]);
        return;
      }

      for (const warning of planWarnings(plan)) {
        toast.toast(`[${warning.code}] ${warning.message}`, "warning");
      }

      actionRegistry.applyPhase(plan, "beforeExecute");
      actionRegistry.applyPhase(plan, "aroundExecute");

      const runningBlock: ConsoleBlock = {
        id: makeConsoleId("run"),
        type: "running",
        sql,
        startedAt: Date.now(),
      };
      pendingRunRef.current = {
        runningBlockId: runningBlock.id,
        sourceSql: sql,
        plan,
      };

      setConsoleBlocks((prev) => [...prev, inputBlock, runningBlock]);
      void handleExecuteSql(plan.context.timeoutMs, plan.compiledSql);
    },
    [activeEditorTab, handleExecuteSql, toast],
  );

  useEffect(() => {
    const pending = pendingRunRef.current;
    if (!pending || !activeEditorTab || activeEditorTab.status === "running" || activeEditorTab.status === "idle") {
      return;
    }

    const createdAt = Date.now();
    if (activeEditorTab.status === "success" && activeEditorTab.queryResult) {
      // 1. Run post-execution 'afterExecute' phases on our plan
      actionRegistry.applyPhase(pending.plan, "afterExecute");

      const exportCfg = pending.plan.context.exportConfig;
      const chartCfg = pending.plan.context.chartConfig;
      const result = activeEditorTab.queryResult!;

      // 2. Automate file export triggers
      if (exportCfg?.enabled) {
        const format = exportCfg.format.toLowerCase();
        const filename = exportCfg.path || `databox_export_${Date.now()}.${format}`;
        if (format === "csv") {
          const escapeCsv = (value: unknown): string => {
            if (value === null || value === undefined) return "";
            const text = String(value);
            return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
          };
          const header = result.columns.map(escapeCsv).join(",");
          const body = result.rows.map((row) => result.columns.map((column) => escapeCsv(row[column])).join(",")).join("\n");
          downloadText(filename, `\uFEFF${header}\n${body}`, "text/csv;charset=utf-8");
        } else if (format === "json") {
          downloadText(filename, JSON.stringify(result.rows, null, 2), "application/json;charset=utf-8");
        }
      }

      setConsoleBlocks((prev) => {
        const next: ConsoleBlock[] = prev.filter((block) => block.id !== pending.runningBlockId);
        next.push({
          id: makeConsoleId("res"),
          type: "result",
          sql: pending.sourceSql,
          result: result,
          chartConfig: chartCfg, // Attach chart configurations to the block!
          createdAt,
        });

        if (exportCfg?.enabled) {
          next.push({
            id: makeConsoleId("export"),
            type: "export",
            sql: pending.sourceSql,
            format: exportCfg.format,
            message: `查询执行完毕！数据已自动按指令配置打包生成并触发浏览器本地下载。`,
            createdAt,
          });
        }
        return next;
      });
      pendingRunRef.current = null;
      return;
    }

    if (["error", "timeout", "cancelled"].includes(activeEditorTab.status)) {
      setConsoleBlocks((prev) => [
        ...prev.filter((block) => block.id !== pending.runningBlockId),
        {
          id: makeConsoleId("err"),
          type: "error",
          sql: pending.sourceSql,
          message: activeEditorTab.queryError ?? "查询已结束，但未返回结果。",
          createdAt,
        },
      ]);
      pendingRunRef.current = null;
    }
  }, [activeEditorTab?.queryError, activeEditorTab?.queryResult, activeEditorTab?.status, activeEditorTab]);

  const handleFormatSql = useCallback(() => {
    if (!activeEditorTab?.sql.trim()) return;
    updateActiveTab(() => ({ sql: keywordFormat(activeEditorTab.sql) }));
    toast.toast("SQL 关键字已格式化", "success");
  }, [activeEditorTab, toast, updateActiveTab]);

  const handleInjectLimit = useCallback(() => {
    if (!activeEditorTab?.sql.trim()) return;
    let sql = activeEditorTab.sql.trim();
    if (/limit\s+\d+/i.test(sql)) {
      toast.toast("SQL 已包含 LIMIT 限制", "info");
      return;
    }
    sql = `${sql.replace(/;\s*$/, "")} LIMIT 100;`;
    updateActiveTab(() => ({ sql }));
    toast.toast("已加入 LIMIT 100", "success");
  }, [activeEditorTab, toast, updateActiveTab]);

  const handleAddExportDirective = useCallback(() => {
    if (!activeEditorTab?.sql.trim()) return;
    if (/^\s*@export\b/im.test(activeEditorTab.sql)) {
      toast.toast("当前 SQL 已包含 @export", "info");
      return;
    }
    updateActiveTab(() => ({ sql: `${activeEditorTab.sql.trimEnd()}\n@export csv` }));
    toast.toast("已加入 @export csv", "success");
  }, [activeEditorTab, toast, updateActiveTab]);

  const handleRunExplain = useCallback(
    (sqlOverride?: string) => {
      const sql = (sqlOverride ?? activeEditorTab?.sql ?? "").trim();
      if (!sql) return;
      const explainSql = /^\s*explain\s/i.test(sql) ? sql : `EXPLAIN ${sql}`;
      updateActiveTab(() => ({ sql: explainSql }));
      executeConsoleSql(explainSql);
    },
    [activeEditorTab, executeConsoleSql, updateActiveTab],
  );

  // Phase 1: Old Text-to-SQL AI handlers replaced by Agent Copilot.
  // These no-ops keep ConsoleTranscript props interface intact.
  const handleAiOptimizeSql = useCallback(
    (_sqlOverride?: string) => {
      toast.toast("AI SQL 优化已迁移至 Agent Copilot — 请在左侧对话面板使用", "info");
    },
    [toast],
  );

  const handleAiExplainSql = useCallback(
    (_sqlOverride?: string) => {
      toast.toast("AI SQL 解读已迁移至 Agent Copilot — 请在左侧对话面板使用", "info");
    },
    [toast],
  );

  const handleAiFixError = useCallback(
    (_sql: string, _message: string) => {
      toast.toast("AI SQL 修复已迁移至 Agent Copilot — 请在左侧对话面板使用", "info");
    },
    [toast],
  );

  const handleGenerateChart = useCallback(
    (sql: string) => {
      const nextSql = /^\s*@chart\b/im.test(sql) ? sql : `${sql.trimEnd()}\n@chart bar`;
      updateActiveTab(() => ({ sql: nextSql }));
      toast.toast("已加入 @chart bar，可继续调整图表参数", "success");
    },
    [toast, updateActiveTab],
  );

  const handleReExecute = useCallback(
    (sql: string) => {
      updateActiveTab(() => ({ sql }));
      executeConsoleSql(sql);
    },
    [executeConsoleSql, updateActiveTab],
  );

  // Phase 1: Golden SQL deprecated. Use Agent eval tasks for golden test cases.
  const handleSaveQuery = useCallback(
    (_sql: string) => {
      toast.toast("保存查询已迁移至 Agent 评测模块 — 请使用 /agent-eval 管理黄金测试用例", "info");
    },
    [toast],
  );

  useEffect(() => {
    if (!actionTrigger?.type || actionTrigger.nonce === undefined) return;
    if (handledActionNonceRef.current === actionTrigger.nonce) return;
    handledActionNonceRef.current = actionTrigger.nonce;

    const timer = window.setTimeout(() => {
      if (actionTrigger.type === "execute") {
        executeConsoleSql();
      } else if (actionTrigger.type === "stop") {
        if (activeEditorTab) handleCancelQuery(activeEditorTab.id);
      } else if (actionTrigger.type === "validate") {
        void handleValidateSql();
      } else if (actionTrigger.type === "export") {
        handleExportCsv();
      } else if (actionTrigger.type === "format") {
        handleFormatSql();
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    actionTrigger,
    activeEditorTab,
    executeConsoleSql,
    handleCancelQuery,
    handleExportCsv,
    handleFormatSql,
    handleValidateSql,
  ]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "TEXTAREA" || target?.tagName === "INPUT") return;
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key === "Enter") {
        event.preventDefault();
        executeConsoleSql();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [executeConsoleSql]);

  const currentSql = activeEditorTab?.sql ?? "";
  const running = activeEditorTab?.status === "running";

  return (
    <div className="query-page-console">
      <ConsoleTranscript
        blocks={consoleBlocks}
        currentSql={currentSql}
        onSqlChange={(sql) => updateActiveTab(() => ({ sql }))}
        onExecute={() => executeConsoleSql()}
        onFormat={handleFormatSql}
        onExplain={handleRunExplain}
        onInjectLimit={handleInjectLimit}
        onAddExportDirective={handleAddExportDirective}
        onAiOptimize={handleAiOptimizeSql}
        onAiExplain={handleAiExplainSql}
        onAiFixError={handleAiFixError}
        onGenerateChart={handleGenerateChart}
        onReExecute={handleReExecute}
        onSaveQuery={handleSaveQuery}
        onCancel={() => activeEditorTab && handleCancelQuery(activeEditorTab.id)}
        onClear={() => setConsoleBlocks([])}
        isRunning={running}
        databaseName={datasource.database_name}
        engineLabel={datasource.db_type}
      />

      <ConfirmDialog
        open={confirmRequest !== null}
        title={confirmRequest?.title ?? ""}
        message={confirmRequest?.message ?? ""}
        variant={confirmRequest?.variant ?? "info"}
        onConfirm={() => resolveConfirm(true)}
        onCancel={() => resolveConfirm(false)}
      />
    </div>
  );
};
