import type { Conversation } from "../../../types/conversation";

interface RecentAccessProps {
  recentTab: string;
  conversations: Conversation[];
  onRecentTabChange: (tab: string) => void;
  onOpenTable: (tableName: string) => void;
  onOpenConversation: (conversation: Conversation) => void;
  onShowMore: () => void;
}

const recentTabs = [
  { id: "tables", label: "最近表" },
  { id: "queries", label: "最近查询" },
  { id: "chat", label: "最近问答" },
];

const recentTables = [
  { tableName: "id_users", desc: "小红书数据" },
  { tableName: "comment_infos", desc: "互动模块" },
  { tableName: "video_watch_records", desc: "流量模块" },
  { tableName: "note_infos", desc: "内容模块" },
  { tableName: "id_organizations", desc: "账号模块" },
];

export function RecentAccess({ recentTab, conversations, onRecentTabChange, onOpenTable, onOpenConversation, onShowMore }: RecentAccessProps) {
  return (
    <div className="hifi-recent-section">
      <div className="hifi-section-header">
        <div className="hifi-recent-tabs">
          {recentTabs.map((tab) => (
            <span key={tab.id} className={`hifi-recent-tab ${recentTab === tab.id ? "active" : ""}`} onClick={() => onRecentTabChange(tab.id)}>
              {tab.label}
            </span>
          ))}
        </div>
        <button className="hifi-text-btn" onClick={onShowMore}>查看更多 &gt;</button>
      </div>

      {recentTab === "chat" ? (
        <div className="hifi-recent-grid">
          {conversations.length === 0 ? (
            <div className="hifi-recent-card cursor-default">
              <span className="hifi-recent-name">暂无问答历史</span>
              <p className="hifi-recent-desc">提交问数后会写入 SQLite</p>
            </div>
          ) : (
            conversations.slice(0, 5).map((conversation) => (
              <RecentConversation key={conversation.id} conversation={conversation} onOpenConversation={onOpenConversation} />
            ))
          )}
        </div>
      ) : (
        <div className="hifi-recent-grid">
          {recentTables.map((item) => (
            <RecentTable key={item.tableName} tableName={item.tableName} desc={item.desc} onOpenTable={onOpenTable} />
          ))}
        </div>
      )}
    </div>
  );
}

function RecentTable({ tableName, desc, onOpenTable }: { tableName: string; desc: string; onOpenTable: (tableName: string) => void }) {
  return (
    <div className="hifi-recent-card" onClick={() => onOpenTable(tableName)}>
      <span className="hifi-recent-name">{tableName}</span>
      <p className="hifi-recent-desc">{desc}</p>
    </div>
  );
}

function RecentConversation({ conversation, onOpenConversation }: { conversation: Conversation; onOpenConversation: (conversation: Conversation) => void }) {
  return (
    <div className="hifi-recent-card" onClick={() => onOpenConversation(conversation)}>
      <span className="hifi-recent-name">{conversation.title}</span>
      <p className="hifi-recent-desc">{conversation.messages.length} 条消息 · {conversation.artifacts.length} 个产物</p>
    </div>
  );
}
