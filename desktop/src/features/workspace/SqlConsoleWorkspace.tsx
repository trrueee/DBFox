import { useState } from "react";
import { Play, Sparkles } from "lucide-react";
import { executeSql, getDefaultDatasource, type EngineSqlResult } from "../engine/engineApi";

interface SqlConsoleWorkspaceProps {
  sqlQuery: string;
  sqlResultsRun: boolean;
  sqlConsoleTab: "results" | "history" | "ai-explain";
  onSqlQueryChange: (value: string) => void;
  onRunSql: () => void;
  onSqlConsoleTabChange: (tab: "results" | "history" | "ai-explain") => void;
  onToast: (message: string) => void;
}

export function SqlConsoleWorkspace({
  sqlQuery,
  sqlResultsRun,
  sqlConsoleTab,
  onSqlQueryChange,
  onRunSql,
  onSqlConsoleTabChange,
  onToast,
}: SqlConsoleWorkspaceProps) {
  const [result, setResult] = useState<EngineSqlResult | null>(null);
  const [running, setRunning] = useState(false);
  const [logLines, setLogLines] = useState<string[]>(["[INFO] SQL Console 已就绪，等待选择数据源。"]);
  const [error, setError] = useState("");

  const runSql = async () => {
    const sql = sqlQuery.trim();
    if (!sql) {
      onToast("SQL 不能为空");
      return;
    }
    setRunning(true);
    setError("");
    setLogLines((prev) => [`[INFO] ${formatTime()} - 开始执行 SQL`, ...prev]);
    try {
      const datasource = await getDefaultDatasource();
      if (!datasource) {
        throw new Error("暂无可用数据源，请先创建并同步数据源。");
      }
      const nextResult = await executeSql(datasource.id, sql, "SQL Console");
      setResult(nextResult);
      setLogLines((prev) => [`[INFO] ${formatTime()} - 执行成功，返回 ${nextResult.rowCount} 行，耗时 ${nextResult.latencyMs}ms`, ...prev]);
      if (nextResult.warnings?.length) onToast(nextResult.warnings[0]);
      onRunSql();
      onSqlConsoleTabChange("results");
    } catch (err) {
      const message = err instanceof Error ? err.message : "SQL 执行失败";
      setError(message);
      setResult(null);
      setLogLines((prev) => [`[ERROR] ${formatTime()} - ${message}`, ...prev]);
      onSqlConsoleTabChange("history");
      onToast(message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="hifi-sql-workspace hifi-tab-pane flex flex-col h-full">
      <div className="hifi-panel-toolbar flex-shrink-0">
        <div className="hifi-toolbar-left">
          <span className="font-semibold text-[11px] text-slate-700">SQL Console / Local Engine</span>
        </div>
        <div className="hifi-toolbar-right">
          <button className="hifi-guide-btn-primary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={runSql} disabled={running}>
            <Play size={10} />
            <span>{running ? "运行中..." : "运行 (F9)"}</span>
          </button>
          <button className="hifi-toolbar-btn" style={{ height: "24px" }} onClick={() => onToast("代码格式化待接入 SQL Formatter")}>格式化</button>
        </div>
      </div>

      <textarea
        value={sqlQuery}
        onChange={(event) => onSqlQueryChange(event.target.value)}
        className="flex-1 bg-slate-950 text-blue-100 font-mono text-[12px] p-4 outline-none resize-none leading-relaxed"
        spellCheck={false}
      />

      <div className="hifi-sql-output-pane">
        <div className="hifi-sql-output-tabs">
          <div className={`hifi-sql-output-tab ${sqlConsoleTab === "results" ? "active" : ""}`} onClick={() => onSqlConsoleTabChange("results")}>查询结果 {result ? `(${result.rowCount}行)` : sqlResultsRun ? "(已运行)" : ""}</div>
          <div className={`hifi-sql-output-tab ${sqlConsoleTab === "history" ? "active" : ""}`} onClick={() => onSqlConsoleTabChange("history")}>消息日志</div>
          <div className={`hifi-sql-output-tab ${sqlConsoleTab === "ai-explain" ? "active" : ""}`} onClick={() => onSqlConsoleTabChange("ai-explain")}>AI 解释 SQL</div>
        </div>

        <div className="hifi-sql-output-content">
          {sqlConsoleTab === "results" && (result ? <SqlResults result={result} /> : <div className="text-slate-400 italic text-[11px] text-center mt-10">点击“运行”执行上方的查询语句并查看输出结果。</div>)}
          {sqlConsoleTab === "history" && <SqlHistory logLines={logLines} error={error} />}
          {sqlConsoleTab === "ai-explain" && <SqlExplain />}
        </div>
      </div>
    </div>
  );
}

function SqlResults({ result }: { result: EngineSqlResult }) {
  return (
    <table className="hifi-table">
      <thead><tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
      <tbody>
        {result.rows.map((row, rowIndex) => (
          <tr key={rowIndex}>{result.columns.map((column) => <td key={column} className="max-w-[240px] truncate" title={row[column] ?? ""}>{row[column] ?? "NULL"}</td>)}</tr>
        ))}
        {result.rows.length === 0 && <tr><td colSpan={Math.max(result.columns.length, 1)} className="text-center text-slate-400">执行成功，无结果集。</td></tr>}
      </tbody>
    </table>
  );
}

function SqlHistory({ logLines, error }: { logLines: string[]; error: string }) {
  return <div className="flex flex-col gap-1.5 font-mono text-[10px]">{error && <div className="text-red-600">[ERROR] {error}</div>}{logLines.map((line, index) => <div key={`${line}-${index}`} className={line.includes("ERROR") ? "text-red-600" : "text-slate-700"}>{line}</div>)}</div>;
}

function SqlExplain() {
  return <div className="hifi-sql-ai-explain-card flex gap-2"><Sparkles size={14} className="text-indigo-500 flex-shrink-0 mt-0.5" /><div><strong className="block text-slate-800 mb-1">SQL 逻辑解释:</strong><span className="text-[10px] text-slate-600">AI 解释待接入 Agent。当前 SQL 执行已走本地 Engine 的安全校验和执行接口。</span></div></div>;
}

function formatTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
