import { useEffect, useMemo, useState } from "react";
import { Copy, Eye, HardDrive, Key, Link2, Terminal, X, Settings, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, ERDiagramData, QueryResult, SchemaColumn, SchemaTable } from "../lib/api";
import { DataTable } from "../components/DataTable";
import { ErDiagram } from "../components/ErDiagram";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { TableDesignDraft } from "../components/TableDesignDraft";
import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";

interface SchemaPageProps {
  datasource: DataSource;
  initialViewTab?: "fields" | "er" | "data" | "design";
  selectedTableName?: string | null;
  onOpenSql?: (sql: string, title?: string) => void;
}

export const SchemaPage = ({ datasource, initialViewTab, selectedTableName, onOpenSql }: SchemaPageProps) => {
  const [tables, setTables] = useState<SchemaTable[]>([]);
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null);
  const [columns, setColumns] = useState<SchemaColumn[]>([]);
  const [columnsLoading, setColumnsLoading] = useState(false);
  const [viewTab, setViewTab] = useState<"fields" | "er" | "data" | "design">("fields");
  const [erData, setErData] = useState<ERDiagramData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<QueryResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewSqlCopied, setPreviewSqlCopied] = useState(false);

  // ER diagram controls
  const [erFocusTable, setErFocusTable] = useState<string | null>(null);
  const [erViewMode, setErViewMode] = useState<"focus" | "module" | "full">("focus");
  const [erDepth, setErDepth] = useState<1 | 2>(1);
  const [erShowInferred, setErShowInferred] = useState(true);

  // Test data generation states
  const [showTestDataModal, setShowTestDataModal] = useState(false);
  const [testDataRowCount, setTestDataRowCount] = useState(10);
  const [testDataLanguage, setTestDataLanguage] = useState<"zh" | "en">("zh");
  const [generatingTestData, setGeneratingTestData] = useState(false);
  const [testDataResult, setTestDataResult] = useState<string | null>(null);
  const [testDataError, setTestDataError] = useState<string | null>(null);
  const [confirmDetails, setConfirmDetails] = useState<ConfirmationDetails | null>(null);

  const handleGenerateTestData = async () => {
    if (!selectedTable) return;
    setGeneratingTestData(true);
    setTestDataError(null);
    setTestDataResult(null);
    try {
      const params = {
        datasource_id: datasource.id,
        table_name: selectedTable.table_name,
        row_count: testDataRowCount,
        language: testDataLanguage,
      };
      const res = await api.generateTestData(params);
      if (res && typeof res === "object" && "requires_confirmation" in res && res.requires_confirmation) {
        setConfirmDetails({
          confirm_token: res.confirm_token,
          impact_summary: res.impact_summary,
          expected_confirm_text: res.expected_confirm_text,
          onConfirm: async (text) => {
            const confirmed = await api.generateTestData(params, { token: res.confirm_token, text });
            if (confirmed && "message" in confirmed) setTestDataResult(confirmed.message ?? null);
            setConfirmDetails(null);
            setTimeout(() => {
              void fetchPreviewData(selectedTable.table_name);
              setShowTestDataModal(false);
              setTestDataResult(null);
            }, 1800);
          },
          onCancel: () => setConfirmDetails(null),
        });
        return;
      }
      if (res && "message" in res) setTestDataResult(res.message ?? null);
      setTimeout(() => {
        void fetchPreviewData(selectedTable.table_name);
        setShowTestDataModal(false);
        setTestDataResult(null);
      }, 1800);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setTestDataError(err.message ?? "注入测试数据失败，请检查主外键关联表是否已填充数据。");
    } finally {
      setGeneratingTestData(false);
    }
  };

  // AI ER Diagram alteration states
  const [aiAlterPrompt, setAiAlterPrompt] = useState("");
  const [aiAlterApiKey, setAiAlterApiKey] = useState("");
  const [aiAlterApiBase, setAiAlterApiBase] = useState("");
  const [aiAlterModelName, setAiAlterModelName] = useState("");
  const [aiAlterGenerating, setAiAlterGenerating] = useState(false);
  const [aiAlterResultDdl, setAiAlterResultDdl] = useState<string | null>(null);
  const [showAiAlterLlmConfig, setShowAiAlterLlmConfig] = useState(false);
  const [aiAlterError, setAiAlterError] = useState<string | null>(null);
  const [applyingAlter, setApplyingAlter] = useState(false);
  const [applySuccess, setApplySuccess] = useState(false);

  const handleAiAlterSubmit = async () => {
    if (!aiAlterPrompt.trim()) return;
    setAiAlterGenerating(true);
    setAiAlterError(null);
    setAiAlterResultDdl(null);
    try {
      const data = await api.generateSchemaAlteration({
        datasource_id: datasource.id,
        instruction: aiAlterPrompt,
        api_key: aiAlterApiKey || undefined,
        api_base: aiAlterApiBase || undefined,
        model: aiAlterModelName || undefined,
      });
      setAiAlterResultDdl(data.ddl);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setAiAlterError(err.message ?? "AI 批注式修改失败，请检查模型配置。");
    } finally {
      setAiAlterGenerating(false);
    }
  };

  const handleApplyAlter = async () => {
    if (!aiAlterResultDdl) return;
    setApplyingAlter(true);
    setAiAlterError(null);
    try {
      const res = await api.executeTableDesignDDL(datasource.id, aiAlterResultDdl);
      if (res && typeof res === "object" && "requires_confirmation" in res && res.requires_confirmation) {
        const ddl = aiAlterResultDdl;
        setConfirmDetails({
          confirm_token: res.confirm_token,
          impact_summary: res.impact_summary,
          expected_confirm_text: res.expected_confirm_text,
          onConfirm: async (text) => {
            await api.executeTableDesignDDL(datasource.id, ddl, { token: res.confirm_token, text });
            setConfirmDetails(null);
            setApplySuccess(true);
            setTimeout(() => {
              void fetchTables();
              void fetchERDiagram();
              setAiAlterResultDdl(null);
              setAiAlterPrompt("");
              setApplySuccess(false);
            }, 1500);
          },
          onCancel: () => setConfirmDetails(null),
        });
        return;
      }
      setApplySuccess(true);
      setTimeout(() => {
        void fetchTables();
        void fetchERDiagram();
        setAiAlterResultDdl(null);
        setAiAlterPrompt("");
        setApplySuccess(false);
      }, 1500);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setAiAlterError(err.message ?? "应用 DDL 变更失败，请检查 SQL 语法或外键冲突。");
    } finally {
      setApplyingAlter(false);
    }
  };

  const buildPreviewSql = (tableName: string) => `SELECT * FROM \`${tableName}\` LIMIT 100;`;

  const fetchPreviewData = async (tableName: string) => {
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const result = await api.executeSql(datasource.id, buildPreviewSql(tableName));
      setPreviewData(result);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      setPreviewError(error.message ?? "预览失败");
    } finally {
      setPreviewLoading(false);
    }
  };

  const fetchERDiagram = async () => {
    try {
      setErData(await api.getERDiagram(datasource.id));
    } catch (err) {
      console.error("ER load failed", err);
    }
  };

  const handleSelectTable = async (table: SchemaTable) => {
    setSelectedTable(table);
    setErFocusTable(table.table_name);
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

  const fetchTables = async (selectTableName?: string) => {
    try {
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
    }
  };

  const handleExecuteSuccess = (newTableName?: string) => {
    void fetchTables(newTableName);
    void fetchERDiagram();
    setViewTab("fields");
  };

  const previewSql = selectedTable ? buildPreviewSql(selectedTable.table_name) : "";

  const handleCopyPreviewSql = async () => {
    if (!previewSql) return;
    await navigator.clipboard.writeText(previewSql);
    setPreviewSqlCopied(true);
    window.setTimeout(() => setPreviewSqlCopied(false), 1400);
  };

  const handleOpenPreviewSql = () => {
    if (!previewSql || !selectedTable) return;
    onOpenSql?.(previewSql, `Preview ${selectedTable.table_name}`);
  };

  useEffect(() => {
    void fetchTables(selectedTableName ?? undefined);
    void fetchERDiagram();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasource.id]);

  useEffect(() => {
    if (!selectedTableName || tables.length === 0) return;
    const nextTable = tables.find((table) => table.table_name === selectedTableName);
    if (nextTable && nextTable.id !== selectedTable?.id) {
  // eslint-disable-next-line react-hooks/set-state-in-effect
      void handleSelectTable(nextTable);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTableName, tables]);

  useEffect(() => {
    if (initialViewTab) {
  // eslint-disable-next-line react-hooks/set-state-in-effect
      setViewTab(initialViewTab);
    }
  }, [initialViewTab]);

  useEffect(() => {
    if (viewTab === "data" && selectedTable) void fetchPreviewData(selectedTable.table_name);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewTab, selectedTable?.id]);

  const safeErData = useMemo<ERDiagramData>(
    () => ({
      nodes: Array.isArray(erData?.nodes) ? erData.nodes : [],
      edges: Array.isArray(erData?.edges) ? erData.edges : [],
    }),
    [erData],
  );

  return (
    <div
      className="animate-fade-in"
      style={{ display: "flex", flexDirection: "column", flex: 1, height: "100%", overflow: "hidden" }}
    >
      {/* Right Content */}
      <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", gap: 0 }}>
        {/* Header */}
        {!initialViewTab && (
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

            <div className="inline-flex bg-secondary rounded-sm p-0.5 gap-px">
              <button className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${viewTab === "fields" ? "active" : ""}`} onClick={() => setViewTab("fields")}>
                字段
              </button>
              <button className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${viewTab === "er" ? "active" : ""}`} onClick={() => setViewTab("er")}>
                关系图
              </button>
              <button className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${viewTab === "data" ? "active" : ""}`} onClick={() => setViewTab("data")}>
                <Eye size={13} />
                数据预览
              </button>
              <button className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${viewTab === "design" ? "active" : ""}`} onClick={() => setViewTab("design")}>
                设计草稿
              </button>
            </div>
          </div>
        )}

        {/* Content Area */}
        <div className="bg-card border border-border rounded-lg" style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
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
                      <div key={i} className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: 36, marginBottom: 4, borderRadius: 4 }} />
                    ))}
                  </div>
                ) : columns.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">未选中表</div>
                    <div className="empty-state-desc">从左侧选择一个表查看字段详情</div>
                  </div>
                ) : (
                  <table className="w-full border-collapse text-xs font-mono tabular-nums">
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
            <div style={{ flex: 1, overflow: "hidden", position: "relative", display: "flex", flexDirection: "column" }}>
              {safeErData.nodes.length > 0 ? (
                <>
                  {/* Toolbar */}
                  <div className="er-toolbar">
                    <div className="er-toolbar-group">
                      <button
                        className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${erViewMode === "focus" ? "active" : ""}`}
                        onClick={() => setErViewMode("focus")}
                      >
                        当前表关系
                      </button>
                      <button
                        className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${erViewMode === "module" ? "active" : ""}`}
                        onClick={() => setErViewMode("module")}
                      >
                        业务模块
                      </button>
                      <button
                        className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${erViewMode === "full" ? "active" : ""}`}
                        onClick={() => setErViewMode("full")}
                      >
                        全库关系
                      </button>
                    </div>

                    {erViewMode === "focus" && (
                      <>
                        <div className="er-toolbar-divider" />
                        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>深度</span>
                        <div className="er-toolbar-group">
                          <button
                            className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${erDepth === 1 ? "active" : ""}`}
                            onClick={() => setErDepth(1)}
                          >
                            1 跳
                          </button>
                          <button
                            className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground bg-transparent border-none rounded-sm cursor-pointer hover:text-foreground hover:bg-black/5 transition-colors ${erDepth === 2 ? "active" : ""}`}
                            onClick={() => setErDepth(2)}
                          >
                            2 跳
                          </button>
                        </div>
                      </>
                    )}

                    <div className="er-toolbar-divider" />
                    <label
                      style={{
                        fontSize: "0.72rem",
                        color: "var(--text-secondary)",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={erShowInferred}
                        onChange={(e) => setErShowInferred(e.target.checked)}
                        style={{ cursor: "pointer" }}
                      />
                      显示推断关系
                    </label>

                    <div className="er-legend">
                      <div className="er-legend-item">
                        <div className="er-legend-line" style={{ background: "var(--accent-teal)" }} />
                        <span>真实 FK</span>
                      </div>
                      <div className="er-legend-item">
                        <div
                          className="er-legend-line"
                          style={{
                            background: "#94A3B8",
                            backgroundImage: "repeating-linear-gradient(90deg, #94A3B8 0 4px, transparent 4px 8px)",
                          }}
                        />
                        <span>推断</span>
                      </div>
                    </div>
                  </div>

                  {/* Diagram + optional side panel */}
                  <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
                    <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
                      <ErrorBoundary title="ER 图渲染异常">
                        <ErDiagram
                          data={safeErData}
                          focusTable={erFocusTable}
                          depth={erDepth}
                          viewMode={erViewMode}
                          showInferred={erShowInferred}
                          onNodeClick={(tableName) => {
                            setErFocusTable(tableName);
                            // Also select in left panel
                            const found = tables.find((t) => t.table_name === tableName);
                            if (found) {
                              setSelectedTable(found);
                              setColumnsLoading(true);
                              api.listColumns(found.id).then(setColumns).catch(console.error).finally(() => setColumnsLoading(false));
                            }
                          }}
                        />
                      </ErrorBoundary>


                      {/* DDL Preview & Execution Drawer Overlay */}
                      {aiAlterResultDdl && (
                        <div
                          style={{
                            position: "absolute",
                            top: 0,
                            right: 0,
                            bottom: 0,
                            width: 380,
                            background: "#FFFFFF",
                            boxShadow: "-8px 0 32px rgba(0,0,0,0.15)",
                            borderLeft: "1px solid var(--border-light)",
                            display: "flex",
                            flexDirection: "column",
                            padding: 20,
                            zIndex: 20,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                            <h4 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 6 }}>
                              <CheckCircle2 size={16} style={{ color: "var(--accent-teal)" }} />
                              审核架构 DDL 变更
                            </h4>
                            <button
                              onClick={() => setAiAlterResultDdl(null)}
                              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                              style={{ padding: 4 }}
                              disabled={applyingAlter}
                            >
                              <X size={15} />
                            </button>
                          </div>

                          <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: 12 }}>
                            AI 根据您的批注生成了以下数据架构变更 SQL。请在应用前仔细审核。
                          </div>

                          <pre
                            style={{
                              flex: 1,
                              background: "var(--bg-secondary)",
                              color: "var(--text-primary)",
                              padding: 12,
                              borderRadius: 8,
                              fontSize: "0.78rem",
                              fontFamily: "'JetBrains Mono', monospace",
                              overflow: "auto",
                              border: "1px solid var(--border-light)",
                              marginBottom: 16,
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            {aiAlterResultDdl}
                          </pre>

                          {aiAlterResultDdl.toLowerCase().includes("drop") && (
                            <div
                              style={{
                                padding: 10,
                                borderRadius: 6,
                                background: "rgba(217, 119, 6, 0.08)",
                                border: "1px solid rgba(217, 119, 6, 0.2)",
                                color: "var(--accent-amber)",
                                fontSize: "0.76rem",
                                display: "flex",
                                gap: 6,
                                marginBottom: 16,
                              }}
                            >
                              <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                              <div>
                                <strong>高危操作警告：</strong>
                                DDL 中包含 DROP 指令，可能会永久删除表或列，请确保这是您的预期行为！
                              </div>
                            </div>
                          )}

                          {applySuccess ? (
                            <div
                              style={{
                                padding: "12px 16px",
                                borderRadius: 8,
                                background: "rgba(13, 115, 119, 0.08)",
                                border: "1px solid rgba(13, 115, 119, 0.2)",
                                color: "var(--accent-teal)",
                                fontSize: "0.82rem",
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                                marginBottom: 10,
                              }}
                            >
                              <CheckCircle2 size={16} />
                              <div>架构修改成功！正在重绘 ER 关系图...</div>
                            </div>
                          ) : null}

                          <div style={{ display: "flex", gap: 10 }}>
                            <button
                              onClick={() => setAiAlterResultDdl(null)}
                              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                              style={{ flex: 1 }}
                              disabled={applyingAlter}
                            >
                              取消
                            </button>
                            <button
                              onClick={handleApplyAlter}
                              disabled={applyingAlter || applySuccess}
                              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
                              style={{
                                flex: 2,
                                background: "linear-gradient(135deg, #0D7377, #14B8A6)",
                              }}
                            >
                              {applyingAlter ? (
                                <>
                                  <Loader2 size={14} className="animate-spin" />
                                  执行中...
                                </>
                              ) : (
                                "确认执行变更"
                              )}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Relationship side panel (focus mode) */}
                    {erViewMode === "focus" && erFocusTable && safeErData.nodes.length > 0 && (() => {
                      const focusNode = safeErData.nodes.find((n) => n.label === erFocusTable);
                      const filteredEdges = erShowInferred
                        ? safeErData.edges
                        : safeErData.edges.filter((e) => e.edge_type === "real");
                      const relatedEdges = filteredEdges.filter(
                        (e) => e.source === erFocusTable || e.target === erFocusTable,
                      );
                      const realEdges = relatedEdges.filter((e) => e.edge_type === "real");
                      const inferredEdges = relatedEdges.filter((e) => e.edge_type === "inferred");

                      return (
                        <div className="er-rel-panel">
                          <div className="er-rel-panel-header">
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}>
                              {erFocusTable}
                            </span>
                            关系
                          </div>
                          <div className="er-rel-panel-body">
                            {focusNode && (
                              <>
                                <div>
                                  <span className="er-module-badge">{focusNode.module_tag}</span>
                                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: 8 }}>
                                    {focusNode.fields.length} 个字段
                                  </span>
                                </div>
                                {focusNode.comment && (
                                  <div style={{ fontSize: "0.74rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                                    {focusNode.comment}
                                  </div>
                                )}
                              </>
                            )}

                            {realEdges.length > 0 && (
                              <div>
                                <div className="er-rel-section-title" style={{ marginBottom: 6 }}>
                                  真实外键 ({realEdges.length})
                                </div>
                                {realEdges.map((e) => (
                                  <div
                                    key={e.id}
                                    className="er-rel-item er-rel-item-real"
                                    onClick={() => {
                                      const other = e.source === erFocusTable ? e.target : e.source;
                                      setErFocusTable(other);
                                      const found = tables.find((t) => t.table_name === other);
                                      if (found) {
                                        setSelectedTable(found);
                                        setColumnsLoading(true);
                                        api.listColumns(found.id).then(setColumns).catch(console.error).finally(() => setColumnsLoading(false));
                                      }
                                    }}
                                  >
                                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem", fontWeight: 500 }}>
                                      {e.source === erFocusTable ? (
                                        <>{e.sourceHandle} → {e.target}.{e.targetHandle}</>
                                      ) : (
                                        <>{e.targetHandle} ← {e.source}.{e.sourceHandle}</>
                                      )}
                                    </div>
                                    <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: 2 }}>
                                      {e.source === erFocusTable ? `关联 → ${e.target}` : `← ${e.source} 引用`}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}

                            {inferredEdges.length > 0 && (
                              <div>
                                <div className="er-rel-section-title" style={{ marginBottom: 6 }}>
                                  推断关系 ({inferredEdges.length})
                                </div>
                                {inferredEdges.map((e) => (
                                  <div
                                    key={e.id}
                                    className="er-rel-item er-rel-item-inferred"
                                    onClick={() => {
                                      const other = e.source === erFocusTable ? e.target : e.source;
                                      setErFocusTable(other);
                                      const found = tables.find((t) => t.table_name === other);
                                      if (found) {
                                        setSelectedTable(found);
                                        setColumnsLoading(true);
                                        api.listColumns(found.id).then(setColumns).catch(console.error).finally(() => setColumnsLoading(false));
                                      }
                                    }}
                                  >
                                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem", fontWeight: 500, color: "#64748B" }}>
                                      {e.source === erFocusTable ? (
                                        <>{e.sourceHandle} → {e.target}.{e.targetHandle}</>
                                      ) : (
                                        <>{e.targetHandle} ← {e.source}.{e.sourceHandle}</>
                                      )}
                                    </div>
                                    <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: 2 }}>
                                      {e.source === erFocusTable ? `可能关联 → ${e.target}` : `← 可能被 ${e.source} 引用`}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}

                            {relatedEdges.length === 0 && (
                              <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                                当前表暂无关联关系
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                </>
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
                {previewLoading && <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-primary/10 text-primary">加载中...</span>}
                {previewError && <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-destructive/15 text-destructive">{previewError}</span>}

                <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <button
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors hover-lift"
                    style={{
                      padding: "3px 10px",
                      fontSize: "0.76rem",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      fontWeight: 600,
                    }}
                    onClick={() => void handleCopyPreviewSql()}
                    disabled={!previewSql}
                    title={previewSql || "请选择表"}
                  >
                    <Copy size={12} />
                    {previewSqlCopied ? "已复制" : "复制 SQL"}
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors hover-lift"
                    style={{
                      padding: "3px 10px",
                      fontSize: "0.76rem",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      fontWeight: 600,
                    }}
                    onClick={handleOpenPreviewSql}
                    disabled={!previewSql}
                  >
                    <Terminal size={12} />
                    打开到工作台
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors hover-lift"
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
                      <div key={i} className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: 32, marginBottom: 4, borderRadius: 4 }} />
                    ))}
                  </div>
                ) : previewData && previewData.rows.length > 0 ? (
                  <DataTable
                    columns={previewData.columns}
                    rows={previewData.rows}
                    tableName={selectedTable?.table_name}
                    databaseName={datasource.database_name}
                  />
                ) : previewData && previewData.rows.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-desc">该表暂无数据</div>
                    <button
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors hover-lift"
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
              <div
                style={{
                  borderTop: "1px solid var(--border-light)",
                  background: "var(--bg-secondary)",
                  padding: "8px 14px",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  minHeight: 38,
                  fontSize: "0.76rem",
                  color: "var(--text-secondary)",
                }}
              >
                <span style={{ fontWeight: 700, color: "var(--text-muted)" }}>当前 SQL</span>
                <code
                  className="text-mono"
                  style={{
                    flex: 1,
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    color: "var(--text-primary)",
                  }}
                  title={previewSql}
                >
                  {previewSql || "选择表后生成预览 SQL"}
                </code>
                <span style={{ color: "var(--text-muted)" }}>可复制或发送到 SQL 工作台继续编辑</span>
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
                className="bg-card border border-border rounded-lg animate-scale-up"
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
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
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
                          className={testDataRowCount === rows ? "inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors" : "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"}
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
                        className={testDataLanguage === "zh" ? "inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors" : "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"}
                        style={{ flex: 1, padding: "6px 0", fontSize: "0.82rem", borderColor: testDataLanguage === "zh" ? "var(--accent-indigo)" : undefined }}
                        onClick={() => setTestDataLanguage("zh")}
                        disabled={generatingTestData}
                      >
                        🇨🇳 中文 (姓名、手机、地址)
                      </button>
                      <button
                        className={testDataLanguage === "en" ? "inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors" : "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"}
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
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"
                    style={{ padding: "6px 16px", fontSize: "0.82rem" }}
                    onClick={() => setShowTestDataModal(false)}
                    disabled={generatingTestData}
                  >
                    取消
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
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
      <DangerConfirmDialog details={confirmDetails} />
    </div>
  );
};
