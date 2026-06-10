import { Play, Sparkles } from "lucide-react";

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
  return (
    <div className="hifi-sql-workspace hifi-tab-pane flex flex-col h-full">
      <div className="hifi-panel-toolbar flex-shrink-0">
        <div className="hifi-toolbar-left">
          <span className="font-semibold text-[11px] text-slate-700">SQL Console / prod-mysql</span>
        </div>
        <div className="hifi-toolbar-right">
          <button className="hifi-guide-btn-primary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={onRunSql}>
            <Play size={10} />
            <span>运行 (F9)</span>
          </button>
          <button className="hifi-toolbar-btn" style={{ height: "24px" }} onClick={() => onToast("代码格式化完成")}>格式化</button>
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
          <div className={`hifi-sql-output-tab ${sqlConsoleTab === "results" ? "active" : ""}`} onClick={() => onSqlConsoleTabChange("results")}>查询结果 {sqlResultsRun && "(5行)"}</div>
          <div className={`hifi-sql-output-tab ${sqlConsoleTab === "history" ? "active" : ""}`} onClick={() => onSqlConsoleTabChange("history")}>消息日志</div>
          <div className={`hifi-sql-output-tab ${sqlConsoleTab === "ai-explain" ? "active" : ""}`} onClick={() => onSqlConsoleTabChange("ai-explain")}>AI 解释 SQL</div>
        </div>

        <div className="hifi-sql-output-content">
          {sqlConsoleTab === "results" && (sqlResultsRun ? <SqlResults /> : <div className="text-slate-400 italic text-[11px] text-center mt-10">点击“运行”执行上方的查询语句并查看输出结果。</div>)}
          {sqlConsoleTab === "history" && <SqlHistory sqlResultsRun={sqlResultsRun} />}
          {sqlConsoleTab === "ai-explain" && <SqlExplain />}
        </div>
      </div>
    </div>
  );
}

function SqlResults() {
  return (
    <table className="hifi-table">
      <thead><tr><th>name</th><th>comment_count</th></tr></thead>
      <tbody><tr><td>张三</td><td>1,432</td></tr><tr><td>李四</td><td>980</td></tr><tr><td>王五</td><td>412</td></tr></tbody>
    </table>
  );
}

function SqlHistory({ sqlResultsRun }: { sqlResultsRun: boolean }) {
  return <div className="flex flex-col gap-1.5 font-mono text-[10px]"><div className="text-emerald-600">[INFO] 14:15:32 - 数据库连接就绪 (prod-mysql)</div>{sqlResultsRun && <div className="text-slate-800">[INFO] 14:16:05 - 执行成功，受影响行数: 3, 耗时: 12ms</div>}</div>;
}

function SqlExplain() {
  return <div className="hifi-sql-ai-explain-card flex gap-2"><Sparkles size={14} className="text-indigo-500 flex-shrink-0 mt-0.5" /><div><strong className="block text-slate-800 mb-1">SQL 逻辑解释:</strong><span className="text-[10px] text-slate-600">这段 SQL 以 `id_users` 作为主表，使用 `LEFT JOIN` 关联 `comment_infos`，并对用户 ID 进行分组。通过 `COUNT(c.id)` 计算出每个用户的评论数，最终按照评论数进行降序排序。</span></div></div>;
}
