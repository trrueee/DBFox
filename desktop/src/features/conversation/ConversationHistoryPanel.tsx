import { ChevronRight, Clock, MessageSquare, Trash2 } from "lucide-react";
import { Button, EmptyState } from "../../components/ui";
import { WorkspaceShell } from "../appShell/WorkspaceShell";
import type { ConversationSummary } from "../../types/conversation";
import "./ConversationHistoryPanel.css";

interface ConversationHistoryPanelProps {
  conversations: ConversationSummary[];
  activeConversationId?: string;
  onOpenConversation: (conversation: ConversationSummary) => void;
  onDeleteConversation: (conversationId: string) => void;
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function ConversationHistoryPanel({
  conversations,
  activeConversationId,
  onOpenConversation,
  onDeleteConversation,
}: ConversationHistoryPanelProps) {
  return (
    <WorkspaceShell
      className="conversation-history"
      title="对话历史"
      description="继续之前的智能问数会话，查看消息与生成产物。"
      toolbar={
        <div className="conversation-history__toolbar">
          <span className="conversation-history__count">{conversations.length} 条</span>
        </div>
      }
      bodyClassName="conversation-history__body"
    >
      {conversations.length === 0 ? (
        <EmptyState
          title="暂无历史记录"
          description="提交问数后，会话会自动保存。"
        />
      ) : (
        <div className="conversation-history__list">
          {conversations.map((conversation) => {
            const preview = conversation.last_message?.slice(0, 100) || "";
            const active = activeConversationId === conversation.id;
            return (
              <article
                key={conversation.id}
                className={cx(
                  "conversation-history__item",
                  active && "conversation-history__item--active",
                )}
              >
                <button
                  type="button"
                  className="conversation-history__item-button"
                  aria-label={`打开 ${conversation.title}`}
                  onClick={() => onOpenConversation(conversation)}
                >
                  <div className="conversation-history__item-head">
                    <MessageSquare size={14} className="conversation-history__message-icon" aria-hidden="true" />
                    <span className="conversation-history__title">{conversation.title}</span>
                    <ChevronRight size={12} className="conversation-history__chevron" aria-hidden="true" />
                  </div>
                  {preview ? <div className="conversation-history__preview">{preview}</div> : null}
                  <div className="conversation-history__meta">
                    <Clock size={12} aria-hidden="true" />
                    <span>{formatTime(conversation.updated_at)}</span>
                    <span>·</span>
                    <span>{conversation.message_count} 条消息</span>
                    {conversation.artifact_count > 0 ? (
                      <>
                        <span>·</span>
                        <span>{conversation.artifact_count} 个产物</span>
                      </>
                    ) : null}
                  </div>
                </button>
                <Button
                  className="conversation-history__delete"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`删除 ${conversation.title}`}
                  title={`删除 ${conversation.title}`}
                  onClick={() => onDeleteConversation(conversation.id)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </Button>
              </article>
            );
          })}
        </div>
      )}
    </WorkspaceShell>
  );
}

function formatTime(value: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} 天前`;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
