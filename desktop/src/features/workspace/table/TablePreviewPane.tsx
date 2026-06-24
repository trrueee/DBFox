import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowUpDown, Code, Database, Download, Filter, RefreshCw, Search, Sparkles } from "lucide-react";
import { ImageCell, isImageUrl } from "../../../components/ImageCell";
import { executeSql, quoteIdentifier } from "../../engine/engineApi";
import { findTableByName, listColumns, type EngineColumn } from "../../../lib/api/schema";
import { downloadTextFile, toCsv } from "../artifacts/artifactActions";

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

// Keeps the last loaded page per table so re-opening a tab shows data instantly
// (then revalidates in the background) instead of flashing an empty loading view.
const previewCache = new Map<string, PreviewData>();

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
  const [filterOpen, setFilterOpen] = useState(false);
  const [filterColumn, setFilterColumn] = useState("");
  const [filterOperator, setFilterOperator] = useState<TableFilterOperator>("contains");
  const [filterValue, setFilterValue] = useState("");
  const [activeFilter, setActiveFilter] = useState<TableFilterState | null>(null);
  const [sortOpen, setSortOpen] = useState(false);
  const [sortColumn, setSortColumn] = useState("");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [activeSort, setActiveSort] = useState<TableSortState | null>(null);
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
        setError("未找到该表的数据源或 Schema 元数据，请先同步 Schema。");
        return;
      }
      const cols = await listColumns(table.id);
      if (seq !== requestSeqRef.current) return;
      const types = new Map<string, string>();
      cols.forEach((c: EngineColumn) => types.set(c.column_name, c.data_type));
      setColumnTypes(types);
      // Request one extra row to know whether a next page exists.
      const offset = (page - 1) * pageSize;
      const previewSql = buildTableSelectSql({
        tableName: tableId,
        dbType: datasourceDbType ?? "mysql",
        columns: cols.map((column: EngineColumn) => column.column_name),
        search,
        filter: activeFilter,
        sort: activeSort,
        limit: pageSize + 1,
        offset,
      });
      const result = await executeSql(datasourceId, previewSql, `preview table ${tableId}`);
      if (seq !== requestSeqRef.current) return;
      const next: PreviewData = {
        columns: result.columns,
        rows: result.rows.slice(0, pageSize),
        latencyMs: result.latencyMs,
        hasNext: result.rows.length > pageSize,
        warnings: result.warnings ?? [],
        notices: result.notices ?? [],
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

  const columns = data?.columns ?? [];
  const rows = data?.rows ?? [];
  const warnings = data?.warnings ?? [];
  const notices = data?.notices ?? [];
  const initialLoading = loading && !data;
  const refreshing = loading && !!data;
  const controlColumns = columns.length > 0 ? columns : Array.from(columnTypes.keys());
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

  const handleExport = async () => {
    try {
      if (!datasourceId) {
        onToast("Cannot export table without an active datasource.");
        return;
      }
      const table = await findTableByName(datasourceId, tableId);
      if (!table) {
        onToast("未找到该表的数据源或 Schema 元数据，请先同步 Schema。");
        return;
      }
      const cols = await listColumns(table.id);
      const exportSql = buildTableSelectSql({
        tableName: tableId,
        dbType: datasourceDbType ?? "mysql",
        columns: cols.map((column: EngineColumn) => column.column_name),
        search,
        filter: activeFilter,
        sort: activeSort,
      });
      const result = await executeSql(datasourceId, exportSql, `export table ${tableId}`);
      const csv = toCsv(
        result.columns,
        result.rows.map((row) => result.columns.map((column) => cellToText(row[column]))),
      );
      const ok = downloadTextFile(`${tableId}.csv`, csv, "text/csv;charset=utf-8");
      onToast(ok ? "已导出 CSV" : "CSV 导出失败");
    } catch {
      onToast("CSV 导出失败");
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="hifi-table-toolbar-stack">
        <div className="hifi-panel-toolbar">
          <div className="hifi-toolbar-left">
            <button className="hifi-toolbar-btn" onClick={() => void loadPreview()} disabled={loading}>
              <RefreshCw size={10} className={loading ? "animate-spin" : ""} /> 刷新
            </button>
            <button className="hifi-toolbar-btn" onClick={() => setFilterOpen((value) => !value)}>
              <Filter size={10} /> 筛选{activeFilter ? " 1" : ""}
            </button>
            <button className="hifi-toolbar-btn" onClick={() => setSortOpen((value) => !value)}>
              <ArrowUpDown size={10} /> 排序{activeSort ? ` ${activeSort.direction === "asc" ? "↑" : "↓"}` : ""}
            </button>
            <button className="hifi-toolbar-btn" onClick={() => void handleExport()} disabled={loading && !data}>
              <Download size={10} /> 导出
            </button>
            <button className="hifi-toolbar-btn" onClick={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")}><Sparkles size={10} className="text-yellow-600" /> 生成测试数据</button>
          </div>
          <div className="hifi-toolbar-right">
            <div className="relative flex items-center">
              <Search size={12} className="hifi-result-search-icon absolute left-2" />
              <input
                className="hifi-input hifi-result-search h-6 w-36 pl-6 pr-2 rounded text-[var(--ui-font-label)]"
                value={search}
                onChange={(event) => handleSearchChange(event.target.value)}
                placeholder="搜索表数据..."
              />
            </div>
            <button className="hifi-text-btn flex items-center gap-1" onClick={() => onOpenSqlConsole()}><Code size={11} /> 在 SQL 运行</button>
          </div>
        </div>
        {filterOpen && (
          <div className="hifi-result-control-row px-2">
            <label className="hifi-result-control-field">
              <span>筛选列</span>
              <select value={selectedFilterColumn} onChange={(event) => setFilterColumn(event.target.value)}>
                {controlColumns.map((column) => (
                  <option key={column} value={column}>{column}</option>
                ))}
              </select>
            </label>
            <label className="hifi-result-control-field">
              <span>筛选条件</span>
              <select value={filterOperator} onChange={(event) => setFilterOperator(event.target.value as TableFilterOperator)}>
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
            <button className="hifi-toolbar-btn" onClick={clearFilter} disabled={!activeFilter && !filterValue}>
              清除筛选
            </button>
          </div>
        )}
        {sortOpen && (
          <div className="hifi-result-control-row px-2">
            <label className="hifi-result-control-field">
              <span>排序列</span>
              <select value={selectedSortColumn} onChange={(event) => setSortColumn(event.target.value)}>
                {controlColumns.map((column) => (
                  <option key={column} value={column}>{column}</option>
                ))}
              </select>
            </label>
            <label className="hifi-result-control-field">
              <span>排序方向</span>
              <select value={sortDirection} onChange={(event) => setSortDirection(event.target.value as "asc" | "desc")}>
                <option value="desc">降序</option>
                <option value="asc">升序</option>
              </select>
            </label>
            <button className="hifi-toolbar-btn" onClick={applySort} disabled={!selectedSortColumn}>
              应用排序
            </button>
            <button className="hifi-toolbar-btn" onClick={clearSort} disabled={!activeSort}>
              清除排序
            </button>
          </div>
        )}
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
            {[0, 1, 2, 3, 4, 5, 6].map((item) => <div key={item} className="hifi-preview-skeleton-row" style={{ opacity: 1 - item * 0.12 }} />)}
          </div>
        )}

        {data && columns.length > 0 && (
          <div className={refreshing ? "hifi-preview-refreshing" : ""}>
            <table className="hifi-table">
              <thead>
                <tr>
                  {columns.map((column) => {
                    const colType = columnTypes.get(column);
                    return (
                      <th key={column}>
                        {column}
                        {colType && <span className="hifi-column-type">{colType}</span>}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {columns.map((column) => {
                      const value = row[column] as string | null | undefined;
                      if (isImageUrl(value)) {
                        return (
                          <td key={column} className="max-w-[240px]">
                            <ImageCell url={value ?? ""} />
                          </td>
                        );
                      }
                      return (
                        <td key={column} className={`max-w-[240px] truncate ${value === null || value === undefined ? "hifi-cell-null" : ""}`} title={value ?? ""}>
                          {value ?? "NULL"}
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
          {loading
            ? "加载中..."
            : data
              ? `第 ${page} 页 · 本页 ${rows.length} 行 · ${data.latencyMs}ms`
              : error
                ? "加载失败"
                : "等待查询"}
          {!loading && data && notices.length > 0 && (
            <span className="text-slate-400"> · {notices.join("；")}</span>
          )}
        </span>
        <div className="hifi-pagination">
          <button
            className={`hifi-toolbar-btn ${page <= 1 ? "opacity-40 cursor-not-allowed" : ""}`}
            style={{ height: "20px", padding: "0 6px" }}
            disabled={page <= 1 || loading}
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
          >
            &lt;
          </button>
          <span className="hifi-page-num active">{page}</span>
          <button
            className={`hifi-toolbar-btn ${!data?.hasNext ? "opacity-40 cursor-not-allowed" : ""}`}
            style={{ height: "20px", padding: "0 6px" }}
            disabled={!data?.hasNext || loading}
            onClick={() => setPage((prev) => prev + 1)}
          >
            &gt;
          </button>
        </div>
        <select
          className="border border-gray-200 rounded px-1 text-[var(--ui-font-caption)]"
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
        </select>
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
          <button className="hifi-toolbar-btn" onClick={onBackToFirstPage}>回到第一页</button>
        ) : (
          <>
            <button className="hifi-toolbar-btn" onClick={onGenerate}><Sparkles size={10} className="text-yellow-600" /> 生成测试数据</button>
            <button className="hifi-toolbar-btn" onClick={() => onOpenSqlConsole()}><Code size={10} /> 打开 SQL 控制台</button>
          </>
        )}
      </div>
    </div>
  );
}

function buildTableSelectSql({
  tableName,
  dbType,
  columns,
  search,
  filter,
  sort,
  limit,
  offset = 0,
}: {
  tableName: string;
  dbType: string;
  columns: string[];
  search: string;
  filter: TableFilterState | null;
  sort: TableSortState | null;
  limit?: number;
  offset?: number;
}) {
  const predicates: string[] = [];
  const normalizedSearch = search.trim();
  if (normalizedSearch && columns.length > 0) {
    const like = sqlLiteral(`%${normalizedSearch}%`);
    predicates.push(`(${columns.map((column) => `${quoteIdentifier(column, dbType)} LIKE ${like}`).join(" OR ")})`);
  }
  if (filter) {
    const predicate = tableFilterPredicate(filter, dbType);
    if (predicate) predicates.push(predicate);
  }

  const whereClause = predicates.length > 0 ? ` WHERE ${predicates.join(" AND ")}` : "";
  const orderClause = sort ? ` ORDER BY ${quoteIdentifier(sort.column, dbType)} ${sort.direction.toUpperCase()}` : "";
  const limitClause = limit === undefined ? "" : ` LIMIT ${limit}${offset > 0 ? ` OFFSET ${offset}` : ""}`;
  return `SELECT * FROM ${quoteIdentifier(tableName, dbType)}${whereClause}${orderClause}${limitClause};`;
}

function tableFilterPredicate(filter: TableFilterState, dbType: string) {
  const column = quoteIdentifier(filter.column, dbType);
  const value = filter.value ?? "";
  switch (filter.operator) {
    case "contains":
      return `${column} LIKE ${sqlLiteral(`%${value}%`)}`;
    case "equals":
      return `${column} = ${sqlLiteral(value)}`;
    case "not_equals":
      return `${column} <> ${sqlLiteral(value)}`;
    case "starts_with":
      return `${column} LIKE ${sqlLiteral(`${value}%`)}`;
    case "ends_with":
      return `${column} LIKE ${sqlLiteral(`%${value}`)}`;
    case "gt":
      return `${column} > ${sqlLiteral(value)}`;
    case "gte":
      return `${column} >= ${sqlLiteral(value)}`;
    case "lt":
      return `${column} < ${sqlLiteral(value)}`;
    case "lte":
      return `${column} <= ${sqlLiteral(value)}`;
    case "is_null":
      return `${column} IS NULL`;
    case "is_not_null":
      return `${column} IS NOT NULL`;
    default:
      return "";
  }
}

function sqlLiteral(value: string) {
  return `'${value.replaceAll("'", "''")}'`;
}

function cellToText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
