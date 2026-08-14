import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnPinningState,
  type ColumnSizingState,
  type VisibilityState,
} from "@tanstack/react-table";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ChevronLeft,
  ChevronRight,
  Code,
  Columns3,
  Copy,
  Database,
  Download,
  EyeOff,
  Filter,
  KeyRound,
  MoreHorizontal,
  Pin,
  PinOff,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { CellValuePreview } from "../../../components/data-grid/CellValuePreview";
import {
  classifyCellValue,
  isNumericCellType,
  isTemporalCellType,
} from "../../../components/data-grid/cellValue";
import { Button, Input, Popover, PopoverContent, PopoverTrigger, Select, Toolbar, ToolbarGroup } from "../../../components/ui";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../../components/ui";
import { copyText, downloadBlobFile } from "../artifacts/artifactActions";
import { useTheme } from "../../../hooks/themeContext";
import {
  useTablePreviewData,
  type TableFilterOperator,
} from "./useTablePreviewData";
import "./TablePreviewPane.css";

interface TablePreviewPaneProps {
  tableId: string;
  datasourceId: string;
  datasourceDbType?: string | null;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

interface PreviewTableRow {
  rowIndex: number;
  values: Record<string, unknown>;
}

interface PreviewColumnMeta {
  column: string;
  dataType?: string;
  isPrimaryKey: boolean;
  isForeignKey: boolean;
  isNullable: boolean;
  comment: string;
}

const EMPTY_PREVIEW_ROWS: Array<Record<string, unknown>> = [];
const SEARCH_DEBOUNCE_MS = 300;

export function TablePreviewPane({
  tableId,
  datasourceId,
  datasourceDbType,
  onOpenSqlConsole,
  onToast,
}: TablePreviewPaneProps) {
  const { appearance } = useTheme();
  const [filterColumn, setFilterColumn] = useState("");
  const [filterOperator, setFilterOperator] = useState<TableFilterOperator>("contains");
  const [filterValue, setFilterValue] = useState("");
  const [sortColumn, setSortColumn] = useState("");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; column: string } | null>(null);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [noticeDismissed, setNoticeDismissed] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [columnSizing, setColumnSizing] = useState<ColumnSizingState>({});
  const [columnPinning, setColumnPinning] = useState<ColumnPinningState>({ left: [] });
  const [pageJump, setPageJump] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const {
    data,
    columnTypes,
    columnDetails,
    isLoading: loading,
    loadingMode,
    error,
    page,
    pageSize,
    setPage,
    setPageSize,
    search,
    setSearch,
    filters,
    setFilters,
    sort,
    setSort,
    warnings,
    notices,
    refresh,
    exportAll,
  } = useTablePreviewData({
    datasourceId,
    datasourceDbType,
    tableName: tableId,
  });
  const activeFilter = filters[0] ?? null;
  const activeSort = sort[0] ?? null;

  useEffect(() => {
    setSearchDraft(search);
  }, [search]);

  useEffect(() => {
    if (searchDraft === search) return undefined;
    const timer = window.setTimeout(() => setSearch(searchDraft), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search, searchDraft, setSearch]);

  useEffect(() => {
    setNoticeDismissed(false);
  }, [data]);

  const metadataColumns = useMemo(() => Array.from(columnTypes.keys()), [columnTypes]);
  const columns = data?.columns.length ? data.columns : metadataColumns;
  const rows = data?.rows ?? EMPTY_PREVIEW_ROWS;
  const initialLoading = loading && !data;
  const refreshing = loading && !!data;
  const displayPage = data?.page ?? page;
  const loadingTargetPage = loadingMode === "page" && page !== displayPage ? page : null;
  const controlColumns = columns.length > 0 ? columns : metadataColumns;
  const defaultPinnedColumn = columns.find((column) => columnDetails.get(column)?.isPrimaryKey) ?? columns[0];

  useEffect(() => {
    setColumnPinning(appearance.freezePrimaryKey && defaultPinnedColumn ? { left: [defaultPinnedColumn] } : { left: [] });
    setColumnVisibility({});
    setColumnSizing({});
  }, [appearance.freezePrimaryKey, datasourceId, defaultPinnedColumn, tableId]);

  useEffect(() => {
    const handleSearchShortcut = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "f") return;
      event.preventDefault();
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    };
    window.addEventListener("keydown", handleSearchShortcut);
    return () => window.removeEventListener("keydown", handleSearchShortcut);
  }, []);
  const previewRows = useMemo<PreviewTableRow[]>(
    () => rows.map((values, rowIndex) => ({ rowIndex, values })),
    [rows],
  );
  const previewColumns = useMemo<Array<ColumnDef<PreviewTableRow, unknown>>>(
    () =>
      columns.map((column) => {
        const dataType = columnTypes.get(column);
        const detail = columnDetails.get(column);
        return {
          id: column,
          accessorFn: (row) => row.values[column],
          header: () => (
            <>
              <span className="table-preview-column-name">{column}</span>
              {dataType && <span className="table-preview-type-badge">{dataType}</span>}
            </>
          ),
          cell: (info) => cellDisplayText(info.getValue(), dataType),
          minSize: 84,
          size: preferredColumnWidth(dataType, detail?.isPrimaryKey ?? false),
          maxSize: 420,
          meta: {
            column,
            dataType,
            isPrimaryKey: detail?.isPrimaryKey ?? false,
            isForeignKey: detail?.isForeignKey ?? false,
            isNullable: detail?.isNullable ?? true,
            comment: detail?.comment ?? "",
          } satisfies PreviewColumnMeta,
        };
      }),
    [columns, columnDetails, columnTypes],
  );
  const previewTable = useReactTable({
    data: previewRows,
    columns: previewColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.rowIndex),
    columnResizeMode: "onChange",
    enableColumnResizing: true,
    onColumnPinningChange: setColumnPinning,
    onColumnSizingChange: setColumnSizing,
    onColumnVisibilityChange: setColumnVisibility,
    state: { columnPinning, columnSizing, columnVisibility },
  });
  const selectedFilterColumn = controlColumns.includes(filterColumn) ? filterColumn : (controlColumns[0] ?? "");
  const selectedSortColumn = controlColumns.includes(sortColumn) ? sortColumn : (activeSort?.column ?? controlColumns[0] ?? "");
  const filterNeedsValue = filterOperator !== "is_null" && filterOperator !== "is_not_null";

  const applyFilter = () => {
    if (!selectedFilterColumn) return;
    setFilters([{
      column: selectedFilterColumn,
      operator: filterOperator,
      value: filterNeedsValue ? filterValue : undefined,
    }]);
    setFilterOpen(false);
  };

  const clearFilter = () => {
    setFilters([]);
    setFilterValue("");
    setFilterOpen(false);
  };

  const applySort = () => {
    if (!selectedSortColumn) return;
    setSort([{ column: selectedSortColumn, direction: sortDirection }]);
  };

  const clearSort = () => {
    setSort([]);
  };

  const selectCell = (rowIndex: number, column: string) => {
    setSelectedCell({ rowIndex, column });
    setSelectedRow(rowIndex);
  };

  const copyCell = async (value: unknown, dataType?: string) => {
    const copyValue = classifyCellValue(value, { dataType }).copyText;
    const ok = await copyText(copyValue);
    onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制");
  };

  const openCell = async (
    cellElement: HTMLTableCellElement,
    rowIndex: number,
    column: string,
    value: unknown,
    dataType?: string,
  ) => {
    selectCell(rowIndex, column);
    const trigger = cellElement.querySelector<HTMLButtonElement>("[data-cell-value-trigger]");
    if (trigger) {
      trigger.click();
      return;
    }
    await copyCell(value, dataType);
  };

  const handleCellKeyDown = (
    event: ReactKeyboardEvent<HTMLTableCellElement>,
    rowIndex: number,
    columnIndex: number,
    column: string,
    value: unknown,
    dataType?: string,
  ) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
      event.preventDefault();
      void copyCell(value, dataType);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      void openCell(event.currentTarget, rowIndex, column, value, dataType);
      return;
    }
    const movement: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const delta = movement[event.key];
    if (!delta) return;
    const targetRow = rowIndex + delta[0];
    const targetColumn = columnIndex + delta[1];
    const target = tableRef.current?.querySelector<HTMLTableCellElement>(
      `[data-row-index="${targetRow}"][data-column-index="${targetColumn}"]`,
    );
    if (!target) return;
    event.preventDefault();
    target.focus();
    const nextColumn = target.dataset.column;
    if (nextColumn) selectCell(targetRow, nextColumn);
  };

  const toggleColumnSort = (column: string) => {
    if (activeSort?.column !== column) {
      setSort([{ column, direction: "asc" }]);
      return;
    }
    if (activeSort.direction === "asc") {
      setSort([{ column, direction: "desc" }]);
      return;
    }
    setSort([]);
  };

  const openColumnFilter = (column: string) => {
    setFilterColumn(column);
    setFilterOpen(true);
  };

  const copyColumnName = async (column: string) => {
    const ok = await copyText(column);
    onToast(ok ? "已复制字段名" : "复制失败，请手动选择复制");
  };

  const submitPageJump = () => {
    const target = Number.parseInt(pageJump, 10);
    if (!Number.isFinite(target) || target < 1) return;
    const maxPage = data?.rowCount ? Math.max(1, Math.ceil(data.rowCount / pageSize)) : null;
    setPage(maxPage ? Math.min(target, maxPage) : target);
    setPageJump("");
  };

  const handleExport = async () => {
    try {
      const blob = await exportAll();
      const ok = downloadBlobFile(`${tableId}.csv`, blob);
      onToast(ok ? "已导出 CSV" : "CSV 导出失败");
    } catch {
      onToast("CSV 导出失败");
    }
  };

  return (
    <div className="hifi-table-preview-pane">
      <div className="hifi-table-toolbar-stack">
        <Toolbar className="hifi-table-toolbar" aria-label="表数据工具栏">
          <ToolbarGroup className="hifi-table-toolbar-group">
            <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={refresh} disabled={loading} title="重新查询当前表数据">
              <RefreshCw className={loading ? "hifi-preview-toolbar-icon is-spinning" : "hifi-preview-toolbar-icon"} aria-hidden="true" />
              <span>刷新</span>
            </Button>
            <Popover open={filterOpen} onOpenChange={setFilterOpen}>
              <PopoverTrigger asChild>
                <Button size="sm" variant="outline" className={`hifi-preview-toolbar-btn ${activeFilter ? "is-active" : ""}`} title="设置表数据筛选条件">
                  <Filter className="hifi-preview-toolbar-icon" aria-hidden="true" />
                  <span>筛选{activeFilter ? " 1" : ""}</span>
                </Button>
              </PopoverTrigger>
              <PopoverContent className="table-preview-popover-content" aria-label="表数据筛选设置">
                <label className="hifi-result-control-field">
                  <span>筛选列</span>
                  <Select
                    className="hifi-preview-control-select"
                    value={selectedFilterColumn}
                    onChange={(event) => setFilterColumn(event.target.value)}
                  >
                    {controlColumns.map((column) => (
                      <option key={column} value={column}>{column}</option>
                    ))}
                  </Select>
                </label>
                <label className="hifi-result-control-field">
                  <span>筛选条件</span>
                  <Select
                    className="hifi-preview-control-select"
                    value={filterOperator}
                    onChange={(event) => setFilterOperator(event.target.value as TableFilterOperator)}
                  >
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
                  </Select>
                </label>
                {filterNeedsValue && (
                  <label className="hifi-result-control-field hifi-result-control-value">
                    <span>筛选值</span>
                    <Input
                      className="hifi-preview-control-input"
                      value={filterValue}
                      onChange={(event) => setFilterValue(event.target.value)}
                    />
                  </label>
                )}
                <div className="table-preview-popover-actions">
                  <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={applyFilter} disabled={!selectedFilterColumn || (filterNeedsValue && !filterValue.trim())}>
                    应用筛选
                  </Button>
                  <Button size="sm" variant="ghost" className="hifi-preview-toolbar-btn" onClick={clearFilter} disabled={!activeFilter && !filterValue}>
                    清除筛选
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
            <Popover>
              <PopoverTrigger asChild>
                <Button size="sm" variant="outline" className={`hifi-preview-toolbar-btn ${activeSort ? "is-active" : ""}`} title="设置表数据排序">
                  <ArrowUpDown className="hifi-preview-toolbar-icon" aria-hidden="true" />
                  <span>排序{activeSort ? ` ${activeSort.direction === "asc" ? "↑" : "↓"}` : ""}</span>
                </Button>
              </PopoverTrigger>
              <PopoverContent className="table-preview-popover-content" aria-label="表数据排序设置">
                <label className="hifi-result-control-field">
                  <span>排序列</span>
                  <Select
                    className="hifi-preview-control-select"
                    value={selectedSortColumn}
                    onChange={(event) => setSortColumn(event.target.value)}
                  >
                    {controlColumns.map((column) => (
                      <option key={column} value={column}>{column}</option>
                    ))}
                  </Select>
                </label>
                <label className="hifi-result-control-field">
                  <span>排序方向</span>
                  <Select
                    className="hifi-preview-control-select"
                    value={sortDirection}
                    onChange={(event) => setSortDirection(event.target.value as "asc" | "desc")}
                  >
                    <option value="desc">降序</option>
                    <option value="asc">升序</option>
                  </Select>
                </label>
                <div className="table-preview-popover-actions">
                  <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={applySort} disabled={!selectedSortColumn}>
                    应用排序
                  </Button>
                  <Button size="sm" variant="ghost" className="hifi-preview-toolbar-btn" onClick={clearSort} disabled={!activeSort}>
                    清除排序
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
            <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={() => void handleExport()} disabled={loading && !data} title="导出当前筛选结果为 CSV">
              <Download className="hifi-preview-toolbar-icon" aria-hidden="true" />
              <span>导出</span>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" title="管理显示字段">
                  <Columns3 className="hifi-preview-toolbar-icon" aria-hidden="true" />
                  <span>列</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="table-preview-column-list" align="start">
                {previewTable.getAllLeafColumns().map((column) => (
                  <DropdownMenuItem key={column.id} onSelect={(event) => { event.preventDefault(); column.toggleVisibility(); }}>
                    {column.getIsVisible() ? <Check size={14} /> : <span className="table-preview-menu-icon-space" />}
                    <span>{column.id}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </ToolbarGroup>
          <ToolbarGroup className="hifi-table-toolbar-group hifi-table-toolbar-right">
            <div className="hifi-preview-search-shell">
              <Search className="hifi-preview-search-icon" aria-hidden="true" />
              <Input
                ref={searchInputRef}
                className="hifi-preview-search"
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setSearch(searchDraft);
                  if (event.key === "Escape") {
                    setSearchDraft("");
                    setSearch("");
                  }
                }}
                placeholder="搜索表数据..."
                aria-label="搜索表数据"
              />
              {searchDraft ? (
                <button className="hifi-preview-search-clear" type="button" onClick={() => { setSearchDraft(""); setSearch(""); }} aria-label="清除搜索">
                  <X size={13} />
                </button>
              ) : (
                <kbd className="hifi-preview-search-shortcut">Ctrl F</kbd>
              )}
            </div>
            <Button size="sm" variant="ghost" className="hifi-preview-toolbar-link" onClick={() => onOpenSqlConsole()} title="打开绑定到当前数据源的 SQL 控制台">
              <Code className="hifi-preview-toolbar-icon" aria-hidden="true" />
              <span>打开 SQL 控制台</span>
            </Button>
          </ToolbarGroup>
        </Toolbar>
      </div>

      <section className="hifi-table-card" aria-label={`表 ${tableId} 的数据预览`}>
      {warnings.length > 0 && !noticeDismissed && (
        <div className="hifi-preview-notice">
          <AlertTriangle size={11} className="flex-shrink-0" />
          <span>{warnings.join("；")}</span>
          <button onClick={() => setNoticeDismissed(true)}>知道了</button>
        </div>
      )}

      <div className="hifi-table-container flex-1 overflow-auto">
        {refreshing && <div className="hifi-preview-loading-bar" />}

        {error && (
          <div className="hifi-preview-error">
            <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {initialLoading && !error && (
          <div className="hifi-preview-skeleton">
            {[0, 1, 2, 3, 4, 5, 6].map((item) => (
              <div key={item} className={`hifi-preview-skeleton-row hifi-preview-skeleton-row-${item}`} />
            ))}
          </div>
        )}

        {data && columns.length > 0 && (
          <div className={refreshing ? "hifi-preview-refreshing" : ""}>
            <table ref={tableRef} className="table-preview-grid" role="grid" aria-label={`表 ${tableId} 的数据`}>
              <colgroup>
                {previewTable.getVisibleLeafColumns().map((column) => (
                  <col key={column.id} width={column.getSize()} />
                ))}
              </colgroup>
              <thead>
                {previewTable.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id} className="table-preview-row" role="row">
                    {headerGroup.headers.map((header) => {
                      const meta = header.column.columnDef.meta as PreviewColumnMeta;
                      const pinned = header.column.getIsPinned();
                      const sortDirectionForColumn = activeSort?.column === meta.column ? activeSort.direction : null;
                      const metadataHint = [
                        meta.isPrimaryKey ? "主键" : "",
                        meta.isForeignKey ? "外键" : "",
                        meta.isNullable ? "允许 NULL" : "不允许 NULL",
                        meta.comment,
                      ].filter(Boolean).join(" · ");
                      return (
                        <th
                          key={header.id}
                          className={`table-preview-head ${pinned ? "is-pinned" : ""}`}
                          role="columnheader"
                          aria-label={meta.dataType ? `${meta.column} ${meta.dataType}` : meta.column}
                          title={metadataHint}
                        >
                          {header.isPlaceholder ? null : (
                            <div className="table-preview-head-content">
                              <button
                                type="button"
                                className="table-preview-sort-trigger"
                                onClick={() => toggleColumnSort(meta.column)}
                                aria-label={`${meta.column} 排序${sortDirectionForColumn === "asc" ? "，当前升序" : sortDirectionForColumn === "desc" ? "，当前降序" : ""}`}
                              >
                                {meta.isPrimaryKey && <KeyRound className="table-preview-key-icon" size={13} aria-label="主键" />}
                                <span className="table-preview-column-name">{meta.column}</span>
                                {meta.dataType && <span className="table-preview-type-badge">{meta.dataType}</span>}
                                {sortDirectionForColumn === "asc" ? <ArrowUp className="table-preview-sort-icon is-active" size={13} /> : sortDirectionForColumn === "desc" ? <ArrowDown className="table-preview-sort-icon is-active" size={13} /> : <ArrowUpDown className="table-preview-sort-icon" size={13} />}
                              </button>
                              <ColumnMenu
                                column={meta.column}
                                isPinned={Boolean(pinned)}
                                canHide={previewTable.getVisibleLeafColumns().length > 1}
                                onFilter={() => openColumnFilter(meta.column)}
                                onCopy={() => void copyColumnName(meta.column)}
                                onHide={() => header.column.toggleVisibility(false)}
                                onPin={() => setColumnPinning(pinned ? { left: [] } : { left: [meta.column] })}
                              />
                            </div>
                          )}
                          <div
                            className={`table-preview-resizer ${header.column.getIsResizing() ? "is-resizing" : ""}`}
                            onDoubleClick={() => header.column.resetSize()}
                            onMouseDown={header.getResizeHandler()}
                            onTouchStart={header.getResizeHandler()}
                            role="separator"
                            aria-label={`调整 ${meta.column} 列宽`}
                          />
                      </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {previewTable.getRowModel().rows.map((row) => (
                  <tr key={row.id} className={`table-preview-row ${selectedRow === row.original.rowIndex ? "is-selected" : ""}`} role="row">
                    {row.getVisibleCells().map((cell, columnIndex) => {
                      const meta = cell.column.columnDef.meta as PreviewColumnMeta;
                      const value = cell.getValue();
                      const pinned = cell.column.getIsPinned();
                      const presentation = classifyCellValue(value, { dataType: meta.dataType });
                      const isNull = presentation.kind === "null";
                      const displayValue = presentation.displayText;
                      const isSelected = selectedCell?.rowIndex === row.original.rowIndex && selectedCell.column === meta.column;
                      const cellClasses = ["table-preview-cell"];
                      if (isNull) cellClasses.push("is-null");
                      if (isSelected) cellClasses.push("is-selected");
                      if (pinned) cellClasses.push("is-pinned");
                      cellClasses.push(`is-${cellAlignment(value, meta.dataType)}`);
                      return (
                        <td
                          key={cell.id}
                          className={cellClasses.join(" ")}
                          role="gridcell"
                          title={displayValue}
                          width={cell.column.getSize()}
                          aria-selected={isSelected ? "true" : undefined}
                          tabIndex={isSelected || (!selectedCell && row.original.rowIndex === 0 && columnIndex === 0) ? 0 : -1}
                          data-row-index={row.original.rowIndex}
                          data-column-index={columnIndex}
                          data-column={meta.column}
                          onClick={() => selectCell(row.original.rowIndex, meta.column)}
                          onDoubleClick={(event) => void openCell(event.currentTarget, row.original.rowIndex, meta.column, value, meta.dataType)}
                          onKeyDown={(event) => handleCellKeyDown(event, row.original.rowIndex, columnIndex, meta.column, value, meta.dataType)}
                        >
                          <CellValuePreview
                            value={value}
                            dataType={meta.dataType}
                            columnName={meta.column}
                            detailHint="单击选择，Ctrl+C 复制"
                            onCopyValue={(copyValue) => void copyText(copyValue).then((ok) => onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制"))}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && (
              <EmptyTableState
                page={page}
                onBackToFirstPage={() => setPage(1)}
                onOpenSqlConsole={onOpenSqlConsole}
              />
            )}
          </div>
        )}

        {data && columns.length === 0 && !error && !initialLoading && (
          <EmptyTableState page={1} onBackToFirstPage={() => setPage(1)} onOpenSqlConsole={onOpenSqlConsole} />
        )}
      </div>

      <div className="hifi-table-footer">
        <span className="hifi-table-status">
          {data ? (
            <>
              <strong>第 {displayPage} 页</strong>
              <span>本页 {rows.length} 行</span>
              <span>{data.rowCount == null ? "总量未计算" : `总计 ${data.rowCount} 行`}</span>
              <span>{loadingTargetPage ? `正在加载第 ${loadingTargetPage} 页` : `查询 ${data.latencyMs}ms`}</span>
            </>
          ) : loading ? "加载中..." : error ? "加载失败" : "等待查询"}
          {!loading && data && notices.length > 0 && (
            <span className="hifi-table-footer-notice"> · {notices.join("；")}</span>
          )}
        </span>
        <div className="hifi-pagination-controls">
          <label className="hifi-page-size-label">
            <span>每页</span>
            <Select
              className="hifi-preview-page-size"
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              <option value="10">10 条</option>
              <option value="20">20 条</option>
              <option value="50">50 条</option>
              <option value="100">100 条</option>
            </Select>
          </label>
          <div className="hifi-pagination" aria-label="分页">
          <Button
            size="sm"
            variant="outline"
            className="hifi-preview-page-btn"
	            disabled={displayPage <= 1 || loading}
	            onClick={() => setPage(Math.max(1, displayPage - 1))}
	          aria-label="上一页"
	          >
            <ChevronLeft size={14} />
          </Button>
	          <span className="hifi-page-num active">{displayPage}</span>
          <Button
            size="sm"
            variant="outline"
            className="hifi-preview-page-btn"
            disabled={!data?.hasNextPage || loading}
	            onClick={() => setPage(displayPage + 1)}
            aria-label="下一页"
          >
            <ChevronRight size={14} />
          </Button>
          </div>
          <form className="hifi-page-jump" onSubmit={(event) => { event.preventDefault(); submitPageJump(); }}>
            <label htmlFor="table-preview-page-jump">跳至</label>
            <Input
              id="table-preview-page-jump"
              inputMode="numeric"
              value={pageJump}
              onChange={(event) => setPageJump(event.target.value.replace(/\D/g, ""))}
              aria-label="跳转页码"
            />
            <Button type="submit" size="sm" variant="outline" disabled={!pageJump || loading}>前往</Button>
          </form>
        </div>
      </div>
      </section>

    </div>
  );
}

function ColumnMenu({
  column,
  isPinned,
  canHide,
  onFilter,
  onCopy,
  onHide,
  onPin,
}: {
  column: string;
  isPinned: boolean;
  canHide: boolean;
  onFilter: () => void;
  onCopy: () => void;
  onHide: () => void;
  onPin: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="table-preview-column-menu-trigger" aria-label={`${column} 列菜单`} title="列操作">
          <MoreHorizontal size={15} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="table-preview-column-menu">
        <DropdownMenuItem onSelect={onFilter}><Filter size={14} />筛选此列</DropdownMenuItem>
        <DropdownMenuItem onSelect={onPin}>
          {isPinned ? <PinOff size={14} /> : <Pin size={14} />}
          {isPinned ? "取消固定" : "固定到左侧"}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onCopy}><Copy size={14} />复制字段名</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={!canHide} onSelect={onHide}><EyeOff size={14} />隐藏此列</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function EmptyTableState({
  page,
  onBackToFirstPage,
  onOpenSqlConsole,
}: {
  page: number;
  onBackToFirstPage: () => void;
  onOpenSqlConsole: (initialSql?: string) => void;
}) {
  const beyondFirstPage = page > 1;
  return (
    <div className="hifi-preview-empty">
      <div className="hifi-preview-empty-illustration" aria-hidden="true">
        <Database size={46} />
      </div>
      <div className="hifi-preview-empty-title">{beyondFirstPage ? "本页没有更多数据" : "这张表还没有数据"}</div>
      <div className="hifi-preview-empty-copy">
        {beyondFirstPage
          ? "已经翻到了数据末尾，可以回到第一页继续浏览。"
          : "表结构已经创建，但目前还没有记录。你可以打开 SQL 控制台执行查询或写入语句。"}
      </div>
      <div className="hifi-preview-empty-actions">
        {beyondFirstPage ? (
          <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={onBackToFirstPage}>
            回到第一页
          </Button>
        ) : (
          <Button size="sm" className="hifi-preview-empty-primary" onClick={() => onOpenSqlConsole()}>
            <Code className="hifi-preview-toolbar-icon" aria-hidden="true" />
            <span>打开 SQL 控制台</span>
          </Button>
        )}
      </div>
      {!beyondFirstPage && <div className="hifi-preview-empty-hint">可以使用 INSERT 语句添加第一条记录</div>}
    </div>
  );
}

function cellDisplayText(value: unknown, dataType?: string) {
  return classifyCellValue(value, { dataType }).displayText;
}

function preferredColumnWidth(dataType?: string, isPrimaryKey = false) {
  const type = (dataType ?? "").toLowerCase();
  if (isPrimaryKey || isNumericCellType(type)) return 112;
  if (/\b(date|time|timestamp|datetime)\b/.test(type)) return 164;
  if (/\b(json|jsonb|text|blob|binary)\b/.test(type)) return 184;
  if (/\b(bool|boolean)\b/.test(type)) return 92;
  return 140;
}

function cellAlignment(value: unknown, dataType?: string) {
  const type = (dataType ?? "").toLowerCase();
  if (typeof value === "number" || isNumericCellType(type)) return "numeric";
  if (isTemporalCellType(type)) return "temporal";
  return "textual";
}
