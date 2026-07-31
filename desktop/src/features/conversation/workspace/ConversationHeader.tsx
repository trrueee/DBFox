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
  const title = detail.title.trim() || "新对话";

  return (
    <header className="conv-header">
      <div className="conv-header-title-group">
        <h2 title={title}>{title}</h2>
      </div>
      <div className="conv-header-actions">
        <button
          type="button"
          className="conv-header-action conv-header-history"
          onClick={onOpenHistory}
          title="打开对话历史"
          aria-label="打开对话历史"
        >
          <History size={16} aria-hidden="true" />
          <span className="conv-header-action-label">历史</span>
        </button>
        <button
          type="button"
          className="conv-header-action conv-header-delete"
          onClick={onDelete}
          title="删除当前对话"
          aria-label="删除当前对话"
        >
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
