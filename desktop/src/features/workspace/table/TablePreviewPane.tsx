import { useEffect, useMemo, useRef, useState } from "react";
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
  CirclePlus,
  Code,
  Columns3,
  Copy,
  Database,
  Download,
  EyeOff,
  Filter,
  KeyRound,
  Link2,
  MoreHorizontal,
  Pin,
  PinOff,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { ImageCell } from "../../../components/ImageCell";
import { isImageUrl } from "../../../components/imageUrl";
import { CellValuePreview } from "../../../components/data-grid/CellValuePreview";
import { JsonTree } from "../../../components/data-grid/json";
import { getCellPreviewJson } from "../../../components/data-grid/cellValue";
import { Button, Input, Popover, PopoverContent, PopoverTrigger, Select, Toolbar, ToolbarGroup } from "../../../components/ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
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

interface DetailCell {
  column: string;
  displayValue: string;
  json: ReturnType<typeof getCellPreviewJson>;
}

const EMPTY_PREVIEW_ROWS: Array<Record<string, unknown>> = [];

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
  const [detailCell, setDetailCell] = useState<DetailCell | null>(null);
  const [pageJump, setPageJump] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
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

  const handleCellCopy = async (rowIndex: number, column: string, value: unknown, dataType?: string) => {
    setSelectedCell({ rowIndex, column });
    setSelectedRow(rowIndex);
    const displayValue = cellDisplayText(value, dataType);
    const json = getCellPreviewJson(value, displayValue);
    if (json !== null) {
      setDetailCell({ column, displayValue, json });
      return;
    }
    const ok = await copyText(displayValue);
    onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制");
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
            <Button
              size="sm"
              variant="outline"
              className="hifi-preview-toolbar-btn hifi-preview-toolbar-btn--accent"
              onClick={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")}
              title="生成少量测试记录"
            >
              <Sparkles className="hifi-preview-toolbar-icon is-accent" aria-hidden="true" />
              <span>生成测试数据</span>
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
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索表数据..."
                aria-label="搜索表数据"
              />
              {search ? (
                <button className="hifi-preview-search-clear" type="button" onClick={() => setSearch("")} aria-label="清除搜索">
                  <X size={13} />
                </button>
              ) : (
                <kbd className="hifi-preview-search-shortcut">Ctrl F</kbd>
              )}
            </div>
            <Button size="sm" variant="ghost" className="hifi-preview-toolbar-link" onClick={() => onOpenSqlConsole()} title="在 SQL 控制台打开当前表">
              <Code className="hifi-preview-toolbar-icon" aria-hidden="true" />
              <span>在 SQL 运行</span>
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
            <table className="table-preview-grid">
              <colgroup>
                {previewTable.getVisibleLeafColumns().map((column) => (
                  <col key={column.id} width={column.getSize()} />
                ))}
              </colgroup>
              <thead>
                {previewTable.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id} className="table-preview-row">
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
                  <tr key={row.id} className={`table-preview-row ${selectedRow === row.original.rowIndex ? "is-selected" : ""}`}>
                    {row.getVisibleCells().map((cell) => {
                      const meta = cell.column.columnDef.meta as PreviewColumnMeta;
                      const value = cell.getValue();
                      const pinned = cell.column.getIsPinned();
                      const isNull = value === null || value === undefined;
                      const displayValue = cellDisplayText(value, meta.dataType);
                      const isSelected = selectedCell?.rowIndex === row.original.rowIndex && selectedCell.column === meta.column;
                      const cellClasses = ["table-preview-cell"];
                      if (isNull) cellClasses.push("is-null");
                      if (isSelected) cellClasses.push("is-selected");
                      if (pinned) cellClasses.push("is-pinned");
                      cellClasses.push(`is-${cellAlignment(value, meta.dataType)}`);
                      if (typeof value === "string" && isImageUrl(value)) {
                        return (
                          <td
                            key={cell.id}
                            className={[...cellClasses, "table-preview-image-cell"].join(" ")}
                            title={displayValue}
                            width={cell.column.getSize()}
                            aria-selected={isSelected ? "true" : undefined}
                            onClick={() => void handleCellCopy(row.original.rowIndex, meta.column, value, meta.dataType)}
                          >
                            <ImageCell url={value} />
                          </td>
                        );
                      }
                      return (
                        <td
                          key={cell.id}
                          className={cellClasses.join(" ")}
                          title={displayValue}
                          width={cell.column.getSize()}
                          aria-selected={isSelected ? "true" : undefined}
                          onClick={() => void handleCellCopy(row.original.rowIndex, meta.column, value, meta.dataType)}
                        >
                          {isNull ? (
                            <span className="table-preview-null-pill">NULL</span>
                          ) : typeof value === "boolean" ? (
                            <span className={`table-preview-boolean ${value ? "is-true" : "is-false"}`}>{value ? "TRUE" : "FALSE"}</span>
                          ) : typeof value === "string" && /^https?:\/\//i.test(value) ? (
                            <span className="table-preview-link-value"><Link2 size={13} aria-hidden="true" />{displayValue}</span>
                          ) : (
                            <CellValuePreview value={value} displayValue={displayValue} detailHint="点击复制单元格" />
                          )}
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
                onGenerate={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")}
                onImport={() => onToast("数据导入入口将在导入功能启用后开放")}
              />
            )}
          </div>
        )}

        {data && columns.length === 0 && !error && !initialLoading && (
          <EmptyTableState page={1} onBackToFirstPage={() => setPage(1)} onOpenSqlConsole={onOpenSqlConsole} onGenerate={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")} onImport={() => onToast("数据导入入口将在导入功能启用后开放")} />
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

      <Dialog open={detailCell !== null} onOpenChange={(open) => { if (!open) setDetailCell(null); }}>
        <DialogContent className="table-preview-detail-drawer">
          <DialogHeader>
            <DialogTitle>JSON · {detailCell?.column}</DialogTitle>
            <DialogDescription>格式化查看字段内容；关闭后仍停留在当前行。</DialogDescription>
          </DialogHeader>
          <div className="table-preview-detail-body">
            {detailCell?.json ? <JsonTree data={detailCell.json} /> : null}
          </div>
          <div className="table-preview-detail-footer">
            <span>{detailCell?.displayValue.length ?? 0} 字符</span>
            <Button size="sm" variant="outline" onClick={() => detailCell && void copyText(detailCell.displayValue).then((ok) => onToast(ok ? "已复制 JSON" : "复制失败，请手动选择复制"))}>
              <Copy size={14} />
              复制 JSON
            </Button>
          </div>
        </DialogContent>
      </Dialog>
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
  onGenerate,
  onImport,
}: {
  page: number;
  onBackToFirstPage: () => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onGenerate: () => void;
  onImport: () => void;
}) {
  const beyondFirstPage = page > 1;
  return (
    <div className="hifi-preview-empty">
      <div className="hifi-preview-empty-illustration" aria-hidden="true">
        <Database size={46} />
        <span><CirclePlus size={22} /></span>
      </div>
      <div className="hifi-preview-empty-title">{beyondFirstPage ? "本页没有更多数据" : "这张表还没有数据"}</div>
      <div className="hifi-preview-empty-copy">
        {beyondFirstPage
          ? "已经翻到了数据末尾，可以回到第一页继续浏览。"
          : "表结构已经创建，但目前还没有记录。你可以生成测试数据、执行 SQL，或从外部文件导入数据。"}
      </div>
      <div className="hifi-preview-empty-actions">
        {beyondFirstPage ? (
          <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={onBackToFirstPage}>
            回到第一页
          </Button>
        ) : (
          <>
            <Button size="sm" className="hifi-preview-empty-primary" onClick={onGenerate}>
              <Sparkles className="hifi-preview-toolbar-icon is-accent" aria-hidden="true" />
              <span>生成测试数据</span>
            </Button>
            <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={() => onOpenSqlConsole()}>
              <Code className="hifi-preview-toolbar-icon" aria-hidden="true" />
              <span>打开 SQL 控制台</span>
            </Button>
          </>
        )}
      </div>
      {!beyondFirstPage && (
        <>
          <button className="hifi-preview-empty-import" type="button" onClick={onImport}>
            导入数据
          </button>
          <div className="hifi-preview-empty-hint">也可以使用 INSERT 语句添加第一条记录</div>
        </>
      )}
    </div>
  );
}

function cellDisplayText(value: unknown, dataType?: string) {
  if (value === null || value === undefined) return "NULL";
  const temporalDisplay = formatTemporalCell(value, dataType);
  if (temporalDisplay) return temporalDisplay;
  return cellToText(value);
}

function cellToText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatTemporalCell(value: unknown, dataType?: string) {
  const text = value instanceof Date ? value.toISOString() : typeof value === "string" || typeof value === "number" ? String(value) : "";
  if (!text) return "";
  const temporalType = /\b(date|time|timestamp|datetime)\b/i.test(dataType ?? "");
  const normalized = text.trim();
  const match = normalized.match(
    /^(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|[+-]\d{2}:?\d{2})?)?$/,
  );
  if (!match || (!temporalType && !normalized.includes("T"))) return "";
  if (!match[2]) return match[1];
  const fraction = (match[3] ?? "").slice(0, 3).replace(/0+$/, "");
  return `${match[1]} ${match[2]}${fraction ? `.${fraction}` : ""}`;
}

function preferredColumnWidth(dataType?: string, isPrimaryKey = false) {
  const type = (dataType ?? "").toLowerCase();
  if (isPrimaryKey || isNumericDataType(type)) return 112;
  if (/\b(date|time|timestamp|datetime)\b/.test(type)) return 164;
  if (/\b(json|jsonb|text|blob|binary)\b/.test(type)) return 184;
  if (/\b(bool|boolean)\b/.test(type)) return 92;
  return 140;
}

function cellAlignment(value: unknown, dataType?: string) {
  const type = (dataType ?? "").toLowerCase();
  if (typeof value === "number" || isNumericDataType(type)) return "numeric";
  if (/\b(date|time|timestamp|datetime)\b/.test(type)) return "temporal";
  return "textual";
}

function isNumericDataType(dataType: string) {
  return /\b(?:tiny|small|medium|big)?int(?:eger)?\b|\b(serial|numeric|decimal|float|double|real)\b/.test(dataType);
}
