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
      <div className="conv-header-title-group">
        <h2>{detail.title || "Conversation"}</h2>
        <span className="conv-header-meta" title={detail.id}>
          会话 {shortIdentifier(detail.id)}
        </span>
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

function shortIdentifier(value: string): string {
  if (value.length <= 16) return value;
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}
