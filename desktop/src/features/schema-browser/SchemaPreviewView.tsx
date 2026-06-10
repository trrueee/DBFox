import { Copy, DatabaseZap, Terminal } from "lucide-react";
import type { QueryResult, SchemaTable } from "../../lib/api";
import { DataTable } from "../../components/DataTable";
import { ErrorBoundary } from "../../components/ErrorBoundary";

interface SchemaPreviewViewProps {
  table: SchemaTable | null;
  databaseName: string;
  previewData: QueryResult | null;
  previewSql: string;
  loading: boolean;
  error: string | null;
  copied: boolean;
  onCopySql: () => void;
  onOpenSql: () => void;
  onRefresh: () => void;
  onGenerateTestData: () => void;
}

export function SchemaPreviewView({
  table,
  databaseName,
  previewData,
  previewSql,
  loading,
  error,
  copied,
  onCopySql,
  onOpenSql,
  onRefresh,
  onGenerateTestData,
}: SchemaPreviewViewProps) {
  return (
    <div className="schema-browser-body">
      <div className="schema-preview-toolbar">
        <span>表: <strong className="text-[var(--text-primary)]">{table?.table_name ?? "-"}</strong></span>
        {previewData && <span>行: <strong className="text-[var(--text-primary)]">{previewData.rowCount}</strong></span>}
        {previewData?.latencyMs !== undefined && <span>耗时: <strong className="text-[var(--text-primary)]">{previewData.latencyMs}ms</strong></span>}
        {loading && <span className="font-black text-[var(--accent-indigo)]">加载中...</span>}
        {error && <span className="font-black text-[var(--accent-red)]">{error}</span>}
        <div className="schema-preview-actions">
          <button className="schema-button" type="button" onClick={onRefresh} disabled={!table || loading}>刷新</button>
          <button className="schema-button" type="button" onClick={onGenerateTestData} disabled={!table || loading} title="为当前表生成少量测试数据">
            <DatabaseZap size={12} />
            生成测试数据
          </button>
          <button className="schema-button" type="button" onClick={onCopySql} disabled={!previewSql} title={previewSql || "请选择表"}>
            <Copy size={12} />
            {copied ? "已复制" : "复制 SQL"}
          </button>
          <button className="schema-button" type="button" onClick={onOpenSql} disabled={!previewSql}>
            <Terminal size={12} />
            打开到工作台
          </button>
        </div>
      </div>
      <div className="schema-content-scroll">
        {loading && !previewData ? (
          <div className="p-6 flex flex-col gap-2">
            {[1, 2, 3, 4, 5].map((item) => <div key={item} className="h-9 rounded-md bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />)}
          </div>
        ) : previewData?.rows?.length ? (
          <ErrorBoundary title="预览数据渲染异常">
            <DataTable
              columns={previewData.columns || []}
              rows={previewData.rows || []}
              tableName={table?.table_name}
              databaseName={databaseName}
              maxHeight="100%"
            />
          </ErrorBoundary>
        ) : (
          <div className="schema-empty">
            <div className="schema-empty-card">
              <div className="schema-empty-title">暂无预览数据</div>
              <div className="schema-empty-copy">点击刷新读取前 100 行，或生成少量测试数据用于本地预览。</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
