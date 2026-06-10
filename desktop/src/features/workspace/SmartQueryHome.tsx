import { AskContextDropZone } from "./smartQuery/AskContextDropZone";
import { AskInputBox } from "./smartQuery/AskInputBox";
import { RecentAccess } from "./smartQuery/RecentAccess";
import { RecommendQuestions } from "./smartQuery/RecommendQuestions";
import { SmartQueryHero } from "./smartQuery/SmartQueryHero";

interface SmartQueryHomeProps {
  askInputValue: string;
  contextTables: string[];
  recentTab: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  onRecommendClick: (text: string) => void;
  onRecentTabChange: (tab: string) => void;
  onOpenTable: (tableName: string) => void;
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
  onToast: (message: string) => void;
}

export function SmartQueryHome({
  askInputValue,
  contextTables,
  recentTab,
  onAskInputChange,
  onSubmitAsk,
  onRecommendClick,
  onRecentTabChange,
  onOpenTable,
  onAddContextTable,
  onRemoveContextTable,
  onClearContextTables,
  onToast,
}: SmartQueryHomeProps) {
  return (
    <div className="hifi-query-home hifi-tab-pane">
      <SmartQueryHero />

      <AskContextDropZone
        contextTables={contextTables}
        onAddContextTable={onAddContextTable}
        onRemoveContextTable={onRemoveContextTable}
        onClearContextTables={onClearContextTables}
      />

      <AskInputBox value={askInputValue} onChange={onAskInputChange} onSubmit={onSubmitAsk} />

      <RecommendQuestions onRecommendClick={onRecommendClick} onRefresh={() => onToast("已随机刷新推荐提问")} />

      <RecentAccess
        recentTab={recentTab}
        onRecentTabChange={onRecentTabChange}
        onOpenTable={onOpenTable}
        onShowMore={() => onToast("打开历史访问中心")}
      />
    </div>
  );
}
