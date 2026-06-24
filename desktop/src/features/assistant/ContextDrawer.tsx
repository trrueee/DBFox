import { Info, Sparkles, X } from "lucide-react";
import type { WorkspaceTab } from "../../types/workspace";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { getStoredApiConfig } from "../../components/SettingsDialog";

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
    <section className={`hifi-right-drawer ${open ? "open" : "closed"}`}>
      <div className="h-full flex flex-col overflow-auto">
        <div className="hifi-assistant-header border-b border-slate-200 p-3 flex-shrink-0 flex justify-between items-center bg-slate-50">
          <span className="hifi-assistant-title flex items-center gap-1.5 font-bold text-[var(--ui-font-control)]">
            {type === "ai-suggest" && <><Sparkles size={13} className="text-purple-600" /> AI 建议</>}
            {type === "props" && <><Info size={13} className="text-blue-600" /> 对象属性</>}
          </span>
          <X size={12} className="cursor-pointer text-slate-400 hover:text-slate-600" onClick={onClose} />
        </div>

        <div className="flex-1 overflow-auto p-3.5">
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
    <div className="flex flex-col gap-3">
      <span className="text-[var(--ui-font-caption)] text-slate-400 uppercase block mb-1">数据库诊断建议</span>
      <div className="text-slate-400 text-center py-8 text-[var(--ui-font-caption)] flex flex-col items-center justify-center gap-2 border border-dashed border-slate-200 rounded-xl p-4 bg-slate-50/50">
        <Sparkles size={16} className="text-slate-300" />
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
    <div className="flex flex-col gap-2.5 font-mono text-[var(--ui-font-caption)] text-slate-700">
      <span className="text-[var(--ui-font-caption)] font-sans text-slate-400 uppercase block mb-1.5">当前对象物理与 AI 属性</span>
      {rows.map(([label, value]) => {
        const isLong = value.length > 25 || label.includes("描述");
        return (
          <div key={label} className={`flex ${isLong ? "flex-col gap-1 items-start" : "justify-between"} border-b border-slate-100 pb-1.5`}>
            <span className="text-slate-400">{label}</span>
            <span className={`font-semibold text-slate-900 ${isLong ? "text-[var(--ui-font-caption)] break-all whitespace-pre-wrap text-left" : "text-right"}`}>{value}</span>
          </div>
        );
      })}
    </div>
  );
}
