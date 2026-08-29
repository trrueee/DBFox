# DBFox UI 组件采用报告

> 文档类型：UI 调研与采用报告
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 对应评审：[`component-market-review.md`](component-market-review.md)

> 2026-08-27 扩展审计说明：用户要求补齐此前未覆盖的大小组件、运行时状态、
> 字体/字号/颜色和错误协同设计，并进一步明确：必须采用真实成熟组件源码；即使已有自研实现也默认替换。
> 该调研基线记录在
> [`ui-runtime-inventory.md`](ui-runtime-inventory.md)、
> [`typography-color-audit.md`](typography-color-audit.md) 和
> [`plan-error-design.md`](plan-error-design.md)。下表只记录已经核验来源、许可证、runtime 边界并实际进入
> 生产的组件；尚未覆盖的真实辅助技术状态继续显式保留，不以 accessibility tree 或手写替身冒充。

## 1. 结果

本轮实现按已归档的[UI 市场驱动重构任务](../archive/reviews/ui-market-driven-refactor-task.md)执行
“先调查、核验源码和许可证、再替换”。新增的
npm 依赖只有上游源码直接需要的 UI utility/primitive，同时实际 vendoring 经核验的上游组件源码；
没有引入第二套 Agent Runtime、布局状态机、
镜像数据模型或兼容层。

最终采用：

| 范围 | 决策 | 实际变化 |
| --- | --- | --- |
| Composer | **ADOPT Prompt Kit + AI Elements 源码** | `UnifiedComposer` 直接组合 vendored `PromptInput` primitives 与 `PromptInputSubmit`；同一个主操作按钮在空 draft 的运行态停止，在有 draft 时按 Queue/Steer/Cancel-and-replace 发送；DBFox 只保留权威 props、引用和投递合同 |
| ToolGroup | **ADOPT Agent Elements ToolGroup / GenericTool 源码** | 用真实上游 disclosure、ToolRowBase、状态、elapsed 和 bounded live-list anatomy 替换旧 `<details>`；直接消费 Timeline 的 `FunctionCallItem` / `FunctionCallOutputItem`，不引入 AI SDK `part`、tool registry 或模拟流状态 |
| Plan | **ADOPT Agent Elements PlanTool + TodoTool 源码** | 用真实上游 card/disclosure/todo status anatomy 替换旧 Plan；直接消费 `PlanItem`，扩展 blocked/skipped、summary、终态文案和 Lucide 图标；完成证据直接选择现有 Artifact，缺失证据明确显示，不建立 AI SDK `part` mapper |
| Empty / Error / Loading / Skeleton | **ADOPT shadcn registry 源码** | Empty、Alert、Spinner、Skeleton 接管生产呈现；旧 `state.css` 删除；现有 `title/description/action` 仅作为产品组合合同保留 |
| Engine startup / recovery | **ADOPT shadcn Empty/Alert/Spinner + Radix Progress** | 启动使用 CSP-safe indeterminate progress，失败使用带恢复动作的 Alert；保留 Electron supervisor、generation、retry、日志和错误码合同 |
| Typography / default colors | **ADOPT Fluent 2 tokens** | 字号/行高/字体角色与默认 light/dark semantic colors 采用 Fluent 官方值；拆分 brand foreground/fill 和 danger foreground/fill；可选 accent/warm 使用 Tailwind 官方色阶 |
| Approval | **ADOPT AI Elements Confirmation 源码** | 真实 compound-component request/accepted/rejected/actions anatomy 接管待审批与审计呈现；直接消费 `ApprovalItem`，不引入 `ToolUIPart`；提交态暴露 `aria-busy`，默认焦点落在更安全的“拒绝”操作 |
| Question | **ADOPT Agent Elements QuestionTool / QuestionPrompt 源码 + Radix RadioGroup** | 真实 question header、编号、字母选项、说明和 action anatomy 替换旧卡片；直接消费单个 durable `QuestionItem`，保留 Radix 单选键盘语义，不复制上游多页答案 registry |
| Conversation stream feedback | **ADOPT shadcn Alert/Spinner；KEEP production SSE runtime** | connecting/live/reconnecting/recovering_snapshot/recovered/failed 由现有 stream runtime 投影；临时断线、409 游标恢复与终止错误分层呈现。mutation 失败后只读刷新且提交恰好一次，不增加 replay、第二连接状态机或全局错误事实源 |
| Message | **ADOPT AI Elements Message presentation source** | User/Assistant Timeline 使用真实 `Message` / `MessageContent` anatomy；继续复用现有 `react-markdown + remark-gfm + rehype-sanitize` 安全管线，不引入 Streamdown、AI SDK 消息类型或第二套 Markdown runtime |
| Evidence / Sources | **ADOPT AI Elements Sources anatomy + HTML disclosure** | 引用与已保存结果保留真实 `Sources` / `SourcesTrigger` / `SourcesContent` compound anatomy，折叠 runtime 改由 Chromium 原生 `details/summary` 管理；内部按钮仍直接选择 DBFox Artifact，不把耐久证据降级为 URL citation，不增加 evidence DTO 或兼容状态 |
| Sidebar | **ADOPT shadcn Sidebar presentation source** | Header/Content/Footer/Group/MenuButton 的真实 registry anatomy 进入 `components/ui/sidebar.tsx`；删除旧自定义 primitives/CSS；DBFox 继续唯一拥有折叠与像素宽度，根节点使用 `<nav>` 补足上游当前 landmark 缺口 |
| Select / Toolbar / Switch | **ADOPT shadcn/Radix composition** | 删除 Select 的 `<option>` 解析兼容层与伪造 change event；生产调用方直接使用 `Root/Trigger/Content/Item`。结果 Toolbar 使用 Radix roving focus，设置 Toggle 使用 Radix Switch；状态与键盘由上游 primitive 管理 |
| Field / validation | **ADOPT shadcn Field compound source** | `SettingsField` 与项目创建表单使用真实 Field/Label/Description/Error anatomy；原生 control 直接获得 `label`/`aria-describedby`，Radix Select trigger 显式关联 helper text；删除对任意 React child 的盲目 ARIA clone，不新增表单 schema |
| Command / Dialog | **ADOPT cmdk inside existing Radix Dialog** | Command Palette 保留唯一 cmdk collection/model，但把旧 click-overlay 删除；Radix 负责 modal focus trap、Escape、outside dismiss 与关闭后焦点恢复，cmdk 继续负责查询、结果与键盘选择 |
| DLC platform controls | **ADOPT native platform semantics at package-free boundary** | Data connection 使用 `<dialog>.showModal()`、`::backdrop`、原生 radio/fieldset；错误关闭、Escape 和焦点恢复交给 Chromium。GitHub 删除嵌套 interactive，Music measure 使用原生 button；伪 Toolbar 降为 group，避免声称不存在的 roving keyboard |
| Tree | **ADOPT Zag Tree View at Host SDK boundary + official virtualized contract；REJECT per-DLC runtime** | `@zag-js/tree-view@1.43.3` + `@zag-js/react@1.43.3` 成为 `host.ui@1.0.0` 的 Tree 状态机；Workspace、GitHub 与 Data 均已迁移，获得 tree/treeitem/group、roving focus、方向键、typeahead、selection、expansion，以及官方 async children/loading/error 回调。超过 100 个 visible nodes 时直接使用 Zag `getVisibleNodes()` / `scrollToIndexFn` 与已有 TanStack Virtual；Host 只接管 DOM/CSS，并通过既有 CSSOM 边界移除 inline layout；Data 保留原 catalog API、分页、刷新和 Dock 动作，无 Resource DTO 或第二状态源 |
| DataGrid | **ADOPT/KEEP TanStack Table v8 + Virtual v3** | 生产 Grid 继续直接使用成熟 headless 引擎；补齐 `aria-rowcount`、`aria-colcount`、`aria-sort` 与单元格方向键验证；不迁移 ReUI 的 TanStack v9，不新增表格引擎或 mapper |
| Work Surface | **ADOPT react-resizable-panels + Radix Tabs** | 主导航和右侧 Dock 统一由 `react-resizable-panels` 处理 pointer、键盘与 separator ARIA；Dock 标签采用 Radix roving tab/tabpanel；关闭标签后焦点回到 store 选出的真实活动 trigger；旧自研 Dock resize 代码删除，不引入 Dockview/FlexLayout/Golden Layout 或第二份布局状态 |
| JSON / Cell preview | **ADOPT react-json-view-lite；KEEP classification authority** | 以 `react-json-view-lite@2.5.0` 替换递归 `useState` 自绘树；获得 tree/ARIA、方向键、中文展开标签和大数据性能基础。DBFox 只保留 semantic classes 与两层/24 子项默认展开门槛；`classifyCellValue`、复制文本和 Dialog/HoverCard 合同不变 |
| Fatal error | **ADOPT shadcn Empty + Button composition** | `ErrorBoundary` 继续作为唯一 React 错误边界；默认 fallback 改为真实 Empty anatomy，敏感错误只写诊断日志；原先未实际 reload 的“重新加载”修正为“重试渲染” |
| Image / value actions | **ADAPT mature lightbox anatomy with existing Radix overlays + shadcn Button + browser scroll** | 保留 HTTPS/Host 保存与外部打开安全边界，Dialog/HoverCard 继续管理焦点和 Escape；使用 Radix `DialogTrigger` 建立真实触发器关系并恢复焦点；加入 fit/actual、100–200% 离散缩放、原生滚动/方向键平移、图片尺寸与 URL 变化复位。调研的三个专用库均运行时写 inline transform/style，会扩大只供审计 renderer 使用的例外；不引入第二 lightbox runtime |
| Message history | **ADOPT TanStack Virtual official chat contract；REUSE generated history contract** | 在现有 `useVirtualizer` 上采用 `anchorTo: end`、`followOnAppend: auto`、`scrollEndThreshold` 与 `scrollToEnd`；直接接通已生成 bounded history endpoint、既有 Store merge/cursor 与 loading/error/retry/exhausted UI。CSP CSSOM 通过 React `useInsertionEffect` 先于 TanStack layout sync 更新尺寸，不手写滚动补偿或第二历史状态机 |
| Toast / persistent error | **KEEP Radix Toast；KEEP blocking/inline error at source surface** | 当前 Toast 已具备队列上限、info/success/warning/error 语义、foreground error、dismiss 和 swipe；不换 Sonner 或 Fluent 形成第二通知系统。本轮补 reduced-motion；需要动作、request id 或持续存在的错误继续留在相关页面 |
| Diagnostics log viewer | **ADAPT PatternFly/Grafana behavior with existing primitives** | 使用现有 Radix Toolbar、shadcn Input/Select/Switch/Button 补齐搜索、级别筛选、换行、命中计数和单行复制；保留每源 300 行、脱敏、frontend fallback 和 Electron Host 导出合同。拒绝引入约 5.4 MB unpacked 且携带整套 PatternFly UI 栈的专用包 |

## 2. Design Lab

Design Lab 只允许展示真实上游包或 vendored 源码。此前手写的 A/B/C 外观仿制不具备来源真实性，
已判定为无效草稿，不得作为采用、视觉或许可证证据；已落地类别直接渲染生产组件。Tree 场景现在
直接渲染同一 Host Tree，而不是候选仿制；lazy child/error/retry 由 Data production fixture 自动化验证。
Conversation History 也直接运行生产 MessageList 和 80→120 Run prepend，不用静态截图伪造；Design Lab
后续只需补视觉矩阵，不再决定 runtime 是否可采用。

比较面板提供：

- Composer、Agent UI、Plan、Approval、Question、Feedback、Data Preview、Typography/Color、Runtime、Tree/Grid/Surface 组件族；
- 已采用生产组件与真实上游候选使用同一 fixture；
- 中文 / English；
- idle、running、disabled、loading、error、long content；
- 720×800、1280×800、1440×900；
- 100%、125%、150%、200%；
- light / dark（沿用 Design Lab 主题开关）；
- 每个候选显示源码来源、许可证、依赖增量和 ADOPT / ADAPT / REJECT 决策。

Design Lab 不得另写候选实现。实际采用的上游源码位于生产组件目录并由生产直接 import；仅用于比较的
真实候选才放在 `desktop/src/design-lab/`，且不得进入生产 import graph。

## 3. 来源追踪

| 本地文件 | 上游 | 许可证 / 使用性质 | 适配内容 |
| --- | --- | --- | --- |
| `desktop/src/components/prompt-kit/prompt-input.tsx` | Prompt Kit `PromptInput`：https://github.com/ibelick/prompt-kit/blob/main/components/prompt-kit/prompt-input.tsx | MIT；vendored upstream source，文件内保留链接 | 保留 context/ref、点击聚焦、textarea 和 actions composition；仅将样式接入 DBFox semantic tokens/CSP |
| `desktop/src/components/ai-elements/prompt-input-submit.tsx` | Vercel AI Elements `PromptInputSubmit`：https://github.com/vercel/ai-elements/blob/main/packages/elements/src/components/prompt-input.tsx | Apache-2.0；vendored upstream source，文件内保留链接 | 保留 submitted/streaming/error/default 图标状态与同按钮 stop/submit 行为；复用已有 Button，不引入 AI SDK runtime |
| `desktop/src/components/agent/UnifiedComposer.tsx` | 上述两个真实上游组件；Hermes Agent composer 与 assistant-ui Thread 作为运行中 payload 行为核验 | 组合层只保留 DBFox authority | 运行中空 draft 停止、有 draft 发送；Queue/Steer/Cancel-and-replace 不复制到第二个状态源 |
| `desktop/src/components/agent-elements/AgentPlan.tsx` | Agent Elements PlanTool / TodoTool registry：https://agent-elements.21st.dev/docs/plan-tool | MIT registry source；vendored upstream source，文件内保留链接 | 直接消费 `PlanItem`；保留上游 disclosure/todo anatomy，扩展 blocked/skipped，不引入 `ai` 类型或 Tabler |
| `desktop/src/components/ui/empty.tsx`、`alert.tsx`、`spinner.tsx`、`skeleton.tsx` | shadcn/ui registry：https://ui.shadcn.com/docs/components/base/empty | MIT；vendored upstream source，文件内保留链接 | 仅换 DBFox semantic token classes；`state.tsx` 只组合产品文案/动作，不再定义 presentation |
| `desktop/src/components/ui/error-details.tsx`、`state.tsx`、`SettingsScaffold.tsx` | RFC 9457：https://www.rfc-editor.org/rfc/rfc9457.html；WHATWG `details/summary`：https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element；Radix Collapsible：https://www.radix-ui.com/primitives/docs/components/collapsible | Web platform；无新增依赖 | 直接读取现有 `ApiError`，只显示 status/code/request ID/check/error 数量；raw payload 永不渲染。Radix Content 因运行时 inline CSS variables 违反 Electron CSP 而在此边界拒绝，采用原生 disclosure，不新增 Error DTO/store/compat layer |
| `desktop/src/components/ui/progress.tsx`、`desktop/src/components/EngineStartupGate.tsx` | shadcn Progress + Radix Progress：https://ui.shadcn.com/docs/components/base/progress 、https://www.radix-ui.com/primitives/docs/components/progress | MIT；vendored shadcn source + official Radix primitive | 只暴露 indeterminate 启动进度；用 CSS animation 代替 inline transform 以满足业务组件无任意 inline layout 合同；不伪造启动百分比 |
| `desktop/src/components/agent-elements/AgentToolGroup.tsx`、`desktop/src/features/conversation/workspace/AgentTimeline.tsx` | Agent Elements ToolGroup / GenericTool registry：https://agent-elements.21st.dev/docs/tool-group | MIT registry source；vendored upstream presentation source，文件内保留链接 | 保留 disclosure、ToolRowBase、elapsed/status、运行中有界列表；以 DBFox durable items 直接替代上游 AI SDK `part`，没有 ViewModel/mapper/第二 runtime |
| `desktop/src/components/ai-elements/confirmation.tsx`、`desktop/src/features/conversation/workspace/ApprovalCard.tsx` | AI Elements Confirmation：https://elements.ai-sdk.dev/components/confirmation | Apache-2.0；vendored upstream compound-component source | 以 DBFox durable decision 替代 AI SDK `ToolUIPart`；request/accepted/rejected/actions 结构、focus/busy/error 语义进入生产 |
| `desktop/src/components/agent-elements/AgentQuestion.tsx` | Agent Elements QuestionTool / QuestionPrompt：https://agent-elements.21st.dev/docs/question-tool | MIT registry source；vendored upstream presentation source | 直接消费 `QuestionItem`；采用 header、编号、option badge、description、action anatomy；Radix 提供 radio 键盘语义，不新增 question DTO/store |
| `desktop/src/components/ai-elements/message.tsx`、`desktop/src/features/conversation/workspace/AgentTimeline.tsx` | AI Elements Message：https://elements.ai-sdk.dev/components/message | Apache-2.0；vendored upstream presentation subset | 采用 Message/Content/Actions anatomy；继续使用现有安全 Markdown pipeline，不引入 Streamdown 或 AI SDK message runtime |
| `desktop/src/components/ai-elements/sources.tsx`、`desktop/src/features/conversation/workspace/DataReferencePanel.tsx` | AI Elements Sources：https://elements.ai-sdk.dev/components/sources；WHATWG `details/summary`：https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element | Apache-2.0 vendored anatomy + Web platform；无 disclosure 依赖 | 保留 Sources compound anatomy，以原生 disclosure 替代会写 inline CSS variables 的 Radix Content；内容保持 Artifact 内部选择，不创建 URL source 映射或受控状态适配层 |
| `desktop/src/components/ui/sidebar.tsx` | shadcn/ui Sidebar：https://ui.shadcn.com/docs/components/base/sidebar 、registry `new-york-v4/sidebar.json` | MIT；vendored upstream presentation source，文件内保留链接 | 采用 Header/Content/Footer/Group/MenuButton 与 `cva` variants；删除旧 primitives/CSS；不复制 Provider/cookie/mobile Sheet 状态，根 `<nav>` 保留导航 landmark |
| `desktop/src/components/ui/select.tsx`、`toolbar.tsx`、`switch.tsx` | shadcn Select/Switch + Radix Select/Toolbar/Switch：https://ui.shadcn.com/docs/components/radix/select 、https://ui.shadcn.com/docs/components/radix/switch 、https://www.radix-ui.com/primitives/docs/components/toolbar | MIT；vendored shadcn anatomy + official Radix primitives | 删除原生 option 解析/伪事件；ToolbarButton 采用 roving focus；SettingsToggle 只保留产品 copy layout，开关状态交给 Radix |
| `desktop/src/components/ui/field.tsx`、`SettingsScaffold.tsx`、`ProjectCreateForm.tsx` | shadcn Field：https://ui.shadcn.com/docs/components/radix/field 、registry `new-york-v4/field.json` | MIT；vendored compound source | 复用既有 Label/Separator/CVA；Field 成为 label/helper/error 的唯一 presentation anatomy，业务表单仍直接消费既有值与校验状态 |
| `desktop/src/components/CommandPalette.tsx` | cmdk：https://github.com/pacocoursey/cmdk；Radix Dialog：https://www.radix-ui.com/primitives/docs/components/dialog | MIT；已有依赖直接复用 | 删除自研 overlay；不复制 command collection；补可访问 Dialog title/description，并由 Radix 管理 modal 生命周期 |
| `desktop/src/components/ui/tree.tsx`、`desktop/src/features/dlc/extensionHost.tsx`、`sdk/frontend/index.d.ts` | Zag Tree View：https://zagjs.com/components/react/tree-view；Ark UI Tree View：https://ark-ui.com/docs/components/tree-view | MIT；`@zag-js/tree-view@1.43.3` 与 `@zag-js/react@1.43.3` 精确锁定；Zag 是 Ark/Chakra 使用的 headless 状态机 | Host SDK 暴露版本化 `ui.Tree`；Zag 负责 collection、键盘、焦点、selection、expansion 与 typeahead，DBFox 只提供静态 token CSS，并在 Host 真边界删除 `--depth` style。DLC 直接传入领域对象与 accessor，不新增 resource DTO、mapper 或 store |
| `dlcs/dbfox_data/frontend/index.js`、`dlcs/dbfox.github/frontend/index.js`、`dlcs/dbfox.music/frontend/index.js` | HTML Dialog / radio / button 平台语义：https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog 、https://html.spec.whatwg.org/dev/interactive-elements.html；WAI-ARIA Toolbar：https://www.w3.org/WAI/ARIA/apg/patterns/toolbar/ | Web platform；无新增依赖 | 在 DLC 无包导入真边界直接采用 Chromium 原语；修正 nested interactive 与错误 role，不建立每 DLC 一套 React primitive runtime |
| `dlcs/dbfox.workspace/frontend/index.js`、`dlcs/dbfox.github/frontend/index.js`、`dlcs/dbfox_data/frontend/index.js` | 上述 Host `ui.Tree` | Host-owned runtime；DLC 无新增 package | Workspace/GitHub 保留路径 authority；Data 保留 profile/catalog/table 对象与 operations。三者只提交 accessor/render callback；Data 的 async load 直接走 Zag `loadChildren`，失败后再次选择重试，refresh/load-more/SQL/table Dock 仍调用原动作 |
| `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx` | TanStack Table v8 + Virtual v3：https://tanstack.com/table/v8 、https://tanstack.com/virtual/latest | MIT；已有依赖直接复用 | 保留服务端分页与结果 authority；补 grid 计数、sort state 和方向键焦点合同，不增加第二 grid model |
| `desktop/src/features/conversation/workspace/MessageList.tsx`、`useConversationViewModel.ts` | TanStack Virtual Chat：https://tanstack.com/virtual/latest/docs/chat；React `useInsertionEffect`：https://react.dev/reference/react/useInsertionEffect | MIT + React 官方 API；已有依赖直接复用 | 直接消费既有 Conversation pagination/cursor 与 Store action；TanStack 保持 prepend anchor 和 append following。`useInsertionEffect` 只在 CSP CSSOM 真边界确保 canvas 尺寸先于 layout effect 生效，不拥有数据或滚动规则 |
| `desktop/src/features/appShell/ConversationWorkspaceLayout.tsx`、`WorkspaceDock.tsx` | react-resizable-panels：https://github.com/bvaughn/react-resizable-panels；Radix Tabs：https://www.radix-ui.com/primitives/docs/components/tabs | MIT；已有依赖直接复用 | 在真实父布局边界替换自研 Dock resizer；Tabs 生成 tablist/tab/tabpanel 关联并直接更新 workspaceStore；无布局 DTO、双写或兼容层 |
| `desktop/src/components/data-grid/json.tsx` | react-json-view-lite：https://github.com/AnyRoad/react-json-view-lite | MIT；`2.5.0` 精确锁定；React 18/19 peer；零运行时依赖 | 直接使用上游 `JsonView`，仅提供 DBFox class map、中文 ARIA 与有界默认展开 callback；拒绝 `@uiw/react-json-view` / react-inspector 的 inline style 路线，避免扩大审计 renderer 例外 |
| `desktop/src/components/ImageCell.tsx` | Yet Another React Lightbox Zoom：https://yet-another-react-lightbox.com/plugins/zoom；react-zoom-pan-pinch：https://github.com/BetterTyped/react-zoom-pan-pinch；react-medium-image-zoom：https://github.com/rpearce/react-medium-image-zoom；CSS `zoom`：https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/zoom | 行为参考 + 现有 MIT Radix/shadcn primitives；无新增依赖 | 三个包分别会写 React `style` / runtime transform，YARL 还重复 portal/dialog/no-scroll 生命周期，因此拒绝直接引入。生产在现有 Dialog 内用静态 CSS zoom classes + 原生 overflow，复用 Button，直接消费 URL，不新增 viewer store、DTO 或兼容层 |
| `desktop/src/components/Toast.tsx` | Radix Toast：https://www.radix-ui.com/primitives/docs/components/toast | MIT；已有依赖直接复用 | 保留 Provider/Root/Viewport、swipe 和 screen-reader behavior；队列仍由本地短暂 UI 投影拥有，不写 Zustand/耐久状态；补 reduced-motion，不增加 Sonner/Fluent runtime |
| `desktop/src/components/ErrorBoundary.tsx` | shadcn Empty/Button：https://ui.shadcn.com/docs/components/base/empty | MIT；复用已 vendored production primitives | class boundary 和日志记录不变；fallback 抽为生产 `FatalErrorFallback` 供 Design Lab 直接渲染，不显示原始 error/stack |
| `desktop/src/pages/DiagnosticsPage.tsx` | PatternFly Log Viewer：https://www.patternfly.org/extensions/log-viewer/html；Grafana Logs Explore：https://grafana.com/docs/grafana/latest/visualizations/explore/logs-integration/ | 行为参考；生产复用现有 Radix/shadcn primitives | 采用 search/filter/wrap/copy/live status anatomy；不引入 PatternFly Core/Icons/Styles、Monaco 或新日志模型 |

## 4. 架构影响

- Core/DLC 边界：正式增加版本化 `host.ui@1.0.0` presentation primitive；注册、数据、动作与 durable authority 未变化。
- durable authority 与 Agent RunLoop 未变化；Store 只新增短暂的 SSE connection projection，事实仍来自耐久 snapshot/event，409 后从权威 snapshot 恢复，成功刷新终态 snapshot 后清除旧连接错误。
- 新增 UI 依赖：`class-variance-authority@0.7.1`（Apache-2.0）、`@radix-ui/react-progress@1.1.16`、`@radix-ui/react-toolbar@1.1.19`、`@radix-ui/react-switch@1.3.7`、`react-json-view-lite@2.5.0`、`@zag-js/tree-view@1.43.3` 与 `@zag-js/react@1.43.3`（其余均为 MIT）。它们分别保持上游 variant、progress、roving focus、switch、JSON tree 与 Tree 状态机语义；`@radix-ui/react-collapsible` 经 CSP 实测后已移除，无第二主题、Agent、日志或布局 runtime。
- 新增 mapper、DTO、双写、fallback 或兼容层：无。
- 临时兼容层：无。Workspace/GitHub 手写文件行与 Data 的 ProfileGroup/DatabaseRow JSX 已被 Host Tree 直接替换；旧扩展集合、Resource DTO、双写和 fallback 均未保留。
- bundle 风险：Tree 状态机与虚拟化组合仍在既有生产分块内；最终首屏 raw 495,762 B / gzip 149,751 B，通过仓库预算。PatternFly Log Viewer 因 5.4 MB unpacked 与第二视觉栈风险未采用。

## 5. 视觉与无障碍验收

使用真实 Chromium 页面 `?design-lab=1` 完成检查：

| 场景 | 结果 |
| --- | --- |
| Composer 同一按钮 Send/Stop、Escape Stop、IME | 自动化组件测试通过；composing Enter 与 Shift+Enter 不误提交 |
| Plan active/waiting/blocked/skipped/completed | Timeline 组件测试通过 |
| Plan / Approval / Question / Stream error | Chromium 720×800 / 200% 直接验证生产组件；Plan 1/12 steps、长内容与证据按钮无水平溢出，expired/cancelled、reconnecting/cursor rejected/snapshot recovered/failed 正确；console 0 error/0 warning |
| Plan progress | 标准 HTML progress（平台成熟原语）直接使用 completed/max；`aria-valuetext` 汇总五类 step 状态，blocked/skipped 用 Lucide + 文本图例；避免 Radix 示例 inline transform 违反 Electron CSP；720×800 / 200% 通过 |
| Run Outcome | shadcn Alert + Fluent MessageBar behavior；failed/partial/cancelled、有/无保留结果、Plan 阻塞摘要、Artifact action 与 safe code 已接生产；Chromium 720×800 / 200% + high contrast，无水平溢出，console 0 error/0 warning |
| 真实浏览器视觉矩阵 | Chromium 实测 1280×800 light、1024×768 dark、720×900 dark、480×800 dark/reduced-motion；480px `scrollWidth === innerWidth`，无水平溢出 |
| Composer 运行态 | 真实 accessibility snapshot：有 draft 时主操作为“发送：排队执行”，清空后原位变为“停止当前任务”，无并列第二按钮 |
| Overlay 焦点 | 480×800 真实 Image Dialog 关闭后焦点返回图片触发器；Radix delivery menu ArrowDown/Escape 与 trigger focus 返回通过 |
| MessageList 长历史 / prepend | 80 Run 自动化进入 TanStack Virtual 分支；Design Lab 直接接通 available/loading/error retry/exhausted。Chromium 80→120 prepend 后“历史问题 41”屏幕位置保持在 469.75→469.25px，挂载 15 行、无 inline style；480px/200% 无水平溢出 |
| Engine generation | 真实 Python Sidecar restart 验证 generation/token 轮换、旧 SSE 关闭、耐久 Conversation 快照恢复；非幂等 POST 不自动 replay |
| Radix Select | 鼠标打开后以 ArrowDown + Enter 从“默认”切到“宽松”；listbox/option/selected 与关闭后 trigger focus 正常 |
| axe-core WCAG 2A/2AA | Settings 与 Agent 综合页均为 0 violation；首次扫描发现的重复 Timeline landmark 和缺少 `h1` 已从权威组件/页面源头修正后复扫归零 |
| JSON / Cell dialog | Chromium 直接验证 production `JsonTree` treeitem/expanded/中文按钮名与 Radix Dialog；发现并修复 Dialog 打开后 HoverCard 残留的 overlay 协调问题，修复后 axe 0 violation、console 0 error/0 warning |
| Image success / decode error | Chromium 直接验证 production `ImageCell`：成功图尺寸、按钮与键盘缩放、fit/actual、失败 alert；发现并修复 URL 变化后旧尺寸/缩放残留。复扫 axe 0 violation、console 0 error/0 warning；证据 `image-preview-zoom.png` |
| Host Tree | Chromium 直接验证 production Tree 的三级层级、分支收起、selection 与 roving focus；ArrowDown 从 `public.orders` 移至 `public.channels`。500-table fixture 的 15,106px logical canvas 仅挂载 22–24 行；End 正确滚动并聚焦 `public.table_500`；声明 `aria-setsize=500`。Tree 内 `[style]` 计数 0，console 0 error/0 warning |
| Data async Tree | fixture 验证 `profiles.list → catalog.tables 失败 → 原位重试 → table treeitem → Catalog Table Dock / SQL Dock`；Zag loading/error 状态与 DLC action/footer 不复制 catalog 状态 |
| Structured error + Sources disclosure | production `ErrorState` / `SettingsStatus` 与 AI Elements Sources anatomy 都使用 HTML `details/summary`；Chromium 480px 下点击与 Enter 展开/收起、焦点保留、无水平溢出，组件 `[style]` 为 0、console 0 error/0 warning。错误详情直接接通 `ApiError`，只读 status/code/request ID/counts；Diagnostics、DLC、Projects/Resources、Conversation、Approval/Question、Model/Update、Table/Chart 已保留结构化错误与就地恢复，服务错误不再重复 toast |

本轮重新生成的证据位于本地 `output/playwright/`；旧手写候选截图不作为当前采用证据。

## 6. 自动化验证

| 命令 | 结果 |
| --- | --- |
| `npm run lint` | 通过；0 errors |
| `npm run typecheck:test` | 通过 |
| `npm test -- --maxWorkers=1` | 93 files / 463 tests 通过 |
| `python -m pytest verification/tests/agent_core/test_event_contracts.py verification/tests/agent_core/test_approval_repository.py verification/tests/agent_core/test_question_repository.py -q --tb=short` | 14 tests 通过 |
| `npm run test:electron` | 10 files / 32 tests 通过 |
| `npm run test:electron-packaged` | 真实 packaged Electron + Frozen Sidecar 通过；Extension Host 加载 Data/Music/Workspace 的 JS/CSS，活动资源 200、未知 digest 403 |
| `npm run build` | 通过；包含 Electron host、CSP/token 和 bundle budget gates |
| `npm audit --omit=dev --registry=https://registry.npmjs.org` | 0 vulnerabilities；配置的 npmmirror 不支持 audit API，因此不能把镜像失败误报为安全结论 |
| `npm audit --registry=https://registry.npmjs.org` | 0 vulnerabilities |
| 生产初始 entry | raw 495,762 B；gzip 149,751 B，通过预算 |
| deferred chart | raw 616,709 B；gzip 208,062 B，通过预算 |

测试日志中的 DLC renderer error、duplicate contribution 和 updater signature mismatch 来自对应 fail-closed 测试的预期 stderr；测试结果均为通过。

## 7. 后续维护

- 外部来源升级时不自动覆盖本地组件；重新运行市场评审并在 Design Lab 同 fixture 比较。
- 若 Electron/Chromium 支持范围变化，首先验证 `field-sizing: content`；不得绕过 CSP 以运行时 style 写入补丁方式回退。
- 如果将来需要全量 docking 或 TanStack v9，只能在出现真实产品需求并明确迁移唯一事实源后重新决策。
- Design Lab 不允许手写“像某上游”的候选；无法直接运行真实上游实现时，记录 REJECT 原因而不是仿制。
