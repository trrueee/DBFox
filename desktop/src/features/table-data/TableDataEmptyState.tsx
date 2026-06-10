import { Database, Layers, Sparkles } from "lucide-react";
import type { SchemaTable } from "../../lib/api";

interface TableDataEmptyStateProps {
  schemaTables: SchemaTable[];
  onSelectTable: (tableName: string) => void;
}

export function TableDataEmptyState({ schemaTables, onSelectTable }: TableDataEmptyStateProps) {
  return (
    <div className="table-data-state">
      <div className="table-data-state-card">
        <div className="table-data-state-icon">
          <Database size={30} />
        </div>
        <div>
          <div className="table-data-state-title">选择数据表开始浏览</div>
          <p className="table-data-state-copy">
            数据页只负责看数据、筛数据和分页预览。表结构、ER 图和 SQL 编辑器都在各自的工作区里处理。
          </p>
        </div>

        {schemaTables.length === 0 ? (
          <div className="table-data-state-copy rounded-lg border border-dashed border-[var(--border-light)] bg-[var(--bg-secondary)] p-4">
            当前连接下没有发现数据表，请先同步 Schema。
          </div>
        ) : (
          <div className="w-full">
            <div className="mb-2 flex items-center gap-1.5 text-[0.72rem] font-black uppercase tracking-[0.08em] text-[var(--text-muted)]">
              <Layers size={13} />
              快速打开
            </div>
            <div className="table-data-table-picker">
              {schemaTables.slice(0, 12).map((table) => (
                <button className="table-data-table-card" key={table.id} type="button" onClick={() => onSelectTable(table.table_name)} title={table.table_name}>
                  <Layers size={13} />
                  <span>{table.table_name}</span>
                </button>
              ))}
              {schemaTables.length > 12 && (
                <div className="table-data-table-card justify-center border-dashed text-[var(--text-muted)]">
                  还有 {schemaTables.length - 12} 张表
                </div>
              )}
            </div>
          </div>
        )}

        <div className="flex items-center gap-1.5 text-[0.72rem] text-[var(--text-muted)]">
          <Sparkles size={13} className="text-[var(--accent-indigo)]" />
          也可以从左侧对象树双击表名打开数据。
        </div>
      </div>
    </div>
  );
}
