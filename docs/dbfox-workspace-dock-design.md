# DBFox Workspace Dock 历史交互草案

> 文档状态：历史
>
> 已由 [`architecture/frontend.md`](architecture/frontend.md) 与
> [`architecture/artifact-representation-visualization.md`](architecture/artifact-representation-visualization.md)
> 取代。本文只保留 2026-08-15 阶段的交互推演，不是当前模型、类型或实现依据；其中
> `openArtifactResultTab`、`TableArtifactView(mode)` 等名称均为历史设计。

> 文档类型：产品与交互设计草案
>
> 状态：草案
>
> 最后核验：2026-08-15
>
> 适用范围：`desktop/src` React 工作区信息架构、右栏 Dock Tab 模型与工件打开方式
>
> 与现行基线的关系：本文只保留交互与视觉细节，不再作为边界决策依据；当前 Workbench 边界见 [`docs/architecture/frontend.md`](architecture/frontend.md)，历史 Shell ADR 已归档。当前已实现的部分以源码为准，文档描述目标形态，不覆盖 [`dbfox-design-baseline.md`](dbfox-design-baseline.md) v2.1。
>
> 实现进度（2026-08-15）：核心布局已落地（`App` 左树 / `ConversationCenter` 中间对话 / `WorkspaceDock` 右侧 Tab）；项目级持久 Console、表 Tab、工件总览与「打开为 Tab」已接入。Dock 宽度拖拽、Console 落盘恢复、WebView 尚未实现。

## 1. 设计结论

```text
左侧 = 项目与数据资源树
中间 = 对话，并且只放对话
右侧 = 可展开/收起的 Dock，内部是 Tab 面板
```

- 左侧栏保留项目卡片、对话列表、数据树与设置入口。
- 中间主区固定渲染对话工作区；不再通过中间 Tab 在「问数 / SQL / 表 / 结果」之间切换。
- 右侧 Dock 是一个可扩展的 Tab 容器：SQL 控制台、表详情、工件总览、打开的工件都在这里。
- 顶部栏只保留项目标识；全局搜索按钮及其命令面板入口删除。
- Dock 是可扩展面板：当前 Tab 类型只覆盖控制台、表、工件，未来可增加 WebView 等新 Tab 类型而不改变整体布局。

## 2. 三栏布局

```text
┌────────── 左侧资源树 ──────────┬────────────── 中间对话 ──────────────┬──────────── 右侧 Dock ────────────┐
│ 项目卡片列表                    │                                     │  [ >_ 控制台 | ▤ 表 | ✦ 工件 ]   │
│  · 对话列表                     │  ✦ DBFox 对话                       │  ────────────────────────────── │
│  · 数据树                       │  · 消息流                            │  当前 Tab 内容                   │
│  · 设置                         │  · 审批 / 提问卡片                   │                                 │
│                                │  · 输入框                            │                                 │
└────────────────────────────────┴─────────────────────────────────────┴─────────────────────────────────┘
```

中间无活动对话时显示问数首页/空状态；对话一旦打开，中间始终保持对话现场，不被 SQL、表或工件替换。

## 3. 顶栏

```text
当前方案：项目标识 + WorkspaceTabs + 搜索
新方案：  项目标识 + 右栏开合按钮
```

- 删除 `app-cmd-btn` 搜索按钮与 `Ctrl K` 全局命令面板入口。
- 顶栏只回答「我在哪个项目」；所有工作能力进入右侧 Dock。
- 右栏开合按钮只控制 Dock 显示/隐藏，不影响中间对话。

## 4. 右侧 Dock 的 Tab 模型

### 4.1 当前固定 Tab 类型

```ts
type DockTab =
  | {
      id: "console";
      kind: "console";
      datasourceId: string;
    }
  | {
      id: `table-${string}`;
      kind: "table";
      tableName: string;
      subTab: "data" | "schema" | "er";
      datasourceId: string;
    }
  | {
      id: "artifacts";
      kind: "artifacts";
      conversationId: string;
    }
  | {
      id: `artifact-${string}`;
      kind: "artifact-preview";
      artifactId: string;
    };
```

### 4.2 Tab 语义

| Tab | 来源 | 关闭行为 |
| --- | --- | --- |
| `>_ 控制台` | 每个项目固定一个 | 不显示关闭按钮；切换项目时切到对应项目的持久 Console |
| `▤ 表名` | 左侧数据树点击 | 带关闭按钮；再次点击同一张表时聚焦已有 Tab |
| `✦ 工件` | 当前对话 | 不显示关闭按钮；换对话时内容跟随当前对话 |
| 具体工件 | 在「✦ 工件」预览中点击「打开为 Tab」 | 带关闭按钮；关闭只关预览，工件总览仍在 |

### 4.3 Dock 行为

- Dock 可展开/收起，默认宽度可拖拽，建议范围约 `320px ~ 60%` 窗口宽度。
- 窄窗口下 Dock 可退化为悬浮 Drawer。
- Tab 溢出时横向滚动；键盘可关闭可关闭 Tab。
- 未来 Tab 类型通过统一描述扩展：

```ts
interface DockTabDescriptor {
  id: string;
  kind: string;
  title: string;
  icon: LucideIcon;
  closeable: boolean;
  // 未来 WebView 等新 Tab 只增加 kind 和渲染器
  render: () => ReactNode;
}

type FutureDockTab =
  | DockTab
  | { id: `webview-${string}`; kind: "webview"; url: string; title: string };
```

## 5. 工件：总览与「打开为 Tab」两个层级

工件的现有数据机制保持不变，只改变「在哪里打开」。

### 5.1 现有机制（保留）

- 工件只保存元数据和引用，不保存全量行。
- 一切数据访问基于 `artifactId`：

```text
TableArtifactView
  → useArtifactTableData(artifact, mode)
  → source = { kind: "artifact-result", artifactId: artifact.id }
  → agentApi.fetchArtifactPage(artifactId, page, pageSize, sort, filters, search)
```

- 总览/预览使用 `mode="inline"`，初始页大小较小（当前实现为 10 行）。
- 「打开为 Tab」使用 `mode="workspace"`，初始页大小更大（当前实现为 50 行），并提供搜索、排序、筛选、刷新、分页、CSV 复制与导出。

### 5.2 新位置

```text
✦ 工件（右侧 Dock 固定 Tab）
┌─────────────┬──────────────────────────┐
│ 工件列表      │ 工件预览                  │
│             │  TableArtifactView inline │
│ ▤ 查询结果   │  [ ⧉ 打开为 Tab ]         │
│ 📊 趋势图    │                          │
│ 📝 分析笔记  │                          │
└─────────────┴──────────────────────────┘
        │ 点击「打开为 Tab」
        ▼
右侧 Dock 新开「📊 趋势图」Tab
TableArtifactView mode="workspace"
仍按 artifactId 分页查询
```

- 「✦ 工件」Tab 就是当前 `ArtifactDock` 的「列表 + 预览」结构，整体迁入 Dock。
- 对话中 AI 引用某工件时，Dock 自动聚焦「✦ 工件」Tab，并高亮对应卡片。
- `workspaceStore.openArtifactResultTab` 的语义从「往中间 WorkspaceTabs 添加 tab」改为「往右栏 Dock 添加 artifact-preview Tab」。

## 6. 组件映射

| 现有组件 / 逻辑 | 新布局中的位置 |
| --- | --- |
| `ConversationWorkspace` | 中间唯一主区；移除其内部嵌的 `ArtifactDock` |
| `ArtifactDock` | 右侧「✦ 工件」Tab 的内容；列表 + 预览结构保留 |
| `TableArtifactView`（inline） | 「✦ 工件」预览 |
| `TableArtifactView`（workspace） | 右侧具体工件 Tab |
| `SqlConsoleWorkspace` | 右侧「>_ 控制台」Tab |
| `TableWorkspace` | 右侧「▤ 表名」Tab |
| `MultiTableWorkspace` | 临时 Tab，按需出现 |
| `WorkspaceRouter` | 不再承担中间多类型路由；中间只渲染对话 |
| `WorkspaceTabs` | 由右栏 Dock Tab 模型取代；可删除或重写为 Dock Tab 条 |
| `AppCommandPalette` / 搜索按钮 | 删除 |
| `ContextDrawer`（props/ai-suggest） | 与 Dock 合并或保持独立，待定 |

## 7. 状态模型草案

```ts
interface SqlConsoleSession {
  entries: ConsoleEntry[];   // transcript
  draft: string;
  history: string[];
  scrollPosition: number;
  running: boolean;
}

interface ProjectWorkbench {
  datasourceId: string;
  console: SqlConsoleSession;          // 每个项目一份，持久
  activeTable?: {
    name: string;
    subTab: "data" | "schema" | "er";
  };
}

interface ConversationDockState {
  conversationId: string;
  selectedArtifactId?: string;         // AI 引用时高亮
}

interface WorkspaceDockState {
  open: boolean;
  activeTabId: string;
  projectTabs: Record<string, ProjectTab[]>;      // 按项目：console / table
  conversationTabs: Record<string, ConversationTab[]>; // 按对话：artifacts / artifact-preview
}

// 核心交互
openProjectConsole(datasourceId, initialSql?):
  → 激活项目 → Dock open → activeTabId = "console"

openTableDockTab(datasourceId, tableName, subTab):
  → 已存在则聚焦，否则新增 → Dock open

openArtifactDockTab(conversationId, artifactId):
  → 新增 artifact-preview Tab 或聚焦已有 → Dock open

focusArtifactsDockTab(conversationId, artifactId?):
  → 聚焦「✦ 工件」Tab，可选高亮指定工件
```

## 8. 核心交互流

### 8.1 AI SQL → 控制台

```text
对话中 AI 给出 SQL
  → 点击「>_ 发送到控制台」
  → 右侧 Dock 打开/聚焦「>_ 控制台」Tab
  → SQL 填入 Live Prompt，不自动执行
  → 中间对话保持可见
```

### 8.2 左侧点表 → 看表

```text
左侧数据树点击表名
  → 右侧 Dock 打开/聚焦「▤ 表名」Tab
  → 默认「数据」子 Tab
```

### 8.3 工件总览 → 工件 Tab

```text
中间对话生成/引用工件
  → 聚焦「✦ 工件」Tab，高亮对应工件
  → 用户点「打开为 Tab」
  → Dock 新开具体工件 Tab，按 artifactId 分页取数
```

## 9. 可扩展性要求

右侧 Dock 是通用 Tab 容器，新增能力不新增布局区域：

- 新增 Tab 类型 = 新增一个 `kind` + 渲染器 + Tab 生命周期动作；
- 关闭、聚焦、重开、拖拽宽度、Dock 开合等行为由 Dock 统一提供；
- 未来 WebView 以 `kind: "webview"` 接入，由宿主安全边界约束（沙箱、权限、白名单），不在前端层自建导航。
- 未来若需要笔记、查询历史、多表组合等能力，优先作为 Dock Tab 进入，不回到中间 Tab 切换模型。

## 10. 与 v2.1 基线的差异

| 主题 | v2.1（当前） | 本草案 |
| --- | --- | --- |
| 中间主区 | 三模式工作面：问数 / 控制台 / 表详情 | 只有对话 |
| 工作模式切换 | 顶部 Workspace Switcher | 删除 |
| 右侧 | 工件 Dock（嵌在对话内部） | 统一 Dock：控制台 / 表 / 工件 / 未来 WebView |
| 顶栏 | 项目标识 + Switcher + 搜索 | 项目标识 + Dock 开合 |
| 工件预览 | 对话内右侧 Dock | 右栏「✦ 工件」Tab |
| 工件 Tab | 中间 `artifact-result-*` Tab | 右栏 Dock Tab |
| 搜索 | 全局搜索 + 命令面板 | 删除 |
| 扩展模型 | 中间 Tab 继续增长 | Dock Tab `kind` 扩展 |

## 11. 视觉与质感总纲

视觉目标从「能用、整齐」提升到「现代、优雅、精致、圆润」，但**不另起一套视觉语言**：

```text
第一步  继承  tokens.css、v2.1 设计基线和现有组件样式
第二步  做增量 只在本草案中标为「V3 建议值」的项才是新增
第三步  验证  亮/暗、neutral/warm、accent、density、对比度全部通过
```

三条视觉纪律：

1. **同层级只用一个表面**：对话、Dock、表格各有一个明确表面，不出现「卡片叠卡片」。
2. **颜色只表达身份和状态**：紫 = AI，青 = 数据库；状态色只用于状态；其余全部中性色。
3. **阴影只给真正浮起的东西**：固定面板用 hairline 和表面色区分，弹层、菜单才用阴影。

### 11.1 与现有 tokens 的锚定关系

所有视觉讨论必须能指向现有 `desktop/src/styles/tokens.css`。下表是 V3 视觉层的继承与增量边界：

| 主题 | 现有权威值（tokens.css） | V3 建议增量 | 说明 |
| --- | --- | --- | --- |
| 品牌紫 | `--color-primary: #6554D9` | 不变 | AI、主操作、选中 |
| 控制台青 | `--color-console-accent: #0284C7` | 可选：小字号场景试 `#0369A1` | 仅在对比度验证后替换，不在本草案直接改 |
| 窗口表面 | `--app-bg / --app-bg-deep` 径向渐变 | 不变 | 三栏都长在这张画布上 |
| 中间对话表面 | `--agent-surface`（light = `--color-panel`） | 不变 | 保留现有对话气质 |
| Dock 表面 | `--agent-surface-muted`（light = `--color-bg`） | 新增别名 `--surface-dock` 指向它 | 与现有 ArtifactDock 背景一致 |
| 表格/代码表面 | `--surface-raised`、`--sql-code-surface`、`--sql-code-text` | 不变 | Console 与结果表继续复用 |
| hairline | `--hairline` 6%、`--hairline-strong` 10% | 不变 | 边框与分隔的唯一来源 |
| 焦点 | `--focus-ring: 0 0 0 3px rgba(101,84,217,.24)` | 不变 | 全产品继续沿用 |
| 圆角 | window/panel/card 12、control 8、sm 6、md 8、pill 999 | 见 §12.1 的 V3 建议值 | 未替换 token 前，所有 CSS 继续用现有值 |
| 动效 | `--motion-fast: 150ms`（唯一权威） | 不新增 `--motion-normal/slow` | 见 §16；不恢复已移除 token |
| 对话字体 | `--agent-font-*`（body/input 默认 16px，可调） | 不变 | 对话文字继续跟随外观设置 |
| 壳层字体 | `--ui-font-*` | 不变 | 项目卡、Tab、表格元数据 |
| 数字 | `--font-mono` + `tabular-nums`（`.dbfox-tnum`） | 不变 | SQL、数据、耗时、错误码 |
| 主题能力 | light/dark、neutral/warm、accent、contrast、density、字体字号 | 不变 | V3 新增表面必须覆盖全部主题 |

## 12. 圆角、边框与阴影

### 12.1 圆角：现有体系 + 明确的 V3 建议值

现有 tokens 已经形成「外 12 / 控件 8 / 小件 6 / 胶囊 999」的节奏；V3 在保持体系不变的前提下整体润一档：

| Token | 现有值 | V3 建议值 | 用途 |
| --- | --- | --- | --- |
| `--radius-window` | 12px | 16px | 桌面窗口 / 三栏最外层 |
| `--radius-panel` | 12px | 14px | Dock、设置面板 |
| `--radius-card` | 12px | 12px | 项目卡、工件卡 |
| `--radius-control` | 8px | 10px | 输入框、按钮、表格容器 |
| `--radius-md` | 8px | 10px | 列表项 hover 底 |
| `--radius-sm` | 6px | 8px | 小标签、代码块 |
| `--radius-pill` | 999px | 不变 | 状态点、Tab、徽标 |

嵌套规则：外层比内层更圆；紧凑密度只压高度和间距，圆角不下探。

### 12.2 边框：沿用 hairline，只补一个聚焦描边

- 大表面分隔：`--hairline`（6%）；
- hover / 输入框：`--hairline-strong`（10%）；
- 选中描边：现有 `--focus-ring` 已经覆盖，V3 不新造描边 token。

### 12.3 阴影：继续沿用现有分层

| 现有 token | V3 用途 |
| --- | --- |
| `--shadow-window` | 窗口 / 三栏最外层（保留现有主表面投影） |
| `--shadow-panel` / `--shadow-card` | 激活 Tab、工件卡、轻浮层 |
| `--shadow-card-hover` | 菜单、Popover、Tooltip |
| `--agent-shadow-soft / hover` | 对话内按钮、卡片 hover（保持对话手感） |

固定面板不额外加投影；Dock 关闭后的悬浮 Drawer 才使用 `--shadow-card-hover`。

## 13. 色彩与表面

### 13.1 表面全部由现有 token 派生，不引入新色值

```text
light：
--app-bg:              #EEF3F8   （现有）
--app-bg-deep:         #E7EDF5   （现有径向渐变）
--sidebar-bg:          #EEF3F8   （现有）
--agent-surface:       #FFFFFF   （现有，中间对话）
--agent-surface-muted: #F4F7FB   （现有，Dock 底 / 总览列表）
--surface-raised:      #FFFFFF   （现有，激活 Tab / 表格 / 输入）
--control-bg-hover:    #F8FAFD   （现有，hover）

dark：
--app-bg / --sidebar-bg / --agent-surface / --agent-surface-muted / --surface-raised
全部沿用 tokens.css 深色值，不另拟。
```

V3 布局只新增一个语义别名（不产生新色值）：

```css
--surface-dock: var(--agent-surface-muted);
```

理由：现有 `ArtifactDock` 已使用 `--agent-surface-muted`，V3 右栏 Dock 继承同一底色，保证新布局不偏离原有配色。

### 13.2 身份色完全沿用

```text
品牌紫 --color-primary: #6554D9
控制台青 --color-console-accent: #0284C7（dark: #38BDF8）
状态色 --color-success / warning / danger / info
柔和底 --color-primary-soft / success-soft / warning-soft / danger-soft
```

颜色使用纪律不变：正文中性；紫色只给 AI、选中、主操作；青色只给数据库、SQL、执行态；状态必须图标 + 文字双编码。

## 14. 字体与数字：尊重现有可调体系

- 对话区域继续使用 `--agent-font-*`：标题 16px、正文 16px、输入 16px（默认值），随外观设置缩放；
- 壳层和右栏继续使用 `--ui-font-*`：项目卡、Tab、工具栏、表格元数据；
- Mono 继续只用于 SQL、prompt、表数据、错误码、耗时、行数，使用 `--font-mono`；
- 数字、时间、ID 继续使用 `.dbfox-tnum` / `tabular-nums`，表格数字右对齐；
- 不再提出新的字号值；层级靠字重、灰度和留白表达。

## 15. 三栏与组件的精致细节（在现有组件样式上微调）

### 15.1 左侧资源树

- 保留现有 `--sidebar-bg`、28–32px 行高、8px 节点圆角和 8px 缩进节奏；
- 项目卡保留现有结构：32px 品牌图标块 + 名称 13px/600 + 副标题 12px muted；
- 激活态继续使用 `--color-primary-soft` + 左侧 3px `--color-primary` 品牌条；
- V3 仅补充：非激活项目卡 hover 使用 `--control-bg-hover`；展开/收起走 150ms 高度过渡。

### 15.2 中间对话

- 完全保留现有 `ConversationWorkspace` 的视觉：`--agent-surface` 底、`conv-header`、`conv-message-column`、`--agent-user-bg` 用户气泡、`--agent-focus-ring`；
- AI 消息继续「不包卡片」；SQL 卡片由 Data DLC 组合 Host `CodeArtifact` / `ArtifactCard`，沿用 `--agent-border`、`--radius-control` 与 mono 呈现；
- V3 仅补充：输入框 focus 使用现有 `--focus-ring`；发送按钮保持现有 32px 圆形控制。

### 15.3 右侧 Dock

- Dock 底色使用 `--agent-surface-muted`，与现有 `conv-artifact-dock` 保持一致；
- 左缘使用现有 `--agent-border` hairline，不再加投影；
- Tab 条高 40px（沿用 `--density-toolbar-min-height`），Tab 项高 28px、圆角沿用 `--radius-control`；
- 激活 Tab：`--surface-raised` 底 + 图标按语义着色（✦ 紫 / `>_` 青）+ `--shadow-card`，不用重色块；
- Dock 默认 440px，可拖 320px–60%；收起后由悬浮 Drawer 承载，使用 `--shadow-card-hover`。

### 15.4 SQL Console

- 继续使用现有 `--sql-code-surface`、`--sql-code-text`、`--sql-code-border`；
- prompt 青、SQL mono、结果表格 `--surface-raised` + `--radius-sm`（V3 随控制圆角升级后自然变为 8px）；
- 错误内联保留现有无卡片结构，补齐 ✕ / 错误码 / 修复动作，动作按钮使用现有 Button token；
- 块间距按基线 §8.1 为 20px；hover 整块使用 4% 中性底。

### 15.5 工件

- 「✦ 工件」Tab 内部就是现有 `ArtifactDock` 的「列表 + 预览」结构：列表 112–132px、列表项 8px 圆角、选中项 `--agent-surface` 底 + `--agent-accent` 图标；
- 预览继续用现有 `TableArtifactView` / `ArtifactCard` / 图表卡样式，不重画；
- 新工件进入时顶部滑入 + 紫边脉冲一次，动效时长仍走 `--motion-fast`。

## 16. 动效：以现有 `--motion-fast: 150ms` 为唯一权威

现有 tokens 只有 `--motion-fast: 150ms`；v2.1 评审已移除 `--motion-normal`，本草案**不恢复、不新造** token：

| 场景 | V3 做法 |
| --- | --- |
| hover / 焦点 / 图标 | `--motion-fast`（150ms） |
| Tab 切换 / 项目卡展开 | `--motion-fast` + 交叉淡入 |
| Dock 开合 | 先使用 150ms 宽度缓动；若评审认为需要更慢，再作为独立 token 决策 |
| 新工件进入 | 150ms 滑入 + 单次脉冲 |
| AI 流式输出 | 保留现有 `conv-stream-caret` 光标呼吸 |
| reduced motion | 沿用现有 `data-motion=reduce` 与 `prefers-reduced-motion` 全局降级 |

## 17. 主题与可访问性：沿用现有主题矩阵

- V3 新增表面全部走现有 token，因此自动继承 light / dark、neutral / warm、accent、contrast、density、字号调节；
- 深色下数据库官方品牌图标：优先沿用现有图标块（`--hairline` 底）；若特定品牌色对比不足，按 §0.2 多重编码补图标 + 文字，不在本草案发明第二套品牌色；
- 状态色、焦点环、等宽数字、灰度可读性、键盘焦点，全部沿用现有基线约束；
- 新增组件必须通过现有 `npm test`、lint 和 `scripts/check-design-contracts.mjs`。

## 18. 视觉验收清单

除功能验收外，视觉评审至少检查：

- [ ] 亮色、深色、中性、暖色四套主题下三栏层级清晰；
- [ ] 紧凑密度下 Tab、行高和圆角不破碎；
- [ ] 125% 缩放与 1100px 窄窗口布局不溢出；
- [ ] 灰度模式下 AI / 用户 / 数据库 / 错误仍可辨认；
- [ ] 键盘焦点完整：项目卡、对话、Tab、控制台、工件列表；
- [ ] 所有动效在 `prefers-reduced-motion` 下瞬时完成；
- [ ] 表格数字右对齐且等宽，长文本省略不换行；
- [ ] 固定面板与浮层阴影区别明确，没有新增无依据色值或动效 token。

## 19. 接受与实现前的验证清单

本草案在进入实现前，应由评审确认以下问题：

- [ ] Dock 固定 Tab 与临时 Tab 的分组和关闭规则；
- [ ] 每个项目的 Console 持久化边界（内存 / 落盘 / 关闭恢复）；
- [ ] 工件 Tab 生命周期：切换对话后是否保留、如何失效；
- [ ] Dock 默认宽度、最大宽度与窄窗口 Drawer 行为；
- [ ] `ContextDrawer` 与 Dock 的关系；
- [ ] 搜索删除后，对话历史、数据源管理、设置等入口是否全部可达；
- [ ] 现有 `WorkspaceTabs` / `WorkspaceRouter` 的删除与测试迁移计划；
- [ ] WebView 未来的权限与安全边界，避免本草案被误读为已承诺实现。
