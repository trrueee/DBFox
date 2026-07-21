import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type SyntheticEvent, type UIEvent } from "react";
import { Play, Trash2 } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Panel } from "../../components/ui/panel";
import { LoadingState } from "../../components/ui/state";
import { Toolbar, ToolbarGroup, ToolbarTitle } from "../../components/ui/toolbar";
import { agentApi } from "../../lib/api/agent";
import type { DataSource } from "../../lib/api/types";
import { databaseTypeLabel } from "../../lib/presentation";
import type { ResultViewArtifact } from "../../types/agentArtifact";
import { toViewArtifacts } from "./artifactProjection";
import { TableArtifactView } from "./artifacts/TableArtifactView";
import { firstSqlKeyword, splitSqlStatements, tokenizeSql, type SqlStatementKind, type SqlTokenKind } from "./artifacts/sqlTokenizer";
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
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
  const statementSummary = useMemo(() => summarizeSqlInput(draftSql, selectedSql), [draftSql, selectedSql]);

  useEffect(() => {
    if (!initializedRef.current && entries.length === 0) {
      initializedRef.current = true;
      onAppendEntries(tabId, [
        { id: nextEntryId(), kind: "info", text: "SQL Console 已就绪，输入语句后按 F9 或 Ctrl+Enter 执行。", time: formatTime() },
      ]);
    }
  }, [tabId, entries.length, onAppendEntries]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [entries, running]);

  const appendEntries = (items: ConsoleEntryDraft[]) => {
    const time = formatTime();
    onAppendEntries(tabId, items.map((item) => ({ ...item, id: nextEntryId(), time }) as ConsoleEntry));
  };

  const selectedTextFromTextarea = (input: HTMLTextAreaElement) => {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    return end > start ? input.value.slice(start, end) : "";
  };

  const updateSelectedSql = (event: SyntheticEvent<HTMLTextAreaElement>) => {
    setSelectedSql(selectedTextFromTextarea(event.currentTarget));
  };

  const handleEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const shouldExecute = event.key === "F9" || ((event.ctrlKey || event.metaKey) && event.key === "Enter");
    if (!shouldExecute) return;
    event.preventDefault();
    const selected = selectedTextFromTextarea(event.currentTarget);
    setSelectedSql(selected);
    void runSql(selected);
  };

  const syncHighlightScroll = (event: UIEvent<HTMLTextAreaElement>) => {
    const highlight = highlightRef.current;
    if (!highlight) return;
    highlight.scrollTop = event.currentTarget.scrollTop;
    highlight.scrollLeft = event.currentTarget.scrollLeft;
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
        question: "SQL Console",
        sessionId: tabId,
      });
      const resultArtifact = toViewArtifacts(result.artifacts)
        .find((artifact): artifact is ResultViewArtifact => artifact.type === "result_view");
      const extras: ConsoleEntryDraft[] = resultArtifact
        ? [{ kind: "result", artifact: resultArtifact, runId: result.runId }]
        : [{ kind: "info", text: "执行成功，无结果集。" }];
      for (const warning of result.warnings ?? []) {
        extras.push({ kind: "info", text: `[WARN] ${warning}` });
      }
      for (const notice of result.notices ?? []) {
        extras.push({ kind: "info", text: `[INFO] ${notice}` });
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
    <Panel className="hifi-sql-workspace hifi-tab-pane" aria-label="SQL Console">
      <Toolbar className="sql-console-toolbar" aria-label="SQL Console 工具栏">
        <ToolbarGroup className="gap-3">
          <ToolbarTitle>SQL Console</ToolbarTitle>
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

      <div className="sql-console">
        <div className="sql-console-scroll" ref={scrollRef}>
          {entries.map((entry) => renderEntry(entry, onToast))}

          {running && <LoadingState className="sql-console-running" label="正在执行…" />}

          <div className={statusClassName} aria-label="SQL 输入状态">
            <span>{datasourceWarning || `数据源 ${dbLabel}`}</span>
            <span>{statementSummary}</span>
          </div>

          <label className="sql-console-prompt sql-console-editor-prompt">
            <span className="sql-console-prompt-label">sql&gt;</span>
            <div className="sql-console-input-stack">
              <pre ref={highlightRef} className="sql-console-highlight" aria-label="SQL 高亮预览">
                {renderSqlConsoleHighlight(draftSql)}
              </pre>
              <textarea
                className="sql-console-input"
                aria-label="SQL 编辑器"
                value={draftSql}
                rows={Math.min(12, Math.max(1, draftSql.split("\n").length))}
                spellCheck={false}
                disabled={running}
                autoFocus
                onChange={(event) => {
                  setSelectedSql("");
                  onPatchState(tabId, { draftSql: event.target.value });
                }}
                onScroll={syncHighlightScroll}
                onSelect={updateSelectedSql}
                onKeyUp={updateSelectedSql}
                onKeyDown={handleEditorKeyDown}
              />
            </div>
          </label>
        </div>
      </div>
    </Panel>
  );
}

function renderEntry(entry: ConsoleEntry, onToast: (message: string) => void) {
  switch (entry.kind) {
    case "info":
      return (
        <div key={entry.id} className={`sql-console-info ${entry.text.startsWith("[WARN]") ? "warn" : ""}`}>
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
          <strong>ERROR</strong> {entry.message}
        </div>
      );
    case "result":
      return <ResultBlock key={entry.id} artifact={entry.artifact} runId={entry.runId} time={entry.time} onToast={onToast} />;
  }
}

function renderSqlConsoleHighlight(sql: string) {
  const statements = splitSqlStatements(sql);
  const segments = statements.length > 0 ? statements : [{ text: sql || "\u200b", kind: "other" as const }];

  return (
    <code>
      {segments.map((statement, statementIndex) => (
        <span
          key={`${statementIndex}-${statement.kind}`}
          className={`sql-console-statement sql-console-statement--${statement.kind}`}
        >
          {tokenizeSql(statement.text).map((token, tokenIndex) => (
            <span key={`${tokenIndex}-${token.kind}`} className={sqlConsoleTokenClass(token.kind)}>
              {token.text}
            </span>
          ))}
        </span>
      ))}
    </code>
  );
}

function sqlConsoleTokenClass(kind: SqlTokenKind) {
  return kind === "whitespace" ? "sql-console-token sql-console-token-whitespace" : `sql-console-token sql-console-token-${kind}`;
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
        SQL-backed result · {rowCount} 行{latencyText} · {time} · {runId}
        {artifact.truncated ? " · 结果已截断" : ""}
      </div>
      <TableArtifactView artifact={artifact} onToast={onToast} mode="workspace" />
    </div>
  );
}

function formatTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
