import { Info, Sparkles, X } from "lucide-react";
import type { WorkspaceTab } from "../../mock/dbfoxMock";

interface ContextDrawerProps {
  open: boolean;
  type: "ai-suggest" | "props";
  activeTab: WorkspaceTab;
  contextTables: string[];
  onClose: () => void;
  onGenerateIndexSql: () => void;
}

export function ContextDrawer({ open, type, activeTab, contextTables, onClose, onGenerateIndexSql }: ContextDrawerProps) {
  return (
    <section className={`hifi-right-drawer ${open ? "open" : "closed"}`}>
      <div className="h-full flex flex-col overflow-auto">
        <div className="hifi-assistant-header border-b border-slate-200 p-3 flex-shrink-0 flex justify-between items-center bg-slate-50">
          <span className="hifi-assistant-title flex items-center gap-1.5 font-bold text-[12px]">
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
      <span className="text-[10px] text-slate-400 uppercase block mb-1">数据库诊断建议</span>
      <div className="border border-purple-200 bg-purple-50/60 rounded-xl p-3 text-purple-900">
        <div className="flex items-center gap-1.5 font-bold text-[11px] mb-1 text-purple-800"><Sparkles size={12} /><span>性能索引推荐</span></div>
        <p className="text-[10px] leading-relaxed mb-2 opacity-90">检测到表 `comment_infos` 的字段 `user_id` 在联合查询中执行了大量全表扫描，建议立即为其创建单列索引。</p>
        <button className="bg-purple-600 hover:bg-purple-700 text-white rounded text-[9px] font-semibold px-2 py-0.5" onClick={onGenerateIndexSql}>生成并运行 DDL</button>
      </div>
      <div className="border border-amber-200 bg-amber-50/60 rounded-xl p-3 text-amber-900">
        <div className="flex items-center gap-1.5 font-bold text-[11px] mb-1 text-amber-800"><Info size={12} /><span>多租户结构警告</span></div>
        <p className="text-[10px] leading-relaxed opacity-90">数据表 `id_users` 与 `id_organizations` 缺少一致的联合主键 `tenant_id`，建议补充主键以确保多租户隔离层级正确。</p>
      </div>
    </div>
  );
}

function PropsPanel({ activeTab, contextTables }: { activeTab: WorkspaceTab; contextTables: string[] }) {
  if (activeTab.type === "table") {
    const tableId = activeTab.tableId || "id_users";
    return <InfoList rows={[["物理表名:", tableId], ["预估行数:", "12,345 Rows"], ["物理大小:", "2.48 MB"], ["存储引擎:", "InnoDB"], ["创建时间:", "2024-11-16"]]} />;
  }
  if (activeTab.type === "sql") {
    return <InfoList rows={[["连接名称:", "prod-mysql"], ["会话端口:", "3306"], ["事务模式:", "AUTO-COMMIT"]]} />;
  }
  return <InfoList rows={[["上下文关联:", `${contextTables.length} 张表`], ["激活大模型:", "DeepSeek-Coder-V2"], ["会话ID:", "caae-f483-d1e4"]]} />;
}

function InfoList({ rows }: { rows: string[][] }) {
  return (
    <div className="flex flex-col gap-2 font-mono text-[10px] text-slate-700">
      <span className="text-[10px] font-sans text-slate-400 uppercase block mb-1.5">当前对象物理属性</span>
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between border-b border-slate-100 pb-1.5">
          <span className="text-slate-400">{label}</span>
          <span className="font-semibold text-slate-900">{value}</span>
        </div>
      ))}
    </div>
  );
}
