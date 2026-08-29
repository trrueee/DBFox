import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../../components/ui";

interface ArtifactTableFooterProps {
  page: number;
  pageSize: number;
  isLoading: boolean;
  visibleRowCount: number;
  latencyMs: number | undefined;
  totalRows: number | undefined;
  truncated?: boolean;
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
  hasNextPage,
  onPageChange,
  onPageSizeChange,
}: ArtifactTableFooterProps) {
  return (
    <div className="artifact-table-footer">
      <span className="artifact-table-footer-text">
        {isLoading ? "正在加载…" : `第 ${page} 页 · 本页 ${visibleRowCount} 行${latencyMs !== undefined ? ` · ${latencyMs}ms` : ""}`}
        {totalRows !== undefined && ` · 总计约 ${totalRows} 行`}
        {truncated && <span className="artifact-table-truncated"> · 结果已截断</span>}
      </span>

      <div className="artifact-table-footer-controls">
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
              <ChevronLeft aria-hidden="true" />
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
              <ChevronRight aria-hidden="true" />
            </Button>
        </div>
        <Select
          value={String(pageSize)}
          onValueChange={(value) => onPageSizeChange(Number(value))}
        >
          <SelectTrigger className="artifact-table-page-size" aria-label="每页行数">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="10">10 条/页</SelectItem>
            <SelectItem value="20">20 条/页</SelectItem>
            <SelectItem value="50">50 条/页</SelectItem>
            <SelectItem value="100">100 条/页</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
