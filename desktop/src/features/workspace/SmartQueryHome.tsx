import type { Conversation } from "../../types/conversation";
import { AskContextDropZone } from "./smartQuery/AskContextDropZone";
import { AskInputBox } from "./smartQuery/AskInputBox";
import { RecentAccess } from "./smartQuery/RecentAccess";
import { RecommendQuestions } from "./smartQuery/RecommendQuestions";
import { SmartQueryHero } from "./smartQuery/SmartQueryHero";

interface SmartQueryHomeProps {
  askInputValue: string;
  contextTables: string[];
  conversations: Conversation[];
  recentTab: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  onRecommendClick: (text: string) => void;
  onRecentTabChange: (tab: string) => void;
  onOpenTable: (tableName: string) => void;
  onOpenConversation: (conversation: Conversation) => void;
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
  onOpenConversationHistory: () => void;
  onToast: (message: string) => void;
}

export function SmartQueryHome({
  askInputValue,
  contextTables,
  conversations,
  recentTab,
  onAskInputChange,
  onSubmitAsk,
  onRecommendClick,
  onRecentTabChange,
  onOpenTable,
  onOpenConversation,
  onAddContextTable,
  onRemoveContextTable,
  onClearContextTables,
  onOpenConversationHistory,
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
        conversations={conversations}
        onRecentTabChange={onRecentTabChange}
        onOpenTable={onOpenTable}
        onOpenConversation={onOpenConversation}
        onShowMore={onOpenConversationHistory}
      />
    </div>
  );
}
