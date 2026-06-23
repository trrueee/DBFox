import { GitMerge } from "lucide-react";

interface MultiTableWorkspaceProps {
  tables: string[];
  onOpenQueryResult: (query: string) => void;
  onToast: (message: string) => void;
}

export function MultiTableWorkspace({ tables, onOpenQueryResult, onToast }: MultiTableWorkspaceProps) {
  return (
    <div className="hifi-multi-table-workspace hifi-tab-pane">
      <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-lg p-3 text-blue-800 flex items-center gap-3">
        <GitMerge size={16} className="text-blue-600" />
        <div>
          <span className="font-semibold block text-[var(--ui-font-label)]">联合 Workspace ({tables.length} 张表)</span>
          <span className="text-[var(--ui-font-caption)] opacity-90">当前工作区已绑定表: {tables.join("，")}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-400 cursor-pointer" onClick={() => onOpenQueryResult(`查询这 ${tables.length} 张表的关联性，并给出数据字典`)}>
          <span className="font-semibold text-[var(--ui-font-label)] block mb-1">分析表关联拓扑图</span>
          <span className="text-[var(--ui-font-caption)] text-slate-500">计算表与表之间的物理键及逻辑外键联系。</span>
        </div>
        <div className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-400 cursor-pointer" onClick={() => onOpenQueryResult(`统计所选表在最近一月的联合活动数据量`)}>
          <span className="font-semibold text-[var(--ui-font-label)] block mb-1">联合数据趋势统计</span>
          <span className="text-[var(--ui-font-caption)] text-slate-500">分析用户、评论、流量记录的联合转化率。</span>
        </div>
      </div>

      <div className="border border-slate-200 rounded-xl p-3 mt-4 bg-slate-50">
        <span className="text-[var(--ui-font-caption)] text-slate-600 font-semibold block mb-2">针对选定的 {tables.length} 张表进行智能提问:</span>
        <div className="flex gap-2">
          <input
            type="text"
            className="hifi-guide-input flex-1 bg-white"
            placeholder={`例如：帮我查询在 ${tables.slice(0, 2).join("和")} 之间进行内连接关联的数据...`}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onOpenQueryResult((event.target as HTMLInputElement).value);
                (event.target as HTMLInputElement).value = "";
              }
            }}
          />
          <button className="hifi-guide-btn-primary" onClick={() => onToast("智能建议已发送")}>联合分析</button>
        </div>
      </div>
    </div>
  );
}
