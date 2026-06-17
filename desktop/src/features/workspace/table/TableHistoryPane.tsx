import { useEffect, useState } from "react";
import { request } from "../../../lib/api/client";

interface TableHistoryPaneProps {
  tableId: string;
  datasourceId: string;
}

interface QueryHistoryItem {
  id: string;
  question: string | null;
  submitted_sql: string | null;
  executed_sql: string | null;
  execution_status: string | null;
  execution_time_ms: number | null;
  rows_returned: number | null;
  created_at: string | null;
}

export function TableHistoryPane({ tableId, datasourceId }: TableHistoryPaneProps) {
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadHistory() {
      setLoading(true);
      try {
        const items = await request<QueryHistoryItem[]>(
          `/query/history?datasource_id=${encodeURIComponent(datasourceId)}&search=${encodeURIComponent(tableId)}&limit=20`
        );
        if (!cancelled) setHistory(items);
      } catch {
        if (!cancelled) setHistory([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadHistory();
    return () => { cancelled = true; };
  }, [tableId, datasourceId]);

  if (loading) {
    return <div className="p-4 text-[11px] text-slate-400">正在加载查询历史...</div>;
  }

  if (history.length === 0) {
    return <div className="p-4 text-[11px] text-slate-400">暂无针对 {tableId} 的查询历史记录。</div>;
  }

  return (
    <div className="p-4 flex flex-col gap-2 text-[11px] text-slate-600">
      {history.map((item) => (
        <div key={item.id} className="border border-slate-200 rounded-lg p-3 bg-white flex flex-col gap-1">
          <div className="flex justify-between items-start">
            <span className="font-medium text-slate-800 truncate max-w-[70%]">
              {item.question || "无标题查询"}
            </span>
            <span className="text-[10px] text-slate-400 shrink-0">
              {item.created_at ? new Date(item.created_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
            </span>
          </div>
          {item.executed_sql && (
            <code className="text-[10px] bg-slate-50 rounded px-1.5 py-0.5 text-slate-500 truncate font-mono">
              {item.executed_sql.length > 80 ? item.executed_sql.slice(0, 80) + "…" : item.executed_sql}
            </code>
          )}
          <div className="flex gap-3 text-[10px] text-slate-400">
            {item.execution_status === "success" && (
              <span className="text-green-600">✓ {item.rows_returned ?? 0} 行 · {item.execution_time_ms ?? 0}ms</span>
            )}
            {item.execution_status === "failed" && (
              <span className="text-red-500">✗ 执行失败</span>
            )}
            {item.execution_status === "timeout" && (
              <span className="text-amber-500">⏱ 超时</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
