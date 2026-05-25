import { useEffect, useState, useMemo } from "react";
import { 
  Database, 
  Search, 
  ChevronLeft, 
  ChevronRight, 
  RefreshCw, 
  Filter,
  Layers,
  Sparkles,
  Info
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, SchemaTable } from "../lib/api";
import { DataTable } from "../components/DataTable";
import { ErrorBoundary } from "../components/ErrorBoundary";

interface DataPageProps {
  datasource: DataSource;
  selectedTableName: string | null;
  schemaTables: SchemaTable[];
  onSelectTable: (tableName: string) => void;
}

export const DataPage = ({ 
  datasource, 
  selectedTableName, 
  schemaTables,
  onSelectTable 
}: DataPageProps) => {
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columnTypes, setColumnTypes] = useState<Record<string, { dataType: string; isPrimaryKey: boolean; isForeignKey: boolean }>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Pagination & Filters state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [filterText, setFilterText] = useState("");
  const [appliedFilter, setAppliedFilter] = useState("");
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const sortDirection: "ASC" | "DESC" = "ASC";
  
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  // Sync columns first when a table is selected
  useEffect(() => {
    setPage(1);
    setSortColumn(null);
    setFilterText("");
    setAppliedFilter("");
    if (selectedTableName) {
      void loadInitialSchemaAndData();
    } else {
      setColumns([]);
      setRows([]);
    }
  }, [selectedTableName, datasource.id]);

  // Load column metadata (types, PKs, etc.) whenever schemaTables updates or selection changes
  useEffect(() => {
    if (!selectedTableName) {
      setColumnTypes({});
      return;
    }
    const loadColumnMeta = async () => {
      const tableInfo = schemaTables.find(
        (t) => t.table_name.toLowerCase().trim() === selectedTableName.toLowerCase().trim()
      );
      if (tableInfo) {
        try {
          const cols = await api.listColumns(tableInfo.id);
          const typesMap: Record<string, { dataType: string; isPrimaryKey: boolean; isForeignKey: boolean }> = {};
          for (const c of cols) {
            typesMap[c.column_name] = {
              dataType: c.column_type || c.data_type,
              isPrimaryKey: c.is_primary_key,
              isForeignKey: c.is_foreign_key
            };
          }
          setColumnTypes(typesMap);
        } catch (colErr) {
          console.error("Failed to load columns metadata for Navicat UI:", colErr);
        }
      }
    };
    void loadColumnMeta();
  }, [selectedTableName, schemaTables]);

  // Reload when page, size, sorting, or applied filters change
  useEffect(() => {
    if (selectedTableName) {
      void fetchTableData();
    }
  }, [page, pageSize, sortColumn, sortDirection, appliedFilter]);

  const loadInitialSchemaAndData = async () => {
    if (!selectedTableName) return;
    setLoading(true);
    setError(null);
    try {
      // Fetch 1 row to get columns quickly and securely
      const sample = await api.executeSql(datasource.id, `SELECT * FROM \`${selectedTableName}\` LIMIT 1;`);
      if (sample.success) {
        setColumns(sample.columns || []);
      }
      await fetchTableData();
    } catch (err: any) {
      setError(err.message ?? "加载表格架构失败");
      setLoading(false);
    }
  };

  const fetchTableData = async () => {
    if (!selectedTableName) return;
    setLoading(true);
    setError(null);
    try {
      const offset = (page - 1) * pageSize;
      
      // Build filters
      let whereClause = "";
      if (appliedFilter && columns.length > 0) {
        const escapedFilter = appliedFilter.replace(/'/g, "''");
        const orConditions = columns
          .map(col => `\`${col}\` LIKE '%${escapedFilter}%'`)
          .join(" OR ");
        whereClause = ` WHERE ${orConditions}`;
      }

      // Build sorting
      let orderClause = "";
      if (sortColumn) {
        orderClause = ` ORDER BY \`${sortColumn}\` ${sortDirection}`;
      }

      const sql = `SELECT * FROM \`${selectedTableName}\`${whereClause}${orderClause} LIMIT ${pageSize} OFFSET ${offset};`;
      const res = await api.executeSql(datasource.id, sql);
      
      if (res.success) {
        setRows(res.rows || []);
        if (res.columns && res.columns.length > 0) {
          setColumns(res.columns);
        }
        setLatencyMs(res.latencyMs || res.totalMs || null);
      } else {
        setError("查询未成功返回结果");
      }
    } catch (err: any) {
      setError(err.message ?? "数据加载出错，请检查 SQL 权限或过滤语法");
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setAppliedFilter(filterText);
  };

  const handleClearFilter = () => {
    setFilterText("");
    setAppliedFilter("");
    setPage(1);
  };


  // Find table metadata
  const activeTableMeta = useMemo(() => {
    return schemaTables.find(t => t.table_name === selectedTableName) || null;
  }, [schemaTables, selectedTableName]);

  if (!selectedTableName) {
    return (
      <div 
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          flex: 1,
          padding: 40,
          background: "var(--bg-primary)",
          overflowY: "auto",
        }}
      >
        <div 
          className="lab-card animate-fade-in"
          style={{
            maxWidth: 620,
            width: "100%",
            padding: "40px 32px",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 20,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-light)",
            borderRadius: 16,
            boxShadow: "0 20px 40px rgba(0, 0, 0, 0.05)"
          }}
        >
          <div 
            style={{
              width: 64,
              height: 64,
              borderRadius: "50%",
              background: "rgba(74, 91, 192, 0.1)",
              display: "grid",
              placeItems: "center",
              marginBottom: 8,
            }}
          >
            <Database size={32} style={{ color: "var(--accent-indigo)" }} />
          </div>
          <div>
            <h2 className="text-display" style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: 8, color: "var(--text-primary)" }}>
              沉浸式数据浏览大屏
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.92rem", lineHeight: 1.6, maxWidth: 460, margin: "0 auto" }}>
              欢迎体验 DataBox 的极简数仓视图。此模式专为浏览、过滤和检索海量数据而设计，去除了多余的控制面板，让您的主任务区达到 100% 宽度。
            </p>
          </div>

          <div 
            style={{ 
              width: "100%", 
              height: "1px", 
              background: "var(--border-light)", 
              margin: "12px 0" 
            }} 
          />

          <div style={{ width: "100%", textAlign: "left" }}>
            <h4 style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
              🚀 选择一张表开始探索:
            </h4>
            {schemaTables.length === 0 ? (
              <div style={{ padding: "16px 20px", background: "var(--bg-secondary)", borderRadius: 8, fontSize: "0.86rem", color: "var(--text-secondary)", border: "1px dashed var(--border-light)" }}>
                当前连接下没有发现任何数据表，请先同步 Schema。
              </div>
            ) : (
              <div 
                style={{ 
                  display: "grid", 
                  gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", 
                  gap: 8,
                  maxHeight: 200,
                  overflowY: "auto",
                  paddingRight: 4
                }}
              >
                {schemaTables.slice(0, 12).map((t) => (
                  <button
                    key={t.id}
                    onClick={() => onSelectTable(t.table_name)}
                    className="hover-lift"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "8px 12px",
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-light)",
                      borderRadius: 8,
                      color: "var(--text-secondary)",
                      fontSize: "0.82rem",
                      fontWeight: 500,
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <Layers size={13} style={{ opacity: 0.6 }} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.table_name}
                    </span>
                  </button>
                ))}
                {schemaTables.length > 12 && (
                  <div 
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "0.78rem",
                      color: "var(--text-muted)",
                      padding: "8px",
                      border: "1px dashed var(--border-light)",
                      borderRadius: 8
                    }}
                  >
                    及其他 {schemaTables.length - 12} 张表
                  </div>
                )}
              </div>
            )}
          </div>
          
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 12 }}>
            <Sparkles size={13} style={{ color: "var(--accent-indigo)" }} />
            <span>您也可以在左侧的 [数据对象] 折叠面板中快速切换数据表</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div 
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        width: "100%",
        overflow: "hidden",
        background: "var(--bg-primary)",
        gap: 0,
      }}
    >
      {/* Immersive Top Control Bar - Bleed to Edge */}
      <div 
        style={{
          padding: "6px 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-light)",
          flexShrink: 0,
          userSelect: "none"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 700, margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "var(--accent-indigo)" }}>{selectedTableName}</span>
            {activeTableMeta?.table_comment && (
              <span style={{ fontSize: "0.74rem", color: "var(--text-muted)", fontWeight: 400 }}>
                ({activeTableMeta.table_comment})
              </span>
            )}
          </h3>
        </div>

        {/* Filters and Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <form onSubmit={handleApplyFilter} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ position: "relative" }}>
              <Search size={11} style={{ position: "absolute", left: 8, top: 7, color: "var(--text-muted)" }} />
              <input
                className="input-field input-field-sm"
                placeholder="搜索表格数据..."
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                style={{ paddingLeft: 22, width: 180, fontSize: "0.74rem", height: 24 }}
              />
            </div>
            <button 
              type="submit" 
              className="btn-primary" 
              style={{ height: 24, padding: "0 8px", fontSize: "0.72rem", fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}
            >
              <Filter size={11} />
              <span>过滤</span>
            </button>
            {appliedFilter && (
              <button 
                type="button" 
                className="btn-secondary" 
                onClick={handleClearFilter}
                style={{ height: 24, padding: "0 8px", fontSize: "0.72rem" }}
              >
                清除
              </button>
            )}
          </form>

          <div style={{ width: "1px", height: 16, background: "var(--border-light)" }} />

          <button 
            className="btn-secondary" 
            onClick={fetchTableData}
            disabled={loading}
            style={{ height: 24, width: 24, padding: 0, display: "grid", placeItems: "center" }}
            title="刷新数据"
          >
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Sorting Indicators Info */}
      {sortColumn && (
        <div 
          style={{ 
            display: "flex", 
            alignItems: "center", 
            gap: 8, 
            padding: "4px 16px", 
            background: "rgba(74, 91, 192, 0.05)", 
            fontSize: "0.74rem", 
            color: "var(--accent-indigo)",
            borderBottom: "1px solid var(--border-light)",
            flexShrink: 0
          }}
        >
          <Info size={11} />
          <span>排序: 列 <strong>{sortColumn}</strong> ({sortDirection === "ASC" ? "升序" : "降序"})</span>
          <button 
            style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--accent-indigo)", cursor: "pointer", fontWeight: 600, fontSize: "0.72rem" }}
            onClick={() => setSortColumn(null)}
          >
            清除排序
          </button>
        </div>
      )}

      {/* Data Table Grid container */}
      <div 
        style={{ 
          flex: 1, 
          overflow: "hidden", 
          display: "flex", 
          flexDirection: "column",
          background: "var(--bg-surface)",
        }}
      >
        {error ? (
          <div style={{ padding: 24, textAlign: "center" }}>
            <div style={{ color: "var(--accent-red)", fontWeight: 600, fontSize: "0.95rem", marginBottom: 8 }}>
              ⚠️ 加载出错
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", maxWidth: 500, margin: "0 auto", lineHeight: 1.5 }}>
              {error}
            </div>
            <button 
              className="btn-primary" 
              style={{ marginTop: 16, padding: "6px 16px", fontSize: "0.82rem" }}
              onClick={loadInitialSchemaAndData}
            >
              重试加载
            </button>
          </div>
        ) : loading && rows.length === 0 ? (
          <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="skeleton" style={{ height: 40, borderRadius: 6 }} />
            {[1, 2, 3, 4, 5, 6, 7].map((i) => (
              <div key={i} className="skeleton" style={{ height: 34, borderRadius: 4 }} />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 60, textAlign: "center", color: "var(--text-muted)" }}>
            <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>
              没有找到任何行
            </div>
            <p style={{ fontSize: "0.85rem", maxWidth: 360, margin: "0 auto 16px" }}>
              {appliedFilter ? "没有与搜索过滤匹配的记录，请尝试更改搜索词。" : "该表目前没有任何行数据，您可以通过 SQL 工作台或 Schema 测试工具写入。"}
            </p>
            {appliedFilter && (
              <button className="btn-secondary" style={{ fontSize: "0.82rem" }} onClick={handleClearFilter}>
                清除搜索词
              </button>
            )}
          </div>
        ) : (
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
              <ErrorBoundary title="数据网格 (DataTable) 渲染崩溃">
                <DataTable
                  columns={columns}
                  rows={rows}
                  tableName={selectedTableName}
                  databaseName={datasource.database_name}
                  maxHeight="100%"
                  columnTypes={columnTypes}
                />
              </ErrorBoundary>
            </div>
          </div>
        )}
      </div>

      {/* Navicat-style Compact Status Bar */}
      {!error && rows.length > 0 && (
        <div 
          style={{
            height: 26,
            padding: "0 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "var(--bg-secondary)",
            borderTop: "1px solid var(--border-light)",
            fontSize: "0.72rem",
            color: "var(--text-secondary)",
            userSelect: "none",
            flexShrink: 0
          }}
        >
          {/* Left Side: Metadata & Counters */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span>预估行数: <strong style={{ color: "var(--text-primary)" }}>{activeTableMeta?.row_count_estimate?.toLocaleString() ?? "0"}</strong></span>
            <span style={{ opacity: 0.5 }}>|</span>
            <span>列数: <strong style={{ color: "var(--text-primary)" }}>{columns.length}</strong></span>
            <span style={{ opacity: 0.5 }}>|</span>
            {latencyMs !== null && (
              <>
                <span>耗时: <strong style={{ color: "var(--text-primary)" }}>{latencyMs}ms</strong></span>
                <span style={{ opacity: 0.5 }}>|</span>
              </>
            )}
            <span>显示 {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, (page - 1) * pageSize + rows.length)} 行</span>
          </div>

          {/* Right Side: Page Controls */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ color: "var(--text-muted)" }}>每页</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPage(1);
                  setPageSize(Number(e.target.value));
                }}
                style={{
                  height: 18,
                  fontSize: "0.7rem",
                  padding: "0 2px",
                  borderRadius: 3,
                  border: "1px solid var(--border-light)",
                  background: "var(--bg-primary)",
                  color: "var(--text-primary)",
                  cursor: "pointer"
                }}
              >
                <option value={50}>50 行</option>
                <option value={100}>100 行</option>
                <option value={200}>200 行</option>
                <option value={500}>500 行</option>
              </select>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 1 }}>
              <button
                disabled={page <= 1 || loading}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                style={{
                  padding: "1px 4px",
                  display: "grid",
                  placeItems: "center",
                  height: 18,
                  border: "none",
                  background: "transparent",
                  cursor: page <= 1 ? "default" : "pointer",
                  color: page <= 1 ? "var(--text-muted)" : "var(--text-primary)"
                }}
                title="上一页"
              >
                <ChevronLeft size={12} />
              </button>
              
              <span style={{ padding: "0 6px", fontWeight: 600, color: "var(--text-primary)" }}>
                {page}
              </span>

              <button
                disabled={rows.length < pageSize || loading}
                onClick={() => setPage(p => p + 1)}
                style={{
                  padding: "1px 4px",
                  display: "grid",
                  placeItems: "center",
                  height: 18,
                  border: "none",
                  background: "transparent",
                  cursor: rows.length < pageSize ? "default" : "pointer",
                  color: rows.length < pageSize ? "var(--text-muted)" : "var(--text-primary)"
                }}
                title="下一页"
              >
                <ChevronRight size={12} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
