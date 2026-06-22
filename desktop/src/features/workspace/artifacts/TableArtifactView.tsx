import { useMemo, useState, useEffect } from "react";
import { Copy, Download, ExternalLink, ChevronLeft, ChevronRight, Loader2, AlertCircle, RefreshCw, Filter, ArrowUpDown, Search, AlertTriangle } from "lucide-react";
import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import { agentApi } from "../../../lib/api/agent";
import type { ResultPageRequest, ResultPageResponse } from "../../../lib/api/types";
import { copyText, downloadTextFile, toCsv } from "./artifactActions";

const PREVIEW_ROW_LIMIT = 10;
const LARGE_RESULT_THRESHOLD = 500;
const WINDOW_ROW_LIMIT = 200;

interface TableArtifactViewProps {
  artifact: TableArtifact | ResultViewArtifact;
  onToast: (message: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
  mode?: "inline" | "workspace";
}

type SortDirection = "asc" | "desc";

interface SortState {
  columnIndex: number;
  direction: SortDirection;
}

export function TableArtifactView({ artifact, onToast, onOpenResultTab, mode = "inline" }: TableArtifactViewProps) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState | null>(null);

  const isSqlBackedWorkspace = mode === "workspace" && artifact.type === "result_view" && artifact.storageMode === "sql_backed";

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [backendData, setBackendData] = useState<ResultPageResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Debounce search a bit before fetching if needed, but since backend search isn't implemented, we just send it.
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!isSqlBackedWorkspace) return;
    let active = true;
    const fetchPage = async () => {
      setIsLoading(true);
      setFetchError(null);
      try {
        const req: ResultPageRequest = {
          datasourceId: (artifact as ResultViewArtifact).datasourceId,
          sourceSqlArtifactId: (artifact as ResultViewArtifact).sourceSqlSemanticId,
          safeSql: (artifact as ResultViewArtifact).safeSql,
          page,
          pageSize,
          sort: sort ? [{ column: artifact.columns[sort.columnIndex], direction: sort.direction }] : undefined,
          search: debouncedSearch.trim() || undefined,
          countMode: "estimate",
        };
        const res = await agentApi.fetchResultPage(req);
        if (active) setBackendData(res);
      } catch (err) {
        if (active) setFetchError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) setIsLoading(false);
      }
    };
    fetchPage();
    return () => { active = false; };
  }, [isSqlBackedWorkspace, artifact, page, pageSize, sort, debouncedSearch]);

  const rowsToUse = artifact.type === "result_view" ? (artifact.rows ?? artifact.previewRows) : artifact.rows;

  const backendRows = useMemo(() => {
    if (!backendData) return [];
    return backendData.rows.map((row) =>
      backendData.columns.map((col) => {
        const val = row[col];
        return typeof val === "object" && val !== null ? JSON.stringify(val) : String(val ?? "");
      })
    );
  }, [backendData]);

  const csv = useMemo(() => toCsv(artifact.columns, isSqlBackedWorkspace ? backendRows : rowsToUse), [artifact.columns, rowsToUse, backendRows, isSqlBackedWorkspace]);
  const normalizedSearch = search.trim().toLowerCase();
  
  const filteredAndSortedRows = useMemo(() => {
    if (isSqlBackedWorkspace) return backendRows;
    const filteredRows =
      normalizedSearch.length > 0
        ? rowsToUse.filter((row) => row.some((cell) => cell.toLowerCase().includes(normalizedSearch)))
        : rowsToUse;

    if (!sort) return filteredRows;
    return [...filteredRows].sort((left, right) =>
      compareCells(left[sort.columnIndex] ?? "", right[sort.columnIndex] ?? "", sort.direction)
    );
  }, [rowsToUse, backendRows, normalizedSearch, sort, isSqlBackedWorkspace]);

  const isSearching = normalizedSearch.length > 0;
  const [expanded, setExpanded] = useState(false);
  const shouldUseWindow = !isSqlBackedWorkspace && (expanded || isSearching) && filteredAndSortedRows.length > LARGE_RESULT_THRESHOLD;
  const visibleRows = isSqlBackedWorkspace 
    ? filteredAndSortedRows
    : expanded || isSearching
      ? filteredAndSortedRows.slice(0, shouldUseWindow ? WINDOW_ROW_LIMIT : filteredAndSortedRows.length)
      : filteredAndSortedRows.slice(0, PREVIEW_ROW_LIMIT);
      
  const totalRows = isSqlBackedWorkspace ? (backendData?.rowCount ?? undefined) : (artifact.rowCount ?? rowsToUse.length);
  const returnedRows = isSqlBackedWorkspace ? backendRows.length : (artifact.returnedRows ?? rowsToUse.length);
  const previewCount = visibleRows.length;
  const warnings = isSqlBackedWorkspace ? (backendData?.warnings ?? []) : (artifact.warnings ?? []);
  const notices = isSqlBackedWorkspace ? (backendData?.notices ?? []) : (artifact.notices ?? []);
  const latencyMs = isSqlBackedWorkspace ? backendData?.latencyMs : artifact.latencyMs;

  const handleSort = (columnIndex: number) => {
    setSort((current) => {
      if (current?.columnIndex !== columnIndex) return { columnIndex, direction: "desc" };
      return { columnIndex, direction: current.direction === "desc" ? "asc" : "desc" };
    });
    setPage(1); // Reset to first page on sort
  };

  const handleCopy = async () => {
    const ok = await copyText(csv);
    onToast(ok ? "已复制 CSV" : "复制失败，请手动选择复制");
  };

  const handleExport = () => {
    const ok = downloadTextFile(`${artifact.id}.csv`, csv, "text/csv;charset=utf-8");
    onToast(ok ? "已导出 CSV" : "CSV 导出失败");
  };

  const handleCellCopy = async (value: string) => {
    const ok = await copyText(value);
    onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制");
  };

  if (mode === "workspace") {
    return (
      <div className="flex flex-col h-full overflow-hidden w-full bg-white">
        <div className="hifi-panel-toolbar border-b border-slate-200 bg-white px-2">
          <div className="hifi-toolbar-left flex items-center gap-1">
            <button className="hifi-toolbar-btn" onClick={() => isSqlBackedWorkspace ? setPage(page) : undefined} disabled={isLoading || !isSqlBackedWorkspace}>
              <RefreshCw size={10} className={isLoading ? "animate-spin" : ""} /> 刷新
            </button>
            <button className="hifi-toolbar-btn" onClick={() => onToast("筛选器待接入：后续会转换为安全 SQL 条件")}><Filter size={10} /> 筛选</button>
            <button className="hifi-toolbar-btn" onClick={() => onToast("排序待接入：后续会转换为安全 SQL 排序")}><ArrowUpDown size={10} /> 排序</button>
            <button className="hifi-toolbar-btn" onClick={handleExport}><Download size={10} /> 导出</button>
            <button className="hifi-toolbar-btn" onClick={handleCopy}><Copy size={10} /> 复制</button>
          </div>
          <div className="hifi-toolbar-right flex items-center gap-2">
            <div className="relative flex items-center">
              <Search size={12} className="absolute left-2 text-gray-400" />
              <input
                className="hifi-input h-6 w-32 pl-6 pr-2 rounded border border-gray-200 text-[11px]"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="本地搜索..."
              />
            </div>
          </div>
        </div>

        {fetchError && (
          <div className="hifi-preview-error m-2">
            <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />
            <span>获取分页数据失败: {fetchError}</span>
          </div>
        )}
        {(warnings.length > 0 || notices.length > 0) && (
          <div className="hifi-preview-notice m-2">
            <AlertTriangle size={11} className="flex-shrink-0" />
            <span>{[...warnings, ...notices].join("；")}</span>
          </div>
        )}

        <div className="hifi-table-container flex-1 overflow-auto bg-white relative">
          {isLoading && <div className="hifi-preview-loading-bar absolute top-0 left-0 right-0" />}
          <table className="hifi-table min-w-full">
            <thead>
              <tr>
                {artifact.columns.map((column, columnIndex) => (
                  <th key={`${column}-${columnIndex}`}>
                    <button
                      type="button"
                      className="w-full text-left flex items-center gap-1"
                      onClick={() => handleSort(columnIndex)}
                      title={sort?.columnIndex === columnIndex ? `当前${sort.direction === "desc" ? "降序" : "升序"}` : "点击排序"}
                    >
                      {column}
                      {sort?.columnIndex === columnIndex && (
                        <span className="text-[10px] text-blue-500">{sort.direction === "asc" ? "↑" : "↓"}</span>
                      )}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.length > 0 ? (
                visibleRows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td
                        key={`${rowIndex}-${cellIndex}`}
                        className={`max-w-[240px] truncate ${cell === null || cell === undefined || cell === "NULL" ? "hifi-cell-null" : "cursor-copy"}`}
                        onClick={() => void handleCellCopy(cell)}
                        title={cell ?? ""}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={artifact.columns.length} className="text-center text-slate-400 py-8">
                    无匹配结果
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="hifi-table-footer border-t border-slate-200 bg-slate-50 px-2 py-1">
          <span className="text-slate-500">
            {isLoading
              ? "加载中..."
              : `第 ${page} 页 · 本页 ${visibleRows.length} 行${latencyMs !== undefined ? ` · ${latencyMs}ms` : ""}`}
            {totalRows !== undefined && ` · 总计约 ${totalRows} 行`}
            {artifact.truncated && <span className="text-amber-600"> · 结果已截断</span>}
          </span>
          
          <div className="flex items-center gap-2">
            {isSqlBackedWorkspace && (
              <div className="hifi-pagination flex items-center gap-1">
                <button
                  className={`hifi-toolbar-btn flex items-center justify-center ${page <= 1 ? "opacity-40 cursor-not-allowed" : ""}`}
                  style={{ height: "20px", padding: "0 6px" }}
                  disabled={page <= 1 || isLoading}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                >
                  &lt;
                </button>
                <span className="hifi-page-num active flex items-center justify-center h-5 px-2 bg-blue-50 text-blue-600 rounded text-[11px] font-medium">{page}</span>
                <button
                  className={`hifi-toolbar-btn flex items-center justify-center ${!backendData?.hasNextPage ? "opacity-40 cursor-not-allowed" : ""}`}
                  style={{ height: "20px", padding: "0 6px" }}
                  disabled={(!backendData?.hasNextPage) || isLoading}
                  onClick={() => setPage(p => p + 1)}
                >
                  &gt;
                </button>
              </div>
            )}
            <select
              className="border border-slate-200 bg-white rounded px-1 h-5 text-[10px] text-slate-600 focus:outline-none"
              value={pageSize}
              disabled={!isSqlBackedWorkspace}
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
      </div>
    );
  }

  // mode === "inline"
  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header flex items-center justify-between gap-2">
        <span>{artifact.title}</span>
        <span className="hifi-artifact-chip hifi-artifact-chip-table">结果表</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor={`${artifact.id}-table-search`}>
            搜索结果
          </label>
          <input
            id={`${artifact.id}-table-search`}
            className="hifi-input h-7 min-w-[180px] flex-1 rounded border border-slate-200 px-2 text-[11px]"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索结果"
          />
          {(!isSqlBackedWorkspace && rowsToUse.length > PREVIEW_ROW_LIMIT && !isSearching) && (
            <button
              type="button"
              className="hifi-guide-btn-secondary"
              style={{ height: "28px", fontSize: "10px" }}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "收起预览" : `查看全部已载入 ${rowsToUse.length} 行`}
            </button>
          )}
        </div>
        {fetchError && (
          <div className="mb-2 p-2 rounded bg-red-50 text-red-700 text-[11px] flex items-center gap-1">
            <AlertCircle size={12} />
            获取分页数据失败: {fetchError}
          </div>
        )}
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
            预览 {previewCount} / 共 {totalRows} 行
          </span>
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">{artifact.columns.length} 列</span>
          {latencyMs !== undefined && (
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">{latencyMs}ms</span>
          )}
          {!isSqlBackedWorkspace && returnedRows > previewCount && (
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">已载入 {returnedRows} 行</span>
          )}
          {artifact.truncated && (
            <span className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700">结果已截断</span>
          )}
        </div>
        {(warnings.length > 0 || notices.length > 0) && (
          <div className="mb-2 grid gap-1 text-[10px]">
            {warnings.map((warning) => <span key={`warning-${warning}`} className="text-amber-700">{warning}</span>)}
            {notices.map((notice) => <span key={`notice-${notice}`} className="text-slate-500">{notice}</span>)}
          </div>
        )}
        <div
          className="overflow-auto rounded border border-slate-200"
          style={{ maxHeight: "320px" }}
        >
          <table className="hifi-table min-w-full">
            <thead>
              <tr>
                {artifact.columns.map((column, columnIndex) => (
                  <th key={`${column}-${columnIndex}`} className="sticky top-0 z-10 bg-slate-50">
                    <button
                      type="button"
                      className="w-full text-left font-semibold text-slate-600 flex items-center gap-1"
                      onClick={() => handleSort(columnIndex)}
                      title={sort?.columnIndex === columnIndex ? `当前${sort.direction === "desc" ? "降序" : "升序"}` : "点击排序"}
                    >
                      {column}
                      {sort?.columnIndex === columnIndex && (
                        <span className="text-[10px] text-blue-500">{sort.direction === "asc" ? "↑" : "↓"}</span>
                      )}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.length > 0 ? (
                visibleRows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td
                        key={`${rowIndex}-${cellIndex}`}
                        className={cellClassName(cell)}
                        onClick={() => void handleCellCopy(cell)}
                        title="点击复制单元格"
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={artifact.columns.length} className="text-center text-slate-400">
                    无匹配结果
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex gap-2 justify-end mt-3">
          {onOpenResultTab && (
            <button
              type="button"
              className="hifi-guide-btn-secondary flex items-center gap-1"
              style={{ height: "24px", fontSize: "10px" }}
              onClick={() => onOpenResultTab(artifact)}
            >
              <ExternalLink size={10} />
              打开为 Tab
            </button>
          )}
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={handleCopy}>
            <Copy size={10} />
            复制 CSV
          </button>
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={handleExport}>
            <Download size={10} />
            导出 CSV
          </button>
        </div>
      </div>
    </div>
  );
}

function compareCells(left: string, right: string, direction: SortDirection): number {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const bothNumeric =
    left.trim() !== "" && right.trim() !== "" && Number.isFinite(leftNumber) && Number.isFinite(rightNumber);
  const result = bothNumeric
    ? leftNumber - rightNumber
    : left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
  return direction === "asc" ? result : -result;
}

function cellClassName(value: string): string {
  const classes = ["cursor-copy"];
  if (value === "NULL") classes.push("text-slate-400", "italic");
  if (value.trim() !== "" && Number.isFinite(Number(value))) {
    classes.push("text-right", "tabular-nums");
  }
  return classes.join(" ");
}
