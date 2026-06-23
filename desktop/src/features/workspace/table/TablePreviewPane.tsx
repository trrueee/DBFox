import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowUpDown, Code, Database, Download, Filter, RefreshCw, Search, Sparkles } from "lucide-react";
import { ImageCell, isImageUrl } from "../../../components/ImageCell";
import { executeSql, listColumns, quoteIdentifier, resolveTableByName } from "../../engine/engineApi";
import type { EngineColumn } from "../../engine/engineApi";

interface TablePreviewPaneProps {
  tableId: string;
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

// Keeps the last loaded page per table so re-opening a tab shows data instantly
// (then revalidates in the background) instead of flashing an empty loading view.
const previewCache = new Map<string, PreviewData>();

export function TablePreviewPane({ tableId, onOpenSqlConsole, onToast }: TablePreviewPaneProps) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const cacheKey = `${tableId}|${page}|${pageSize}`;
  const [data, setData] = useState<PreviewData | null>(() => previewCache.get(cacheKey) ?? null);
  const [columnTypes, setColumnTypes] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [noticeDismissed, setNoticeDismissed] = useState(false);
  const requestSeqRef = useRef(0);

  const [prevTableId, setPrevTableId] = useState(tableId);
  const [prevPage, setPrevPage] = useState(page);
  const [prevPageSize, setPrevPageSize] = useState(pageSize);

  if (tableId !== prevTableId || page !== prevPage || pageSize !== prevPageSize) {
    let nextPage = page;
    if (tableId !== prevTableId) {
      nextPage = 1;
      setPage(1);
      setPrevTableId(tableId);
    }
    setPrevPage(nextPage);
    setPrevPageSize(pageSize);

    const nextCacheKey = `${tableId}|${nextPage}|${pageSize}`;
    const cached = previewCache.get(nextCacheKey);
    if (cached) {
      setData(cached);
    } else if (tableId !== prevTableId) {
      setData(null);
    }
  }

  const loadPreview = async () => {
    const seq = ++requestSeqRef.current;
    setLoading(true);
    setError("");
    try {
      const resolved = await resolveTableByName(tableId);
      if (seq !== requestSeqRef.current) return;
      if (!resolved) {
        setError("未找到该表的数据源或 Schema 元数据，请先同步 Schema。");
        return;
      }
      // Fetch column metadata for type display
      void listColumns(resolved.table.id).then((cols: EngineColumn[]) => {
        const types = new Map<string, string>();
        cols.forEach((c) => types.set(c.column_name, c.data_type));
        setColumnTypes(types);
      });
      // Request one extra row to know whether a next page exists.
      const offset = (page - 1) * pageSize;
      const previewSql = `SELECT * FROM ${quoteIdentifier(tableId, resolved.datasource.db_type)} LIMIT ${pageSize + 1}${offset > 0 ? ` OFFSET ${offset}` : ""};`;
      const result = await executeSql(resolved.datasource.id, previewSql, `preview table ${tableId}`);
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
  }, [tableId, page, pageSize]);

  const columns = data?.columns ?? [];
  const rows = data?.rows ?? [];
  const warnings = data?.warnings ?? [];
  const notices = data?.notices ?? [];
  const initialLoading = loading && !data;
  const refreshing = loading && !!data;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="hifi-panel-toolbar">
        <div className="hifi-toolbar-left">
          <button className="hifi-toolbar-btn" onClick={() => void loadPreview()} disabled={loading}>
            <RefreshCw size={10} className={loading ? "animate-spin" : ""} /> 刷新
          </button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("筛选器待接入：后续会转换为安全 SQL 条件")}><Filter size={10} /> 筛选</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("排序待接入：后续会转换为安全 SQL 排序")}><ArrowUpDown size={10} /> 排序</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("导出待接入：后续从当前结果集导出 CSV")}><Download size={10} /> 导出</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")}><Sparkles size={10} className="text-yellow-600" /> 生成测试数据</button>
        </div>
        <div className="hifi-toolbar-right">
          <Search size={12} className="text-gray-400 cursor-pointer" />
          <button className="hifi-text-btn flex items-center gap-1" onClick={() => onOpenSqlConsole()}><Code size={11} /> 在 SQL 运行</button>
        </div>
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
