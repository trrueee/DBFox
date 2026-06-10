import { useEffect, useState } from "react";
import { listColumns, resolveTableByName, type EngineColumn } from "../../engine/engineApi";

export function TableSchemaPane({ tableId }: { tableId: string }) {
  const [columns, setColumns] = useState<EngineColumn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadColumns() {
      setLoading(true);
      setError("");
      try {
        const resolved = await resolveTableByName(tableId);
        if (!resolved) {
          if (!cancelled) setError("未找到该表的 Schema 元数据，请先同步 Schema。");
          return;
        }
        const nextColumns = await listColumns(resolved.table.id);
        if (!cancelled) setColumns(nextColumns);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "读取字段结构失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadColumns();
    return () => {
      cancelled = true;
    };
  }, [tableId]);

  return (
    <div className="flex flex-col p-3 h-full overflow-auto">
      <span className="text-[10px] text-gray-400 block mb-1">字段列表 (Schema Structure) &gt; {tableId}</span>
      {loading && <div className="text-[11px] text-slate-400 mt-4">正在读取字段结构...</div>}
      {error && <div className="text-[11px] text-red-500 bg-red-50 rounded-lg p-3 mt-3">{error}</div>}
      {!loading && !error && (
        <table className="hifi-table">
          <thead>
            <tr><th>字段名</th><th>类型</th><th>约束</th><th>可空</th><th>默认值</th><th>注释</th></tr>
          </thead>
          <tbody>
            {columns.map((column) => (
              <tr key={column.id}>
                <td>{column.column_name}</td>
                <td className="text-blue-600 font-mono">{column.column_type || column.data_type}</td>
                <td>
                  {column.is_primary_key && <span className="hifi-constraint-badge pk">PK</span>}
                  {column.is_foreign_key && <span className="hifi-constraint-badge index ml-1">FK</span>}
                  {!column.is_primary_key && !column.is_foreign_key && "—"}
                </td>
                <td>{column.is_nullable ? "是" : "否"}</td>
                <td>{column.column_default || "—"}</td>
                <td>{column.column_comment || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
