interface RecentAccessProps {
  recentTab: string;
  onRecentTabChange: (tab: string) => void;
  onOpenTable: (tableName: string) => void;
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

export function RecentAccess({ recentTab, onRecentTabChange, onOpenTable, onShowMore }: RecentAccessProps) {
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

      <div className="hifi-recent-grid">
        {recentTables.map((item) => (
          <RecentTable key={item.tableName} tableName={item.tableName} desc={item.desc} onOpenTable={onOpenTable} />
        ))}
      </div>
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
