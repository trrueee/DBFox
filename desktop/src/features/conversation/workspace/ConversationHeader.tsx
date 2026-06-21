import { History, Trash2 } from "lucide-react";
import type { ConversationDetail } from "../../../types/conversation";

export function ConversationHeader({
  detail,
  onOpenHistory,
  onDelete,
}: {
  detail: ConversationDetail;
  onOpenHistory: () => void;
  onDelete: () => void;
}) {
  return (
    <header className="conv-header">
      <div>
        <h2>{detail.title || "Conversation"}</h2>
        <span>{detail.datasource_id}</span>
      </div>
      <div className="conv-header-actions">
        <button type="button" onClick={onOpenHistory} title="Open history">
          <History size={16} />
        </button>
        <button type="button" onClick={onDelete} title="Delete conversation">
          <Trash2 size={16} />
        </button>
      </div>
    </header>
  );
}
