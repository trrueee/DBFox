import { Copy, Database, EyeOff } from "lucide-react";
import type { ColumnFilter, FilterMode, SortState } from "../../hooks/useDataTableView";

interface DataGridColumnMenuProps {
  column: string;
  filter?: ColumnFilter;
  sortState: SortState;
  onSort: (direction: "asc" | "desc") => void;
  onClearSort: () => void;
  onFilter: (mode: FilterMode, value?: string) => void;
  onClearFilter: () => void;
  onCopyColumnName: () => void;
  onCopySelectColumn: () => void;
  onHideColumn: () => void;
}

export function DataGridColumnMenu({
  column,
  filter,
  sortState,
  onSort,
  onClearSort,
  onFilter,
  onClearFilter,
  onCopyColumnName,
  onCopySelectColumn,
  onHideColumn,
}: DataGridColumnMenuProps) {
  const isAsc = sortState?.column === column && sortState.direction === "asc";
  const isDesc = sortState?.column === column && sortState.direction === "desc";

  return (
    <div className="data-grid-menu" onClick={(event) => event.stopPropagation()}>
      <div className="data-grid-menu-section">
        <button className={`data-grid-menu-item ${isAsc ? "data-grid-menu-item--active" : ""}`} type="button" onClick={() => onSort("asc")}>
          <span>▲</span> 升序排序
        </button>
        <button className={`data-grid-menu-item ${isDesc ? "data-grid-menu-item--active" : ""}`} type="button" onClick={() => onSort("desc")}>
          <span>▼</span> 降序排序
        </button>
        {sortState?.column === column && (
          <button className="data-grid-menu-item" type="button" onClick={onClearSort}>取消排序</button>
        )}
      </div>

      <div className="data-grid-menu-section">
        <input
          className="data-grid-menu-input"
          value={filter?.mode === "contains" ? filter.value || "" : ""}
          placeholder="搜索当前列值..."
          onChange={(event) => {
            const value = event.target.value;
            if (value) onFilter("contains", value);
            else onClearFilter();
          }}
        />
        <button className={`data-grid-menu-item ${filter?.mode === "is_null" ? "data-grid-menu-item--active" : ""}`} type="button" onClick={() => onFilter("is_null")}>
          只看 NULL
        </button>
        <button className={`data-grid-menu-item ${filter?.mode === "is_not_null" ? "data-grid-menu-item--active" : ""}`} type="button" onClick={() => onFilter("is_not_null")}>
          只看非 NULL
        </button>
        {filter && <button className="data-grid-menu-item" type="button" onClick={onClearFilter}>清除筛选</button>}
      </div>

      <div className="data-grid-menu-section">
        <button className="data-grid-menu-item" type="button" onClick={onCopyColumnName}>
          <Copy size={12} /> 复制列名
        </button>
        <button className="data-grid-menu-item" type="button" onClick={onCopySelectColumn}>
          <Database size={12} /> 复制 SELECT 当前列
        </button>
        <button className="data-grid-menu-item" type="button" onClick={onHideColumn}>
          <EyeOff size={12} /> 隐藏列
        </button>
      </div>
    </div>
  );
}
