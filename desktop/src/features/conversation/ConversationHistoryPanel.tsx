import { Clock, MessageSquare, Trash2 } from "lucide-react";
import type { Conversation } from "../../types/conversation";

interface ConversationHistoryPanelProps {
  conversations: Conversation[];
  activeConversationId?: string;
  onOpenConversation: (conversation: Conversation) => void;
  onDeleteConversation: (conversationId: string) => void;
}

export function ConversationHistoryPanel({ conversations, activeConversationId, onOpenConversation, onDeleteConversation }: ConversationHistoryPanelProps) {
  return (
    <div className="p-4 flex flex-col gap-2 overflow-auto h-full">
      <div className="flex items-center justify-between mb-1">
        <div>
          <div className="font-bold text-[13px] text-slate-800">对话历史</div>
          <div className="text-[10px] text-slate-400 mt-0.5">SQLite 本地会话记录</div>
        </div>
        <span className="hifi-guide-chip-prod">{conversations.length} 条</span>
      </div>

      {conversations.length === 0 ? (
        <div className="border border-dashed border-slate-200 rounded-xl p-5 text-center text-[11px] text-slate-400 bg-white">
          暂无历史记录。提交问数后，会话会写入本地 SQLite。
        </div>
      ) : (
        conversations.map((conversation) => (
          <button
            key={conversation.id}
            className={`text-left border rounded-xl bg-white p-3 hover:border-indigo-300 hover:bg-indigo-50/40 transition-all ${activeConversationId === conversation.id ? "border-indigo-300 bg-indigo-50/60" : "border-slate-200"}`}
            onClick={() => onOpenConversation(conversation)}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-800 truncate">
                  <MessageSquare size={12} className="text-indigo-500 shrink-0" />
                  <span className="truncate">{conversation.title}</span>
                </div>
                <div className="flex items-center gap-1.5 text-[9px] text-slate-400 mt-1">
                  <Clock size={10} />
                  <span>{formatTime(conversation.updatedAt)}</span>
                  <span>·</span>
                  <span>{conversation.messages.length} 条消息</span>
                  <span>·</span>
                  <span>{conversation.artifacts.length} 个产物</span>
                </div>
              </div>
              <span
                className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500"
                onClick={(event) => {
                  event.stopPropagation();
                  onDeleteConversation(conversation.id);
                }}
              >
                <Trash2 size={12} />
              </span>
            </div>
            {conversation.contextTables.length > 0 && (
              <div className="flex gap-1 flex-wrap mt-2">
                {conversation.contextTables.slice(0, 3).map((table) => (
                  <span key={table} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-mono">{table}</span>
                ))}
              </div>
            )}
          </button>
        ))
      )}
    </div>
  );
}

function formatTime(value: number) {
  if (!value) return "未知时间";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
