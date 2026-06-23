import { AlertCircle, AlertTriangle, Copy, Download, ExternalLink } from "lucide-react";
import type { ResultViewArtifact, TableArtifact } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";
import { copyText, downloadBlobFile, downloadTextFile } from "./artifactActions";
import { ArtifactTableFooter } from "./table/ArtifactTableFooter";
import { ArtifactTableGrid } from "./table/ArtifactTableGrid";
import { ArtifactTableToolbar } from "./table/ArtifactTableToolbar";
import { useArtifactTableData } from "./table/useArtifactTableData";

interface TableArtifactViewProps {
  artifact: TableArtifact | ResultViewArtifact;
  onToast: (message: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
  mode?: "inline" | "workspace";
}

export function TableArtifactView({ artifact, onToast, onOpenResultTab, mode = "inline" }: TableArtifactViewProps) {
  const table = useArtifactTableData(artifact, mode);

  const handleCopy = async () => {
    const ok = await copyText(table.csv);
    onToast(ok ? "已复制 CSV" : "复制失败，请手动选择复制");
  };

  const handleExport = async () => {
    if (table.exportAll) {
      try {
        const blob = await table.exportAll();
        const ok = downloadBlobFile(`${artifact.id}.csv`, blob);
        onToast(ok ? "已导出 CSV" : "CSV 导出失败");
      } catch {
        onToast("CSV 导出失败");
      }
      return;
    }
    const ok = downloadTextFile(`${artifact.id}.csv`, table.csv, "text/csv;charset=utf-8");
    onToast(ok ? "已导出 CSV" : "CSV 导出失败");
  };

  const handleCellCopy = async (value: string) => {
    const ok = await copyText(value);
    onToast(ok ? "已复制单元格" : "复制失败，请手动选择复制");
  };

  const toolbar = (
    <ArtifactTableToolbar
      mode={mode}
      artifactId={artifact.id}
      search={table.search}
      onSearchChange={table.setSearch}
      isLoading={table.isLoading}
      isSqlBackedWorkspace={table.isSqlBackedWorkspace}
      onRefresh={table.refresh}
      onFilter={() => onToast("筛选器待接入：后续会转换为安全 SQL 条件")}
      onSortNotice={() => onToast("排序待接入：后续会转换为安全 SQL 排序")}
      onExport={() => void handleExport()}
      onCopy={() => void handleCopy()}
      canToggleLoadedRows={!table.isSqlBackedWorkspace && table.rowsToUseLength > 10 && !table.isSearching}
      expanded={table.expanded}
      loadedRowCount={table.rowsToUseLength}
      onToggleExpanded={() => table.setExpanded((value) => !value)}
    />
  );

  if (mode === "workspace") {
    return (
      <div className="hifi-result-workspace flex flex-col h-full overflow-hidden w-full">
        {toolbar}
        {table.fetchError && (
          <div className="hifi-preview-error m-2">
            <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />
            <span>获取分页数据失败: {table.fetchError}</span>
          </div>
        )}
        {(table.warnings.length > 0 || table.notices.length > 0) && (
          <div className="hifi-preview-notice m-2">
            <AlertTriangle size={11} className="flex-shrink-0" />
            <span>{[...table.warnings, ...table.notices].join("；")}</span>
          </div>
        )}

        <div className="hifi-table-container hifi-result-table-wrap flex-1 overflow-auto relative">
          {table.isLoading && <div className="hifi-preview-loading-bar absolute top-0 left-0 right-0" />}
          <ArtifactTableGrid
            columns={artifact.columns}
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
          isSqlBackedWorkspace={table.isSqlBackedWorkspace}
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
            <button
              type="button"
              className="hifi-guide-btn-secondary hifi-artifact-action-btn flex items-center gap-1"
              onClick={() => onOpenResultTab(artifact)}
            >
              <ExternalLink size={10} />
              打开为 Tab
            </button>
          )}
          <button className="hifi-guide-btn-secondary hifi-artifact-action-btn flex items-center gap-1" onClick={handleCopy}>
            <Copy size={10} />
            复制 CSV
          </button>
          <button className="hifi-guide-btn-secondary hifi-artifact-action-btn flex items-center gap-1" onClick={() => void handleExport()}>
            <Download size={10} />
            导出 CSV
          </button>
        </>
      }
    >
      {toolbar}
      {table.fetchError && (
        <div className="hifi-result-error mb-2 p-2 rounded text-[var(--ui-font-label)] flex items-center gap-1">
          <AlertCircle size={12} />
          获取分页数据失败: {table.fetchError}
        </div>
      )}
      <div className="hifi-result-inline-table overflow-auto">
        <ArtifactTableGrid
          columns={artifact.columns}
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
  artifact: TableArtifact | ResultViewArtifact;
  table: ReturnType<typeof useArtifactTableData>;
}) {
  return (
    <div className="artifact-table-meta">
      <span className="hifi-artifact-pill">
        预览 {table.previewCount} / 共 {table.totalRows} 行
      </span>
      {table.shouldUseWindow && (
        <span className="hifi-artifact-pill">
          窗口 1-{table.visibleRows.length} / {table.filteredAndSortedRows.length}
        </span>
      )}
      <span className="hifi-artifact-pill">{artifact.columns.length} 列</span>
      {table.latencyMs !== undefined && <span className="hifi-artifact-pill">{table.latencyMs}ms</span>}
      {!table.isSqlBackedWorkspace && table.returnedRows > table.previewCount && (
        <span className="hifi-artifact-pill">已载入 {table.returnedRows} 行</span>
      )}
      {artifact.truncated && <span className="hifi-artifact-pill hifi-artifact-pill-warning">结果已截断</span>}
      {table.warnings.map((warning) => (
        <span key={`warning-${warning}`} className="hifi-artifact-pill hifi-artifact-pill-warning">
          {warning}
        </span>
      ))}
      {table.notices.map((notice) => (
        <span key={`notice-${notice}`} className="hifi-artifact-pill">
          {notice}
        </span>
      ))}
    </div>
  );
}
