import { FoxIcon } from "../../../components/brand/FoxIcon";
import "./EmptyArtifactsState.css";

export function EmptyArtifactsState() {
  return (
    <div className="hifi-ai-card hifi-artifact-empty">
      <div className="hifi-ai-card-header hifi-artifact-empty-header">
        <FoxIcon variant="ai-tight" size={16} alt="" aria-hidden="true" className="hifi-artifact-empty-icon" />
        <span>等待 Agent 产物</span>
      </div>
      <div className="hifi-ai-card-body hifi-artifact-empty-body">
        当前会话还没有返回 artifacts。后端返回 chart、sql、table 或 markdown 类型产物后，会在这里自动渲染。
      </div>
    </div>
  );
}
