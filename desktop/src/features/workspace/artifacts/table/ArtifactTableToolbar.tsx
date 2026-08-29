import { ArrowUpDown, Copy, Download, Filter, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import {
  Button,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Toolbar,
  ToolbarButton,
  ToolbarGroup,
} from "../../../../components/ui";
import type { DataFrameFilter, DataFrameFilterOperator } from "../../../../lib/api/types";
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
  filters: DataFrameFilter[];
  onFiltersChange: (value: DataFrameFilter[]) => void;
  isLoading: boolean;
  onRefresh: () => void;
  onExport: () => void;
  onCopy: () => void;
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
  onRefresh,
  onExport,
  onCopy,
}: ArtifactTableToolbarProps) {
  const [filterColumn, setFilterColumn] = useState(columns[0] ?? "");
  const [filterOperator, setFilterOperator] = useState<DataFrameFilterOperator>("contains");
  const [filterValue, setFilterValue] = useState("");
  const [sortColumn, setSortColumn] = useState(columns[sort?.columnIndex ?? 0] ?? columns[0] ?? "");
  const [sortDirection, setSortDirection] = useState<SortDirection>(sort?.direction ?? "desc");

  const selectedFilterColumn = columns.includes(filterColumn) ? filterColumn : (columns[0] ?? "");
  const selectedSortColumn = columns.includes(sortColumn) ? sortColumn : (columns[sort?.columnIndex ?? 0] ?? columns[0] ?? "");
  const filterNeedsValue = filterOperator !== "is_null" && filterOperator !== "is_not_null";

  const applyFilter = () => {
    if (!selectedFilterColumn) return;
    const nextFilter: DataFrameFilter = {
      field: selectedFilterColumn,
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
      <div className="artifact-table-toolbar-stack">
        <Toolbar className="artifact-table-toolbar">
          <ToolbarGroup className="artifact-table-toolbar-main">
            <ToolbarButton asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="artifact-table-toolbar-button"
                onClick={onRefresh}
                disabled={isLoading}
              >
                <RefreshCw size={14} className={isLoading ? "artifact-table-refresh-icon is-spinning" : "artifact-table-refresh-icon"} /> 刷新
              </Button>
            </ToolbarButton>
            <Popover>
              <ToolbarButton asChild>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="artifact-table-toolbar-button"
                  >
                    <Filter size={14} /> 筛选{filters.length > 0 ? ` ${filters.length}` : ""}
                  </Button>
                </PopoverTrigger>
              </ToolbarButton>
              <PopoverContent className="artifact-table-popover-content" aria-label="结果筛选设置">
                <label className="artifact-table-control-field">
                  <span>筛选列</span>
                  <Select value={selectedFilterColumn} onValueChange={setFilterColumn}>
                    <SelectTrigger className="artifact-table-control-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {columns.map((column) => (
                        <SelectItem key={column} value={column}>{column}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>
                <label className="artifact-table-control-field">
                  <span>筛选条件</span>
                  <Select value={filterOperator} onValueChange={(value) => setFilterOperator(value as DataFrameFilterOperator)}>
                    <SelectTrigger className="artifact-table-control-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="contains">包含</SelectItem>
                      <SelectItem value="equals">等于</SelectItem>
                      <SelectItem value="not_equals">不等于</SelectItem>
                      <SelectItem value="starts_with">开头为</SelectItem>
                      <SelectItem value="ends_with">结尾为</SelectItem>
                      <SelectItem value="gt">大于</SelectItem>
                      <SelectItem value="gte">大于等于</SelectItem>
                      <SelectItem value="lt">小于</SelectItem>
                      <SelectItem value="lte">小于等于</SelectItem>
                      <SelectItem value="is_null">为空</SelectItem>
                      <SelectItem value="is_not_null">不为空</SelectItem>
                    </SelectContent>
                  </Select>
                </label>
                {filterNeedsValue && (
                  <label className="artifact-table-control-field artifact-table-control-value">
                    <span>筛选值</span>
                    <Input className="artifact-table-control-input" value={filterValue} onChange={(event) => setFilterValue(event.target.value)} />
                  </label>
                )}
                <div className="artifact-table-popover-actions">
                  <Button type="button" variant="outline" size="sm" className="artifact-table-control-button" onClick={applyFilter} disabled={!selectedFilterColumn || (filterNeedsValue && !filterValue.trim())}>
                    应用筛选
                  </Button>
                  <Button type="button" variant="ghost" size="sm" className="artifact-table-control-button" onClick={clearFilters} disabled={filters.length === 0 && !filterValue}>
                    清除筛选
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
            <Popover>
              <ToolbarButton asChild>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="artifact-table-toolbar-button"
                  >
                    <ArrowUpDown size={14} /> 排序{sort ? ` ${sort.direction === "asc" ? "↑" : "↓"}` : ""}
                  </Button>
                </PopoverTrigger>
              </ToolbarButton>
              <PopoverContent className="artifact-table-popover-content" aria-label="结果排序设置">
                <label className="artifact-table-control-field">
                  <span>排序列</span>
                  <Select value={selectedSortColumn} onValueChange={setSortColumn}>
                    <SelectTrigger className="artifact-table-control-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {columns.map((column) => (
                        <SelectItem key={column} value={column}>{column}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>
                <label className="artifact-table-control-field">
                  <span>排序方向</span>
                  <Select value={sortDirection} onValueChange={(value) => setSortDirection(value as SortDirection)}>
                    <SelectTrigger className="artifact-table-control-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="desc">降序</SelectItem>
                      <SelectItem value="asc">升序</SelectItem>
                    </SelectContent>
                  </Select>
                </label>
                <div className="artifact-table-popover-actions">
                  <Button type="button" variant="outline" size="sm" className="artifact-table-control-button" onClick={applySort} disabled={!selectedSortColumn}>
                    应用排序
                  </Button>
                  <Button type="button" variant="ghost" size="sm" className="artifact-table-control-button" onClick={onClearSort} disabled={!sort}>
                    清除排序
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
            <ToolbarButton asChild>
              <Button type="button" variant="ghost" size="sm" className="artifact-table-toolbar-button" onClick={onExport}>
                <Download size={14} /> 导出
              </Button>
            </ToolbarButton>
            <ToolbarButton asChild>
              <Button type="button" variant="ghost" size="sm" className="artifact-table-toolbar-button" onClick={onCopy}>
                <Copy size={14} /> 复制
              </Button>
            </ToolbarButton>
            <div className="artifact-table-search-shell">
              <Search size={14} className="artifact-table-search-icon" />
              <Input
                className="artifact-table-search"
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder="搜索 SQL 结果..."
              />
            </div>
          </ToolbarGroup>
        </Toolbar>
      </div>
    );
  }

  return (
    <div className="artifact-table-inline-toolbar">
      <label className="artifact-table-visually-hidden" htmlFor={`${artifactId}-table-search`}>
        搜索结果
      </label>
      <Input
        id={`${artifactId}-table-search`}
        className="artifact-table-inline-search"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="搜索结果"
      />
    </div>
  );
}
