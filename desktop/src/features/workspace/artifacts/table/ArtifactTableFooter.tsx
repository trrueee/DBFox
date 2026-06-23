interface ArtifactTableFooterProps {
  page: number;
  pageSize: number;
  isLoading: boolean;
  visibleRowCount: number;
  latencyMs: number | undefined;
  totalRows: number | undefined;
  truncated?: boolean;
  isSqlBackedWorkspace: boolean;
  hasNextPage: boolean;
  onPageChange: (updater: number | ((page: number) => number)) => void;
  onPageSizeChange: (value: number) => void;
}

export function ArtifactTableFooter({
  page,
  pageSize,
  isLoading,
  visibleRowCount,
  latencyMs,
  totalRows,
  truncated,
  isSqlBackedWorkspace,
  hasNextPage,
  onPageChange,
  onPageSizeChange,
}: ArtifactTableFooterProps) {
  return (
    <div className="hifi-table-footer px-2 py-1">
      <span className="hifi-result-footer-text">
        {isLoading ? "加载中..." : `第 ${page} 页 · 本页 ${visibleRowCount} 行${latencyMs !== undefined ? ` · ${latencyMs}ms` : ""}`}
        {totalRows !== undefined && ` · 总计约 ${totalRows} 行`}
        {truncated && <span className="hifi-result-truncated"> · 结果已截断</span>}
      </span>

      <div className="flex items-center gap-2">
        {isSqlBackedWorkspace && (
          <div className="hifi-pagination flex items-center gap-1">
            <button
              className={`hifi-toolbar-btn hifi-result-page-btn flex items-center justify-center ${page <= 1 ? "opacity-40 cursor-not-allowed" : ""}`}
              disabled={page <= 1 || isLoading}
              onClick={() => onPageChange((current) => Math.max(1, current - 1))}
            >
              &lt;
            </button>
            <span className="hifi-page-num active flex items-center justify-center h-5 px-2 rounded text-[var(--ui-font-label)] font-medium">{page}</span>
            <button
              className={`hifi-toolbar-btn hifi-result-page-btn flex items-center justify-center ${!hasNextPage ? "opacity-40 cursor-not-allowed" : ""}`}
              disabled={!hasNextPage || isLoading}
              onClick={() => onPageChange((current) => current + 1)}
            >
              &gt;
            </button>
          </div>
        )}
        <select
          className="hifi-result-page-size px-1 focus:outline-none"
          value={pageSize}
          disabled={!isSqlBackedWorkspace}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
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
