import { Filter, RefreshCw, Search } from "lucide-react";
import type { FormEvent } from "react";
import type { SchemaTable } from "../../lib/api";

interface TableDataToolbarProps {
  tableName: string;
  tableMeta: SchemaTable | null;
  filterText: string;
  appliedFilter: string;
  loading: boolean;
  onFilterTextChange: (value: string) => void;
  onApplyFilter: (event: FormEvent) => void;
  onClearFilter: () => void;
  onRefresh: () => void;
}

export function TableDataToolbar({
  tableName,
  tableMeta,
  filterText,
  appliedFilter,
  loading,
  onFilterTextChange,
  onApplyFilter,
  onClearFilter,
  onRefresh,
}: TableDataToolbarProps) {
  return (
    <header className="table-data-toolbar">
      <div className="table-data-title" title={tableName}>
        <span>{tableName}</span>
        {tableMeta?.table_comment && <span className="table-data-comment">{tableMeta.table_comment}</span>}
      </div>

      <div className="table-data-actions">
        <form className="table-data-search" onSubmit={onApplyFilter}>
          <div className="table-data-search-input-wrap">
            <Search size={12} />
            <input
              placeholder="搜索表格数据..."
              value={filterText}
              onChange={(event) => onFilterTextChange(event.target.value)}
            />
          </div>
          <button className="table-data-button table-data-button--primary" type="submit">
            <Filter size={12} />
            过滤
          </button>
          {appliedFilter && (
            <button className="table-data-button" type="button" onClick={onClearFilter}>
              清除
            </button>
          )}
        </form>

        <span className="table-data-separator" />

        <button className="table-data-button" type="button" onClick={onRefresh} disabled={loading} title="刷新数据">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
    </header>
  );
}
