import { useEffect, useRef, useState } from "react";
import { Play, Trash2 } from "lucide-react";
import { ImageCell, isImageUrl } from "../../components/ImageCell";
import { SqlEditor } from "../../components/SqlEditor";
import { Button } from "../../components/ui/button";
import { Panel } from "../../components/ui/panel";
import { LoadingState } from "../../components/ui/state";
import { Toolbar, ToolbarGroup, ToolbarTitle } from "../../components/ui/toolbar";
import { executeSql, type EngineSqlResult } from "../engine/engineApi";
import type { DataSource } from "../../lib/api/types";
import "./SqlConsoleWorkspace.css";

export type SqlConsoleTabState = {
  draftSql: string;
  entries: ConsoleEntry[];
  running: boolean;
};

export type ConsoleEntry =
  | { id: number; kind: "info"; text: string; time: string }
  | { id: number; kind: "sql"; sql: string; time: string }
  | { id: number; kind: "result"; result: EngineSqlResult; time: string }
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
export const nextEntryId = () => ++entrySeq;

export function SqlConsoleWorkspace({ tabId, state, onPatchState, onAppendEntries, onToast, datasources, activeDatasourceId }: SqlConsoleWorkspaceProps) {
  const { draftSql, entries, running } = state;
  const scrollRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const [selectedSql, setSelectedSql] = useState("");

  const resolvedDatasource = datasources.find(ds => ds.id === activeDatasourceId) || datasources[0] || null;
  const dbLabel = resolvedDatasource
    ? `${resolvedDatasource.database_name} · ${resolvedDatasource.db_type}`
    : "local engine";

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

  const runSql = async (requestedSql?: string) => {
    const selectedRequest = requestedSql?.trim() ?? "";
    const currentSelection = selectedSql.trim();
    const sql = selectedRequest || currentSelection || draftSql.trim();
    if (!sql) {
      onToast("SQL 不能为空");
      return;
    }
    if (running) return;
    const isSelectionExecution = Boolean(selectedRequest || currentSelection);
    onPatchState(tabId, { running: true });
    appendEntries([{ kind: "sql", sql }]);
    if (!isSelectionExecution) {
      onPatchState(tabId, { draftSql: "" });
    }
    try {
      if (!resolvedDatasource) {
        throw new Error("暂无可用数据源，请先创建并同步数据源。");
      }
      const result = await executeSql(resolvedDatasource.id, sql, "SQL Console");
      const extras: ConsoleEntryDraft[] = [{ kind: "result", result }];
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
  const executeDisabled = running || !executableSql;
  const runLabel = running ? "运行中..." : selectedSql.trim() ? "运行选中 (F9)" : "运行 (F9)";

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
          {entries.map((entry) => renderEntry(entry))}

          {running && <LoadingState className="sql-console-running" label="执行中..." />}

          <div className="sql-console-prompt sql-console-editor-prompt">
            <span className="sql-console-prompt-label">sql&gt;</span>
            <div className="sql-console-editor-inline">
              <SqlEditor
                value={draftSql}
                onChange={(value) => {
                  setSelectedSql("");
                  onPatchState(tabId, { draftSql: value });
                }}
                disabled={running}
                onExecute={(sql) => void runSql(sql)}
                onSelectionChange={setSelectedSql}
                ariaLabel="SQL 编辑器"
                testId="sql-console-editor"
              />
            </div>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function renderEntry(entry: ConsoleEntry) {
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
      return <ResultBlock key={entry.id} result={entry.result} time={entry.time} />;
  }
}

function ResultBlock({ result, time }: { result: EngineSqlResult; time: string }) {
  return (
    <div className="sql-console-result">
      <div className="sql-console-result-meta">
        {result.rowCount} 行 · {result.latencyMs}ms · {time}
        {result.truncated ? " · 结果已截断" : ""}
      </div>
      {result.columns.length > 0 ? (
        <div className="sql-console-table-wrap">
          <table className="sql-console-table">
            <thead>
              <tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr>
            </thead>
            <tbody>
              {result.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {result.columns.map((column) => {
                    const rawValue = row[column];
                    const value = rawValue == null ? null : String(rawValue);
                    if (isImageUrl(value)) {
                      return (
                        <td key={column}>
                          <ImageCell url={value ?? ""} />
                        </td>
                      );
                    }
                    return (
                      <td key={column} title={value ?? ""}>
                        {value ?? <span className="sql-console-null">NULL</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {result.rows.length === 0 && (
                <tr><td colSpan={Math.max(result.columns.length, 1)} className="sql-console-empty">执行成功，无结果集。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="sql-console-info">执行成功。</div>
      )}
    </div>
  );
}

function formatTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
