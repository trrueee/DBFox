import { Info, Sparkles, X } from "lucide-react";
import type { WorkspaceTab } from "../../types/workspace";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDatasourceStore } from "../../stores/datasourceStore";

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
  return (
    <div className="flex flex-col gap-3">
      <span className="text-[var(--ui-font-caption)] text-slate-400 uppercase block mb-1">数据库诊断建议</span>
      <div className="border border-purple-200 bg-purple-50/60 rounded-xl p-3 text-purple-900">
        <div className="flex items-center gap-1.5 font-bold text-[var(--ui-font-label)] mb-1 text-purple-800"><Sparkles size={12} /><span>性能索引推荐</span></div>
        <p className="text-[var(--ui-font-caption)] leading-relaxed mb-2 opacity-90">检测到表 `comment_infos` 的字段 `user_id` 在联合查询中执行了大量全表扫描，建议立即为其创建单列索引。</p>
        <button className="bg-purple-600 hover:bg-purple-700 text-white rounded text-[var(--ui-font-micro)] font-semibold px-2 py-0.5" onClick={onGenerateIndexSql}>生成并运行 DDL</button>
      </div>
      <div className="border border-amber-200 bg-amber-50/60 rounded-xl p-3 text-amber-900">
        <div className="flex items-center gap-1.5 font-bold text-[var(--ui-font-label)] mb-1 text-amber-800"><Info size={12} /><span>多租户结构警告</span></div>
        <p className="text-[var(--ui-font-caption)] leading-relaxed opacity-90">数据表 `id_users` 与 `id_organizations` 缺少一致的联合主键 `tenant_id`，建议补充主键以确保多租户隔离层级正确。</p>
      </div>
    </div>
  );
}

function PropsPanel({ activeTab, contextTables }: { activeTab: WorkspaceTab; contextTables: string[] }) {
  const tables = useDatasourceStore((s) => s.tables);

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
      rows.push(["预估行数:", "12,345 Rows"]);
      rows.push(["存储引擎:", "InnoDB"]);
    }
    return <InfoList rows={rows} />;
  }
  if (activeTab.type === "sql") {
    return <InfoList rows={[["连接名称:", "prod-mysql"], ["会话端口:", "3306"], ["事务模式:", "AUTO-COMMIT"]]} />;
  }
  return <InfoList rows={[["上下文关联:", `${contextTables.length} 张表`], ["激活大模型:", "DeepSeek-Coder-V2"], ["会话ID:", "caae-f483-d1e4"]]} />;
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
