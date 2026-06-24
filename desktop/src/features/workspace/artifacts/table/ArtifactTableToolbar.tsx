import { ArrowUpDown, Copy, Download, Filter, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import type { ResultFilter, ResultFilterOperator } from "../../../../lib/api/types";
import type { SortDirection, SortState } from "./useArtifactTableData";

interface ArtifactTableToolbarProps {
  mode: "inline" | "workspace";
  artifactId: string;
  columns: string[];
  search: string;
  onSearchChange: (value: string) => void;
  sort: SortState | null;
  onApplySort: (columnIndex: number, direction: SortDirection) => void;
  onClearSort: () => void;
  filters: ResultFilter[];
  onFiltersChange: (value: ResultFilter[]) => void;
  isLoading: boolean;
  isSqlBackedWorkspace: boolean;
  onRefresh: () => void;
  onExport: () => void;
  onCopy: () => void;
  canToggleLoadedRows: boolean;
  expanded: boolean;
  loadedRowCount: number;
  onToggleExpanded: () => void;
}

export function ArtifactTableToolbar({
  mode,
  artifactId,
  columns,
  search,
  onSearchChange,
  sort,
  onApplySort,
  onClearSort,
  filters,
  onFiltersChange,
  isLoading,
  isSqlBackedWorkspace,
  onRefresh,
  onExport,
  onCopy,
  canToggleLoadedRows,
  expanded,
  loadedRowCount,
  onToggleExpanded,
}: ArtifactTableToolbarProps) {
  const [filterOpen, setFilterOpen] = useState(false);
  const [filterColumn, setFilterColumn] = useState(columns[0] ?? "");
  const [filterOperator, setFilterOperator] = useState<ResultFilterOperator>("contains");
  const [filterValue, setFilterValue] = useState("");
  const [sortOpen, setSortOpen] = useState(false);
  const [sortColumn, setSortColumn] = useState(columns[sort?.columnIndex ?? 0] ?? columns[0] ?? "");
  const [sortDirection, setSortDirection] = useState<SortDirection>(sort?.direction ?? "desc");

  const selectedFilterColumn = columns.includes(filterColumn) ? filterColumn : (columns[0] ?? "");
  const selectedSortColumn = columns.includes(sortColumn) ? sortColumn : (columns[sort?.columnIndex ?? 0] ?? columns[0] ?? "");
  const filterNeedsValue = filterOperator !== "is_null" && filterOperator !== "is_not_null";

  const applyFilter = () => {
    if (!selectedFilterColumn) return;
    const nextFilter: ResultFilter = {
      column: selectedFilterColumn,
      operator: filterOperator,
      value: filterNeedsValue ? filterValue : undefined,
    };
    onFiltersChange([nextFilter]);
  };

  const clearFilters = () => {
    onFiltersChange([]);
    setFilterValue("");
  };

  const applySort = () => {
    const columnIndex = columns.indexOf(selectedSortColumn);
    if (columnIndex < 0) return;
    onApplySort(columnIndex, sortDirection);
  };

  if (mode === "workspace") {
    return (
      <div className="hifi-result-toolbar-stack">
        <div className="hifi-panel-toolbar hifi-result-toolbar px-2">
          <div className="hifi-toolbar-left hifi-result-toolbar-main flex items-center gap-1">
            <button className="hifi-toolbar-btn" onClick={onRefresh} disabled={isLoading || !isSqlBackedWorkspace}>
              <RefreshCw size={10} className={isLoading ? "animate-spin" : ""} /> 刷新
            </button>
            <button
              className="hifi-toolbar-btn"
              onClick={() => setFilterOpen((value) => !value)}
              disabled={!isSqlBackedWorkspace}
            >
              <Filter size={10} /> 筛选{filters.length > 0 ? ` ${filters.length}` : ""}
            </button>
            <button
              className="hifi-toolbar-btn"
              onClick={() => setSortOpen((value) => !value)}
              disabled={!isSqlBackedWorkspace}
            >
              <ArrowUpDown size={10} /> 排序{sort ? ` ${sort.direction === "asc" ? "↑" : "↓"}` : ""}
            </button>
            <button className="hifi-toolbar-btn" onClick={onExport}>
              <Download size={10} /> 导出
            </button>
            <button className="hifi-toolbar-btn" onClick={onCopy}>
              <Copy size={10} /> 复制
            </button>
            <div className="hifi-result-search-shell relative flex items-center">
              <Search size={12} className="hifi-result-search-icon absolute left-2" />
              <input
                className="hifi-input hifi-result-search pl-6 pr-2 text-[var(--ui-font-label)]"
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder={isSqlBackedWorkspace ? "搜索 SQL 结果..." : "本地搜索..."}
              />
            </div>
          </div>
        </div>
        {isSqlBackedWorkspace && filterOpen && (
          <div className="hifi-result-control-row px-2">
            <label className="hifi-result-control-field">
              <span>筛选列</span>
              <select value={selectedFilterColumn} onChange={(event) => setFilterColumn(event.target.value)}>
                {columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </select>
            </label>
            <label className="hifi-result-control-field">
              <span>筛选条件</span>
              <select value={filterOperator} onChange={(event) => setFilterOperator(event.target.value as ResultFilterOperator)}>
                <option value="contains">包含</option>
                <option value="equals">等于</option>
                <option value="not_equals">不等于</option>
                <option value="starts_with">开头为</option>
                <option value="ends_with">结尾为</option>
                <option value="gt">大于</option>
                <option value="gte">大于等于</option>
                <option value="lt">小于</option>
                <option value="lte">小于等于</option>
                <option value="is_null">为空</option>
                <option value="is_not_null">不为空</option>
              </select>
            </label>
            {filterNeedsValue && (
              <label className="hifi-result-control-field hifi-result-control-value">
                <span>筛选值</span>
                <input value={filterValue} onChange={(event) => setFilterValue(event.target.value)} />
              </label>
            )}
            <button className="hifi-toolbar-btn" onClick={applyFilter} disabled={!selectedFilterColumn || (filterNeedsValue && !filterValue.trim())}>
              应用筛选
            </button>
            <button className="hifi-toolbar-btn" onClick={clearFilters} disabled={filters.length === 0 && !filterValue}>
              清除筛选
            </button>
          </div>
        )}
        {isSqlBackedWorkspace && sortOpen && (
          <div className="hifi-result-control-row px-2">
            <label className="hifi-result-control-field">
              <span>排序列</span>
              <select value={selectedSortColumn} onChange={(event) => setSortColumn(event.target.value)}>
                {columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </select>
            </label>
            <label className="hifi-result-control-field">
              <span>排序方向</span>
              <select value={sortDirection} onChange={(event) => setSortDirection(event.target.value as SortDirection)}>
                <option value="desc">降序</option>
                <option value="asc">升序</option>
              </select>
            </label>
            <button className="hifi-toolbar-btn" onClick={applySort} disabled={!selectedSortColumn}>
              应用排序
            </button>
            <button className="hifi-toolbar-btn" onClick={onClearSort} disabled={!sort}>
              清除排序
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor={`${artifactId}-table-search`}>
        搜索结果
      </label>
      <input
        id={`${artifactId}-table-search`}
        className="hifi-input h-7 min-w-[180px] flex-1 rounded px-2 text-[var(--ui-font-label)]"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="搜索结果"
      />
      {canToggleLoadedRows && (
        <button type="button" className="hifi-guide-btn-secondary hifi-artifact-action-btn" onClick={onToggleExpanded}>
          {expanded ? "收起预览" : `查看全部已载入 ${loadedRowCount} 行`}
        </button>
      )}
    </div>
  );
}
