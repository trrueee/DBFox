import { FoxIcon } from "../../../components/brand/FoxIcon";
import "../SmartQueryHome.css";

export function SmartQueryHero() {
  return (
    <div className="smart-query-hero">
      <div className="smart-query-hero__fox">
        <FoxIcon variant="app" size={78} alt="DBFox fox" />
      </div>
      <h2 className="smart-query-hero__title">
        你好，开始你的 <span className="smart-query-gradient-text">智能问数之旅</span>
      </h2>
      <p className="smart-query-hero__subtitle">用自然语言提问，AI 帮你从数据中找到答案</p>
      <div className="smart-query-hero__pattern" />
    </div>
  );
}
