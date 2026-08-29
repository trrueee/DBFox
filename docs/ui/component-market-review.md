# DBFox UI 组件市场评审

> 文档类型：UI 组件市场评审
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 适用范围：`desktop/` 的 App Shell、Agent Workspace、Work Surface、Tree、DataGrid 与基础交互组件。

## 1. 目的与约束

本评审是已归档的[UI 市场驱动重构任务](../archive/reviews/ui-market-driven-refactor-task.md)要求的
阶段性实现前置门禁。目标不是引入另一套设计系统，而是把成熟组件中的交互解剖、无障碍语义和
状态处理，适配到 DBFox 已有的 Core UI、Radix、TanStack 与 `react-resizable-panels` 基础上。

评审使用五路证据交叉决策，而不是把组件市场或 `ui-ux-pro-max` 当作单一权威：

1. 当前项目能力、调用图、历史提交和已接受合同；
2. Electron/React/浏览器平台与现有依赖的官方能力；
3. 成熟开源组件的真实源码、维护状态、许可证和供应链成本；
4. VS Code、assistant-ui、Hermes Agent 等真实产品/开源产品的运行态交互；
5. `ui-ux-pro-max` 的可访问性、密度、响应式、颜色与状态检查。

Pro Max 对 DBFox 给出的 landing-page、活动橙色和在线 Fira 字体建议与本地优先 Windows/CJK 桌面
边界冲突，已明确 REJECT；其 data-dense、对比度、错误恢复和 reduced-motion 检查继续采用。

以下约束优先于市场组件的默认设计：

- `docs/dbfox-master-product-ui-contract.md` 是产品与视觉最高权威；保持 Neutral Shell、Blue Signal、任务优先导航、统一 Composer 与一等 Work Surface。
- Core 继续拥有 Agent Runtime、Workbench 编排和权威状态；DLC 只通过既有 Connector/Dock/Artifact 扩展点贡献领域能力。
- 不引入第二套 Chat Runtime、布局状态机、设计令牌或持久状态。
- 不用 registry installer 无差别覆盖已有 primitives；对胜出的可分离组件直接 vendoring 经核验的上游源码，
  只有运行时/数据合同无法兼容时才拒绝，不能退回到手写外观仿制。
- 生产组件只能消费 DBFox 语义令牌和 Lucide 图标。

## 2. 当前 UI 清单

| 类别 | 当前入口 | 当前能力 | 主要缺口 |
| --- | --- | --- | --- |
| App Shell | `App.tsx`、`WorkspaceShell` | 标题栏、主侧栏、内容区、Dock | 需要验证窄屏、缩放和焦点顺序 |
| Navigation | shadcn-derived `components/ui/sidebar.tsx`、Project Overview | Core-only 分组、项目/会话入口、导航 landmark | 已采用 registry presentation；继续验证窄屏与缩放 |
| Composer | `UnifiedComposer` → Prompt Kit / AI Elements | 引用、自动增高、容器聚焦、运行中投递策略、同按钮发送/停止 | 已采用；继续浏览器验证 IME、缩放和长草稿 |
| Timeline | `AgentTimeline` + AI/Agent Elements | Message、ToolGroup、Plan、Evidence、运行错误/停止/处理中 | 已采用真实 presentation；继续补 reconnect/stale 等运行矩阵 |
| Approval | AI Elements Confirmation + `ApprovalCard` | 批准/拒绝、提交与耐久审计态 | 已采用；继续补 expired/409 fixture |
| Question | `AgentQuestion` | 单选/自由文本/提交与耐久回答 | 已采用 Agent Elements presentation + Radix radio；继续补 expired/409 fixture |
| Work Surface | `ResizableWorkspaceLayout`、`ConversationWorkspaceLayout`、`WorkspaceDock` | react-resizable-panels 分栏、Radix Tabs、DLC Dock | 已删除自研 Dock resize；继续浏览器验证缩放、全屏和关闭后焦点 |
| Tree | Host `ui.Tree`、Workspace/GitHub DLC、Data Catalog | 层级浏览、选择、上下文操作 | Zag Tree View 已在 `host.ui@1.0.0` 落地并替换三套手写 presentation；Data 直接采用官方 async children/loading/error，并保留 refresh/load-more/SQL/table actions |
| DataGrid | Artifact/Data DLC tables | TanStack Table v8 + Virtual v3 | 已补 grid 计数、sort state 和方向键焦点；继续覆盖虚拟/截断/错误状态 |
| Foundation | shadcn/Radix `components/ui/*` | Field/Dialog/Menu/Select/Switch/Toolbar/Tabs/Feedback 等成熟 primitives | Field、Command Dialog 与 Select 已完成真实浏览器/键盘/axe 验收；不引入重复 primitive 集合 |
| Design Lab | `design-lab/DesignLab.tsx`、`ComponentComparison.tsx` | 直接渲染已采用生产组件；状态/语言/主题/视口/缩放矩阵 | 1280/1024/720 与 light/dark 已验；真实 Host Tree 的三级层级、selection、collapse、keyboard 与 CSP 已验，async/error/retry 由 Data fixture 验证；480px/200%/IME 仍保持门禁 |

## 3. 调研方法与决策口径

对每个候选检查：实时 Demo 与源码可达性、React/TypeScript/Tailwind/Radix 兼容性、键盘与可访问性、响应式和状态覆盖、API 与 DBFox 数据模型匹配度、许可证、令牌改造量、重复 primitive、运行时耦合、升级和退出成本。

决策含义：

- **ADOPT**：源码可直接纳入并由 DBFox 后续维护。
- **ADAPT**：只复制明确的结构/交互片段，改为 DBFox props、语义令牌和权威状态。
- **REFERENCE ONLY**：仅用于行为或视觉校验，不复制源码、不引入依赖。
- **REJECT**：与架构、版本、许可证或维护风险不匹配。

## 4. 市场入口覆盖

| 来源 | 实际检查入口 | 发现与用途 | 结论 |
| --- | --- | --- | --- |
| 21st.dev | https://21st.dev/、Input Bar | React/Tailwind 社区组件，适合发现具体作者实现；不能以聚合页替代单组件许可证确认 | 发现/比较 |
| Uiverse | https://uiverse.io/ | 大量按钮、loader、micro-interaction；与桌面 shell/Agent 信息架构不匹配 | REFERENCE ONLY（loader） |
| Component System Directory | https://componentsystem.directory/compare | 跨库能力和维护信号比较，不提供 DBFox 可直接消费的统一源码合同 | 发现/比较 |
| registry.directory | https://www.registry.directory/、https://ui.shadcn.com/docs/directory | shadcn registry 发现；第三方条目仍需逐项审查 | 发现/比较 |
| Shoogle | https://shoogle.dev/directory | shadcn 生态目录，适合查缺，不作为许可证或质量权威 | 发现/比较 |
| shadcn/ui | https://ui.shadcn.com/docs/components、Sidebar、Data Table | MIT；与现有 Radix/Tailwind 解剖最接近 | ADOPT 可分离 presentation source；不重复 runtime |
| Dice UI | https://diceui.com/ | Accessible React/TS/Tailwind/shadcn 组件；与已有 primitives 有重复 | REFERENCE ONLY |
| ReUI | https://reui.io/docs、Data Grid | 应用型 block 丰富；当前 Data Grid 基于 TanStack Table v9，DBFox 为 v8 | REFERENCE ONLY |
| React Aria / Spectrum | https://react-spectrum.adobe.com/TreeView | TreeView 键盘、选择、disabled、drag/drop 规范成熟 | ADAPT 交互规范 |
| blocks.so | https://blocks.so/sidebar、https://github.com/ephraimduncan/blocks | MIT；React/Tailwind/shadcn，多种 sidebar block | REFERENCE ONLY |
| Origin UI | https://originui.com/、https://github.com/shadcn/originui | MIT；新组件以 Tailwind v4 为主，并建议替换 primitives | REJECT |
| Coss UI | https://coss.com/ui/docs/get-started | shadcn 风格应用组件；与已有 foundation 重复 | REFERENCE ONLY |
| Tailark | https://tailark.com/docs | 以营销页面和 Tailwind v4 block 为主 | REJECT |
| AI Elements | https://elements.ai-sdk.dev/components | Prompt Input、Tool、Confirmation 等状态覆盖完整；默认绑定 AI SDK 数据 | ADAPT 解剖，不引入 runtime |
| Agent Elements | https://agent-elements.21st.dev/docs | InputBar、ToolGroup、PlanTool、TodoTool、QuestionTool 提供 registry 源码；具体采用项逐项读取 registry 元数据和许可证 | **ADOPT ToolGroup / GenericTool、PlanTool + TodoTool 源码**；其余逐项核验 |
| Prompt Kit | https://github.com/ibelick/prompt-kit、Prompt Input 源码 | MIT；组合式 PromptInput、自动增高、容器聚焦、action slots 与现有合同高度匹配 | **ADOPT（Composer 主结构）** |
| Nexus UI | https://nexus-ui.dev/docs/components/prompt-input、Questions、Citation | MIT；Agent UI 覆盖广，Questions 交互有价值；Citation URL 模型不等于 DBFox artifact | REFERENCE ONLY / ADAPT 问题流程 |
| assistant-ui | https://www.assistant-ui.com/docs/ui/thread、Tool Group、Reasoning | MIT；现代 registry 完整但围绕其 runtime，旧 styled 包已停止维护 | REFERENCE ONLY |
| Manifest UI | https://github.com/mnfst/manifest-ui、https://ui.manifest.build/ | MIT；ChatGPT/MCP block，适合内容层参考，不替换桌面工作台 | REFERENCE ONLY |
| agentcn | https://www.agentcn.dev/about | agent recipe/registry 较多，本地展示原语较少 | REJECT（本范围） |

## 5. 关键组件候选矩阵

### 5.1 Composer（最高优先级）

| 候选 | Demo / 源码 | 栈、许可、运行时 | A11y / 状态 / 响应式 | 与当前对比及代价 | 决策 |
| --- | --- | --- | --- | --- | --- |
| Prompt Kit `PromptInput` / `PromptInputWithActions` | https://www.prompt-kit.com/docs/prompt-input / https://github.com/ibelick/prompt-kit/blob/main/components/prompt-kit/prompt-input.tsx | React 19、Tailwind、shadcn；MIT；不要求其 chat runtime | textarea 原生键盘；controlled/uncontrolled；自动增高；自由 action slots | 与 `UnifiedComposer` props 最匹配；vendoring 原始 composition，仅换 semantic token classes 并保留 DBFox 投递合同 | **ADOPT（已接入）** |
| Agent Elements `InputBar` | https://agent-elements.21st.dev/docs/input-bar | React、Tailwind、shadcn；registry 展示源码但单项上游许可证需另行核验；依赖 `ai` 的 `ChatStatus`、Tabler 及多子组件 | controlled、drag/paste、附件、info/question bar、自动增高、点击聚焦、disabled/streaming | 状态覆盖最全，但直接采用会复制 DBFox runtime/图标/attachment 模型 | ADAPT（概念参考） |
| AI Elements `PromptInput` / `PromptInputSubmit` | https://elements.ai-sdk.dev/components/prompt-input | React、shadcn、AI SDK；Apache-2.0 | 附件/拖放、语音、model picker、自动增高；Submit 直接覆盖 submitted/streaming/error/default 及同按钮 stop/submit | 完整 PromptInput runtime 会越过 Core 边界；Submit 是可分离 presentation primitive | **ADOPT Submit 源码；REJECT 完整 runtime** |
| Nexus UI `PromptInput` | https://nexus-ui.dev/docs/components/prompt-input | React/Tailwind/shadcn；MIT | 可组合 header/body/footer、附件、提交状态 | 解剖适合，但与 Prompt Kit 重叠且没有更低适配成本 | REFERENCE ONLY |
| assistant-ui Composer | https://www.assistant-ui.com/docs/ui/thread | React registry；MIT；依赖 assistant-ui runtime primitives | 完整 send/cancel/attachment/branch 状态与键盘 | 采用会创建第二个 Agent runtime 与状态源 | REJECT |
| 21st Input Bar variants | https://21st.dev/%4021st/components/input-bar/toolbar-actions | React/Tailwind；条目许可证需逐项核验 | demo 强，常含 toolbar/model picker | 多为样式变体，状态合同与来源稳定性不及 Prompt Kit | REFERENCE ONLY |

结论：`UnifiedComposer` 已直接组合 vendored Prompt Kit `PromptInput` primitives 与 AI Elements
`PromptInputSubmit`。同一物理按钮在运行中空 draft 时停止、有 draft 时发送；Hermes Agent 的 payload-aware
composer 与 assistant-ui Thread 的 Send/Cancel 同槽位用于行为交叉核验。DBFox store 和投递语义保持唯一事实源。

### 5.2 Sidebar

| 候选 | Demo / 源码 | 栈与许可 | 交互覆盖 | 代价与结论 | 决策 |
| --- | --- | --- | --- | --- | --- |
| shadcn `Sidebar` | https://ui.shadcn.com/docs/components/base/sidebar / registry `new-york-v4/sidebar.json` | Radix/Base/React Aria variants、Tailwind；MIT | Provider、Header/Content/Footer、Group、Menu、active、collapsible、Cmd/Ctrl+B | **采用可分离 presentation source**；Provider/cookie/mobile Sheet 会复制 DBFox store/panel authority而拒绝；根 `<nav>` 修复当前上游 landmark 缺口 | **ADOPT presentation / REJECT runtime** |
| blocks.so Sidebar | https://blocks.so/sidebar / https://github.com/ephraimduncan/blocks | React/Tailwind/shadcn；MIT | 6 个布局变体、响应式 | 更适合页面 block，Core/DLC 分区规则需重写 | REFERENCE ONLY |
| ReUI Application blocks | https://reui.io/blocks/application | React/Tailwind/shadcn | app shell、navigation、mobile variants | 视觉密度与现有 tokens 需大改，重复 primitives | REFERENCE ONLY |
| Origin UI navigation | https://originui.com/ | React/Tailwind v4；MIT | 多种 sidebar/menu pattern | Tailwind 版本不匹配且建议替换基础组件 | REJECT |
| Coss UI navigation | https://coss.com/ui/docs/get-started | React/shadcn | 应用导航 pattern | 组件层与现有 foundation 重叠，收益不足 | REFERENCE ONLY |
| Dice UI primitives | https://diceui.com/ | React/TS/Tailwind | accessible primitives | 未提供比 shadcn Sidebar 更贴合的完整 anatomy | REJECT（Sidebar） |

### 5.3 ToolGroup / Plan / Approval / Question

| 类别 | 候选（至少五项） | 可访问性、状态与 API 结论 | 决策 |
| --- | --- | --- | --- |
| ToolGroup | Agent Elements ToolGroup / GenericTool；assistant-ui ToolGroup；AI Elements Tool；Nexus Tool；Manifest UI tool block；旧 `<details>` | Agent Elements 提供真实 disclosure、ToolRowBase、最大可见数、elapsed/status 源码；其 AI SDK registry/`part` 与模拟 streaming 不适合作为 DBFox authority；assistant-ui/AI Elements 也与各自 runtime 绑定 | **ADOPT Agent Elements presentation source**，直接消费 DBFox durable items；上游 runtime registry 与其余候选 REJECT / REFERENCE ONLY |
| Plan | Agent Elements PlanTool + TodoTool；AI Elements Plan；Prompt Kit Steps；Nexus Chain of Thought；assistant-ui Reasoning/parts；旧 Plan details | Agent Elements 的 file header、progress、controlled disclosure 与 Todo status row 可直接组合；其他候选把 reasoning/plan 混合或绑定 runtime | **ADOPT Agent Elements registry 源码**；直接消费 `PlanItem`，只扩展 blocked/skipped 与现有 Lucide |
| Approval | AI Elements Confirmation；Agent Elements Plan approval；assistant-ui Tool UI；Nexus Questions action footer；Manifest UI confirmation block；旧 ApprovalCard | AI Elements 对 requested/responded/denied/output 状态划分最清楚，且 Confirmation compound source 可脱离 runtime；按钮语义可直接接 DBFox approval authority | **ADOPT AI Elements Confirmation source**；以 durable decision 替代 `ToolUIPart`，保持现有审批 API |
| Question | Agent Elements QuestionTool / QuestionPrompt；Nexus Questions；Agent Elements InputBar question bar；AI Elements custom tool UI；assistant-ui custom tool UI；旧 QuestionCard | Agent Elements 提供完整 header、编号、选项 badge、free text 与 action 源码；其多页 localAnswers registry 不符合 DBFox 每 item 一题的耐久合同 | **ADOPT Agent Elements presentation source + Radix RadioGroup**；直接消费 `QuestionItem`，不复制多页 registry |

共同风险：Agent 组件普遍把展示组件与 Vercel AI SDK/assistant-ui runtime 类型绑定。DBFox 只采用能够
脱离这些 runtime 的真实 presentation source，并直接消费 Timeline/Plan/Approval/Question 权威 props；不能
直接接入且需要长期 mapper 或镜像模型的完整组件明确 REJECT，不用自研仿制品代替。

### 5.4 Tree

| 候选 | Demo / 源码 | 键盘 / A11y / 状态 | 兼容与风险 | 决策 |
| --- | --- | --- | --- | --- |
| Zag Tree View | https://zagjs.com/components/react/tree-view | collection、Arrow/Home/End/typeahead、single/multi selection、focus、expand、lazy loading 与 error callback；Ark/Chakra 使用同一状态机 | React 18+、MIT、活跃发布；prop getter 唯一的 inline `--depth` 可在 Host DOM 边界剥离，嵌套静态 CSS 不需要复制数据模型 | **ADOPT AT HOST BOUNDARY** |
| React Aria Components Tree | https://react-aria.adobe.com/Tree；https://github.com/adobe/react-spectrum/blob/main/packages/react-aria-components/src/Tree.tsx | Arrow/Home/End/typeahead/selection/focus/virtualization 语义成熟 | 当前普通 Tree 节点也会写 mandatory inline `display: contents`；上游 CSP issue https://github.com/adobe/react-spectrum/issues/8273 尚未解决。为通用 UI 扩大经审计 renderer 的 style-attribute 例外或长期 patch 上游均不接受 | **REJECT FOR CURRENT CONTRACT** |
| Headless Tree | https://github.com/lukasbach/headless-tree | headless、async children、keyboard、virtualization adapter | 更小且灵活，但当前上游仍标注 Beta；同样不能逐 DLC 复制 | CANDIDATE；不进生产 |
| MUI X Tree View | https://mui.com/x/react-tree-view/quickstart/ | selection、expansion、lazy loading、ordering 与完整键盘 | 需要 Material/Emotion；virtualization 与部分 advanced features 进入 Pro 商业边界，会引入第二 styling runtime | REJECT |
| `@rc-component/tree` | https://github.com/react-component/tree | 长期维护、selection/check/drag/drop/virtual list | 为当前只读导航引入 virtual-list 与 geometry runtime，且 runtime inline position 与当前 CSP/密度边界不匹配 | REJECT |
| React Arborist | https://github.com/brimdata/react-arborist | virtualized tree、selection、drag/drop、rename | Redux、react-window 与 DnD 能力超出需求；几何依赖使 CSP 适配和 bundle 成本不划算 | REJECT |
| Ark UI Tree View | https://ark-ui.com/docs/components/tree-view | 与 Zag 同状态机，提供完整 component anatomy | 高层 package 和默认 anatomy 会重复 Host UI 层；直接采用底层 Zag 更小且边界清楚 | REFERENCE / USE ZAG CORE |
| `react-accessible-treeview` | https://github.com/dgreene1/react-accessible-treeview | WAI-ARIA tree、完整键盘、多选/disabled，零运行依赖 | MIT，但项目明确寻求维护者 | REFERENCE ONLY |
| ReUI hierarchical Data Grid | https://reui.io/components/data-grid | 虚拟化、selection、expand、loading/empty | TanStack v9，与 DBFox v8 不兼容 | REJECT（依赖） |
| shadcn community tree registries | https://www.registry.directory/ | 多种 copy-in tree | 质量、许可、键盘覆盖逐项不一致 | REFERENCE ONLY |
| Dice UI composable tree patterns | https://diceui.com/ | accessible primitive 方向正确 | 与现有 Radix/本地 tree primitives 重叠 | REFERENCE ONLY |
| 旧 DBFox Project/DLC Tree | 本仓库 | 已绑定资源 authority 与 DLC slot | Workspace/GitHub 手写行及 Data `ProfileGroup`/`DatabaseRow` JSX 已删除；数据与 action authority 原位保留 | **REPLACED；KEEP DATA CONTRACT** |

### 5.5 DataGrid

| 候选 | Demo / 源码 | 状态与性能 | 兼容与风险 | 决策 |
| --- | --- | --- | --- | --- |
| 当前 TanStack Table v8 + Virtual v3 | https://tanstack.com/table/latest | headless sorting/filtering/selection + virtual rows；可保持大结果有界 | 已在依赖与产品数据模型内，是事实上的成熟引擎 | **ADOPT/KEEP** |
| ReUI Data Grid | https://reui.io/components/data-grid | sorting/filtering/pagination/resize/pin/select/virtual/DnD | 当前使用 TanStack Table v9，版本不匹配，迁移成本高 | REJECT（代码）；REFERENCE ONLY（状态） |
| shadcn Data Table | https://v3.shadcn.com/docs/components/data-table | 基于 TanStack，展示 sorting/filter/pagination/select | 示例而非完整 grid；适合作为 toolbar/empty state 参考 | REFERENCE ONLY |
| React Spectrum TableView | https://react-spectrum.adobe.com/react-spectrum/TableView.html | 键盘、focus、selection、loading/empty/disabled 完整 | 引入 Spectrum runtime/theme 与现有表格重复 | REFERENCE ONLY |
| AG Grid | https://www.ag-grid.com/react-data-grid/ | 功能与虚拟化成熟 | 大依赖、社区/企业功能边界、退出成本高 | REJECT |
| Material React Table | https://www.material-react-table.com/ | TanStack-based rich grid | 引入 Material 视觉与 primitive 栈 | REJECT |

### 5.6 Work Surface

| 候选 | Demo / 源码 | 能力、许可、A11y | 代价 | 决策 |
| --- | --- | --- | --- | --- |
| `react-resizable-panels`（现有） | https://github.com/bvaughn/react-resizable-panels | MIT；React；ARIA separator、键盘调整、collapse/expand 与像素约束 | 已统一接管主导航及右侧 Dock，直接受现有 store open 状态控制 | **ADOPT** |
| Radix Tabs（现有） | https://www.radix-ui.com/primitives/docs/components/tabs | MIT；roving focus、方向键、tab/tabpanel 关联 | 已接管 Dock tab strip；不拥有 tab 数据或持久状态 | **ADOPT** |
| shadcn Resizable | https://ui.shadcn.com/docs/components/resizable | 对 `react-resizable-panels` 的 copy-in 包装 | 与现有 `components/ui/resizable` 重复 | REFERENCE ONLY |
| Dockview | https://dockview.dev/ / https://github.com/mathuo/dockview | MIT；tabs/docking/serialization/keyboard | 引入完整 docking runtime 和第二套布局状态 | REJECT |
| FlexLayout | https://github.com/caplin/FlexLayout | MIT；tabs/docking/accessibility | 同上，且需要维护布局 JSON 事实源 | REJECT |
| Allotment | https://github.com/johnwalley/allotment | MIT；split-pane | 与现有 resizable-panels 能力重复 | REJECT |
| Golden Layout | https://github.com/golden-layout/golden-layout | MIT；复杂 docking | v3 开发状态且架构过重 | REJECT |

## 6. 一般组件类别（每类至少三候选）

| 类别 | 候选 | 采用结论 |
| --- | --- | --- |
| Dialog / Popover / Menu / Tooltip | 现有 Radix；shadcn 对应组件；React Aria 对应组件 | 保留 Radix；shadcn 只用于 composition 参考；不引入 React Aria runtime |
| Tabs / Segmented controls | 现有 Radix Tabs；shadcn Tabs；Dice UI | 保留现有；补 active/focus/overflow 状态 |
| Empty / Loading / Error | shadcn Empty/Alert/Spinner/Skeleton；Fluent MessageBar behavior | **ADOPT shadcn registry source**；Fluent 用于错误恢复动作、reflow 和 aria-live 验收 |
| Cards / Evidence | 现有 Artifact authority；Nexus Citation；AI Elements Sources | **ADOPT AI Elements Sources disclosure**；内部内容仍直接选择 Artifact，不降级为 URL citation 模型 |
| Command / Search | 现有 cmdk；shadcn Command；React Aria ComboBox | 保留 cmdk；不建立第二 command model |
| Form / Select / Radio | 现有 Radix + react-hook-form + zod；shadcn Form；React Aria forms | **ADOPT shadcn/Radix Select composition**，删除 `<option>` 兼容解析；保留现有 schema 与 Radix Radio |

## 7. 最终复用决策

### 7.1 采用

1. **Composer：Prompt Kit + AI Elements 源码采用。** 直接 vendoring PromptInput composition 和 PromptInputSubmit；DBFox 保留现有 props、引用与投递 authority。
2. **ToolGroup 与 Plan：Agent Elements 源码采用。** 直接 vendoring ToolGroup/GenericTool 与 PlanTool/TodoTool presentation source，分别直接消费 `FunctionCallItem` / `FunctionCallOutputItem` 和 `PlanItem`，不新增 DTO 或 runtime。
3. **Approval 与 Question：真实上游源码采用。** Approval vendoring AI Elements Confirmation compound source；Question vendoring Agent Elements QuestionTool/QuestionPrompt presentation source并组合现有 Radix RadioGroup；两者直接消费 Core items，不引入 AI SDK 或答案 registry。
4. **Sidebar：shadcn Sidebar presentation source。** Vendoring Header/Content/Footer/Group/MenuButton 的真实 registry 源码；不接入会复制折叠/宽度 authority 的 Provider/cookie/mobile Sheet runtime，并以 `<nav>` 修复当前上游 SidebarContent landmark 缺口。
5. **Tree：采用 Zag Tree View 并建立 Host SDK 真边界。** `host.ui@1.0.0` 暴露泛型 Tree，Workspace/GitHub/Data 直接传入现有对象与 accessor；Data 使用 Zag 官方 async child/AbortSignal/load error 回调，并通过 action/footer slot 保留刷新、分页与 Dock 动作。没有 universal resource node、DTO、mapper 或 per-DLC runtime。
6. **DataGrid：直接复用 TanStack v8/Virtual v3。** 已补 WAI grid 计数、sort 和方向键焦点合同，不新增 wrapper 或 mapper。
7. **Work Surface：直接复用 `react-resizable-panels` 与 Radix Tabs。** 删除 `WorkspaceDock` 自研 pointer/keyboard resize；布局和标签仍只写现有 workspaceStore。
8. **Message 与 Sources：AI Elements presentation source。** Timeline 采用 Message anatomy，证据采用 Sources disclosure；继续直接使用 DBFox Markdown 安全管线和 Artifact authority，不接入 AI SDK runtime。
9. **Select、Toolbar 与 Switch：shadcn/Radix 真实 composition。** 删除 Select 原生 option 解析和伪 ChangeEvent；Toolbar 由 Radix roving focus 管理方向键，SettingsToggle 由 Radix Switch 管理状态/键盘。
10. **Field 与 Command Dialog：真实上游 composition。** Settings/Project 表单采用 shadcn Field compound source；Command Palette 继续使用唯一 cmdk collection，并删除自研 overlay，交由现有 Radix Dialog 管理 modal 生命周期。
11. **DLC package-free 控件：直接使用 Web Platform。** Data connection 采用 native dialog/showModal 与 radio/fieldset；GitHub/Music 修正 nested interactive、非键盘 role=button 和伪 Toolbar。该边界不复制 Host React primitive runtime。

### 7.2 未采用其他方案的原因

- assistant-ui 及 AI/Agent Elements 的完整 runtime 安装会把展示层绑定到非 DBFox Agent runtime；只采用其可分离的真实源码组件。
- Dockview/FlexLayout/Golden Layout 提供超出需求的 docking，新增持久布局模型和升级/退出成本。
- ReUI Data Grid 当前基于 TanStack Table v9，和项目锁定的 v8 API 不兼容。
- Origin UI/Tailark 的 Tailwind v4 假设与项目 Tailwind v3 不匹配。
- React Spectrum、Material React Table 会引入第二视觉/primitive 系统。
- shadcn 2026-07 已将 Base UI 设为新项目默认，但官方同时明确 Radix 仍被支持、稳定项目不必迁移；DBFox 已有完整 Radix overlay/selection 基线，因此不为统一外观进行全栈 primitive 迁移。

## 8. 来源与本地落点

| 上游 | 组件 / 源码 | 许可 | 使用方式 | 本地落点 | 适配摘要 |
| --- | --- | --- | --- | --- | --- |
| Prompt Kit | `PromptInput` / https://github.com/ibelick/prompt-kit/blob/main/components/prompt-kit/prompt-input.tsx | MIT | vendored upstream source | `desktop/src/components/prompt-kit/prompt-input.tsx` | composition 与 focus 行为保持上游；样式接 semantic tokens/CSP |
| AI Elements | `PromptInputSubmit` / https://github.com/vercel/ai-elements/blob/main/packages/elements/src/components/prompt-input.tsx | Apache-2.0 | vendored upstream source | `desktop/src/components/ai-elements/prompt-input-submit.tsx` | 保留同按钮 stop/submit 状态；复用已有 Button，不引入 AI SDK runtime |
| Agent Elements | ToolGroup + GenericTool / https://agent-elements.21st.dev/docs/tool-group | MIT（采用项 registry/source repository） | vendored upstream presentation source | `desktop/src/components/agent-elements/AgentToolGroup.tsx` | 保留 disclosure、ToolRowBase、elapsed/status、bounded live list；直接消费 durable DBFox items，不引入 AI SDK `part`/registry/模拟 streaming |
| Agent Elements | PlanTool + TodoTool / https://agent-elements.21st.dev/docs/plan-tool | MIT（采用项 registry metadata） | vendored upstream source | `desktop/src/components/agent-elements/AgentPlan.tsx` | 直接消费 `PlanItem`；扩展 blocked/skipped，复用 Lucide；无 mapper |
| AI Elements | Confirmation / https://elements.ai-sdk.dev/components/confirmation、https://elements.ai-sdk.dev/api/registry/confirmation.json | Apache-2.0 | vendored upstream compound source | `desktop/src/components/ai-elements/confirmation.tsx`、`ApprovalCard.tsx` | 以 DBFox durable decision 替代 `ToolUIPart`；不引入 AI SDK runtime 或镜像状态 |
| Agent Elements | QuestionTool + QuestionPrompt / https://agent-elements.21st.dev/docs/question-tool | MIT | vendored upstream presentation source | `desktop/src/components/agent-elements/AgentQuestion.tsx` | 直接消费单题 `QuestionItem`；采用真实 header/options/actions，保留 Radix radio 语义；不复制多题 localAnswers registry |
| AI Elements | Message / https://elements.ai-sdk.dev/components/message | Apache-2.0 | vendored upstream presentation subset | `desktop/src/components/ai-elements/message.tsx`、`AgentTimeline.tsx` | 采用 Message/Content anatomy；保留 react-markdown 安全管线，不引入 Streamdown/AI SDK types |
| AI Elements + WHATWG | Sources / https://elements.ai-sdk.dev/components/sources；`details/summary` | Apache-2.0 anatomy + Web platform runtime | vendored compound anatomy + native disclosure | `desktop/src/components/ai-elements/sources.tsx`、`DataReferencePanel.tsx` | Artifact id/selection 仍是唯一证据 authority；Radix Collapsible 因 CSP 拒绝并移除，无 URL mapper 或受控状态适配层 |
| shadcn/ui | Sidebar / https://ui.shadcn.com/docs/components/base/sidebar、https://ui.shadcn.com/r/styles/new-york-v4/sidebar.json | MIT | vendored upstream presentation source | `desktop/src/components/ui/sidebar.tsx` | 采用 data-slot/anatomy/MenuButton cva；删除旧 primitives/CSS；不复制 Provider 状态，保留 Core-only 导航与 `<nav>` landmark |
| shadcn/ui + Radix | Select / Switch / Toolbar | MIT | vendored anatomy + official primitives | `desktop/src/components/ui/select.tsx`、`switch.tsx`、`toolbar.tsx` | 直接采用 compound API、Switch state 和 Toolbar roving focus；删除 option/event 兼容层 |
| Zag | Tree View / https://zagjs.com/components/react/tree-view | MIT | exact npm dependency + Host-owned DOM/CSS | `desktop/src/components/ui/tree.tsx`、`host.ui@1.0.0`、Workspace/GitHub DLC | 采用状态机；剥离 `--depth` inline style；直接消费领域对象。React Aria 因 mandatory inline style/CSP、Headless Tree 因 Beta、MUI/rc-tree/Arborist 因 styling/virtualization/依赖成本未采用 |
| TanStack | Table v8 / Virtual v3 | MIT | 已有依赖直接复用 | `ArtifactTableGrid.tsx` 与 Data DLC grids | 不迁移 v9；补 `aria-rowcount`、`aria-colcount`、`aria-sort` 和 cell keyboard test；无 mapper |
| react-resizable-panels + Radix | Group/Panel/Separator + Tabs | MIT | 已有依赖直接复用 | `components/ui/resizable.tsx`、`ResizableWorkspaceLayout.tsx`、`ConversationWorkspaceLayout.tsx`、`WorkspaceDock.tsx` | 删除自研 Dock resizer；唯一 store authority 不变；Tabs 直接生成 roving focus 与 panel 语义 |

源文件中对实际复制或结构性改写的部分保留上游链接与许可证说明。纯行为参考不复制源码。

## 9. 风险、债务与退出条件

- **新增依赖：** `class-variance-authority@0.7.1`、`@radix-ui/react-progress@1.1.16`、`@radix-ui/react-toolbar@1.1.19`、`@radix-ui/react-switch@1.3.7`、`react-json-view-lite@2.5.0`、`@zag-js/tree-view@1.43.3`、`@zag-js/react@1.43.3`。均为已采用源码直接需要的 utility/primitive/runtime，不引入新主题或 Agent runtime；`@radix-ui/react-collapsible` 经实测拒绝并移除，首屏 bundle gate 已通过。
- **新增兼容层/mapper：无。** 所有适配发生在真实 UI 边界，直接消费现有权威 props/store。
- **迁移债务：无双实现长期并存。** 旧 Composer/Plan presentation、Workspace/GitHub 手写文件行和 Data `ProfileGroup`/`DatabaseRow` presentation 已删除；Host Tree 直接承载同步与异步路径。
- **主要风险：** 从外部组件移植交互时可能遗漏 focus、composition event、reduced-motion 或长文本状态；用单测、axe、Design Lab 视觉矩阵和生产构建约束验证。
- **清理条件：** Design Lab 候选在决策落地后保留为可回归的 provenance 场景，但若不再用于比较，应删除候选专用 CSS/代码，不能被其他模块依赖。

## 10. 实施门禁

生产接入前必须先在 Design Lab 同屏展示真实上游候选并使用同一 fixture 覆盖；若候选无法运行，记录
依赖/runtime 冲突并 REJECT，不得手写替身填充 A/B/C：

- light / dark；中文 / English；
- 1280×800、1440×900；125%、150%；
- idle、focused、disabled、loading、error、running、long content；
- keyboard-only focus、Enter/Shift+Enter、disclosure、resize；
- reduced-motion。

通过比较后，生产只接入本评审表中标记为 ADAPT/KEEP 的部分。验证证据和最终实际采用情况记录在 `docs/ui/component-adoption-report.md`。

## 11. 补充盘点：基础 Primitive 与 Overlay

本节补齐首次评审中过于概括的按钮、字段、菜单、弹层和选择器。DBFox 已经使用 Radix、cmdk、
react-hook-form 和 zod，候选必须证明能解决现有能力缺口，不能只因视觉示例更多而引入第二套 runtime。

| 候选 | 成熟能力 | 集成与退出成本 | 决策 |
| --- | --- | --- | --- |
| 当前 Radix Primitives | Dialog、Dropdown、Popover、Tooltip、Tabs、Select；focus、keyboard、typeahead、portal 和 collision handling | 已有依赖和本地样式；无新增事实源 | **ADOPT/KEEP** |
| Base UI | headless Dialog/Popover/Select；文档明确 focus 与 Select/Combobox 分工 | 与 Radix 功能重叠；替换会改动所有 overlay 行为 | REFERENCE ONLY |
| React Aria / Spectrum | 完整键盘、locale、collection 与表单语义 | runtime/theme 较大，collection model 会形成第二数据模型 | REFERENCE ONLY |
| Fluent UI React | Windows 交互语言、Field/Menu/Toolbar/Switch anatomy 完整 | 引入另一套 token、slot 和 styling runtime | REFERENCE ONLY |
| Ariakit | ComboBox/Menu/Dialog 的 headless API 与 a11y 参考 | 与 cmdk/Radix 重叠 | REFERENCE ONLY |

参考：

- Radix components / accessibility：https://www.radix-ui.com/primitives/docs/components 、https://www.radix-ui.com/primitives/docs/overview/accessibility
- Base UI Dialog / Popover / Select：https://base-ui.com/react/components/dialog 、https://base-ui.com/react/components/popover 、https://base-ui.com/react/components/select
- Ariakit Combobox：https://ariakit.org/reference/combobox
- Fluent React components：https://fluent2.microsoft.design/components/web/react/

逐 primitive 结论：

- Button/IconButton：保留本地 variants，补 loading、icon-only name、danger 与 focus fixture；不装新库。
- Dialog/Popover/Menu/Tooltip：保留 Radix；Command Palette 已删除自研 overlay，直接把既有 cmdk 放入 Radix Dialog，由 primitive 统一负责 focus trap、Escape、outside dismiss 和焦点恢复。
- Select：有限固定选项已直接采用 Radix compound API，旧 `<option>` 解析和伪造 ChangeEvent 已删除；需要搜索的长集合使用现有 cmdk composition，不把 Select 伪装成 autocomplete。
- Checkbox/Radio/Switch：设置即时二元选项已采用 Radix Switch；需提交的选择继续 checkbox/radio。
- ScrollArea/Resizable：保留现有 Radix/react-resizable-panels；补键盘、缩放和高对比度验收。

## 12. 补充盘点：反馈、空态、加载与错误

### 12.1 Surface feedback

| 候选 | 关键模式 | 风险 | 决策 |
| --- | --- | --- | --- |
| 旧 `EmptyState/ErrorState/LoadingState/Skeleton` | 已在 App 内使用，直接消费业务状态 | 自研 presentation 与重复 CSS，不符合真实组件采用要求 | **REPLACE** |
| shadcn Empty / Alert / Spinner / Skeleton | MIT registry source；composition、slot 和状态原语可独立采用 | 无第二 runtime；EmptyMedia 使用 `class-variance-authority` | **ADOPT（已接入）** |
| Fluent Message Bar / Toast | Message Bar 留在相关表面；Toast 只做短暂非关键反馈；错误/警告带恢复动作 | 引入 Fluent 组件会重复 token/runtime | **ADAPT anatomy** |
| Carbon Notification | inline/actionable/toast 变体；错误信息包含下一步 | Carbon runtime/视觉不匹配 | **ADAPT anatomy** |
| Primer Blank Slate | visual、heading、description、primary/secondary action 的稳定结构 | 只覆盖空态，不是错误合同 | **ADAPT anatomy** |
| Atlassian Empty State | first use/no result/permission 等原因驱动的空态 | 引入组件会重复基础层 | REFERENCE ONLY |
| Radix/shadcn Progress | Radix WAI-ARIA primitive + shadcn registry source；可分离、MIT、与已有 Radix 栈一致 | 上游 shadcn 使用 inline transform，需适配 Electron CSP | **ADOPT（已接入）** |
| Radix Collapsible | 成熟 disclosure primitive、MIT、键盘与 ARIA 完整 | `Collapsible.Content` 在运行时写入尺寸 CSS variables，违反业务组件无任意 inline layout 合同 | **REJECT（严格 disclosure 边界；依赖已移除）** |
| HTML `details` / `summary` | WHATWG 原生 disclosure；Chromium 直接提供展开状态、键盘与可访问语义 | 视觉需使用静态 token CSS；不能滥用于非 disclosure 控件 | **ADOPT（ErrorDetails 与 Sources 已接入）** |
| PatternFly Progress / Stepper | determinate/indeterminate、status、helper text、ARIA 进度 | 整套视觉/runtime 不同；启动阶段也无可信步骤百分比 | REFERENCE ONLY |

参考：

- Fluent Toast / Message Bar：https://fluent2.microsoft.design/components/web/react/core/toast/usage 、https://fluent2.microsoft.design/components/web/react/core/messagebar/usage
- Carbon Notification：https://carbondesignsystem.com/components/notification/usage/
- Primer Blank Slate：https://primer.style/product/components/blankslate/
- shadcn Empty / Alert / Spinner / Skeleton：https://ui.shadcn.com/docs/components/base/empty 、https://ui.shadcn.com/docs/components/base/alert 、https://ui.shadcn.com/docs/components/base/spinner 、https://ui.shadcn.com/docs/components/base/skeleton
- Atlassian Empty State：https://atlassian.design/components/empty-state
- PatternFly Progress / Progress Stepper：https://www.patternfly.org/components/progress/ 、https://pf6.patternfly.org/components/progress-stepper/
- Radix Progress / shadcn Progress：https://www.radix-ui.com/primitives/docs/components/progress 、https://ui.shadcn.com/docs/components/base/progress
- Radix Collapsible / WHATWG disclosure：https://www.radix-ui.com/primitives/docs/components/collapsible 、https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element

### 12.2 DBFox 错误 anatomy

采用现有 RFC 9457 `ProblemDetails`，不创建 UI Error DTO：

1. **标题**：用户语言说明哪个表面失败；
2. **说明**：原因、影响范围、已完成内容；
3. **主恢复动作**：重试、刷新、打开设置、重启 Engine 或打开日志，只出现当前真正可执行的动作；
4. **技术详情 disclosure**：`code`、`request_id`、安全的 checks/errors；
5. **状态保留**：表单输入、旧结果和已完成步骤不因错误被清空。

错误卡片不是新增 service/mapper。通用 presentation 已由 shadcn `Alert`/`AlertTitle`/`AlertDescription`
接管；`SettingsStatus` 只组合产品状态，业务特有错误直接在本组件呈现。DLC render exception 仅写诊断日志，
用户表面显示安全通用文案，不把原始异常或秘密带到公开错误消息。

生产 `ErrorDetails` 直接读取现有 `ApiError`/RFC 9457 payload，只白名单化显示 HTTP status、稳定 code、
request ID 与 checks/errors 数量，不复制错误数据模型，也不渲染原始 detail 或检查内容。Diagnostics、
DLC、Projects/Resources、Conversation、Approval/Question、Model/Update 与 Table/Chart 已接入；结果失败
继续保留上次成功数据或当前输入。真实 Chromium 发现 Radix Content 的 runtime style attribute 与 CSP
冲突后，ErrorDetails 和 Sources 统一改用 WHATWG `details/summary`，并移除 Collapsible 依赖，未增加兼容层。

### 12.3 Toast、Banner 与 Inline 的边界

| 反馈 | 使用场景 | 禁止场景 |
| --- | --- | --- |
| Toast | 保存成功、复制成功、非关键后台完成 | 需要用户立即处理、需要保留 request id、持续故障 |
| Surface message | 当前页面/面板仍可使用但部分失败 | 全应用不可启动 |
| Inline field error | 单字段输入与约束 | 网络失败或跨字段系统错误 |
| Blocking state | 当前表面没有可用内容 | 仍有旧数据可安全阅读时覆盖全部内容 |
| Fatal gate | Engine/React 无法继续 | 单 DLC、单 Artifact 或单请求失败 |

## 13. 补充盘点：设置、表单、Toolbar、Tabs 与状态标签

| 类别 | 候选 | 结论 |
| --- | --- | --- |
| Field / helper / validation | shadcn Field registry；当前 `SettingsField` + react-hook-form/zod；Fluent Field；React Aria forms | **ADOPT shadcn Field compound source**；Settings/Project 表单使用统一 label/helper/error anatomy，不新增 schema、mapper 或 form runtime |
| Toggle | 当前 `SettingsToggle` copy layout；Fluent Switch；Radix Switch/shadcn | **ADOPT Radix/shadcn Switch runtime**；SettingsToggle 仅保留产品 label/description composition |
| Action bar | 当前 `SettingsActionBar`；Carbon/Fluent form footer；Atlassian modal footer | **KEEP + REFINE** dirty/saving/error/saved；避免每页自建 footer |
| Status / Badge / Tag | 当前 Badge/SettingsStatus；Fluent Tag；Carbon Tag | **KEEP**；状态必须带文字，Tag 不承担 alert |
| Toolbar | artifact toolbar；Radix Toolbar；Fluent/React Aria Toolbar | **ADOPT Radix Toolbar roving focus**；方向键合同已测，overflow/no-wrap 继续浏览器验收 |
| Tabs | 当前 Radix Tabs；Fluent TabList；React Aria Tabs | **KEEP**；补 overflow、closable、dirty、键盘与关闭后焦点 |
| Command / autocomplete | 当前 cmdk + Radix Dialog；shadcn Command；Ariakit ComboBox；React Spectrum ComboBox | **ADOPT existing cmdk + Radix Dialog composition**；删除自研 modal overlay，不引入第二 collection model |

参考：

- Fluent Field / Switch / Toolbar / TabList / Tag：
  https://fluent2.microsoft.design/components/web/react/core/field/usage 、
  https://fluent2.microsoft.design/components/web/react/core/switch/usage 、
  https://fluent2.microsoft.design/components/web/react/core/toolbar/usage 、
  https://fluent2.microsoft.design/components/web/react/core/tablist/usage 、
  https://fluent2.microsoft.design/components/web/react/core/tag/usage
- React Spectrum ComboBox：https://react-spectrum.adobe.com/ComboBox
- shadcn Field：https://ui.shadcn.com/docs/components/radix/field
- shadcn Command：https://ui.shadcn.com/docs/components/radix/command

## 14. 补充盘点：Tree、日志、代码、Diff、JSON 与数据预览

### 14.1 Tree 与资源导航

| 候选 | 能力 | 决策 |
| --- | --- | --- |
| Host `ui.Tree` + Workspace/GitHub | Zag 状态机提供 collection、层级 ARIA、selection、expansion、roving focus、typeahead；DLC 保留真实 authority | **ADOPTED PRODUCTION** |
| Data Catalog tree | 真实连接、catalog lazy load、节点动作、分页与错误恢复直接组合 Host Tree | **ADOPTED PRODUCTION；KEEP DATA CONTRACT** |
| Fluent Tree | flat/nested、single/multi select、checkbox 和 action anatomy | **ADAPT behavior** |
| Zag Tree View | collection、keyboard、selection、lazy loading/error callback；可拆 Host DOM/CSS | **ADOPT HOST RUNTIME** |
| React Aria Components Tree | collection、keyboard、selection、loading、virtualization；当前源码写 inline node style | **REJECT CURRENT CSP** |
| Headless Tree | headless collection、async children、keyboard、virtualization adapter | CANDIDATE；Beta 信号未消除 |
| WAI-ARIA APG Treeview | 官方 keyboard/focus 交互基线 | **ADOPT behavior/test** |

树节点的 loading/error 必须局部呈现，不能因一个目录失败替换整棵树；active selection、focus、expanded
三种状态需要同时可辨。参考：https://fluent2.microsoft.design/components/web/react/core/tree/usage

### 14.2 SQL / Code editor

| 候选 | 能力与成本 | 决策 |
| --- | --- | --- |
| 当前 CodeMirror 6 | 已有模块化 extension、SQL 编辑与 autocomplete 基础；包体可控 | **ADOPT/KEEP** |
| Monaco Editor | 强编辑器、diff、大文件和 accessibility；同时带来显著 worker/语言/bundle/runtime 成本 | REJECT（当前）；REFERENCE（a11y/diff） |
| Shiki | 高质量只读语法高亮，可输出 token/html | REFERENCE ONLY；当前为少量只读块不值得新增 WASM/theme/language 管理 |
| PatternFly Code Editor | Monaco-based composition 和无障碍示例 | REFERENCE ONLY |

参考：

- CodeMirror extensions / autocomplete：https://codemirror.com/docs/extensions/ 、https://codemirror.com/examples/autocompletion/
- Monaco accessibility：https://github.com/microsoft/monaco-editor/wiki/Monaco-Editor-Accessibility-Guide
- Shiki：https://shiki.style/guide/install
- PatternFly Code Editor accessibility：https://www.patternfly.org/components/code-editor/accessibility

### 14.3 Diff、JSON、Cell preview

| 类别 | 候选 | 决策 |
| --- | --- | --- |
| JSON | 当前 `JsonTree`；`react-json-view-lite@2.5.0`；`@uiw/react-json-view`；Storybook react-inspector；json-edit-react | **ADOPT react-json-view-lite**：MIT、React 18/19、零依赖、内建 tree/keyboard/ARIA；DBFox 只保留 class map 与有界展开策略。其余候选因 inline style/CSP 冲突或编辑能力过重而拒绝 |
| Diff | 当前 file/artifact view；Monaco Diff；`react-diff-viewer` | Monaco 过重；react-diff-viewer 维护活跃度不足；**REFERENCE ONLY** |
| Cell preview | 当前 `CellValuePreview`；AG Grid cell viewer；Spectrum TableView patterns | 保留当前 authority/类型分发；补 null/binary/JSON/image/truncated/copy error |
| Log viewer | 当前 `DiagnosticsPage`；PatternFly Log Viewer 6.5；Grafana Explore；Monaco readonly | **ADAPT mature anatomy**：搜索、级别筛选、换行、命中状态、逐行复制/诊断包下载、empty/error 已进入生产；PatternFly 包约 5.4 MB unpacked 且依赖完整 Core/Icons/Styles，当前 300 行上限不值得引入第二 UI 栈；不引入 Monaco |

参考：

- `@uiw/react-json-view`：https://github.com/uiwjs/react-json-view
- `react-json-view-lite`：https://github.com/AnyRoad/react-json-view-lite
- Storybook react-inspector：https://github.com/storybookjs/react-inspector
- json-edit-react：https://github.com/CarlosNZ/json-edit-react
- react-diff-viewer：https://github.com/praneshr/react-diff-viewer
- PatternFly Log Viewer：https://www.patternfly.org/extensions/log-viewer/html

任何新 JSON/Diff 包在采用前必须补：维护状态、bundle 增量、深层/大值安全、复制敏感信息边界、
许可证和键盘覆盖。`react-json-view-lite` 已通过这些门禁；Diff 依赖仍未达到引入门槛。

## 15. 补充盘点：图表、图片与 Artifact Work Surface

| 类别 | 候选 | 结论 |
| --- | --- | --- |
| Chart runtime | Vega-Lite；restricted Vega；ECharts；Recharts | **ADOPT Vega-Lite + restricted Vega**：Visualization DLC 持有安全声明式 grammar 与 lazy vendor boundary；Host 只提供 Artifact/Representation/View 运行面，不保留第二套 ECharts 新建链路 |
| Chart fallback | Host DataFrame Table View；Fluent/Carbon data viz a11y guidance | **ADAPT**：无数据、无效配置、过多点、resize error 与 accessible data table；数据读取复用通用 Representation 生命周期 |
| Image preview | 当前 `ImageCell`；Radix Dialog/HoverCard；Yet Another React Lightbox 3.32.2 + Zoom；react-zoom-pan-pinch 4.0.4；react-medium-image-zoom 5.4.9 | **ADAPT mature anatomy**：保留现有 overlay/HTTPS/Host 边界，采用 shadcn Button、静态 CSS zoom levels 和原生 overflow/方向键。三套候选虽成熟且 React 19 可用，但都运行时写 inline style/transform；YARL 还重复 portal/dialog/no-scroll，故不适配当前 CSP 和单 overlay authority |
| Dock tabs/layout | `ConversationWorkspaceLayout` + `WorkspaceDock`；react-resizable-panels；Radix Tabs/DropdownMenu；Dockview；FlexLayout | **ADOPT existing mature primitives**；自研 resize 已删除，overflow 继续由 Radix menu 暴露，关闭后焦点恢复到 workspaceStore 选出的活动 Radix trigger；完整 docking runtime 仍 REJECT |
| Unknown artifact | 当前 renderer fallback；DLC boundary；generic JSON renderer | 保留 type/schema error；禁止把未知 Artifact 悄悄降级成不可信 JSON |

Work Surface 不再另选 docking 框架：伸缩与 tab semantics 已由成熟现有依赖接管；后续验收聚焦
tab overflow、关闭后焦点、DLC renderer 异常隔离、Artifact stale/unsupported 和窄宽度工具栏行为。

图片预览没有因为“成熟包存在”就盲目加依赖。包源审查确认：`react-zoom-pan-pinch` 的 content
transform、YARL Zoom 的 scale/translate 和 `react-medium-image-zoom` 的定位计算都通过 inline style
落 DOM；这与 DBFox 业务组件无任意运行时样式属性门禁冲突。采用的 CSS `zoom` 已是
Baseline 2024，且 DBFox 生产只面向固定 Electron Chromium；若未来浏览器支持范围变化，按当前
离散 class 合同验证或退出，不放宽 CSP。

## 16. 补充盘点：启动、更新、诊断与 DLC 生命周期

| 领域 | 现有能力 | 调研参照 | 决策 |
| --- | --- | --- | --- |
| Engine startup/recovery | `EngineStartupGate` + Electron supervisor | shadcn Empty/Alert/Spinner、Radix Progress、Fluent MessageBar | **KEEP authority + ADOPT presentation**；阶段文本、indeterminate progress、重启/日志/技术详情已接入 |
| Fatal error | React `ErrorBoundary` | Fluent/Carbon blocking error anatomy、shadcn Empty | **KEEP boundary + ADOPT presentation**；真实 Empty/Button fallback 已接入，“重试渲染”与实际行为一致，不装错误 UI runtime |
| DLC lifecycle | installed disabled、enable pending restart、active、disable pending restart、activation failed | progress/status/notification patterns | **KEEP authority + ADAPT presentation** |
| Update | check/download/progress/install/restart | Fluent progress、PatternFly progress | **ADAPT behavior**；不新增 updater 状态机 |
| Diagnostics | grouped logs、fallback frontend logs、audit clear | PatternFly Log Viewer、Grafana Explore | **ADAPT anatomy DONE**：search/level/wrap/count/copy；保留 300 行、脱敏和 Host export authority |

Progress indicator 不创造百分比。只有 updater/transcription 等有真实数值时使用 determinate；Engine health
check、DLC activation 等未知时间使用 indeterminate 并显示阶段文本。

## 17. 补充盘点：Music 专业组件

### 17.1 音频波形与 Transport

| 候选 | 能力 | 成本/风险 | 决策 |
| --- | --- | --- | --- |
| 当前 Web Audio + SVG waveform | 与内存 buffer 和转录状态直接绑定，依赖最小 | 当前波形仅固定采样，缺 zoom/seek/segment/keyboard | **KEEP for current scope + REFINE** |
| Wavesurfer.js | 成熟 waveform、regions/timeline/minimap plugins | 新 runtime、canvas/media 生命周期和 bundle；需适配现有 AudioBuffer authority | CANDIDATE A，仅在需要 seek/zoom/regions 时采用 |
| BBC Peaks.js | overview+zoom、segments/points、keyboard/API 成熟 | 开发已迁移 Codeberg；集成比当前需求重 | CANDIDATE B / REFERENCE |
| Media Chrome | framework-compatible Web Components media controls | 适合标准 media element，当前 playback 由 Web Audio/合成器驱动 | REJECT（当前） |

参考：Wavesurfer https://wavesurfer.xyz/docs/ 、Peaks.js
https://github.com/bbc/peaks.js/blob/master/README.md 、Media Chrome
https://github.com/muxinc/media-chrome/blob/main/README.md

采用门槛：产品确实需要用户 seek、zoom、选择区间或标注 uncertain range；否则继续改进本地 SVG，
避免为静态波形引入完整播放器。若采用，只在 Music DLC 的真实边界内使用，不进入 Core。

### 17.2 乐谱

| 候选 | 能力 | 决策 |
| --- | --- | --- |
| 当前 VexFlow 5 | 已有依赖和许可证处理；直接渲染 DBFox score document | **ADOPT/KEEP** |
| OpenSheetMusicDisplay | MusicXML renderer，内部基于 VexFlow；适合 MusicXML 输入 | REJECT（当前）；当 MusicXML 成为权威输入需求时重评 |
| 自建 SVG notation | 会重复成熟 engraving/layout 能力 | REJECT |

OSMD 参考：https://github.com/opensheetmusicdisplay/opensheetmusicdisplay 。当前 DBFox 内部 score document
不是 MusicXML，接入 OSMD 需要额外双向映射和第二事实源，违反架构克制。

### 17.3 钢琴键盘

| 候选 | 能力与风险 | 决策 |
| --- | --- | --- |
| 当前 SVG piano keys | 已直接绑定 Music DLC note authority；每个 key 已有焦点、Enter/Space 与非颜色 active state | **KEEP specialized control**；继续以 keyboard fixture 验证 |
| `react-piano` | MIT、提供键盘与 MIDI 风格交互；但公开实现仍以 React 16 时代构建为主，依赖与当前 React 19/Electron 栈不匹配，未提供足够的现代无障碍证据 | REJECT（当前） |
| AudioUI piano keys | 明确强调 accessible piano keys，但仍是 developer preview，且 GPL/commercial 许可证与当前分发约束不匹配 | REJECT |

参考：`react-piano` https://github.com/kevinsqi/react-piano ，AudioUI
https://github.com/cutoff/audio-ui 。本项不是“因已有实现而保留”：候选在兼容性、成熟度或许可证上均未达到替换门槛。

### 17.4 Music 当前必须补的状态

- Score loading/error/retry、播放/暂停/停止/loop/ended；
- measure active/selected/uncertain/focus 的非颜色表达；
- 原音频 buffer 丢失、转录模型加载、determinate progress、取消、无音符、失败；
- waveform no-buffer/ready/playing、A/B 当前播放源；
- 88 键大量 tab stops 的键盘策略；
- score/transcription Artifact failed/stale/schema unsupported。

## 18. 扩展后的统一决策

### 18.1 直接复用

- Radix primitives、cmdk、react-hook-form/zod；
- Chromium 原生 `<dialog>`、radio/fieldset 与 button 语义（DLC 无包导入边界）；
- TanStack Query v5、Table v8、Virtual v3；
- CodeMirror 6；
- react-resizable-panels；
- Visualization DLC 内固定版本的 Vega-Lite、Vega 与 `vega-interpreter`；
- VexFlow 5 与既有 Web Audio 边界。

### 18.2 最小适配

- Fluent/Carbon 的 surface feedback 与 Toolbar anatomy；shadcn Field compound source；
- shadcn Empty/Alert/Spinner/Skeleton 源码与 Radix/shadcn Progress；
- Primer/Atlassian 的原因驱动空态；
- PatternFly 的 Progress Stepper、Code Editor a11y 和 Log Viewer 行为；
- WAI-ARIA/React Spectrum/Fluent 的 Tree 键盘与状态测试；
- Wavesurfer/Peaks 只作为 Music 波形需求升级时的候选，不预装。

### 18.3 明确拒绝

- 第二套基础组件 runtime/theme：Fluent UI、React Spectrum、Base UI、Ariakit 全量接入；
- 第二套编辑器/数据模型：Monaco、完整 docking、另一套 grid/chart grammar；
- 只为视觉效果引入 Web Font、loader 库或 Uiverse CSS；
- 未证明维护和大数据安全的 JSON/Diff 依赖；
- 为 OSMD 引入 MusicXML ↔ 内部 score document 双向映射。

前一轮 UI 重构新增生产依赖为 **7 个经核验的 UI 依赖**：`class-variance-authority@0.7.1`、
`@radix-ui/react-progress@1.1.16`、`@radix-ui/react-toolbar@1.1.19`、`@radix-ui/react-switch@1.3.7`、
`react-json-view-lite@2.5.0`、`@zag-js/tree-view@1.43.3` 与 `@zag-js/react@1.43.3`；
`@radix-ui/react-collapsible` 不在最终依赖中。本轮 Visualization DLC 另新增精确固定的
`vega@6.4.0`、`vega-lite@6.4.3` 与 `vega-interpreter@2.3.2`，通过离线 vendor 构建、许可证清单、
禁止网络 loader 和 AST interpreter 合同约束。`vega-tooltip` 经实现审计后拒绝：其默认实现注入
style 标签并使用自有 HTML/定位生命周期；inline style element 已由生产 CSP 禁止，且它会扩大审计
面。交互详情改用 Vega View 的官方 tooltip 回调投影到 DLC 自身的可访问 React surface。Vega
Canvas/SVG renderer 的有界 presentation attribute 是唯一明确记录的例外。新增 mapper/兼容层仍为 **0**；
外部方案不改变 Engine、Agent、Artifact、DLC 或资源 authority。

## 19. 下一阶段 Design Lab 覆盖表

| Lab 组 | Current / 候选 | 必测 fixture |
| --- | --- | --- |
| Feedback | 当前 State / Fluent anatomy / Carbon anatomy / Primer empty | inline/section/page、retry、details、long error、request id |
| Plan | 当前 / Agent Elements / PatternFly stepper / Carbon progress | blocked/skipped/waiting/fail/cancel、long plan、determinate |
| Forms | 当前 Settings / Fluent Field / Base UI anatomy / Spectrum reference | helper/error/dirty/saving、keyboard、long Chinese |
| Toolbar/Tabs | 当前 / Fluent / React Aria / compact overflow | 720px surface、overflow、closable、focus return |
| Tree | 当前 / Fluent / Spectrum / APG behavior | lazy child/error/deep/long/keyboard |
| Data preview | 当前 JSON/cell / uiw reference / log viewer / diff reference | deep/large/null/binary/truncated/copy fail |
| Startup/DLC | 当前 gates / surface message variants | recover/migrate/fail/pending restart/activation fail |
| Music | 当前 SVG / Wavesurfer spike / Peaks reference | no buffer/seek/zoom/uncertain/playback/progress |
| Typography | 当前 ramp / role consolidation candidates | 中英/数字/SQL/error、themes/density/scales/high contrast |

在这些组完成同数据比较和采用记录之前，不恢复大范围生产施工。
