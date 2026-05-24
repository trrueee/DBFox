import { useEffect, useState } from "react";
import { Eye, HardDrive, Key, Link2, Search, Table, X } from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, ERDiagramData, QueryResult, SchemaColumn, SchemaTable } from "../lib/api";
import { DataTable } from "../components/DataTable";
import { ErDiagram } from "../components/ErDiagram";
import { TableDesignDraft } from "../components/TableDesignDraft";

interface SchemaPageProps {
  datasource: DataSource;
  initialViewTab?: "fields" | "er" | "data";
}

export const SchemaPage = ({ datasource, initialViewTab }: SchemaPageProps) => {
  const [tables, setTables] = useState<SchemaTable[]>([]);
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null);
  const [columns, setColumns] = useState<SchemaColumn[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [columnsLoading, setColumnsLoading] = useState(false);
  const [viewTab, setViewTab] = useState<"fields" | "er" | "data" | "design">("fields");
  const [erData, setErData] = useState<ERDiagramData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<QueryResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Test data generation states
  const [showTestDataModal, setShowTestDataModal] = useState(false);
  const [testDataRowCount, setTestDataRowCount] = useState(10);
  const [testDataLanguage, setTestDataLanguage] = useState<"zh" | "en">("zh");
  const [generatingTestData, setGeneratingTestData] = useState(false);
  const [testDataResult, setTestDataResult] = useState<string | null>(null);
  const [testDataError, setTestDataError] = useState<string | null>(null);

  const handleGenerateTestData = async () => {
    if (!selectedTable) return;
    setGeneratingTestData(true);
    setTestDataError(null);
    setTestDataResult(null);
    try {
      const res = await api.generateTestData({
        datasource_id: datasource.id,
        table_name: selectedTable.table_name,
        row_count: testDataRowCount,
        language: testDataLanguage,
      });
      setTestDataResult(res.message);
      // Wait a bit, then refresh preview and close modal
      setTimeout(() => {
        void fetchPreviewData(selectedTable.table_name);
        setShowTestDataModal(false);
        setTestDataResult(null);
      }, 1800);
    } catch (err: any) {
      setTestDataError(err.message ?? "注入测试数据失败，请检查主外键关联表是否已填充数据。");
    } finally {
      setGeneratingTestData(false);
    }
  };

  useEffect(() => {
    void fetchTables();
    void fetchERDiagram();
  }, [datasource.id]);

  useEffect(() => {
    if (initialViewTab === "data" && selectedTable) setViewTab("data");
  }, [initialViewTab, selectedTable?.id]);

  useEffect(() => {
    if (viewTab === "data" && selectedTable) void fetchPreviewData(selectedTable.table_name);
  }, [viewTab, selectedTable?.id]);

  const fetchTables = async (selectTableName?: string) => {
    try {
      setLoading(true);
      const data = await api.listTables(datasource.id);
      setTables(data);
      if (data.length > 0) {
        const found = selectTableName ? data.find((t) => t.table_name === selectTableName) : null;
        await handleSelectTable(found || data[0]);
      } else {
        setSelectedTable(null);
        setColumns([]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchERDiagram = async () => {
    try {
      setErData(await api.getERDiagram(datasource.id));
    } catch (err) {
      console.error("ER load failed", err);
    }
  };

  const handleExecuteSuccess = (newTableName?: string) => {
    void fetchTables(newTableName);
    void fetchERDiagram();
    setViewTab("fields");
  };

  const fetchPreviewData = async (tableName: string) => {
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const result = await api.executeSql(datasource.id, `SELECT * FROM \`${tableName}\` LIMIT 100`);
      setPreviewData(result);
    } catch (error: any) {
      setPreviewError(error.message ?? "预览失败");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSelectTable = async (table: SchemaTable) => {
    setSelectedTable(table);
    setColumnsLoading(true);
    setPreviewData(null);
    setPreviewError(null);
    try {
      setColumns(await api.listColumns(table.id));
    } catch (err) {
      console.error(err);
    } finally {
      setColumnsLoading(false);
    }
  };

  const filteredTables = tables.filter(
    (t) =>
      t.table_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.table_comment.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div
      className="animate-fade-in"
      style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20, height: "100%", overflow: "hidden" }}
    >
      {/* Table List Panel */}
      <div className="lab-card" style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
        <div style={{ padding: "16px 16px 12px", borderBottom: "1px solid var(--border-light)" }}>
          <h4
            style={{ fontWeight: 600, fontSize: "0.92rem", marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}
          >
            <Table size={15} />
            数据表
            <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.82rem" }}>({tables.length})</span>
          </h4>
          <div style={{ position: "relative" }}>
            <Search
              size={14}
              style={{ position: "absolute", left: 10, top: 10, color: "var(--text-muted)" }}
            />
            <input
              className="input-field input-field-sm"
              placeholder="搜索表名或注释..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: 30, fontSize: "0.82rem" }}
            />
          </div>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "6px 8px" }}>
          {loading ? (
            <div style={{ padding: 12 }}>
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="skeleton" style={{ height: 30, marginBottom: 4, borderRadius: 4 }} />
              ))}
            </div>
          ) : filteredTables.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: "0.82rem" }}>
              没有匹配的表
            </div>
          ) : (
            filteredTables.map((table) => {
              const isSelected = selectedTable?.id === table.id;
              return (
                <button
                  key={table.id}
                  onClick={() => void handleSelectTable(table)}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: "8px 12px",
                    border: "none",
                    borderRadius: 5,
                    background: isSelected ? "var(--bg-active)" : "transparent",
                    color: isSelected ? "var(--accent-indigo)" : "var(--text-secondary)",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "background 0.1s",
                    marginBottom: 1,
                  }}
                >
                  <div
                    style={{
                      fontSize: "0.84rem",
                      fontWeight: isSelected ? 600 : 500,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {table.table_name}
                  </div>
                  {table.table_comment && (
                    <div
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--text-muted)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        marginTop: 1,
                      }}
                    >
                      {table.table_comment}
                    </div>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right Content */}
      <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", gap: 0 }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <h3 className="text-display" style={{ fontSize: "1.3rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              {selectedTable?.table_name ?? "Schema"}
              {selectedTable?.table_comment && (
                <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 400 }}>
                  — {selectedTable.table_comment}
                </span>
              )}
            </h3>
          </div>

          <div className="pill-tabs">
            <button className={`pill-tab ${viewTab === "fields" ? "active" : ""}`} onClick={() => setViewTab("fields")}>
              字段
            </button>
            <button className={`pill-tab ${viewTab === "er" ? "active" : ""}`} onClick={() => setViewTab("er")}>
              关系图
            </button>
            <button className={`pill-tab ${viewTab === "data" ? "active" : ""}`} onClick={() => setViewTab("data")}>
              <Eye size={13} />
              数据预览
            </button>
            <button className={`pill-tab ${viewTab === "design" ? "active" : ""}`} onClick={() => setViewTab("design")}>
              设计草稿
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="lab-card" style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {/* Fields Tab */}
          {viewTab === "fields" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              {/* Meta bar */}
              <div
                style={{
                  padding: "10px 20px",
                  borderBottom: "1px solid var(--border-light)",
                  background: "var(--bg-secondary)",
                  display: "flex",
                  gap: 24,
                  fontSize: "0.82rem",
                  color: "var(--text-secondary)",
                }}
              >
                <span>类型: <strong style={{ color: "var(--text-primary)" }}>{selectedTable?.table_type ?? "-"}</strong></span>
                {selectedTable?.row_count_estimate ? (
                  <span>预估行数: <strong style={{ color: "var(--text-primary)" }}>{selectedTable.row_count_estimate.toLocaleString()}</strong></span>
                ) : null}
                <span>字段: <strong style={{ color: "var(--text-primary)" }}>{columns.length}</strong></span>
              </div>

              <div style={{ flex: 1, overflow: "auto" }}>
                {columnsLoading ? (
                  <div style={{ padding: 24 }}>
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="skeleton" style={{ height: 36, marginBottom: 4, borderRadius: 4 }} />
                    ))}
                  </div>
                ) : columns.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">未选中表</div>
                    <div className="empty-state-desc">从左侧选择一个表查看字段详情</div>
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>字段名</th>
                        <th>数据类型</th>
                        <th>约束</th>
                        <th>可空</th>
                        <th>默认值</th>
                        <th>注释</th>
                      </tr>
                    </thead>
                    <tbody>
                      {columns.map((col) => (
                        <tr key={col.id}>
                          <td style={{ fontWeight: 600 }}>{col.column_name}</td>
                          <td>
                            <span className="text-mono" style={{ fontSize: "0.8rem", color: "var(--accent-teal)" }}>
                              {col.column_type}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: "flex", gap: 4 }}>
                              {col.is_primary_key && <span className="tag tag-indigo"><Key size={9} />PK</span>}
                              {col.is_foreign_key && <span className="tag tag-teal"><Link2 size={9} />FK</span>}
                              {!col.is_primary_key && !col.is_foreign_key && <span style={{ color: "var(--text-muted)" }}>-</span>}
                            </div>
                          </td>
                          <td>
                            {col.is_nullable ? (
                              <span style={{ color: "var(--text-secondary)" }}>YES</span>
                            ) : (
                              <span style={{ color: "var(--accent-amber)", fontWeight: 500 }}>NO</span>
                            )}
                          </td>
                          <td className="text-mono" style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                            {col.column_default != null && String(col.column_default) !== "None" ? String(col.column_default) : <span style={{ color: "var(--text-muted)" }}>NULL</span>}
                          </td>
                          <td style={{ color: "var(--text-secondary)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {col.column_comment || <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>-</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}

          {/* ER Tab */}
          {viewTab === "er" && (
            <div style={{ flex: 1, overflow: "hidden" }}>
              {erData && erData.nodes.length > 0 ? (
                <ErDiagram data={erData} />
              ) : (
                <div className="empty-state" style={{ height: "100%" }}>
                  <HardDrive size={36} className="empty-state-icon" />
                  <div className="empty-state-title">ER 关系图</div>
                  <div className="empty-state-desc">基于外键关系自动生成，当前数据库暂无外键约束或尚未同步</div>
                </div>
              )}
            </div>
          )}

          {/* Data Preview Tab */}
          {viewTab === "data" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div
                style={{
                  padding: "10px 20px",
                  borderBottom: "1px solid var(--border-light)",
                  background: "var(--bg-secondary)",
                  display: "flex",
                  gap: 20,
                  fontSize: "0.82rem",
                  color: "var(--text-secondary)",
                  alignItems: "center",
                }}
              >
                <span>表: <strong style={{ color: "var(--text-primary)" }}>{selectedTable?.table_name}</strong></span>
                {previewData && (
                  <>
                    <span>行: <strong style={{ color: "var(--text-primary)" }}>{previewData.rowCount}</strong></span>
                    <span>耗时: <strong style={{ color: "var(--text-primary)" }}>{previewData.latencyMs}ms</strong></span>
                  </>
                )}
                {previewLoading && <span className="status-badge status-badge-info">加载中...</span>}
                {previewError && <span className="status-badge status-badge-error">{previewError}</span>}

                <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <button
                    className="btn-secondary hover-lift"
                    style={{
                      padding: "3px 10px",
                      fontSize: "0.76rem",
                      color: "var(--accent-indigo)",
                      borderColor: "rgba(74, 91, 192, 0.2)",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      fontWeight: 600,
                    }}
                    onClick={() => setShowTestDataModal(true)}
                    disabled={previewLoading || !selectedTable}
                  >
                    <span>✨ AI 造测试数据</span>
                  </button>
                </div>
              </div>
              <div style={{ flex: 1, overflow: "auto" }}>
                {previewLoading ? (
                  <div style={{ padding: 32 }}>
                    {[1, 2, 3, 4, 5].map((i) => (
                      <div key={i} className="skeleton" style={{ height: 32, marginBottom: 4, borderRadius: 4 }} />
                    ))}
                  </div>
                ) : previewData && previewData.rows.length > 0 ? (
                  <DataTable columns={previewData.columns} rows={previewData.rows} />
                ) : previewData && previewData.rows.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-desc">该表暂无数据</div>
                    <button
                      className="btn-primary hover-lift"
                      style={{ marginTop: 12, padding: "6px 16px", fontSize: "0.82rem" }}
                      onClick={() => setShowTestDataModal(true)}
                    >
                      ✨ 智能造测试数据
                    </button>
                  </div>
                ) : !previewError ? (
                  <div className="empty-state"><div className="empty-state-desc">切换到「数据预览」查看前 100 行</div></div>
                ) : null}
              </div>
            </div>
          )}

          {/* ── Smart Test Data Generation Modal ── */}
          {showTestDataModal && selectedTable && (
            <div
              style={{
                position: "fixed",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: "rgba(0, 0, 0, 0.4)",
                backdropFilter: "blur(4px)",
                display: "grid",
                placeItems: "center",
                zIndex: 999,
                animation: "fade-in 0.2s ease-out",
              }}
              onClick={() => {
                if (!generatingTestData) setShowTestDataModal(false);
              }}
            >
              <div
                className="lab-card animate-scale-up"
                style={{
                  width: 440,
                  padding: 24,
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                  background: "var(--bg-surface)",
                  boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
                  border: "1px solid var(--border-light)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ fontSize: "1.1rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
                    <span>✨ AI 智能关联造测试数据</span>
                  </h3>
                  <button
                    className="btn-ghost"
                    style={{ padding: 4 }}
                    onClick={() => setShowTestDataModal(false)}
                    disabled={generatingTestData}
                  >
                    <X size={16} />
                  </button>
                </div>

                <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  为表 <strong style={{ color: "var(--text-primary)" }}>`{selectedTable.table_name}`</strong> 自动解析字段属性并注入高仿真的模拟数据。系统会自动解析外键依赖并进行智能关联，确保数据引用完整性。
                </p>

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div>
                    <label className="field-label" style={{ marginBottom: 6, display: "block" }}>生成行数</label>
                    <div style={{ display: "flex", gap: 8 }}>
                      {[10, 50, 100].map((rows) => (
                        <button
                          key={rows}
                          className={testDataRowCount === rows ? "btn-primary" : "btn-secondary"}
                          style={{ flex: 1, padding: "6px 0", fontSize: "0.82rem" }}
                          onClick={() => setTestDataRowCount(rows)}
                          disabled={generatingTestData}
                        >
                          {rows} 行
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="field-label" style={{ marginBottom: 6, display: "block" }}>语言与数据风格</label>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        className={testDataLanguage === "zh" ? "btn-primary" : "btn-secondary"}
                        style={{ flex: 1, padding: "6px 0", fontSize: "0.82rem", borderColor: testDataLanguage === "zh" ? "var(--accent-indigo)" : undefined }}
                        onClick={() => setTestDataLanguage("zh")}
                        disabled={generatingTestData}
                      >
                        🇨🇳 中文 (姓名、手机、地址)
                      </button>
                      <button
                        className={testDataLanguage === "en" ? "btn-primary" : "btn-secondary"}
                        style={{ flex: 1, padding: "6px 0", fontSize: "0.82rem", borderColor: testDataLanguage === "en" ? "var(--accent-indigo)" : undefined }}
                        onClick={() => setTestDataLanguage("en")}
                        disabled={generatingTestData}
                      >
                        🇺🇸 英文 (Names, Phones, Cities)
                      </button>
                    </div>
                  </div>

                  <div
                    style={{
                      background: "var(--bg-secondary)",
                      borderRadius: 8,
                      padding: 12,
                      fontSize: "0.76rem",
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-light)",
                    }}
                  >
                    🔒 <strong style={{ color: "var(--text-secondary)" }}>本地优先安全保障</strong>：推理与填充工作完全在本地执行，测试数据直接插入本地容器，无任何敏感信息离境上云风险。
                  </div>

                  {testDataResult && (
                    <div
                      style={{
                        background: "rgba(16, 185, 129, 0.08)",
                        border: "1px solid rgba(16, 185, 129, 0.2)",
                        borderRadius: 6,
                        padding: "8px 12px",
                        color: "var(--accent-green)",
                        fontSize: "0.82rem",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span style={{ fontSize: 14 }}>✅</span>
                      <span>{testDataResult}</span>
                    </div>
                  )}

                  {testDataError && (
                    <div
                      style={{
                        background: "rgba(239, 68, 68, 0.08)",
                        border: "1px solid rgba(239, 68, 68, 0.2)",
                        borderRadius: 6,
                        padding: "8px 12px",
                        color: "var(--accent-red)",
                        fontSize: "0.82rem",
                        lineHeight: 1.4,
                      }}
                    >
                      ⚠️ <strong>注入失败</strong>: {testDataError}
                    </div>
                  )}
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
                  <button
                    className="btn-secondary"
                    style={{ padding: "6px 16px", fontSize: "0.82rem" }}
                    onClick={() => setShowTestDataModal(false)}
                    disabled={generatingTestData}
                  >
                    取消
                  </button>
                  <button
                    className="btn-primary"
                    style={{ padding: "6px 20px", fontSize: "0.82rem", display: "flex", alignItems: "center", gap: 6 }}
                    onClick={handleGenerateTestData}
                    disabled={generatingTestData}
                  >
                    {generatingTestData ? (
                      <>
                        <span className="animate-spin">⏳</span> 正在智能生成并注入...
                      </>
                    ) : (
                      "🚀 开始造数"
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Table Design Draft Tab */}
          {viewTab === "design" && (
            <div style={{ flex: 1, overflow: "hidden" }}>
              <TableDesignDraft datasource={datasource} onExecuteSuccess={handleExecuteSuccess} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
