import { useMemo, useState } from "react";
import { Copy, Download, ExternalLink } from "lucide-react";
import type { TableArtifact } from "../../../types/agentArtifact";
import { copyText, downloadTextFile, toCsv } from "./artifactActions";

const PREVIEW_ROW_LIMIT = 10;
const LARGE_RESULT_THRESHOLD = 500;
const WINDOW_ROW_LIMIT = 200;

interface TableArtifactViewProps {
  artifact: TableArtifact;
  onToast: (message: string) => void;
  onOpenResultTab?: (artifact: TableArtifact) => void;
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

  const csv = useMemo(() => toCsv(artifact.columns, artifact.rows), [artifact.columns, artifact.rows]);
  const normalizedSearch = search.trim().toLowerCase();
  const filteredAndSortedRows = useMemo(() => {
    const filteredRows =
      normalizedSearch.length > 0
        ? artifact.rows.filter((row) => row.some((cell) => cell.toLowerCase().includes(normalizedSearch)))
        : artifact.rows;

    if (!sort) return filteredRows;
    return [...filteredRows].sort((left, right) =>
      compareCells(left[sort.columnIndex] ?? "", right[sort.columnIndex] ?? "", sort.direction)
    );
  }, [artifact.rows, normalizedSearch, sort]);

  const isSearching = normalizedSearch.length > 0;
  const [expanded, setExpanded] = useState(false);
  const shouldUseWindow = (expanded || isSearching) && filteredAndSortedRows.length > LARGE_RESULT_THRESHOLD;
  const visibleRows =
    expanded || isSearching
      ? filteredAndSortedRows.slice(0, shouldUseWindow ? WINDOW_ROW_LIMIT : filteredAndSortedRows.length)
      : filteredAndSortedRows.slice(0, PREVIEW_ROW_LIMIT);
  const totalRows = artifact.rowCount ?? artifact.rows.length;
  const returnedRows = artifact.returnedRows ?? artifact.rows.length;
  const previewCount = visibleRows.length;
  const warnings = artifact.warnings ?? [];
  const notices = artifact.notices ?? [];

  const handleSort = (columnIndex: number) => {
    setSort((current) => {
      if (current?.columnIndex !== columnIndex) return { columnIndex, direction: "desc" };
      return { columnIndex, direction: current.direction === "desc" ? "asc" : "desc" };
    });
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
          {artifact.rows.length > PREVIEW_ROW_LIMIT && !isSearching && (
            <button
              type="button"
              className="hifi-guide-btn-secondary"
              style={{ height: "28px", fontSize: "10px" }}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "收起预览" : `查看全部已载入 ${artifact.rows.length} 行`}
            </button>
          )}
        </div>
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
            预览 {previewCount} / 共 {totalRows} 行
          </span>
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">{artifact.columns.length} 列</span>
          {artifact.latencyMs !== undefined && (
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">{artifact.latencyMs}ms</span>
          )}
          {returnedRows > previewCount && (
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">已载入 {returnedRows} 行</span>
          )}
          {artifact.truncated && (
            <span className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700">结果已截断</span>
          )}
          {shouldUseWindow && (
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
              窗口 1-{visibleRows.length} / {filteredAndSortedRows.length}
            </span>
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
          style={{ maxHeight: mode === "workspace" ? "calc(100vh - 240px)" : "320px" }}
        >
          <table className="hifi-table min-w-full">
            <thead>
              <tr>
                {artifact.columns.map((column, columnIndex) => (
                  <th key={`${column}-${columnIndex}`} className="sticky top-0 z-10 bg-slate-50">
                    <button
                      type="button"
                      className="w-full text-left font-semibold text-slate-600"
                      onClick={() => handleSort(columnIndex)}
                      title={sort?.columnIndex === columnIndex ? `当前${sort.direction === "desc" ? "降序" : "升序"}` : "点击排序"}
                    >
                      {column}
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
