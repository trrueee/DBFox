# DataBox 前端产品化素材

这个目录提供一批可直接被 React 前端消费的产品化素材，覆盖首页主视觉、功能卡片、用户角色、上手引导、空状态、Prompt 示例、信任背书、Demo 场景、FAQ、命令面板文案和 Toast 文案。

## 为什么放在 `src/product-assets`

这些内容不是纯文档，而是前端可渲染的数据资产：

- 有 TypeScript 类型约束，适合直接传给组件。
- 文案与 DataBox 当前产品能力保持一致：本地优先、AI 问数、SQL 控制台、TrustGate、Agent Eval。
- 不包含真实业务数据、密钥、连接信息或生产库样本。
- icon 使用 `IconKey` 字符串，前端可映射到 `lucide-react` 图标。

## 快速使用

```tsx
import { databoxProductAssets } from "../product-assets";

export function ProductHero() {
  const { hero } = databoxProductAssets;

  return (
    <section>
      <p>{hero.eyebrow}</p>
      <h1>{hero.title}</h1>
      <p>{hero.description}</p>
      <button data-action={hero.primaryCta.action}>{hero.primaryCta.label}</button>
    </section>
  );
}
```

## 建议落地点

| 素材 | 建议组件 / 页面 | 用途 |
| --- | --- | --- |
| `hero` | `SmartQueryHome` 或欢迎页 | 产品定位、主 CTA、信任点 |
| `features` | 首页功能区、设置页侧栏 | 功能卡片和入口 CTA |
| `personas` | 新手引导、模板选择 | 按角色推荐入口和示例问题 |
| `workflow` | Onboarding / Empty State | 展示从连接到问数再到评测的闭环 |
| `onboarding` | 新用户 Checklist | 驱动首次配置、建连接、同步 Schema、第一次问数 |
| `prompts` | 问数输入框推荐问题 | 示例 Prompt、意图和所需上下文 |
| `emptyStates` | 数据源、Schema、历史、评测等空状态 | 引导用户下一步操作 |
| `trustSignals` | 安全说明卡片 | 展示本地 Engine、Token、TrustGate 和可观测性 |
| `demoScenarios` | Demo / 官网截图 / Mock 页面 | 构造产品化示例结果和洞察卡片 |
| `navigation` | Command Palette、Header、Toast | 统一导航、命令和反馈文案 |

## 图标映射示例

```tsx
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  Layers3,
  LineChart,
  Lock,
  MessageSquare,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
} from "lucide-react";
import type { IconKey } from "../product-assets";

const iconMap: Record<IconKey, React.ComponentType<{ size?: number }>> = {
  AlertTriangle,
  CheckCircle2,
  Clock3: CheckCircle2,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  Layers3,
  LineChart,
  Lock,
  MessageSquare,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
};
```

> 如果需要严格一一映射，请从 `lucide-react` 额外引入 `Clock3`。

## 维护规则

1. 新增素材时先补类型，再补数据。
2. 避免提交真实公司、真实用户、真实数据库表或敏感字段。
3. Prompt 示例要包含业务目标、时间范围、分组维度或验收结果，降低 Agent 误解。
4. 高风险 SQL Demo 只展示预检查或伪 SQL，不提供可直接删除生产数据的语句。
5. 文案保持产品化表达：明确结果、边界和下一步动作。
