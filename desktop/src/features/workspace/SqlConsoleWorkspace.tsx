import { useEffect, useMemo, useRef, useState } from "react";
import { Play, Trash2 } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Panel } from "../../components/ui/panel";
import { LoadingState } from "../../components/ui/state";
import { Toolbar, ToolbarGroup, ToolbarTitle } from "../../components/ui/toolbar";
import { agentApi } from "../../lib/api/agent";
import type { DataSource } from "../../lib/api/types";
import { databaseTypeLabel } from "../../lib/presentation";
import type { ResultViewArtifact } from "../../types/agentArtifact";
import { parseConversationArtifact } from "../conversation/conversationWireSchema";
import { toResultViewArtifactModel } from "../conversation/workspace/conversationArtifactModels";
import { TableArtifactView } from "./artifacts/TableArtifactView";
import { firstSqlKeyword, splitSqlStatements, type SqlStatementKind } from "./artifacts/sqlTokenizer";
import { SqlEditor } from "./sqlEditor/SqlEditor";
import { useSqlCompletionCatalog } from "./sqlEditor/useSqlCompletionCatalog";
import "./SqlConsoleWorkspace.css";

export type SqlConsoleTabState = {
  draftSql: string;
  entries: ConsoleEntry[];
  running: boolean;
};

export type ConsoleEntry =
  | { id: number; kind: "info"; text: string; time: string }
  | { id: number; kind: "sql"; sql: string; time: string }
  | { id: number; kind: "result"; artifact: ResultViewArtifact; runId: string; time: string }
  | { id: number; kind: "error"; message: string; time: string };

interface SqlConsoleWorkspaceProps {
  tabId: string;
  state: SqlConsoleTabState;
  onPatchState: (tabId: string, patch: Partial<SqlConsoleTabState>) => void;
  onAppendEntries: (tabId: string, entries: ConsoleEntry[]) => void;
  onToast: (message: string) => void;
  datasources: DataSource[];
  activeDatasourceId: string;
}

// Distributive omit: Omit over a discriminated union collapses variants,
// so map each variant separately.
type ConsoleEntryDraft = ConsoleEntry extends infer T
  ? T extends ConsoleEntry
    ? Omit<T, "id" | "time">
    : never
  : never;

let entrySeq = 0;
const nextEntryId = () => ++entrySeq;

export function SqlConsoleWorkspace({ tabId, state, onPatchState, onAppendEntries, onToast, datasources, activeDatasourceId }: SqlConsoleWorkspaceProps) {
  const { draftSql, entries, running } = state;
  const terminalScrollRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const [selectedSql, setSelectedSql] = useState("");

  const requestedDatasourceId = activeDatasourceId.trim();
  const resolvedDatasource = requestedDatasourceId
    ? datasources.find(ds => ds.id === requestedDatasourceId) ?? null
    : datasources[0] ?? null;
  const datasourceReady = Boolean(resolvedDatasource);
  const datasourceWarning = datasourceReady
    ? resolvedDatasource?.status && resolvedDatasource.status !== "active"
      ? `数据源状态 ${resolvedDatasource.status}`
      : ""
    : requestedDatasourceId
      ? `绑定的数据源不可用: ${requestedDatasourceId}`
      : "没有可用数据源";
  const dbLabel = resolvedDatasource
    ? `${resolvedDatasource.name} · ${resolvedDatasource.database_name} · ${databaseTypeLabel(resolvedDatasource.db_type)}`
    : "数据源不可用";
  const completionCatalog = useSqlCompletionCatalog({
    datasourceId: resolvedDatasource?.id ?? "",
    connectionGeneration: resolvedDatasource?.connection_generation ?? 0,
    enabled: Boolean(resolvedDatasource),
  });
  const statementSummary = useMemo(() => summarizeSqlInput(draftSql, selectedSql), [draftSql, selectedSql]);
  const hasCommandHistory = entries.some((entry) => entry.kind === "sql" || entry.kind === "result" || entry.kind === "error");

  useEffect(() => {
    if (!initializedRef.current && entries.length === 0) {
      initializedRef.current = true;
      onAppendEntries(tabId, [
        { id: nextEntryId(), kind: "info", text: "SQL 控制台已就绪，输入语句后按 F9 或 Ctrl+Enter 执行。", time: formatTime() },
      ]);
    }
  }, [tabId, entries.length, onAppendEntries]);

  useEffect(() => {
    const node = terminalScrollRef.current;
    if (!node) return;
    const frame = requestAnimationFrame(() => {
      node.scrollTop = node.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [entries.length, running]);

  const appendEntries = (items: ConsoleEntryDraft[]) => {
    const time = formatTime();
    onAppendEntries(tabId, items.map((item) => ({ ...item, id: nextEntryId(), time }) as ConsoleEntry));
  };

  const runSql = async (requestedSql?: string) => {
    const selectedRequest = requestedSql?.trim() ?? "";
    const currentSelection = selectedSql.trim();
    const sql = selectedRequest || currentSelection || draftSql.trim();
    if (!sql) {
      onToast("SQL 不能为空");
      return;
    }
    if (running) return;
    if (!resolvedDatasource) {
      onToast(datasourceWarning || "暂无可用数据源，请先创建并同步数据源。");
      return;
    }
    const isSelectionExecution = Boolean(selectedRequest || currentSelection);
    onPatchState(tabId, { running: true });
    appendEntries([{ kind: "sql", sql }]);
    if (!isSelectionExecution) {
      onPatchState(tabId, { draftSql: "" });
    }
    try {
      const result = await agentApi.executeSqlConsole({
        datasourceId: resolvedDatasource.id,
        sql,
        question: "SQL 控制台",
        sessionId: tabId,
      });
      const resultArtifact = result.artifacts
        .map(parseConversationArtifact)
        .filter((artifact) => artifact.type === "result_view")
        .map(toResultViewArtifactModel)
        .at(0);
      const extras: ConsoleEntryDraft[] = resultArtifact
        ? [{ kind: "result", artifact: resultArtifact, runId: result.runId }]
        : [{ kind: "info", text: "执行成功，无结果集。" }];
      for (const warning of result.warnings ?? []) {
        extras.push({ kind: "info", text: `警告：${warning}` });
      }
      for (const notice of result.notices ?? []) {
        extras.push({ kind: "info", text: `提示：${notice}` });
      }
      appendEntries(extras);
    } catch (err) {
      const message = err instanceof Error ? err.message : "SQL 执行失败";
      appendEntries([{ kind: "error", message }]);
      onPatchState(tabId, { draftSql: sql });
    } finally {
      onPatchState(tabId, { running: false });
    }
  };

  const clearConsole = () => {
    onPatchState(tabId, { entries: [{ id: nextEntryId(), kind: "info", text: "控制台已清屏。", time: formatTime() }] });
  };

  const executableSql = selectedSql.trim() || draftSql.trim();
  const executeDisabled = running || !executableSql || !resolvedDatasource;
  const runLabel = running ? "正在运行…" : selectedSql.trim() ? "运行选中内容 (F9)" : "运行 (F9)";
  const statusClassName = ["sql-console-status", datasourceWarning ? "is-warning" : ""].filter(Boolean).join(" ");

  return (
    <Panel className="hifi-sql-workspace hifi-tab-pane" aria-label="SQL 控制台">
      <Toolbar className="sql-console-toolbar" aria-label="SQL 控制台工具栏">
        <ToolbarGroup className="gap-3">
          <ToolbarTitle>SQL 控制台</ToolbarTitle>
          <span className="sql-console-datasource-label">{dbLabel}</span>
        </ToolbarGroup>
        <ToolbarGroup>
          {selectedSql.trim() ? <span className="sql-console-selection-meta">已选中 {selectedSql.trim().length} 字符</span> : null}
          <Button size="sm" onClick={() => void runSql()} disabled={executeDisabled}>
            <Play className="sql-console-action-icon" aria-hidden="true" />
            <span>{runLabel}</span>
          </Button>
          <Button size="sm" variant="outline" onClick={clearConsole} disabled={running}>
            <Trash2 className="sql-console-action-icon" aria-hidden="true" />
            <span>清屏</span>
          </Button>
        </ToolbarGroup>
      </Toolbar>

      <div className="sql-console-workbench">
        <section
          className="sql-console-terminal"
          aria-label="SQL 命令行控制台"
          ref={terminalScrollRef}
        >
          <div className="sql-console-transcript">
            {entries.map((entry) => renderEntry(entry, onToast))}
            {running && <LoadingState className="sql-console-running" label="正在执行…" />}
          </div>

          <div
            className={`sql-console-command-row ${hasCommandHistory ? "has-history" : "is-empty"}`}
            aria-label="当前 SQL 输入"
          >
            <span className="sql-console-prompt-label">sql&gt;</span>
            <div className="sql-console-input-stack">
                <SqlEditor
                  value={draftSql}
                  disabled={running}
                  dbType={resolvedDatasource?.db_type ?? null}
                  tables={completionCatalog.tables}
                  loadColumns={completionCatalog.loadColumns}
                  onChange={(nextValue) => {
                    setSelectedSql("");
                    onPatchState(tabId, { draftSql: nextValue });
                  }}
                  onSelectionChange={setSelectedSql}
                  onExecute={(selection) => void runSql(selection)}
                />
            </div>
          </div>
        </section>

        <div className={statusClassName} aria-label="SQL 输入状态">
          {datasourceWarning ? <span>{datasourceWarning}</span> : null}
          <span>{statementSummary}</span>
          {completionCatalog.loading ? <span>正在加载表结构提示…</span> : null}
        </div>
      </div>
    </Panel>
  );
}

function renderEntry(entry: ConsoleEntry, onToast: (message: string) => void) {
  switch (entry.kind) {
    case "info":
      return (
        <div key={entry.id} className={`sql-console-info ${entry.text.startsWith("警告：") ? "warn" : ""}`}>
          {entry.text}
        </div>
      );
    case "sql":
      return (
        <div key={entry.id} className="sql-console-stmt">
          <span className="sql-console-prompt-label">sql&gt;</span>
          <pre className="sql-console-sql">{entry.sql}</pre>
        </div>
      );
    case "error":
      return (
        <div key={entry.id} className="sql-console-error">
          <strong>执行失败</strong> {entry.message}
        </div>
      );
    case "result":
      return <ResultBlock key={entry.id} artifact={entry.artifact} runId={entry.runId} time={entry.time} onToast={onToast} />;
  }
}

function summarizeSqlInput(sql: string, selectedSql: string) {
  const trimmed = sql.trim();
  if (!trimmed) return "等待输入 SQL";

  const statements = splitSqlStatements(sql);
  const labels = Array.from(new Set(statements.map((statement) => firstSqlKeyword(statement.text)).filter(Boolean)));
  const typeText = labels.length > 0 ? labels.join(" / ") : "SQL";
  const kindText = Array.from(new Set(statements.map((statement) => statementKindLabel(statement.kind)))).join(" / ");
  const selection = selectedSql.trim();
  const selectionText = selection ? ` · 将执行选中 ${selection.length} 字符` : "";
  return `${statements.length || 1} 条语句 · ${typeText}${kindText ? ` · ${kindText}` : ""}${selectionText}`;
}

function statementKindLabel(kind: SqlStatementKind) {
  if (kind === "read") return "查询";
  if (kind === "write") return "写入";
  if (kind === "ddl") return "结构变更";
  return "语句";
}

function ResultBlock({
  artifact,
  runId,
  time,
  onToast,
}: {
  artifact: ResultViewArtifact;
  runId: string;
  time: string;
  onToast: (message: string) => void;
}) {
  const rowCount = artifact.rowCount ?? artifact.returnedRows ?? 0;
  const latencyText = artifact.latencyMs !== undefined ? ` · ${artifact.latencyMs}ms` : "";
  return (
    <div className="sql-console-result">
      <div className="sql-console-result-meta">
        查询结果 · {rowCount} 行{latencyText} · {time}
        {artifact.truncated ? " · 结果已截断" : ""}
        <details className="sql-console-result-details">
          <summary>执行详情</summary>
          <span>Run ID：{runId}</span>
        </details>
      </div>
      <TableArtifactView artifact={artifact} onToast={onToast} mode="workspace" />
    </div>
  );
}

function formatTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
