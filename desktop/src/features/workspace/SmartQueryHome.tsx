import { FileText, GitMerge, RefreshCw, Search, Send, Sparkles, TrendingUp, User, X } from "lucide-react";

interface SmartQueryHomeProps {
  askInputValue: string;
  contextTables: string[];
  recentTab: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  onRecommendClick: (text: string) => void;
  onRecentTabChange: (tab: string) => void;
  onOpenTable: (tableName: string) => void;
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
  onToast: (message: string) => void;
}

export function SmartQueryHome({
  askInputValue,
  contextTables,
  recentTab,
  onAskInputChange,
  onSubmitAsk,
  onRecommendClick,
  onRecentTabChange,
  onOpenTable,
  onAddContextTable,
  onRemoveContextTable,
  onClearContextTables,
  onToast,
}: SmartQueryHomeProps) {
  return (
    <div className="hifi-query-home hifi-tab-pane">
      <div className="hifi-hero">
        <h2 className="hifi-hero-title">
          你好，开始你的<span className="hifi-gradient-text">智能问数之旅</span>
        </h2>
        <p className="hifi-hero-subtitle">用自然语言提问，AI 帮你从数据中找到答案</p>
        <div className="hifi-hero-pattern" />
      </div>

      <div
        className="hifi-drop-zone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          const tableName = event.dataTransfer.getData("text/plain");
          if (tableName) onAddContextTable(tableName);
        }}
      >
        <GitMerge size={12} className="text-indigo-500 flex-shrink-0" />
        <span className="text-[10px] text-slate-500 font-semibold mr-1">问数上下文:</span>
        {contextTables.length === 0 ? (
          <span className="text-[10px] text-slate-400 italic">拖拽左侧的表到这里以加载问数上下文</span>
        ) : (
          <div className="flex gap-1.5 flex-wrap items-center">
            {contextTables.map((tableName) => (
              <span key={tableName} className="hifi-context-chip flex items-center gap-1 bg-indigo-50 border border-indigo-200 text-indigo-700 px-1.5 py-0.5 rounded text-[9px] font-mono">
                <span>{tableName}</span>
                <X size={8} className="cursor-pointer hover:bg-indigo-200 rounded-full p-0.5" onClick={() => onRemoveContextTable(tableName)} />
              </span>
            ))}
            <button className="text-[9px] text-red-500 hover:underline ml-1" onClick={onClearContextTables}>清除</button>
          </div>
        )}
      </div>

      <div className="hifi-ask-input-container">
        <textarea
          className="hifi-ask-input"
          value={askInputValue}
          onChange={(event) => onAskInputChange(event.target.value)}
          placeholder="用自然语言提问，例如：帮我查一下“市场运营部”上个月发布了多少资产？"
        />
        <button className="hifi-ask-send-btn animate-pulse" onClick={onSubmitAsk}>
          <Send size={14} />
        </button>
      </div>

      <div className="hifi-recommend-section">
        <div className="hifi-section-header">
          <span className="hifi-section-title">推荐提问</span>
          <button className="hifi-text-btn" onClick={() => onToast("已随机刷新推荐提问")}>
            <RefreshCw size={11} />
            换一换
          </button>
        </div>

        <div className="hifi-recommend-grid">
          <RecommendCard icon={<TrendingUp size={13} />} text="分析近 7 天评论数据趋势" tag="数据分析" onClick={onRecommendClick} />
          <RecommendCard icon={<User size={13} />} text="查询活跃用户 Top 10" tag="用户分析" onClick={onRecommendClick} />
          <RecommendCard icon={<FileText size={13} />} text="统计本月新增笔记数量" tag="内容分析" onClick={onRecommendClick} />
          <RecommendCard icon={<Search size={13} />} text="检查 comment_infos 是否有异常数据" tag="数据治理" onClick={onRecommendClick} />
        </div>
      </div>

      <div className="hifi-recent-section">
        <div className="hifi-section-header">
          <div className="hifi-recent-tabs">
            {["tables", "queries", "chat"].map((tab) => (
              <span key={tab} className={`hifi-recent-tab ${recentTab === tab ? "active" : ""}`} onClick={() => onRecentTabChange(tab)}>
                {tab === "tables" ? "最近表" : tab === "queries" ? "最近查询" : "最近问答"}
              </span>
            ))}
          </div>
          <button className="hifi-text-btn" onClick={() => onToast("打开历史访问中心")}>查看更多 &gt;</button>
        </div>

        <div className="hifi-recent-grid">
          <RecentTable tableName="id_users" desc="小红书数据" onOpenTable={onOpenTable} />
          <RecentTable tableName="comment_infos" desc="互动模块" onOpenTable={onOpenTable} />
          <RecentTable tableName="video_watch_records" desc="流量模块" onOpenTable={onOpenTable} />
          <RecentTable tableName="note_infos" desc="内容模块" onOpenTable={onOpenTable} />
          <RecentTable tableName="id_organizations" desc="账号模块" onOpenTable={onOpenTable} />
        </div>
      </div>
    </div>
  );
}

function RecommendCard({ icon, text, tag, onClick }: { icon: React.ReactNode; text: string; tag: string; onClick: (text: string) => void }) {
  return (
    <div className="hifi-recommend-card" onClick={() => onClick(text)}>
      <div className="hifi-recommend-icon">{icon}</div>
      <span className="hifi-recommend-text">{text}</span>
      <span className="hifi-tag">{tag}</span>
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
