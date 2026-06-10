import { useEffect, useMemo, useState } from "react";
import { ArrowUpDown, Code, Download, Filter, RefreshCw, Search, Sparkles } from "lucide-react";
import { executeSql, quoteIdentifier, resolveTableByName } from "../../engine/engineApi";

interface TablePreviewPaneProps {
  tableId: string;
  onOpenSqlConsole: () => void;
  onToast: (message: string) => void;
}

export function TablePreviewPane({ tableId, onOpenSqlConsole, onToast }: TablePreviewPaneProps) {
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Array<Record<string, string | null>>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pageSize, setPageSize] = useState(20);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const previewSql = useMemo(() => `SELECT * FROM ${quoteIdentifier(tableId)} LIMIT ${pageSize};`, [tableId, pageSize]);

  const loadPreview = async () => {
    setLoading(true);
    setError("");
    try {
      const resolved = await resolveTableByName(tableId);
      if (!resolved) {
        setColumns([]);
        setRows([]);
        setError("未找到该表的数据源或 Schema 元数据，请先同步 Schema。");
        return;
      }
      const result = await executeSql(resolved.datasource.id, previewSql, `preview table ${tableId}`);
      setColumns(result.columns);
      setRows(result.rows);
      setLatencyMs(result.latencyMs);
      if (result.warnings?.length) onToast(result.warnings[0]);
    } catch (err) {
      setColumns([]);
      setRows([]);
      setError(err instanceof Error ? err.message : "读取表预览失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPreview();
  }, [previewSql]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="hifi-panel-toolbar">
        <div className="hifi-toolbar-left">
          <button className="hifi-toolbar-btn" onClick={() => void loadPreview()}><RefreshCw size={10} /> 刷新</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("筛选器待接入：后续会转换为安全 SQL 条件")}><Filter size={10} /> 筛选</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("排序待接入：后续会转换为安全 SQL 排序")}><ArrowUpDown size={10} /> 排序</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("导出待接入：后续从当前结果集导出 CSV")}><Download size={10} /> 导出</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("生成测试数据需要后端写入接口，当前只读预览不执行写入")}><Sparkles size={10} className="text-yellow-600" /> 生成测试数据</button>
        </div>
        <div className="hifi-toolbar-right">
          <Search size={12} className="text-gray-400 cursor-pointer" />
          <button className="hifi-text-btn flex items-center gap-1" onClick={onOpenSqlConsole}><Code size={11} /> 在 SQL 运行</button>
        </div>
      </div>

      <div className="hifi-table-container flex-1 overflow-auto">
        {loading && <div className="text-[11px] text-slate-400 text-center mt-10">正在通过 Local Engine 读取预览数据...</div>}
        {error && <div className="text-[11px] text-red-500 bg-red-50 rounded-lg p-3 m-3">{error}</div>}
        {!loading && !error && (
          <table className="hifi-table">
            <thead>
              <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => (
                    <td key={column} className="max-w-[240px] truncate" title={row[column] ?? ""}>{row[column] ?? "NULL"}</td>
                  ))}
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={Math.max(columns.length, 1)} className="text-center text-slate-400">暂无数据</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="hifi-table-footer">
        <span>{latencyMs === null ? "等待查询" : `返回 ${rows.length} 行 · ${latencyMs}ms`}</span>
        <div className="hifi-pagination">
          <span className="text-gray-400 cursor-pointer">&lt;</span>
          <span className="hifi-page-num active">1</span>
          <span className="text-gray-400">预览模式</span>
          <span className="text-gray-400 cursor-pointer">&gt;</span>
        </div>
        <select className="border border-gray-200 rounded px-1 text-[10px]" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>
          <option value="10">10条/页</option>
          <option value="20">20条/页</option>
          <option value="50">50条/页</option>
        </select>
      </div>
    </div>
  );
}
