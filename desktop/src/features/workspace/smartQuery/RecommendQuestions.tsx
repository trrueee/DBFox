import type { ReactNode } from "react";
import { FileText, RefreshCw, Search, TrendingUp, User } from "lucide-react";

interface RecommendQuestionsProps {
  onRecommendClick: (text: string) => void;
  onRefresh: () => void;
}

export function RecommendQuestions({ onRecommendClick, onRefresh }: RecommendQuestionsProps) {
  return (
    <div className="hifi-recommend-section">
      <div className="hifi-section-header">
        <span className="hifi-section-title">推荐提问</span>
        <button className="hifi-text-btn" onClick={onRefresh}>
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
  );
}

function RecommendCard({ icon, text, tag, onClick }: { icon: ReactNode; text: string; tag: string; onClick: (text: string) => void }) {
  return (
    <div className="hifi-recommend-card" onClick={() => onClick(text)}>
      <div className="hifi-recommend-icon">{icon}</div>
      <span className="hifi-recommend-text">{text}</span>
      <span className="hifi-tag">{tag}</span>
    </div>
  );
}
