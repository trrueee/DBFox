import { Button, Select } from "../../../../components/ui";

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
    <div className="artifact-table-footer">
      <span className="artifact-table-footer-text">
        {isLoading ? "加载中..." : `第 ${page} 页 · 本页 ${visibleRowCount} 行${latencyMs !== undefined ? ` · ${latencyMs}ms` : ""}`}
        {totalRows !== undefined && ` · 总计约 ${totalRows} 行`}
        {truncated && <span className="artifact-table-truncated"> · 结果已截断</span>}
      </span>

      <div className="artifact-table-footer-controls">
        {isSqlBackedWorkspace && (
          <div className="artifact-table-pagination">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="artifact-table-page-button"
              aria-label="上一页"
              disabled={page <= 1 || isLoading}
              onClick={() => onPageChange((current) => Math.max(1, current - 1))}
            >
              &lt;
            </Button>
            <span className="artifact-table-page-number">{page}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="artifact-table-page-button"
              aria-label="下一页"
              disabled={!hasNextPage || isLoading}
              onClick={() => onPageChange((current) => current + 1)}
            >
              &gt;
            </Button>
          </div>
        )}
        <Select
          className="artifact-table-page-size"
          value={pageSize}
          disabled={!isSqlBackedWorkspace}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
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
