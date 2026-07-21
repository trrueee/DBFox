import { AlertCircle, AlertTriangle, Copy, Download, ExternalLink, RefreshCw } from "lucide-react";
import { Button } from "../../../components/ui";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";
import { copyText, downloadBlobFile } from "./artifactActions";
import { ArtifactTableFooter } from "./table/ArtifactTableFooter";
import { ArtifactTableGrid } from "./table/ArtifactTableGrid";
import { ArtifactTableToolbar } from "./table/ArtifactTableToolbar";
import { useArtifactTableData } from "./table/useArtifactTableData";
import "./table/ArtifactTable.css";

interface TableArtifactViewProps {
  artifact: ResultViewArtifact;
  onToast: (message: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  mode?: "inline" | "workspace";
}

export function TableArtifactView({ artifact, onToast, onOpenResultTab, mode = "inline" }: TableArtifactViewProps) {
  const table = useArtifactTableData(artifact, mode);

  const handleCopy = async () => {
    const ok = await copyText(table.csv);
    onToast(ok ? "已复制 CSV" : "复制失败，请手动选择复制");
  };

  const handleExport = async () => {
    try {
      const blob = await table.exportAll();
      const ok = downloadBlobFile(`${artifact.id}.csv`, blob);
      onToast(ok ? "已导出 CSV" : "CSV 导出失败");
    } catch {
      onToast("CSV 导出失败");
    }
  };

  const handleCellCopy = async (value: string) => {
    const ok = await copyText(value);
    onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制");
  };

  const toolbar = (
    <ArtifactTableToolbar
      mode={mode}
      artifactId={artifact.id}
      columns={table.columns}
      search={table.search}
      onSearchChange={table.setSearch}
      sort={table.sort}
      onApplySort={table.setSortState}
      onClearSort={table.clearSort}
      filters={table.filters}
      onFiltersChange={table.setFilters}
      isLoading={table.isLoading}
      onRefresh={table.refresh}
      onExport={() => void handleExport()}
      onCopy={() => void handleCopy()}
    />
  );

  if (mode === "workspace") {
    return (
      <div className="artifact-table-workspace">
        {toolbar}
        {table.consistency === "live_reexecution" && table.viewExecutedAt && (
          <div className="artifact-table-alert artifact-table-alert-live">
            <RefreshCw size={12} className="artifact-table-alert-icon" />
            <span>
              {table.originalExecutedAt
                ? `分析取数 ${formatExecutionTime(table.originalExecutedAt)} · 当前重查 ${formatExecutionTime(table.viewExecutedAt)}`
                : `当前重查 ${formatExecutionTime(table.viewExecutedAt)}`}
              ；当前表格不是历史结果快照
            </span>
          </div>
        )}
        {table.fetchError && (
          <div className="artifact-table-alert artifact-table-alert-error">
            <AlertCircle size={13} className="artifact-table-alert-icon" />
            <span>获取分页数据失败: {table.fetchError}</span>
          </div>
        )}
        {(table.warnings.length > 0 || table.notices.length > 0) && (
          <div className="artifact-table-alert artifact-table-alert-notice">
            <AlertTriangle size={11} className="artifact-table-alert-icon" />
            <span>{[...table.warnings, ...table.notices].join("；")}</span>
          </div>
        )}

        <div className="artifact-table-container">
          {table.isLoading && <div className="artifact-table-loading-bar" />}
          <ArtifactTableGrid
            columns={table.columns}
            columnTypes={table.columnTypes}
            rows={table.visibleRows}
            sort={table.sort}
            onSort={table.setSortColumn}
            onCopyCell={(value) => void handleCellCopy(value)}
            emptyLabel="无匹配结果"
          />
        </div>

        <ArtifactTableFooter
          page={table.page}
          pageSize={table.pageSize}
          isLoading={table.isLoading}
          visibleRowCount={table.visibleRows.length}
          latencyMs={table.latencyMs}
          totalRows={table.totalRows}
          truncated={artifact.truncated}
          hasNextPage={table.hasNextPage}
          onPageChange={table.setPage}
          onPageSizeChange={(value) => {
            table.setPageSize(value);
            table.setPage(1);
          }}
        />
      </div>
    );
  }

  return (
    <ArtifactCard
      title={artifact.title}
      badge="结果表"
      tone="table"
      description={artifact.description}
      meta={<InlineTableMeta artifact={artifact} table={table} />}
      actions={
        <>
          {onOpenResultTab && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="artifact-table-action-button"
              onClick={() => onOpenResultTab(artifact)}
            >
              <ExternalLink size={10} />
              打开为 Tab
            </Button>
          )}
          <Button type="button" variant="outline" size="sm" className="artifact-table-action-button" onClick={handleCopy}>
            <Copy size={10} />
            复制 CSV
          </Button>
          <Button type="button" variant="outline" size="sm" className="artifact-table-action-button" onClick={() => void handleExport()}>
            <Download size={10} />
            导出 CSV
          </Button>
        </>
      }
    >
      {toolbar}
      {table.fetchError && (
        <div className="artifact-table-inline-error">
          <AlertCircle size={12} className="artifact-table-alert-icon" />
          获取分页数据失败: {table.fetchError}
        </div>
      )}
      <div className="artifact-table-inline-table">
        <ArtifactTableGrid
          columns={table.columns}
          columnTypes={table.columnTypes}
          rows={table.visibleRows}
          sort={table.sort}
          onSort={table.setSortColumn}
          onCopyCell={(value) => void handleCellCopy(value)}
          emptyLabel="无匹配结果"
        />
      </div>
    </ArtifactCard>
  );
}

function InlineTableMeta({
  artifact,
  table,
}: {
  artifact: ResultViewArtifact;
  table: ReturnType<typeof useArtifactTableData>;
}) {
  return (
    <div className="artifact-table-meta">
      <span className="artifact-pill">
        本页 {table.visibleRows.length} / 共 {table.totalRows ?? "未知"} 行
      </span>
      <span className="artifact-pill">{table.columns.length} 列</span>
      {table.latencyMs !== undefined && <span className="artifact-pill">{table.latencyMs}ms</span>}
      {artifact.truncated && <span className="artifact-pill artifact-pill--warning">结果已截断</span>}
      {table.consistency === "live_reexecution" && table.viewExecutedAt && (
        <>
          {table.originalExecutedAt && (
            <span className="artifact-pill">分析取数 {formatExecutionTime(table.originalExecutedAt)}</span>
          )}
          <span className="artifact-pill artifact-pill--live">
            当前重查 {formatExecutionTime(table.viewExecutedAt)}
          </span>
        </>
      )}
      {table.warnings.map((warning) => (
        <span key={`warning-${warning}`} className="artifact-pill artifact-pill--warning">
          {warning}
        </span>
      ))}
      {table.notices.map((notice) => (
        <span key={`notice-${notice}`} className="artifact-pill">
          {notice}
        </span>
      ))}
    </div>
  );
}

function formatExecutionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
