import { useEffect, useMemo, useRef, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { AlertTriangle, ArrowUpDown, Code, Database, Download, Filter, RefreshCw, Search, Sparkles } from "lucide-react";
import { ImageCell } from "../../../components/ImageCell";
import { isImageUrl } from "../../../components/imageUrl";
import { CellValuePreview } from "../../../components/data-grid/CellValuePreview";
import { Button, Input, Popover, PopoverContent, PopoverTrigger, Select, Toolbar, ToolbarGroup } from "../../../components/ui";
import { agentApi } from "../../../lib/api/agent";
import { findTableByName, listColumns, type EngineColumn } from "../../../lib/api/schema";
import { copyText, downloadBlobFile } from "../artifacts/artifactActions";
import "./TablePreviewPane.css";

interface TablePreviewPaneProps {
  tableId: string;
  datasourceId: string;
  datasourceDbType?: string | null;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

interface PreviewData {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  latencyMs: number;
  hasNext: boolean;
  warnings: string[];
  notices: string[];
  page: number;
  pageSize: number;
}

type TableFilterOperator =
  | "contains"
  | "equals"
  | "not_equals"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "is_null"
  | "is_not_null";

interface TableFilterState {
  column: string;
  operator: TableFilterOperator;
  value?: string;
}

interface TableSortState {
  column: string;
  direction: "asc" | "desc";
}

interface PreviewTableRow {
  rowIndex: number;
  values: Record<string, unknown>;
}

interface PreviewColumnMeta {
  column: string;
  dataType?: string;
}

// Keeps the last loaded page per table so re-opening a tab shows data instantly
// (then revalidates in the background) instead of flashing an empty loading view.
const previewCache = new Map<string, PreviewData>();
const EMPTY_PREVIEW_COLUMNS: string[] = [];
const EMPTY_PREVIEW_ROWS: PreviewData["rows"] = [];
const EMPTY_PREVIEW_MESSAGES: string[] = [];

export function TablePreviewPane({
  tableId,
  datasourceId,
  datasourceDbType,
  onOpenSqlConsole,
  onToast,
}: TablePreviewPaneProps) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [filterColumn, setFilterColumn] = useState("");
  const [filterOperator, setFilterOperator] = useState<TableFilterOperator>("contains");
  const [filterValue, setFilterValue] = useState("");
  const [activeFilter, setActiveFilter] = useState<TableFilterState | null>(null);
  const [sortColumn, setSortColumn] = useState("");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [activeSort, setActiveSort] = useState<TableSortState | null>(null);
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; column: string } | null>(null);
  const querySignature = JSON.stringify({ search: search.trim(), filter: activeFilter, sort: activeSort });
  const cacheKey = `${datasourceId}|${tableId}|${page}|${pageSize}|${querySignature}`;
  const [data, setData] = useState<PreviewData | null>(() => previewCache.get(cacheKey) ?? null);
  const [columnTypes, setColumnTypes] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [noticeDismissed, setNoticeDismissed] = useState(false);
  const requestSeqRef = useRef(0);

  const [prevDatasourceId, setPrevDatasourceId] = useState(datasourceId);
  const [prevTableId, setPrevTableId] = useState(tableId);
  const [prevPage, setPrevPage] = useState(page);
  const [prevPageSize, setPrevPageSize] = useState(pageSize);
  const [prevQuerySignature, setPrevQuerySignature] = useState(querySignature);

  if (
    datasourceId !== prevDatasourceId ||
    tableId !== prevTableId ||
    page !== prevPage ||
    pageSize !== prevPageSize ||
    querySignature !== prevQuerySignature
  ) {
    let nextPage = page;
    if (datasourceId !== prevDatasourceId || tableId !== prevTableId) {
      nextPage = 1;
      setPage(1);
      setPrevDatasourceId(datasourceId);
      setPrevTableId(tableId);
    }
    setPrevPage(nextPage);
    setPrevPageSize(pageSize);
    setPrevQuerySignature(querySignature);

    const nextCacheKey = `${datasourceId}|${tableId}|${nextPage}|${pageSize}|${querySignature}`;
    const cached = previewCache.get(nextCacheKey);
    if (cached) {
      setData(cached);
    } else if (datasourceId !== prevDatasourceId || tableId !== prevTableId) {
      setData(null);
    }
  }

  const loadPreview = async () => {
    const seq = ++requestSeqRef.current;
    setLoading(true);
    setError("");
    try {
      if (!datasourceId) {
        setError("Cannot preview table without an active datasource.");
        return;
      }
      const table = await findTableByName(datasourceId, tableId);
      if (seq !== requestSeqRef.current) return;
      if (!table) {
        setError("未找到该表的数据源或字段信息，请先同步表结构。");
        return;
      }
      const cols = await listColumns(table.id);
      if (seq !== requestSeqRef.current) return;
      const types = new Map<string, string>();
      cols.forEach((c: EngineColumn) => types.set(c.column_name, c.data_type));
      setColumnTypes(types);
      const result = await agentApi.fetchTableResultPage({
        datasourceId,
        tableId: table.id,
        tableName: tableId,
        page,
        pageSize,
        filters: activeFilter ? [activeFilter] : undefined,
        sort: activeSort ? [activeSort] : undefined,
        search: search.trim() || undefined,
        countMode: "estimate",
      });
      if (seq !== requestSeqRef.current) return;
      const next: PreviewData = {
        columns: result.columns,
        rows: result.rows,
        latencyMs: result.latencyMs,
        hasNext: result.hasNextPage,
        warnings: result.warnings ?? [],
        notices: result.notices ?? [],
        page: result.page,
        pageSize: result.pageSize,
      };
      previewCache.set(cacheKey, next);
      setData(next);
      setNoticeDismissed(false);
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(err instanceof Error ? err.message : "读取表预览失败");
    } finally {
      if (seq === requestSeqRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    void loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasourceId, datasourceDbType, tableId, page, pageSize, querySignature]);

  const columns = data?.columns ?? EMPTY_PREVIEW_COLUMNS;
  const rows = data?.rows ?? EMPTY_PREVIEW_ROWS;
  const warnings = data?.warnings ?? EMPTY_PREVIEW_MESSAGES;
  const notices = data?.notices ?? EMPTY_PREVIEW_MESSAGES;
  const initialLoading = loading && !data;
  const refreshing = loading && !!data;
  const displayPage = data?.page ?? page;
  const loadingTargetPage = refreshing && page !== displayPage ? page : null;
  const controlColumns = columns.length > 0 ? columns : Array.from(columnTypes.keys());
  const previewRows = useMemo<PreviewTableRow[]>(
    () => rows.map((values, rowIndex) => ({ rowIndex, values })),
    [rows],
  );
  const previewColumns = useMemo<Array<ColumnDef<PreviewTableRow, unknown>>>(
    () =>
      columns.map((column) => {
        const dataType = columnTypes.get(column);
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
          meta: { column, dataType } satisfies PreviewColumnMeta,
        };
      }),
    [columns, columnTypes],
  );
  const previewTable = useReactTable({
    data: previewRows,
    columns: previewColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.rowIndex),
  });
  const selectedFilterColumn = controlColumns.includes(filterColumn) ? filterColumn : (controlColumns[0] ?? "");
  const selectedSortColumn = controlColumns.includes(sortColumn) ? sortColumn : (activeSort?.column ?? controlColumns[0] ?? "");
  const filterNeedsValue = filterOperator !== "is_null" && filterOperator !== "is_not_null";

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  const applyFilter = () => {
    if (!selectedFilterColumn) return;
    setActiveFilter({
      column: selectedFilterColumn,
      operator: filterOperator,
      value: filterNeedsValue ? filterValue : undefined,
    });
    setPage(1);
  };

  const clearFilter = () => {
    setActiveFilter(null);
    setFilterValue("");
    setPage(1);
  };

  const applySort = () => {
    if (!selectedSortColumn) return;
    setActiveSort({ column: selectedSortColumn, direction: sortDirection });
    setPage(1);
  };

  const clearSort = () => {
    setActiveSort(null);
    setPage(1);
  };

  const handleCellCopy = async (rowIndex: number, column: string, value: unknown, dataType?: string) => {
    setSelectedCell({ rowIndex, column });
    const ok = await copyText(cellDisplayText(value, dataType));
    onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制");
  };

  const handleExport = async () => {
    try {
      if (!datasourceId) {
        onToast("Cannot export table without an active datasource.");
        return;
      }
      const table = await findTableByName(datasourceId, tableId);
      if (!table) {
        onToast("未找到该表的数据源或字段信息，请先同步表结构。");
        return;
      }
      const blob = await agentApi.exportTableResultCsv({
        datasourceId,
        tableId: table.id,
        tableName: tableId,
        filters: activeFilter ? [activeFilter] : undefined,
        sort: activeSort ? [activeSort] : undefined,
        search: search.trim() || undefined,
      });
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
            <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={() => void loadPreview()} disabled={loading}>
              <RefreshCw className={loading ? "hifi-preview-toolbar-icon is-spinning" : "hifi-preview-toolbar-icon"} aria-hidden="true" />
              <span>刷新</span>
            </Button>
            <Popover>
              <PopoverTrigger asChild>
                <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn">
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
                <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn">
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
            <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={() => void handleExport()} disabled={loading && !data}>
              <Download className="hifi-preview-toolbar-icon" aria-hidden="true" />
              <span>导出</span>
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="hifi-preview-toolbar-btn"
              onClick={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")}
            >
              <Sparkles className="hifi-preview-toolbar-icon is-accent" aria-hidden="true" />
              <span>生成测试数据</span>
            </Button>
          </ToolbarGroup>
          <ToolbarGroup className="hifi-table-toolbar-group hifi-table-toolbar-right">
            <div className="hifi-preview-search-shell">
              <Search className="hifi-preview-search-icon" aria-hidden="true" />
              <Input
                className="hifi-preview-search"
                value={search}
                onChange={(event) => handleSearchChange(event.target.value)}
                placeholder="搜索表数据..."
              />
            </div>
            <Button size="sm" variant="ghost" className="hifi-preview-toolbar-link" onClick={() => onOpenSqlConsole()}>
              <Code className="hifi-preview-toolbar-icon" aria-hidden="true" />
              <span>在 SQL 运行</span>
            </Button>
          </ToolbarGroup>
        </Toolbar>
      </div>

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
              <thead>
                {previewTable.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id} className="table-preview-row">
                    {headerGroup.headers.map((header) => {
                      const meta = header.column.columnDef.meta as PreviewColumnMeta;
                      return (
                        <th
                          key={header.id}
                          className="table-preview-head"
                          aria-label={meta.dataType ? `${meta.column} ${meta.dataType}` : meta.column}
                        >
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {previewTable.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="table-preview-row">
                    {row.getVisibleCells().map((cell) => {
                      const meta = cell.column.columnDef.meta as PreviewColumnMeta;
                      const value = cell.getValue();
                      const isNull = value === null || value === undefined;
                      const displayValue = cellDisplayText(value, meta.dataType);
                      const isSelected = selectedCell?.rowIndex === row.original.rowIndex && selectedCell.column === meta.column;
                      const cellClasses = ["table-preview-cell"];
                      if (isNull) cellClasses.push("is-null");
                      if (isSelected) cellClasses.push("is-selected");
                      if (typeof value === "string" && isImageUrl(value)) {
                        return (
                          <td
                            key={cell.id}
                            className={[...cellClasses, "table-preview-image-cell"].join(" ")}
                            title={displayValue}
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
                          aria-selected={isSelected ? "true" : undefined}
                          onClick={() => void handleCellCopy(row.original.rowIndex, meta.column, value, meta.dataType)}
                        >
                          {isNull ? (
                            <span className="table-preview-null-pill">NULL</span>
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
              />
            )}
          </div>
        )}

        {data && columns.length === 0 && !error && !initialLoading && (
          <EmptyTableState page={1} onBackToFirstPage={() => setPage(1)} onOpenSqlConsole={onOpenSqlConsole} onGenerate={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")} />
        )}
      </div>

      <div className="hifi-table-footer">
        <span>
	          {data
	            ? `第 ${displayPage} 页 · 本页 ${rows.length} 行 · ${loadingTargetPage ? `正在加载第 ${loadingTargetPage} 页` : `${data.latencyMs}ms`}`
	            : loading
	              ? "加载中..."
	              : error
	                ? "加载失败"
	                : "等待查询"}
          {!loading && data && notices.length > 0 && (
            <span className="hifi-table-footer-notice"> · {notices.join("；")}</span>
          )}
        </span>
        <div className="hifi-pagination">
          <Button
            size="sm"
            variant="outline"
            className="hifi-preview-page-btn"
	            disabled={displayPage <= 1 || loading}
	            onClick={() => setPage(Math.max(1, displayPage - 1))}
	          >
            &lt;
          </Button>
	          <span className="hifi-page-num active">{displayPage}</span>
          <Button
            size="sm"
            variant="outline"
            className="hifi-preview-page-btn"
            disabled={!data?.hasNext || loading}
	            onClick={() => setPage(displayPage + 1)}
          >
            &gt;
          </Button>
        </div>
        <Select
          className="hifi-preview-page-size"
          value={pageSize}
          onChange={(event) => {
            setPageSize(Number(event.target.value));
            setPage(1);
          }}
        >
          <option value="10">10条/页</option>
          <option value="20">20条/页</option>
          <option value="50">50条/页</option>
          <option value="100">100条/页</option>
        </Select>
      </div>
    </div>
  );
}

function EmptyTableState({
  page,
  onBackToFirstPage,
  onOpenSqlConsole,
  onGenerate,
}: {
  page: number;
  onBackToFirstPage: () => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onGenerate: () => void;
}) {
  const beyondFirstPage = page > 1;
  return (
    <div className="hifi-preview-empty">
      <div className="hifi-preview-empty-icon"><Database size={18} /></div>
      <div className="hifi-preview-empty-title">{beyondFirstPage ? "本页没有更多数据" : "这张表还没有数据"}</div>
      <div className="hifi-preview-empty-copy">
        {beyondFirstPage
          ? "已经翻到了数据末尾，可以回到第一页继续浏览。"
          : "表结构已就绪，但还没有任何记录。可以生成少量测试数据用于本地预览，或在 SQL 控制台写入数据。"}
      </div>
      <div className="hifi-preview-empty-actions">
        {beyondFirstPage ? (
          <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={onBackToFirstPage}>
            回到第一页
          </Button>
        ) : (
          <>
            <Button size="sm" variant="outline" className="hifi-preview-toolbar-btn" onClick={onGenerate}>
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
