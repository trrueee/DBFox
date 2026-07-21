import { useEffect, useState } from "react";
import { findTableByName, listColumns, type EngineColumn } from "../../../lib/api/schema";
import "./TableSchemaPane.css";

interface TableSchemaPaneProps {
  tableId: string;
  datasourceId: string;
}

function confidenceClass(confidence: number) {
  if (confidence >= 0.8) return "table-schema-confidence--high";
  if (confidence >= 0.5) return "table-schema-confidence--medium";
  return "table-schema-confidence--low";
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
        const table = await findTableByName(datasourceId, tableId);
        if (!table) {
          if (!cancelled) setError("未找到该表的字段信息，请先同步表结构。");
          return;
        }
        const nextColumns = await listColumns(table.id);
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
    <div className="table-schema-pane">
      <span className="table-schema-pane__caption">字段列表 &gt; {tableId}</span>
      {loading && <div className="table-schema-pane__loading">正在读取字段结构…</div>}
      {error && <div className="table-schema-pane__error">{error}</div>}
      {!loading && !error && (
        <table className="table-schema-table">
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
                <td className="table-schema-table__type">{column.column_type || column.data_type}</td>
                <td>
                  <span className="table-schema-constraints">
                    {column.is_primary_key && <span className="table-schema-constraint table-schema-constraint--primary">PK</span>}
                    {column.is_foreign_key && <span className="table-schema-constraint table-schema-constraint--foreign">FK</span>}
                  </span>
                  {!column.is_primary_key && !column.is_foreign_key && "—"}
                </td>
                <td>{column.is_nullable ? "是" : "否"}</td>
                <td>{column.column_default || "—"}</td>
                <td>{column.column_comment || "—"}</td>
                <td className="table-schema-muted">{column.ai_description || "—"}</td>
                <td>
                  {column.ai_confidence !== undefined && column.ai_confidence !== null ? (
                    <span className={`table-schema-confidence ${confidenceClass(column.ai_confidence)}`}>
                      {(column.ai_confidence * 100).toFixed(0)}%
                    </span>
                  ) : "—"}
                </td>
                <td>
                  {column.semantic_tags ? (
                    <span className="table-schema-tag">
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
