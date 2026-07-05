import { Info, Sparkles, X } from "lucide-react";
import type { WorkspaceTab } from "../../types/workspace";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { getStoredApiConfig } from "../../lib/llmConfig";
import "./ContextDrawer.css";

interface ContextDrawerProps {
  open: boolean;
  type: "ai-suggest" | "props";
  activeTab: WorkspaceTab;
  onClose: () => void;
  onGenerateIndexSql: () => void;
}

export function ContextDrawer({ open, type, activeTab, onClose, onGenerateIndexSql }: ContextDrawerProps) {
  const contextTables = useWorkspaceStore((s) => s.contextTables);

  return (
    <section className={`context-drawer ${open ? "is-open" : "is-closed"}`}>
      <div className="context-drawer__surface">
        <div className="context-drawer__header">
          <span className="context-drawer__title">
            {type === "ai-suggest" && <><Sparkles size={13} className="context-drawer__icon context-drawer__icon--suggest" /> AI 建议</>}
            {type === "props" && <><Info size={13} className="context-drawer__icon context-drawer__icon--props" /> 对象属性</>}
          </span>
          <button type="button" className="context-drawer__close" onClick={onClose} aria-label="关闭抽屉">
            <X size={12} />
          </button>
        </div>

        <div className="context-drawer__body">
          {type === "ai-suggest" ? <AiSuggest onGenerateIndexSql={onGenerateIndexSql} /> : <PropsPanel activeTab={activeTab} contextTables={contextTables} />}
        </div>
      </div>
    </section>
  );
}

function AiSuggest({ onGenerateIndexSql }: { onGenerateIndexSql: () => void }) {
  // Keep onGenerateIndexSql to satisfy any potential callbacks, but display a premium empty state instead of hardcoded demo data
  void onGenerateIndexSql;
  return (
    <div className="context-drawer__stack">
      <span className="context-drawer__eyebrow">数据库诊断建议</span>
      <div className="context-drawer__empty">
        <Sparkles size={16} className="context-drawer__empty-icon" />
        <span>暂无诊断建议。在 SQL 控制台执行查询或与智能助手交互时，相关的性能优化建议会呈现在此处。</span>
      </div>
    </div>
  );
}

function PropsPanel({ activeTab, contextTables }: { activeTab: WorkspaceTab; contextTables: string[] }) {
  const tables = useDatasourceStore((s) => s.tables);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDs = datasources.find((ds) => ds.id === activeDatasourceId) ?? datasources[0] ?? null;
  const apiConfig = getStoredApiConfig();

  if (activeTab.type === "table") {
    const tableId = activeTab.tableId || "";
    const table = tables.find((t) => t.table_name === tableId);

    const rows = [
      ["物理表名:", tableId],
      ["表类型:", table?.table_type || "BASE TABLE"],
      ["注释描述:", table?.table_comment || "—"],
    ];

    if (table) {
      if (table.row_count_estimate !== undefined && table.row_count_estimate !== null) {
        rows.push(["预估行数:", `${table.row_count_estimate.toLocaleString()} 行`]);
      }
      rows.push(["AI 描述:", table.ai_description || "—"]);
      rows.push(["主题域:", table.subject_area || "—"]);
      rows.push(["业务术语:", table.business_terms || "—"]);
      rows.push(["语义标签:", table.semantic_tags || "—"]);
      if (table.ai_confidence !== undefined && table.ai_confidence !== null) {
        rows.push(["AI 置信度/打分:", `${(table.ai_confidence * 100).toFixed(1)}%`]);
      }
    } else {
      rows.push(["预估行数:", "—"]);
      rows.push(["存储引擎:", "—"]);
    }
    return <InfoList rows={rows} />;
  }
  if (activeTab.type === "sql") {
    return (
      <InfoList
        rows={[
          ["连接名称:", activeDs ? activeDs.name : "—"],
          ["激活数据库:", activeDs ? activeDs.database_name : "—"],
          ["连接主机:", activeDs?.host ? `${activeDs.host}:${activeDs.port}` : "—"],
          ["事务模式:", "AUTO-COMMIT"],
        ]}
      />
    );
  }
  return (
    <InfoList
      rows={[
        ["上下文关联:", `${contextTables.length} 张表`],
        ["激活大模型:", apiConfig?.modelName || "—"],
        ["会话ID:", activeTab.conversationId || "—"],
      ]}
    />
  );
}

function InfoList({ rows }: { rows: string[][] }) {
  return (
    <div className="context-drawer__info-list">
      <span className="context-drawer__eyebrow">当前对象物理与 AI 属性</span>
      {rows.map(([label, value]) => {
        const isLong = value.length > 25 || label.includes("描述");
        return (
          <div key={label} className={`context-drawer__info-row ${isLong ? "context-drawer__info-row--long" : ""}`}>
            <span className="context-drawer__info-label">{label}</span>
            <span className="context-drawer__info-value">{value}</span>
          </div>
        );
      })}
    </div>
  );
}
