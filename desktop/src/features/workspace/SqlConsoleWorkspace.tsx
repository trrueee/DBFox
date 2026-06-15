import { useEffect, useRef } from "react";
import { Play } from "lucide-react";
import { ImageCell, isImageUrl } from "../../components/ImageCell";
import { executeSql, type EngineSqlResult } from "../engine/engineApi";
import type { DataSource } from "../../lib/api/types";

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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const initializedRef = useRef(false);

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

  const runSql = async () => {
    const sql = draftSql.trim();
    if (!sql) {
      onToast("SQL 不能为空");
      return;
    }
    if (running) return;
    onPatchState(tabId, { running: true });
    appendEntries([{ kind: "sql", sql }]);
    onPatchState(tabId, { draftSql: "" });
    try {
      if (!resolvedDatasource) {
        throw new Error("暂无可用数据源，请先创建并同步数据源。");
      }
      setDbLabel(`${resolvedDatasource.database_name} · ${resolvedDatasource.db_type}`);
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
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "F9" || (event.key === "Enter" && (event.ctrlKey || event.metaKey))) {
      event.preventDefault();
      void runSql();
    }
  };

  const clearConsole = () => {
    onPatchState(tabId, { entries: [{ id: nextEntryId(), kind: "info", text: "控制台已清屏。", time: formatTime() }] });
  };

  return (
    <div className="hifi-sql-workspace hifi-tab-pane flex flex-col h-full">
      <div className="hifi-panel-toolbar flex-shrink-0">
        <div className="hifi-toolbar-left">
          <span className="font-semibold text-[11px] text-slate-700">SQL Console / {dbLabel}</span>
        </div>
        <div className="hifi-toolbar-right">
          <button className="hifi-guide-btn-primary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={runSql} disabled={running}>
            <Play size={10} />
            <span>{running ? "运行中..." : "运行 (F9)"}</span>
          </button>
          <button className="hifi-toolbar-btn" style={{ height: "24px" }} onClick={clearConsole}>清屏</button>
        </div>
      </div>

      <div className="sql-console" onClick={(event) => { if (event.target === event.currentTarget) inputRef.current?.focus(); }}>
        <div className="sql-console-scroll" ref={scrollRef}>
          {entries.map((entry) => renderEntry(entry))}

          {running && <div className="sql-console-running">执行中...</div>}

          <div className="sql-console-prompt">
            <span className="sql-console-prompt-label">sql&gt;</span>
            <textarea
              ref={inputRef}
              className="sql-console-input"
              value={draftSql}
              onChange={(event) => onPatchState(tabId, { draftSql: event.target.value })}
              onKeyDown={handleKeyDown}
              rows={Math.min(12, Math.max(1, draftSql.split("\n").length))}
              placeholder="输入 SQL，Ctrl+Enter 执行"
              spellCheck={false}
              autoCapitalize="off"
              autoComplete="off"
            />
          </div>
        </div>
      </div>
    </div>
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
                    const value = row[column] as string | null | undefined;
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
