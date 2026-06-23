import { Clock, MessageSquare, Trash2, ChevronRight } from "lucide-react";
import type { ConversationSummary } from "../../types/conversation";

interface ConversationHistoryPanelProps {
  conversations: ConversationSummary[];
  activeConversationId?: string;
  onOpenConversation: (conversation: ConversationSummary) => void;
  onDeleteConversation: (conversationId: string) => void;
}

export function ConversationHistoryPanel({ conversations, activeConversationId, onOpenConversation, onDeleteConversation }: ConversationHistoryPanelProps) {
  return (
    <div className="p-4 flex flex-col gap-2 overflow-auto h-full">
      <div className="flex items-center justify-between mb-1">
        <div>
          <div className="font-bold text-[var(--ui-font-body)] text-slate-800">对话历史</div>
          <div className="text-[var(--ui-font-caption)] text-slate-400 mt-0.5">SQLite 本地会话记录</div>
        </div>
        <span className="hifi-guide-chip-prod">{conversations.length} 条</span>
      </div>

      {conversations.length === 0 ? (
        <div className="border border-dashed border-slate-200 rounded-xl p-5 text-center text-[var(--ui-font-label)] text-slate-400 bg-white">
          暂无历史记录。提交问数后，会话会写入本地 SQLite。
        </div>
      ) : (
        conversations.map((conversation) => {
          const preview = conversation.last_message?.slice(0, 100) || "";
          return (
            <button
              key={conversation.id}
              className={`text-left border rounded-xl bg-white p-3 hover:border-indigo-300 hover:bg-indigo-50/40 transition-all group ${activeConversationId === conversation.id ? "border-indigo-300 bg-indigo-50/60" : "border-slate-200"}`}
              onClick={() => onOpenConversation(conversation)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-[var(--ui-font-label)] font-bold text-slate-800">
                    <MessageSquare size={12} className="text-indigo-500 shrink-0" />
                    <span className="truncate">{conversation.title}</span>
                    <ChevronRight size={10} className="text-slate-300 group-hover:text-indigo-400 shrink-0 ml-auto" />
                  </div>
                  {preview && (
                    <div className="text-[var(--ui-font-caption)] text-slate-500 mt-0.5 line-clamp-1">{preview}</div>
                  )}
                  <div className="flex items-center gap-1.5 text-[var(--ui-font-micro)] text-slate-400 mt-1.5">
                    <Clock size={10} />
                    <span>{formatTime(conversation.updated_at)}</span>
                    <span>·</span>
                    <span>{conversation.message_count} 条消息</span>
                    {conversation.artifact_count > 0 && (
                      <>
                        <span>·</span>
                        <span>{conversation.artifact_count} 个产物</span>
                      </>
                    )}
                  </div>
                </div>
                <span
                  className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteConversation(conversation.id);
                  }}
                >
                  <Trash2 size={12} />
                </span>
              </div>
            </button>
          );
        })
      )}
    </div>
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
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(date);
}
