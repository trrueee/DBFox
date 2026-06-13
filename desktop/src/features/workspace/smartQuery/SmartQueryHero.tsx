import { FoxIcon } from "../../../components/brand/FoxIcon";

export function SmartQueryHero() {
  return (
    <div className="hifi-hero">
      <div className="hifi-hero-fox">
        <FoxIcon variant="ai-tight" size={72} alt="DataBox AI fox" />
      </div>
      <h2 className="hifi-hero-title">
        你好，开始你的 <span className="hifi-gradient-text">智能问数之旅</span>
      </h2>
      <p className="hifi-hero-subtitle">用自然语言提问，AI 帮你从数据中找到答案</p>
      <div className="hifi-hero-pattern" />
    </div>
  );
}
