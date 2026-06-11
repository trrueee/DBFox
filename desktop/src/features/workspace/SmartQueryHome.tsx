import type { Conversation } from "../../types/conversation";
import { AskContextDropZone } from "./smartQuery/AskContextDropZone";
import { AskInputBox } from "./smartQuery/AskInputBox";
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
  onAskInputChange,
  onSubmitAsk,
  onAddContextTable,
  onRemoveContextTable,
  onClearContextTables,
}: SmartQueryHomeProps) {
  return (
    <div className="hifi-query-home hifi-tab-pane">
      <div className="hifi-query-home-content">
        <SmartQueryHero />

        <AskContextDropZone
          contextTables={contextTables}
          onAddContextTable={onAddContextTable}
          onRemoveContextTable={onRemoveContextTable}
          onClearContextTables={onClearContextTables}
        />

        <AskInputBox value={askInputValue} onChange={onAskInputChange} onSubmit={onSubmitAsk} />
      </div>
    </div>
  );
}
