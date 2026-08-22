import type { ConversationDetail } from "../../../types/conversation";

export function ConversationHeader({ detail }: { detail: ConversationDetail }) {
  const title = detail.title.trim() || "新对话";

  return (
    <header className="conv-header">
      <div className="conv-header-rail">
        <div className="conv-header-title-group">
          <h2 className="conv-header-title" title={title}>{title}</h2>
        </div>
      </div>
    </header>
  );
}
