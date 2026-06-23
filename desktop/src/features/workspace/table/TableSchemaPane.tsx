import { useEffect, useState } from "react";
import { request } from "../../../lib/api/client";
import type { EngineColumn } from "../../engine/engineApi";

interface TableSchemaPaneProps {
  tableId: string;
  datasourceId: string;
}

export function TableSchemaPane({ tableId, datasourceId }: TableSchemaPaneProps) {
  const [columns, setColumns] = useState<EngineColumn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadColumns() {
      setLoading(true);
      setError("");
      try {
        // Resolve table by name within the correct datasource
        const tables = await request<Array<{ id: string; table_name: string }>>(
          `/schema/tables?datasource_id=${encodeURIComponent(datasourceId)}`
        );
        const table = tables.find((t) => t.table_name === tableId);
        if (!table) {
          if (!cancelled) setError("未找到该表的 Schema 元数据，请先同步 Schema。");
          return;
        }
        const nextColumns = await request<EngineColumn[]>(
          `/schema/tables/${encodeURIComponent(table.id)}/columns`
        );
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
  }, [tableId, datasourceId]);

  return (
    <div className="flex flex-col p-3 h-full overflow-auto">
      <span className="text-[var(--ui-font-caption)] text-gray-400 block mb-1">字段列表 (Schema Structure) &gt; {tableId}</span>
      {loading && <div className="text-[var(--ui-font-label)] text-slate-400 mt-4">正在读取字段结构...</div>}
      {error && <div className="text-[var(--ui-font-label)] text-red-500 bg-red-50 rounded-lg p-3 mt-3">{error}</div>}
      {!loading && !error && (
        <table className="hifi-table">
          <thead>
            <tr>
              <th>字段名</th>
              <th>类型</th>
              <th>约束</th>
              <th>可空</th>
              <th>默认值</th>
              <th>注释</th>
              <th>AI 描述</th>
              <th>AI 置信度</th>
              <th>语义标签</th>
            </tr>
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
                <td style={{ color: "var(--text-secondary)" }}>{column.ai_description || "—"}</td>
                <td>
                  {column.ai_confidence !== undefined && column.ai_confidence !== null ? (
                    <span style={{ 
                      fontSize: "0.7rem", 
                      color: column.ai_confidence >= 0.8 ? "var(--color-success)" : column.ai_confidence >= 0.5 ? "var(--color-warning)" : "var(--color-danger)",
                      background: column.ai_confidence >= 0.8 ? "var(--color-success-soft)" : column.ai_confidence >= 0.5 ? "var(--color-warning-soft)" : "var(--color-danger-soft)",
                      padding: "2px 6px",
                      borderRadius: 4,
                      fontWeight: 600
                    }}>
                      {(column.ai_confidence * 100).toFixed(0)}%
                    </span>
                  ) : "—"}
                </td>
                <td>
                  {column.semantic_tags ? (
                    <span style={{ 
                      fontSize: "0.7rem", 
                      color: "var(--color-primary)",
                      background: "var(--color-primary-soft)",
                      padding: "2px 6px",
                      borderRadius: 4
                    }}>
                      {column.semantic_tags}
                    </span>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
