import { ChevronLeft, ChevronRight } from "lucide-react";
import type { SchemaTable } from "../../lib/api";

interface TableDataStatusBarProps {
  tableMeta: SchemaTable | null;
  columnsCount: number;
  rowsCount: number;
  latencyMs: number | null;
  page: number;
  pageSize: number;
  loading: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function TableDataStatusBar({
  tableMeta,
  columnsCount,
  rowsCount,
  latencyMs,
  page,
  pageSize,
  loading,
  onPageChange,
  onPageSizeChange,
}: TableDataStatusBarProps) {
  const start = rowsCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, (page - 1) * pageSize + rowsCount);
  const canPrev = page > 1 && !loading;
  const canNext = rowsCount >= pageSize && !loading;

  return (
    <footer className="table-data-footer">
      <div className="table-data-footer-left">
        <span>预估行数: <strong className="text-[var(--text-primary)]">{tableMeta?.row_count_estimate?.toLocaleString() ?? "0"}</strong></span>
        <span className="opacity-40">|</span>
        <span>列数: <strong className="text-[var(--text-primary)]">{columnsCount}</strong></span>
        {latencyMs !== null && (
          <>
            <span className="opacity-40">|</span>
            <span>耗时: <strong className="text-[var(--text-primary)]">{latencyMs}ms</strong></span>
          </>
        )}
        <span className="opacity-40">|</span>
        <span>显示 {start} - {end} 行</span>
      </div>

      <div className="table-data-footer-right">
        <span className="text-[var(--text-muted)]">每页</span>
        <select
          className="table-data-page-size"
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
        >
          <option value={50}>50 行</option>
          <option value={100}>100 行</option>
          <option value={200}>200 行</option>
          <option value={500}>500 行</option>
        </select>

        <div className="table-data-page-nav">
          <button type="button" disabled={!canPrev} onClick={() => onPageChange(Math.max(1, page - 1))} title="上一页">
            <ChevronLeft size={13} />
          </button>
          <strong className="px-1 text-[var(--text-primary)]">{page}</strong>
          <button type="button" disabled={!canNext} onClick={() => onPageChange(page + 1)} title="下一页">
            <ChevronRight size={13} />
          </button>
        </div>
      </div>
    </footer>
  );
}
