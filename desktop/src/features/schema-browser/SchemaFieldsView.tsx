import { Key, Link2 } from "lucide-react";
import type { SchemaColumn, SchemaTable } from "../../lib/api";

interface SchemaFieldsViewProps {
  table: SchemaTable | null;
  columns: SchemaColumn[];
  loading: boolean;
}

export function SchemaFieldsView({ table, columns, loading }: SchemaFieldsViewProps) {
  return (
    <div className="schema-browser-body">
      <div className="schema-meta-bar">
        <span>类型: <strong className="text-[var(--text-primary)]">{table?.table_type ?? "-"}</strong></span>
        <span>预估行数: <strong className="text-[var(--text-primary)]">{table?.row_count_estimate?.toLocaleString() ?? "0"}</strong></span>
        <span>字段: <strong className="text-[var(--text-primary)]">{columns.length}</strong></span>
      </div>
      <div className="schema-content-scroll">
        {loading ? (
          <div className="p-6 flex flex-col gap-2">
            {[1, 2, 3, 4, 5].map((item) => (
              <div key={item} className="h-9 rounded-md bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />
            ))}
          </div>
        ) : columns.length === 0 ? (
          <div className="schema-empty">
            <div className="schema-empty-card">
              <div className="schema-empty-title">未选中表</div>
              <div className="schema-empty-copy">从对象树选择一个表查看字段详情。</div>
            </div>
          </div>
        ) : (
          <table className="schema-fields-table">
            <thead>
              <tr>
                <th>字段名</th>
                <th>数据类型</th>
                <th>约束</th>
                <th>可空</th>
                <th>默认值</th>
                <th>注释</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((column) => (
                <tr key={column.id}>
                  <td className="schema-code font-black">{column.column_name}</td>
                  <td><span className="schema-code schema-type">{column.column_type || column.data_type}</span></td>
                  <td>
                    <div className="flex items-center gap-1">
                      {column.is_primary_key && <span className="schema-tag schema-tag--pk"><Key size={9} />PK</span>}
                      {column.is_foreign_key && <span className="schema-tag schema-tag--fk"><Link2 size={9} />FK</span>}
                      {!column.is_primary_key && !column.is_foreign_key && <span className="text-[var(--text-muted)]">-</span>}
                    </div>
                  </td>
                  <td>{column.is_nullable ? <span>YES</span> : <span className="font-bold text-[var(--accent-amber)]">NO</span>}</td>
                  <td className="schema-code text-[var(--text-secondary)]">
                    {column.column_default != null && String(column.column_default) !== "None" ? String(column.column_default) : <span className="text-[var(--text-muted)]">NULL</span>}
                  </td>
                  <td className="max-w-[240px] truncate text-[var(--text-secondary)]">
                    {column.column_comment || <span className="italic text-[var(--text-muted)]">-</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
