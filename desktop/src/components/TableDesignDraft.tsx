import { useState } from "react";
import { AlertTriangle, Copy, Plus, Trash2, Wand2, Play, CheckCircle2, ShieldAlert, X, FolderOpen, Save, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import type { TableDesignDDLResponse, DataSource } from "../lib/api";

type DraftColumn = {
  id: string;
  name: string;
  type: string;
  nullable: boolean;
  default_value: string;
  primary_key: boolean;
  auto_increment: boolean;
  comment: string;
};

type DraftIndex = {
  id: string;
  name: string;
  columnsText: string;
  unique: boolean;
};

const newId = () => Math.random().toString(36).slice(2);

const defaultColumns = (): DraftColumn[] => [
  {
    id: newId(),
    name: "id",
    type: "BIGINT",
    nullable: false,
    default_value: "",
    primary_key: true,
    auto_increment: true,
    comment: "主键",
  },
  {
    id: newId(),
    name: "name",
    type: "VARCHAR(255)",
    nullable: false,
    default_value: "",
    primary_key: false,
    auto_increment: false,
    comment: "名称",
  },
];

interface TableDesignDraftProps {
  datasource: DataSource;
  onExecuteSuccess: (newTableName?: string) => void;
}

export function TableDesignDraft({ datasource, onExecuteSuccess }: TableDesignDraftProps) {
  const [tableName, setTableName] = useState("new_business_table");
  const [tableComment, setTableComment] = useState("业务表");
  const [columns, setColumns] = useState<DraftColumn[]>(defaultColumns);
  const [indexes, setIndexes] = useState<DraftIndex[]>([]);
  const [result, setResult] = useState<TableDesignDDLResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  // DDL execution and double-confirmation states
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [confirmTableNameInput, setConfirmTableNameInput] = useState("");
  const [executing, setExecuting] = useState(false);
  const [executionSuccess, setExecutionSuccess] = useState(false);
  const [executionError, setExecutionError] = useState<string | null>(null);

  // Table Design Draft Metastore CRUD states
  const [currentDraftId, setCurrentDraftId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDraftsModalOpen, setIsDraftsModalOpen] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [draftsList, setDraftsList] = useState<any[]>([]);
  const [loadingDrafts, setLoadingDrafts] = useState(false);

  // AI Design States
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiApiKey, setAiApiKey] = useState("");
  const [aiApiBase, setAiApiBase] = useState("");
  const [aiModelName, setAiModelName] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [isLlmConfigOpen, setIsLlmConfigOpen] = useState(false);

  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) return;
    setAiGenerating(true);
    setError(null);
    try {
      const data = await api.generateTableDesignAi(aiPrompt, {
        apiKey: aiApiKey || undefined,
        apiBase: aiApiBase || undefined,
        model: aiModelName || undefined,
      });

      // Load tableName and tableComment
      setTableName(data.table_name);
      setTableComment(data.table_comment);

      // Load columns
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const loadedCols = (data.columns || []).map((col: any) => ({
        id: newId(),
        name: col.name,
        type: col.type,
        nullable: col.nullable !== false,
        default_value: col.default_value || "",
        primary_key: !!col.primary_key,
        auto_increment: !!col.auto_increment,
        comment: col.comment || "",
      }));
      setColumns(loadedCols.length > 0 ? loadedCols : defaultColumns());

      // Load indexes
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const loadedIdxs = (data.indexes || []).map((idx: any) => ({
        id: newId(),
        name: idx.name,
        columnsText: (idx.columns || []).join(", "),
        unique: !!idx.unique,
      }));
      setIndexes(loadedIdxs);

      // Clear any previous DDL result
      setResult(null);

      // Notify the user
      alert("✨ AI 智能设计结构已成功载入！");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setError("AI 表结构生成失败: " + (err.message || err));
    } finally {
      setAiGenerating(false);
    }
  };

  const fetchDrafts = async () => {
    if (!datasource.project_id) return;
    setLoadingDrafts(true);
    try {
      const data = await api.listTableDesignDrafts(datasource.project_id);
      setDraftsList(data);
    } catch (err) {
      console.error("Failed to load drafts list:", err);
    } finally {
      setLoadingDrafts(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!datasource.project_id) return;
    setIsSaving(true);
    try {
      const draft = await api.saveTableDesignDraft({
        project_id: datasource.project_id,
        draft_id: currentDraftId || undefined,
        table_name: tableName,
        table_comment: tableComment,
        columns: columns.map((col) => ({
          name: col.name,
          type: col.type,
          nullable: col.nullable,
          default_value: col.default_value.trim() || null,
          primary_key: col.primary_key,
          auto_increment: col.auto_increment,
          comment: col.comment.trim() || null,
        })),
        indexes: indexes.map((idx) => ({
          name: idx.name.trim() || null,
          columns: idx.columnsText
            .split(",")
            .map((c) => c.trim())
            .filter(Boolean),
          unique: idx.unique,
        })),
      });
      setCurrentDraftId(draft.id);
      alert("草稿保存成功！");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      alert("保存草稿失败: " + (err.message || err));
    } finally {
      setIsSaving(false);
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleLoadDraft = (draft: any) => {
    setCurrentDraftId(draft.id);
    setTableName(draft.table_name);
    setTableComment(draft.table_comment || "");
    
    // Transform columns back to DraftColumn format
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const loadedCols = (draft.columns || []).map((col: any) => ({
      id: newId(),
      name: col.name || "",
      type: col.type || "VARCHAR(255)",
      nullable: col.nullable !== false,
      default_value: col.default_value || "",
      primary_key: !!col.primary_key,
      auto_increment: !!col.auto_increment,
      comment: col.comment || "",
    }));
    setColumns(loadedCols.length > 0 ? loadedCols : defaultColumns());

    // Transform indexes back to DraftIndex format
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const loadedIdxs = (draft.indexes || []).map((idx: any) => ({
      id: newId(),
      name: idx.name || "",
      columnsText: (idx.columns || []).join(", "),
      unique: !!idx.unique,
    }));
    setIndexes(loadedIdxs);
    setResult(null);
    setIsDraftsModalOpen(false);
  };

  const handleDeleteDraft = async (e: React.MouseEvent, draftId: string) => {
    e.stopPropagation();
    if (!confirm("确定要删除此草稿吗？")) return;
    try {
      await api.deleteTableDesignDraft(draftId);
      if (currentDraftId === draftId) {
        setCurrentDraftId(null);
      }
      void fetchDrafts();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      alert("删除草稿失败: " + (err.message || err));
    }
  };

  const handleNewDraft = () => {
    if (confirm("确定要重置当前草稿，开始新的设计吗？")) {
      setCurrentDraftId(null);
      setTableName("new_business_table");
      setTableComment("业务表");
      setColumns(defaultColumns());
      setIndexes([]);
      setResult(null);
    }
  };

  const updateColumn = (id: string, patch: Partial<DraftColumn>) => {
    setColumns((items) =>
      items.map((item) => {
        if (item.id !== id) return item;
        const next = { ...item, ...patch };
        if (patch.primary_key === true) next.nullable = false;
        if (patch.auto_increment === true) {
          next.primary_key = true;
          next.nullable = false;
        }
        return next;
      }),
    );
  };

  const removeColumn = (id: string) => {
    setColumns((items) => items.filter((item) => item.id !== id));
  };

  const addColumn = () => {
    setColumns((items) => [
      ...items,
      {
        id: newId(),
        name: "",
        type: "VARCHAR(255)",
        nullable: true,
        default_value: "",
        primary_key: false,
        auto_increment: false,
        comment: "",
      },
    ]);
  };

  const updateIndex = (id: string, patch: Partial<DraftIndex>) => {
    setIndexes((items) => items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const addIndex = () => {
    setIndexes((items) => [
      ...items,
      {
        id: newId(),
        name: "",
        columnsText: "",
        unique: false,
      },
    ]);
  };

  const removeIndex = (id: string) => {
    setIndexes((items) => items.filter((item) => item.id !== id));
  };

  const generateDDL = async () => {
    setGenerating(true);
    setError(null);
    try {
      const generated = await api.generateCreateTableDDL({
        table_name: tableName,
        table_comment: tableComment,
        engine: "InnoDB",
        charset: "utf8mb4",
        collation: "utf8mb4_0900_ai_ci",
        columns: columns.map((column) => ({
          name: column.name,
          type: column.type,
          nullable: column.nullable,
          default_value: column.default_value.trim() || null,
          primary_key: column.primary_key,
          auto_increment: column.auto_increment,
          comment: column.comment.trim() || null,
        })),
        indexes: indexes
          .map((index) => ({
            name: index.name.trim() || null,
            columns: index.columnsText
              .split(",")
              .map((name) => name.trim())
              .filter(Boolean),
            unique: index.unique,
          }))
          .filter((index) => index.columns.length > 0),
      });
      setResult(generated);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setError(err.message ?? "生成 DDL 失败");
      setResult(null);
    } finally {
      setGenerating(false);
    }
  };

  const copyDDL = () => {
    if (!result?.ddl) return;
    void navigator.clipboard?.writeText(result.ddl);
  };

  const handleExecuteDDL = async () => {
    if (!result?.ddl) return;
    setExecuting(true);
    setExecutionError(null);
    try {
      const response = await api.executeTableDesignDDL(datasource.id, result.ddl);
      if (response.success) {
        setExecutionSuccess(true);
        setTimeout(() => {
          setIsConfirmOpen(false);
          setExecutionSuccess(false);
          setConfirmTableNameInput("");
          onExecuteSuccess(tableName);
        }, 1500);
      } else {
        throw new Error(response.message || "执行建表 SQL 失败");
      }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setExecutionError(err.message ?? "执行 DDL 遇到未知错误");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.15fr) minmax(360px, 0.85fr)", height: "100%", overflow: "hidden" }}>
      <div style={{ overflow: "auto", padding: 18, borderRight: "1px solid var(--border-light)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 16 }}>
          <div>
            <h4 style={{ margin: 0, fontSize: "1rem", fontWeight: 700 }}>
              表结构设计草稿 {currentDraftId && <span style={{ fontSize: "0.78rem", fontWeight: 400, color: "var(--accent-indigo)", marginLeft: 6 }}>(已载入草稿)</span>}
            </h4>
            <p style={{ margin: "6px 0 0", color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.6 }}>
              设计项目数据库表结构，支持持久化为草稿或直接生成 MySQL DDL。
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={handleNewDraft} style={{ padding: "6px 10px", fontSize: "0.78rem", display: "flex", alignItems: "center", gap: 4 }}>
              <Plus size={13} />
              新建
            </button>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={() => { void fetchDrafts(); setIsDraftsModalOpen(true); }} style={{ padding: "6px 10px", fontSize: "0.78rem", display: "flex", alignItems: "center", gap: 4 }}>
              <FolderOpen size={13} />
              加载草稿
            </button>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={() => void handleSaveDraft()} disabled={isSaving} style={{ padding: "6px 10px", fontSize: "0.78rem", display: "flex", alignItems: "center", gap: 4 }}>
              {isSaving ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={13} />}
              {currentDraftId ? "更新草稿" : "保存草稿"}
            </button>
            <button className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors btn-sm" onClick={() => void generateDDL()} disabled={generating} style={{ padding: "6px 12px", fontSize: "0.78rem", display: "flex", alignItems: "center", gap: 4, border: "none" }}>
              <Wand2 size={13} />
              {generating ? "生成中..." : "生成 DDL"}
            </button>
          </div>
        </div>

        {/* AI Table Design Intelligent Generation Panel */}
        <div 
          style={{ 
            padding: 16, 
            marginBottom: 14, 
            background: "linear-gradient(135deg, rgba(79, 70, 229, 0.04) 0%, rgba(147, 51, 234, 0.04) 100%)",
            border: "1px solid rgba(79, 70, 229, 0.15)",
            borderRadius: 12,
            boxShadow: "inset 0 1px 2px rgba(255, 255, 255, 0.05)",
            display: "flex",
            flexDirection: "column",
            gap: 12
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Wand2 size={15} style={{ color: "var(--accent-indigo)" }} />
              <strong style={{ fontSize: "0.85rem", color: "var(--text-primary)", fontWeight: 700 }}>AI 智能表结构生成</strong>
            </div>
            <button
              style={{
                background: "none",
                border: "none",
                color: "var(--text-muted)",
                cursor: "pointer",
                padding: "2px 8px",
                fontSize: "0.72rem",
                display: "flex",
                alignItems: "center",
                gap: 4
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = "var(--text-primary)"}
              onMouseLeave={(e) => e.currentTarget.style.color = "var(--text-muted)"}
              onClick={() => setIsLlmConfigOpen(!isLlmConfigOpen)}
            >
              {isLlmConfigOpen ? "隐藏 AI 设置" : "展开 AI 设置"}
            </button>
          </div>

          {/* AI LLM Settings Config (apiKey, apiBase, modelName) */}
          {isLlmConfigOpen && (
            <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1.5fr 1fr", gap: 10, padding: 12, background: "var(--bg-primary)", border: "1px solid var(--border-light)", borderRadius: 8 }}>
              <label style={{ display: "grid", gap: 4 }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>OpenAI API Key (留空默认启用离线 Heuristic 模型)</span>
                <input
                  type="password"
                  placeholder="sk-..."
                  className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  value={aiApiKey}
                  onChange={(e) => setAiApiKey(e.target.value)}
                  style={{ fontSize: "0.74rem" }}
                />
              </label>
              <label style={{ display: "grid", gap: 4 }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>API Base URL</span>
                <input
                  type="text"
                  placeholder="https://api.openai.com/v1"
                  className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  value={aiApiBase}
                  onChange={(e) => setAiApiBase(e.target.value)}
                  style={{ fontSize: "0.74rem" }}
                />
              </label>
              <label style={{ display: "grid", gap: 4 }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Model</span>
                <input
                  type="text"
                  placeholder="gpt-4o-mini"
                  className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  value={aiModelName}
                  onChange={(e) => setAiModelName(e.target.value)}
                  style={{ fontSize: "0.74rem" }}
                />
              </label>
            </div>
          )}

          <div style={{ display: "flex", gap: 10 }}>
            <input
              type="text"
              placeholder="输入你的建表设想，例如：‘设计一张用户表，包含用户名、邮箱、加密密码，最后登录时间和状态，并加唯一索引’"
              className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void handleAiGenerate(); }}
              style={{ flex: 1, fontSize: "0.82rem" }}
              disabled={aiGenerating}
            />
            <button
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
              onClick={() => void handleAiGenerate()}
              disabled={aiGenerating || !aiPrompt.trim()}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 16px",
                fontSize: "0.82rem",
                background: "linear-gradient(135deg, var(--accent-indigo) 0%, #7c3aed 100%)",
                border: "none",
                borderRadius: 8,
                boxShadow: "0 4px 10px rgba(79, 70, 229, 0.15)",
                color: "#ffffff",
                cursor: "pointer"
              }}
            >
              {aiGenerating ? (
                <>
                  <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
                  <span>AI 正在思考...</span>
                </>
              ) : (
                <>
                  <Wand2 size={14} />
                  <span>智能设计</span>
                </>
              )}
            </button>
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg" style={{ padding: 14, marginBottom: 14 }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 12 }}>
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>表名</span>
              <input className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring" value={tableName} onChange={(event) => setTableName(event.target.value)} />
            </label>
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>表注释</span>
              <input className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring" value={tableComment} onChange={(event) => setTableComment(event.target.value)} />
            </label>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h5 style={{ margin: 0, fontSize: "0.9rem", fontWeight: 700 }}>字段</h5>
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={addColumn}>
            <Plus size={13} />
            添加字段
          </button>
        </div>

        <div style={{ overflowX: "auto", marginBottom: 18 }}>
          <table className="w-full border-collapse text-xs font-mono tabular-nums">
            <thead>
              <tr>
                <th>字段名</th>
                <th>类型</th>
                <th>默认值</th>
                <th>注释</th>
                <th>约束</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {columns.map((column) => (
                <tr key={column.id}>
                  <td>
                    <input
                      className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      value={column.name}
                      placeholder="column_name"
                      onChange={(event) => updateColumn(column.id, { name: event.target.value })}
                      style={{ minWidth: 120 }}
                    />
                  </td>
                  <td>
                    <input
                      className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring text-mono"
                      value={column.type}
                      placeholder="VARCHAR(255)"
                      onChange={(event) => updateColumn(column.id, { type: event.target.value })}
                      style={{ minWidth: 128 }}
                    />
                  </td>
                  <td>
                    <input
                      className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      value={column.default_value}
                      placeholder="可空"
                      onChange={(event) => updateColumn(column.id, { default_value: event.target.value })}
                      style={{ minWidth: 100 }}
                    />
                  </td>
                  <td>
                    <input
                      className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      value={column.comment}
                      placeholder="字段说明"
                      onChange={(event) => updateColumn(column.id, { comment: event.target.value })}
                      style={{ minWidth: 130 }}
                    />
                  </td>
                  <td>
                    <div style={{ display: "grid", gap: 5, minWidth: 122, fontSize: "0.74rem", color: "var(--text-secondary)" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: 5 }}>
                        <input
                          type="checkbox"
                          checked={column.primary_key}
                          onChange={(event) => updateColumn(column.id, { primary_key: event.target.checked })}
                        />
                        主键
                      </label>
                      <label style={{ display: "flex", alignItems: "center", gap: 5 }}>
                        <input
                          type="checkbox"
                          checked={column.auto_increment}
                          onChange={(event) => updateColumn(column.id, { auto_increment: event.target.checked })}
                        />
                        自增
                      </label>
                      <label style={{ display: "flex", alignItems: "center", gap: 5 }}>
                        <input
                          type="checkbox"
                          checked={column.nullable}
                          disabled={column.primary_key || column.auto_increment}
                          onChange={(event) => updateColumn(column.id, { nullable: event.target.checked })}
                        />
                        可空
                      </label>
                    </div>
                  </td>
                  <td>
                    <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={() => removeColumn(column.id)} disabled={columns.length <= 1}>
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h5 style={{ margin: 0, fontSize: "0.9rem", fontWeight: 700 }}>索引</h5>
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={addIndex}>
            <Plus size={13} />
            添加索引
          </button>
        </div>

        {indexes.length === 0 ? (
          <div style={{ padding: 14, border: "1px dashed var(--border-light)", borderRadius: 10, color: "var(--text-muted)", fontSize: "0.82rem" }}>
            暂无二级索引。主键会根据字段勾选自动生成。
          </div>
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {indexes.map((index) => (
              <div key={index.id} className="bg-card border border-border rounded-lg" style={{ padding: 12, display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: 10, alignItems: "center" }}>
                <input
                  className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  value={index.name}
                  placeholder="索引名，可留空自动生成"
                  onChange={(event) => updateIndex(index.id, { name: event.target.value })}
                />
                <input
                  className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  value={index.columnsText}
                  placeholder="字段名，多个用逗号分隔"
                  onChange={(event) => updateIndex(index.id, { columnsText: event.target.value })}
                />
                <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: "0.76rem", color: "var(--text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={index.unique}
                    onChange={(event) => updateIndex(index.id, { unique: event.target.checked })}
                  />
                  唯一
                </label>
                <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={() => removeIndex(index.id)}>
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ overflow: "auto", padding: 18, background: "var(--bg-secondary)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>DDL 预览</h4>
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors btn-sm" onClick={copyDDL} disabled={!result?.ddl}>
            <Copy size={13} />
            复制
          </button>
        </div>

        {error && (
          <div className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-secondary text-secondary-foreground inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-destructive/15 text-destructive" style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 10, whiteSpace: "normal" }}>
            <AlertTriangle size={14} />
            {error}
          </div>
        )}

        {result?.warnings.map((warning) => (
          <div key={warning} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-secondary text-secondary-foreground inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-warning/15 text-warning" style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8, whiteSpace: "normal" }}>
            <AlertTriangle size={14} />
            {warning}
          </div>
        ))}

        <textarea
          className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring text-mono"
          readOnly
          value={result?.ddl ?? "点击「生成 DDL」后，这里会出现 CREATE TABLE 草稿。"}
          style={{
            width: "100%",
            minHeight: 360,
            resize: "vertical",
            fontSize: "0.78rem",
            lineHeight: 1.65,
            color: result?.ddl ? "var(--text-primary)" : "var(--text-muted)",
          }}
        />

        <div style={{ marginTop: 12, color: "var(--text-muted)", fontSize: "0.78rem", lineHeight: 1.6 }}>
          当前 MVP 只允许常见 MySQL 类型、ASCII 标识符、InnoDB、utf8mb4。这个限制是有意的：先保证生成结果可解释、可审计，再逐步开放更多语法。
        </div>

        {result?.ddl && (
          <div style={{ marginTop: 16 }}>
            <button
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
              style={{
                width: "100%",
                padding: "10px 14px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                background: datasource.is_read_only ? "var(--bg-disabled)" : "var(--accent-indigo)",
                cursor: datasource.is_read_only ? "not-allowed" : "pointer"
              }}
              disabled={!!datasource.is_read_only}
              onClick={() => setIsConfirmOpen(true)}
            >
              <Play size={14} />
              执行 DDL (建表)
            </button>
            {datasource.is_read_only && (
              <p style={{ margin: "6px 0 0", color: "var(--accent-amber)", fontSize: "0.75rem", textAlign: "center" }}>
                ⚠️ 当前数据源处于只读模式，禁止执行 DDL 写操作
              </p>
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from { transform: translateY(12px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>

      {isConfirmOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(15, 17, 23, 0.7)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: 24,
            animation: "fadeIn 0.2s ease",
          }}
        >
          <div
            className="bg-card border border-border rounded-lg"
            style={{
              width: "100%",
              maxWidth: 580,
              maxHeight: "90vh",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              border: "1px solid var(--border-light)",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2)",
              animation: "slideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid var(--border-light)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: datasource.env === "prod" ? "rgba(239, 68, 68, 0.08)" : "var(--bg-secondary)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {datasource.env === "prod" ? (
                  <ShieldAlert size={20} style={{ color: "var(--accent-red)" }} />
                ) : (
                  <Play size={18} style={{ color: "var(--accent-indigo)" }} />
                )}
                <h4 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700 }}>
                  确认执行 DDL 建表
                </h4>
              </div>
              <button
                style={{
                  border: "none",
                  background: "transparent",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  padding: 4,
                  display: "flex",
                  alignItems: "center",
                  borderRadius: "50%",
                  transition: "background 0.1s"
                }}
                onClick={() => {
                  setIsConfirmOpen(false);
                  setExecutionError(null);
                  setConfirmTableNameInput("");
                }}
                disabled={executing}
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: 20, overflowY: "auto", flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Target info */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, 1fr)",
                  gap: 12,
                  padding: 14,
                  background: "var(--bg-secondary)",
                  borderRadius: 8,
                  fontSize: "0.82rem",
                  border: "1px solid var(--border-light)",
                }}
              >
                <div>
                  <span style={{ color: "var(--text-muted)" }}>数据源:</span>{" "}
                  <strong style={{ color: "var(--text-primary)" }}>{datasource.name}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>数据库:</span>{" "}
                  <strong style={{ color: "var(--text-primary)" }}>{datasource.database_name}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>目标环境:</span>{" "}
                  <span
                    className={`tag ${
                      datasource.env === "prod"
                        ? "tag-red"
                        : datasource.env === "dev"
                        ? "tag-teal"
                        : "tag-indigo"
                    }`}
                    style={{ fontSize: "0.72rem", padding: "1px 6px" }}
                  >
                    {(datasource.env || "dev").toUpperCase()}
                  </span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>新表名:</span>{" "}
                  <code style={{ color: "var(--accent-teal)" }}>{tableName}</code>
                </div>
              </div>

              {/* Warnings / Double Confirm for PROD */}
              {datasource.env === "prod" && (
                <div
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-secondary text-secondary-foreground inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-destructive/15 text-destructive"
                  style={{
                    padding: 12,
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    fontSize: "0.78rem",
                    whiteSpace: "normal",
                    borderRadius: 8,
                    border: "1px solid rgba(239, 68, 68, 0.2)",
                  }}
                >
                  <div style={{ display: "flex", gap: 6, alignItems: "center", fontWeight: 700, color: "var(--accent-red)" }}>
                    <ShieldAlert size={15} />
                    ⚠️ 生产环境执行警告
                  </div>
                  <div style={{ color: "var(--text-primary)", lineHeight: 1.5 }}>
                    您正在对 <strong>生产环境 (PROD)</strong> 进行 DDL 结构变更。这可能对线上活跃流量和业务造成影响。请确保表结构经过严格评审！
                  </div>
                </div>
              )}

              {/* SQL Preview inside Modal */}
              <div>
                <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                  即将执行的 SQL 语句:
                </span>
                <pre
                  style={{
                    margin: 0,
                    padding: 12,
                    background: "var(--bg-active)",
                    borderRadius: 6,
                    border: "1px solid var(--border-light)",
                    fontSize: "0.75rem",
                    maxHeight: 180,
                    overflowY: "auto",
                    color: "var(--text-primary)",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                    fontFamily: "monospace",
                    lineHeight: 1.5,
                  }}
                >
                  {result?.ddl}
                </pre>
              </div>

              {/* Error messages if any */}
              {executionError && (
                <div className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-secondary text-secondary-foreground inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm bg-destructive/15 text-destructive" style={{ display: "flex", gap: 6, alignItems: "center", whiteSpace: "normal" }}>
                  <AlertTriangle size={14} />
                  {executionError}
                </div>
              )}

              {/* PROD Verification Input */}
              {datasource.env === "prod" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    请输入表名 <code style={{ color: "var(--accent-red)", fontWeight: 600 }}>{tableName}</code> 以确认执行:
                  </label>
                  <input
                    className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    style={{ border: "1px solid var(--border-light)" }}
                    placeholder={tableName}
                    value={confirmTableNameInput}
                    onChange={(e) => setConfirmTableNameInput(e.target.value)}
                    disabled={executing || executionSuccess}
                  />
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: "12px 20px",
                borderTop: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
                display: "flex",
                justifyContent: "flex-end",
                gap: 10,
              }}
            >
              <button
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"
                onClick={() => {
                  setIsConfirmOpen(false);
                  setExecutionError(null);
                  setConfirmTableNameInput("");
                }}
                disabled={executing}
              >
                取消
              </button>
              <button
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
                style={{
                  background: datasource.env === "prod" ? "var(--accent-red)" : "var(--accent-indigo)",
                  color: "white",
                  opacity:
                    executing ||
                    (datasource.env === "prod" && confirmTableNameInput !== tableName)
                      ? 0.6
                      : 1,
                  cursor:
                    executing ||
                    (datasource.env === "prod" && confirmTableNameInput !== tableName)
                      ? "not-allowed"
                      : "pointer",
                }}
                disabled={
                  executing ||
                  (datasource.env === "prod" && confirmTableNameInput !== tableName)
                }
                onClick={handleExecuteDDL}
              >
                {executing ? (
                  "正在执行并同步..."
                ) : executionSuccess ? (
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <CheckCircle2 size={14} /> 执行成功
                  </span>
                ) : (
                  "确认执行"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Drafts List Picker Modal */}
      {isDraftsModalOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.4)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: 20,
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: 600,
              background: "var(--bg-primary)",
              borderRadius: 12,
              border: "1px solid var(--border-light)",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              maxHeight: "80vh",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid var(--border-light)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "var(--bg-secondary)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <FolderOpen size={16} style={{ color: "var(--accent-indigo)" }} />
                <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>载入设计草稿</h4>
              </div>
              <button
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  padding: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
                onClick={() => setIsDraftsModalOpen(false)}
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Content */}
            <div style={{ padding: 20, overflowY: "auto", flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
              {loadingDrafts ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 0", gap: 10 }}>
                  <Loader2 size={24} style={{ color: "var(--accent-indigo)", animation: "spin 1s linear infinite" }} />
                  <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>正在加载草稿列表...</span>
                </div>
              ) : draftsList.length === 0 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 0", gap: 8 }}>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>暂无已保存的设计草稿</div>
                  <button className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors btn-sm" onClick={() => setIsDraftsModalOpen(false)} style={{ fontSize: "0.78rem" }}>
                    开始全新设计
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {draftsList.map((draft) => (
                    <div
                      key={draft.id}
                      onClick={() => handleLoadDraft(draft)}
                      style={{
                        padding: "12px 16px",
                        borderRadius: 8,
                        border: currentDraftId === draft.id ? "1.5px solid var(--accent-indigo)" : "1px solid var(--border-light)",
                        background: currentDraftId === draft.id ? "rgba(79, 70, 229, 0.03)" : "var(--bg-active)",
                        cursor: "pointer",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        transition: "all 0.2s ease",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.border = currentDraftId === draft.id ? "1.5px solid var(--accent-indigo)" : "1px solid rgba(79, 70, 229, 0.4)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.border = currentDraftId === draft.id ? "1.5px solid var(--accent-indigo)" : "1px solid var(--border-light)";
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <strong style={{ fontSize: "0.86rem", color: "var(--text-primary)" }}>{draft.table_name}</strong>
                          {draft.table_comment && (
                            <span style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>({draft.table_comment})</span>
                          )}
                        </div>
                        <div style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                          包含 {draft.columns?.length || 0} 个字段 · {draft.indexes?.length || 0} 个索引 · 最近更新 {new Date(draft.updated_at).toLocaleString()}
                        </div>
                      </div>
                      <button
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-muted)",
                          cursor: "pointer",
                          padding: 6,
                          borderRadius: 4,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          transition: "all 0.2s",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = "var(--accent-red)";
                          e.currentTarget.style.background = "rgba(239, 68, 68, 0.08)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = "var(--text-muted)";
                          e.currentTarget.style.background = "none";
                        }}
                        onClick={(e) => handleDeleteDraft(e, draft.id)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: "12px 20px",
                borderTop: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
                display: "flex",
                justifyContent: "flex-end",
              }}
            >
              <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors" onClick={() => setIsDraftsModalOpen(false)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
