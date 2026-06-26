import type { ColumnFilter, DataGridDensity, SortState } from "./types";

interface DataGridToolbarProps {
  rowsCount: number;
  visibleRowsCount: number;
  filters: Record<string, ColumnFilter>;
  sortState: SortState;
  hiddenColumnsCount: number;
  density: DataGridDensity;
  onClearFilter: (column: string) => void;
  onClearSort: () => void;
  onShowAllColumns: () => void;
  onResetView: () => void;
  onToggleDensity: () => void;
}

function filterLabel(filter: ColumnFilter) {
  if (filter.mode === "is_null") return `${filter.column} 为 NULL`;
  if (filter.mode === "is_not_null") return `${filter.column} 非 NULL`;
  return `${filter.column} 包含 ${filter.value || ""}`;
}

export function DataGridToolbar({
  rowsCount,
  visibleRowsCount,
  filters,
  sortState,
  hiddenColumnsCount,
  density,
  onClearFilter,
  onClearSort,
  onShowAllColumns,
  onResetView,
  onToggleDensity,
}: DataGridToolbarProps) {
  const activeFilters = Object.values(filters);
  const hasViewState = activeFilters.length > 0 || sortState || hiddenColumnsCount > 0;

  return (
    <div className="data-grid-toolbar">
      <div className="data-grid-toolbar-left">
        <span>显示 <strong>{visibleRowsCount}</strong> / {rowsCount} 行</span>
        {activeFilters.map((filter) => (
          <span className="data-grid-chip" key={filter.column} title={filterLabel(filter)}>
            {filterLabel(filter)}
            <button type="button" onClick={() => onClearFilter(filter.column)}>×</button>
          </span>
        ))}
        {sortState && (
          <span className="data-grid-chip">
            {sortState.column} {sortState.direction === "asc" ? "升序" : "降序"}
            <button type="button" onClick={onClearSort}>×</button>
          </span>
        )}
        {hiddenColumnsCount > 0 && (
          <span className="data-grid-chip">
            隐藏 {hiddenColumnsCount} 列
            <button type="button" onClick={onShowAllColumns}>×</button>
          </span>
        )}
      </div>

      <div className="data-grid-toolbar-right">
        <button className="data-grid-button" type="button" onClick={onToggleDensity}>
          {density === "compact" ? "舒适模式" : "紧凑模式"}
        </button>
        {hasViewState && (
          <button className="data-grid-button" type="button" onClick={onResetView}>
            重置视图
          </button>
        )}
      </div>
    </div>
  );
}
