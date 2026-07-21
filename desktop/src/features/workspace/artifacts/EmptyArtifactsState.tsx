import { FoxIcon } from "../../../components/brand/FoxIcon";
import "./EmptyArtifactsState.css";

export function EmptyArtifactsState() {
  return (
    <div className="hifi-ai-card hifi-artifact-empty">
      <div className="hifi-ai-card-header hifi-artifact-empty-header">
        <FoxIcon variant="ai-tight" size={16} alt="" aria-hidden="true" className="hifi-artifact-empty-icon" />
        <span>分析结果将在这里显示</span>
      </div>
      <div className="hifi-ai-card-body hifi-artifact-empty-body">
        当智能分析生成图表、查询语句或数据表时，会自动显示在这里。
      </div>
    </div>
  );
}
