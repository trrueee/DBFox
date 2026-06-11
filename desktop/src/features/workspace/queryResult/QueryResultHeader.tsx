import { TrendingUp, RefreshCw } from "lucide-react";

export function QueryResultHeader({
  queryText,
  onRegenerate,
}: {
  queryText: string;
  onRegenerate?: () => void;
}) {
  return (
    <div className="hifi-query-result-header">
      <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-1">
        <TrendingUp size={11} className="text-purple-500" />
        <span>智能问数分析结果</span>
      </div>
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-[12px] text-slate-800">“{queryText}”</h3>
        {onRegenerate && (
          <button
            className="hifi-agent-regenerate-btn"
            title="重新生成"
            onClick={onRegenerate}
          >
            <RefreshCw size={12} />
            <span>重新生成</span>
          </button>
        )}
      </div>
    </div>
  );
}
