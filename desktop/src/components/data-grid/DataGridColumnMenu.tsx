import { Copy, Database, EyeOff } from "lucide-react";
import type { ColumnFilter, FilterMode, SortState } from "./types";
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "../ui";

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
    <DropdownMenuContent className="data-grid-menu" align="end" sideOffset={6} onClick={(event) => event.stopPropagation()}>
      <div className="data-grid-menu-section">
        <DropdownMenuItem className={`data-grid-menu-item ${isAsc ? "data-grid-menu-item--active" : ""}`} onSelect={() => onSort("asc")}>
          <span>▲</span> 升序排序
        </DropdownMenuItem>
        <DropdownMenuItem className={`data-grid-menu-item ${isDesc ? "data-grid-menu-item--active" : ""}`} onSelect={() => onSort("desc")}>
          <span>▼</span> 降序排序
        </DropdownMenuItem>
        {sortState?.column === column && (
          <DropdownMenuItem className="data-grid-menu-item" onSelect={onClearSort}>取消排序</DropdownMenuItem>
        )}
      </div>

      <DropdownMenuSeparator className="data-grid-menu-separator" />

      <div className="data-grid-menu-section">
        <input
          className="data-grid-menu-input"
          value={filter?.mode === "contains" ? filter.value || "" : ""}
          placeholder="搜索当前列值..."
          onKeyDown={(event) => event.stopPropagation()}
          onChange={(event) => {
            const value = event.target.value;
            if (value) onFilter("contains", value);
            else onClearFilter();
          }}
        />
        <DropdownMenuItem className={`data-grid-menu-item ${filter?.mode === "is_null" ? "data-grid-menu-item--active" : ""}`} onSelect={() => onFilter("is_null")}>
          只看 NULL
        </DropdownMenuItem>
        <DropdownMenuItem className={`data-grid-menu-item ${filter?.mode === "is_not_null" ? "data-grid-menu-item--active" : ""}`} onSelect={() => onFilter("is_not_null")}>
          只看非 NULL
        </DropdownMenuItem>
        {filter && <DropdownMenuItem className="data-grid-menu-item" onSelect={onClearFilter}>清除筛选</DropdownMenuItem>}
      </div>

      <DropdownMenuSeparator className="data-grid-menu-separator" />

      <div className="data-grid-menu-section">
        <DropdownMenuItem className="data-grid-menu-item" onSelect={onCopyColumnName}>
          <Copy size={12} /> 复制列名
        </DropdownMenuItem>
        <DropdownMenuItem className="data-grid-menu-item" onSelect={onCopySelectColumn}>
          <Database size={12} /> 复制 SELECT 当前列
        </DropdownMenuItem>
        <DropdownMenuItem className="data-grid-menu-item" onSelect={onHideColumn}>
          <EyeOff size={12} /> 隐藏列
        </DropdownMenuItem>
      </div>
    </DropdownMenuContent>
  );
}
