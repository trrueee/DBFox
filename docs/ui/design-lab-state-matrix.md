# DBFox Design Lab 全状态矩阵

> 文档类型：UI 验收矩阵
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 本文定义持续比较实验；“已采用/已验证”只表示采用报告中有来源和验证证据的项目，其余仍是门禁。

## 1. 实验原则

1. 已采用组件与真实上游 Candidate A / B / C 使用完全相同的 props、文案、数据量和容器宽度；
   禁止为了填满比较列而手写上游外观仿制品。
2. fixture 直接采用产品权威数据形状；不得为候选组件建立长期 ViewModel。
3. 每个候选同时展示来源、许可证、依赖增量、复制/概念适配范围和最终决策。
4. 比较交互、状态、键盘、缩放和长内容，不以单张理想静态截图决策。
5. 仅用于比较的真实候选代码只存在于 Design Lab；已采用的 vendored 上游源码位于生产组件目录，
   生产模块不得 import 未采用 candidate implementation。
6. 每组输出 KEEP / ADAPT / ADOPT / REJECT。ADAPT 必须列保留和舍弃的具体能力。

## 2. 全局环境轴

每个高风险组至少覆盖以下组合；低风险 primitive 可用 pairwise 组合减少重复，但不得删除极端状态。

| 轴 | 值 |
| --- | --- |
| Theme | light、dark、system-light、system-dark、high contrast |
| Accent | blue、teal、emerald、rose、violet |
| Neutral | cool、neutral、warm |
| Density | compact、comfortable |
| OS/UI scale | 100%、125%、150%、200% |
| Surface | 1280×800、1440×900、1920×1080、最小窗口、单面板 480/720px |
| Language | zh-CN、en-US、混合中英/数字/路径/SQL |
| Input | mouse、keyboard-only、IME、screen reader semantics |
| Motion | normal、reduced motion |
| Content | normal、long、maximum contract length、empty、large collection |

## 3. Lab 导航结构

| 组 | 子场景 | 优先级 |
| --- | --- | --- |
| Foundations | typography、color、buttons、fields、select、menus、dialog、popover、tabs、toolbar | P0 |
| Feedback | empty/loading/error/toast/surface message/fatal/progress | P0 |
| Agent | Composer、Message、ToolGroup、Plan、Approval、Question、Evidence | P0 |
| Shell | titlebar、sidebar、command、three-pane、dock/tabs | P1 |
| Data | tree、grid、cell/JSON、SQL、chart、image、artifact fallback | P0 |
| Settings | scaffold、model、DLC lifecycle、update、diagnostics/logs | P1 |
| DLC | Data、Workspace、GitHub、Music components | P1 |
| Runtime | boot/engine/offline/reconnect/cancel/stale/unsupported | P0 |

## 4. Foundations fixture

### 4.1 Typography and color

| Fixture ID | 内容 | 通过条件 |
| --- | --- | --- |
| `type-ramp-ui` | caption/label/control/body/section/title/page/display | computed size/line-height/weight 来自 token；层级可辨 |
| `type-ramp-agent` | agent caption/code/UI/body/title/subtitle/display | 阅读态更舒展，不污染 UI ramp |
| `type-cjk-mixed` | 中文、English、数字、标点、emoji、SQL | fallback 不跳高；无在线字体请求 |
| `type-long` | 240 字标题、1000 字说明、长 URL/path | wrap/truncate 规则正确，可获知全文 |
| `color-text` | primary/secondary/muted/disabled/on-color | 全主题对比达标 |
| `color-state` | info/success/warning/danger/trust/selected/focus | 状态不只靠颜色；focus 独立可见 |
| `color-chart` | 6 series、legend、tooltip、table fallback | 色弱/高对比下仍可区分 |

### 4.2 Primitive interactions

| 组件 | Fixture |
| --- | --- |
| Button/IconButton | all variants/sizes、loading、disabled、icon-only、long label、danger |
| Field/Input/Textarea | shadcn Field compound source 已采用；empty/filled/invalid/readonly/disabled/IME/autocomplete/helper/description association |
| Select/Command | Radix Select compound API 与 cmdk + Radix Dialog 已采用；open/closed/no result/disabled option/typeahead/long collection/Esc/return focus |
| Dialog | Radix Dialog 用于 Host overlay、native `<dialog>.showModal()` 用于 package-free Data DLC；safe initial focus、busy、validation error、nested popover、outside/Escape、close return focus |
| Menu | checked/radio/submenu/disabled/danger/typeahead/collision |
| Tooltip/HoverCard/Popover | delay、long content、viewport edge、dismiss、touch fallback |
| Tabs | overflow/closable/dirty/disabled/keyboard/close neighbor focus |
| Toolbar | Radix Toolbar 已采用且 roving focus 单测通过；继续 720/480px、overflow menu、disabled group、no-wrap |
| Switch | Radix/shadcn Switch 已采用；checked/unchecked/disabled/keyboard/high contrast/immediate persistence |
| Tree | Host Zag Tree 已接三级真实 production fixture，并验证 collapsed/expanded、selected+focus、Arrow keyboard 与 long label；Data fixture 已验证 async child/error/retry/action；500 visible nodes 使用 Zag `getVisibleNodes`/`scrollToIndexFn` + TanStack Virtual，只挂载窗口行 |
| Scroll/Resizable | nested scroll、keyboard separator、min/max、200% scale |

## 5. Feedback fixture

| Fixture ID | Current | Candidate | 数据/状态 |
| --- | --- | --- | --- |
| `feedback-empty-first` | adopted shadcn Empty composition | Primer/Atlassian anatomy | first use + primary/secondary action |
| `feedback-empty-filter` | adopted shadcn Empty composition | compact no-results | query active + clear filter |
| `feedback-loading-short` | spinner | Fluent/Carbon reference | <2s、stable layout |
| `feedback-loading-long` | adopted shadcn Spinner/Skeleton + Radix Progress | progress + stage | indeterminate、cancel possible/impossible |
| `feedback-error-inline` | adopted shadcn Alert | Fluent MessageBar behavior | retry、open settings、long message |
| `feedback-error-section` | adopted shadcn Alert composition | Carbon actionable reference | impact + old data preserved + details |
| `feedback-error-fatal` | Engine/ErrorBoundary | fatal gate variants | restart/reload/logs/request ID |
| `feedback-toast` | current Toast | Fluent toast behavior | success/info、queue、dismiss、no critical error |
| `feedback-progress` | current | PatternFly progress | 0/37/100、indeterminate、error、aria-valuetext |

错误数据固定覆盖 401、403、404、409、422、429、500、503、network、invalid ProblemDetails；详情中放置
测试用 token/password/DSN 标记，断言普通 UI 和复制内容均不泄露。

## 6. Agent fixture

### 6.1 Composer and messages

| 组件 | 状态 |
| --- | --- |
| Composer | idle/focus/multiline/max height/IME/reference/running-empty→stop/running-draft→send/queue/steer/cancel-and-replace/cancelling/sending/disabled/error |
| User message | adopted AI Elements Message anatomy；queued/steered/sent/long/mixed content |
| Assistant | adopted AI Elements Message anatomy + existing sanitized Markdown；commentary streaming/final/complete/bounded partial/evidence/no evidence/long markdown |
| MessageList | empty/history paging/streaming/user scrolled/reconnect |

### 6.2 Tool, Plan, approval and question

| 组 | Current / Candidate | 状态 |
| --- | --- | --- |
| ToolGroup | adopted production Agent Elements source / AI Elements reference | pending/running/waiting/success/fail/cancel、1/8 tools、long args/output；Design Lab 已接入 running/completed/failed/cancelled/8 tools，其余继续补测 |
| Plan | adopted production Agent Elements / PatternFly vertical / Carbon reference | pending/active/waiting/blocked/skipped/completed/partial/failed/cancelled、1/5/12 steps、长 objective、Artifact present/missing、revision 折叠保持、标准 determinate progress 与 blocked/skipped 图例已接生产 fixture |
| Approval | adopted production AI Elements Confirmation / Fluent reference | safe/warning/danger、submitting、approved/rejected/expired/cancelled/409/error 已接生产 fixture |
| Question | adopted production Agent Elements + Radix / Nexus reference | option/free text/submitting/answered/expired/cancelled/409/error 已接生产 fixture |
| Run Outcome | adopted production shadcn Alert + Fluent MessageBar behavior | failed + result/no result、bounded partial + result/no result、cancelled + result；Plan 摘要、阻塞步骤、限制原因、Artifact action 与 safe code 已接生产 fixture |
| Evidence | adopted AI Elements Sources disclosure / Nexus reference | none/1/many/missing/stale/value omitted；Artifact authority 保持不变 |

Plan 专项 fixture 使用 1、5、12 步；至少一个 evidence-required completed step 带 Artifact，一个 blocked
step 带 note，一个 skipped step；revision 更新时验证用户手动折叠不被抢回。

## 7. Shell 与运行时 fixture

| Fixture ID | 状态 |
| --- | --- |
| `shell-sidebar` | expanded/collapsed/no project/active/long labels/DLC connector error |
| `shell-command` | adopted cmdk + Radix Dialog；empty query/results/no result/keyboard/long shortcut/IME/focus restore |
| `shell-layout` | adopted production react-resizable-panels；left only/two-pane/three-pane/min/max/restored/keyboard separator/200% |
| `shell-dock` | adopted production react-resizable-panels + Radix Tabs；closed/one/many/overflow/closable/renderer unavailable/DLC exception/tabpanel association |
| `runtime-boot` | pre-React starting/fail/timeout |
| `runtime-engine` | adopted Alert/Spinner/Progress presentation；starting/health/recovering/migrating/maintaining/failed/ready；Design Lab 已接 starting/restarting/ready/failed/stopped |
| `runtime-offline` | Sidecar unreachable/token invalid/provider offline |
| `runtime-stream` | live 由 runtime 单测覆盖；reconnecting/cursor rejected/snapshot recovered/failed 已接生产状态与 Design Lab fixture |
| `runtime-cancel` | cancel requested/cancelled/non-idempotent not replayed |

## 8. Data 与 Artifact fixture

| 组件 | 状态 |
| --- | --- |
| Resource tree | `host.ui@1.0.0` Zag Tree 已落地，Workspace/GitHub/Data 已迁移；Design Lab 直接渲染 production Tree。同步 deep/selection/collapse/keyboard/CSP、Data async child/error/retry/action、500-node virtualization 与 root 切换后丢弃旧异步结果均已通过 |
| Conversation history | production MessageList 直接使用生成的 bounded history endpoint 与现有 Zustand action；available/loading/error retry/exhausted 已进入 Design Lab，80→120 Run prepend 保持可见锚点 |
| Table/Grid | adopted production TanStack v8 + Virtual v3；Design Lab 直接渲染真实 Grid；已覆盖 grid count/sort/cell arrows，继续 loading/empty/1 row/10k virtual/filter/select/page/truncated/error/old result retained |
| Cell preview | Design Lab `Data Preview` 已直接渲染生产 `JsonTree` + `CellValuePreview`；普通/deep/wide JSON、long text、image success、image decode error 已接；继续补 null/bool/number/date/binary/copy fail |
| SQL | blank/edit/validating/rejected/validated/executing/cancel/done/error/stale/diff |
| Markdown | empty/long/code/table/link/unsafe HTML/mixed CJK |
| Chart | lazy/no data/invalid config/1/6 series/too many points/resize/error/table fallback |
| Image | production `ImageCell` 已覆盖 loading/decode error/fit/actual/100–200% zoom/native scroll pan/keyboard/metadata/URL change reset；missing 与 copy/save fail 继续保留 fixture 门禁 |
| Artifact | creating/completed/failed/stale/unsupported type/schema/DLC disabled |
| File | text/binary/encoding/large/truncated/not found/permission/external change |

## 9. Settings 与 Diagnostics fixture

| 页面 | 状态 |
| --- | --- |
| Appearance | all themes/accents/neutrals/densities/scales/preview/reset/unsaved |
| Model | unconfigured/secret present/edit/test busy/pass/auth/network/rate limit/save/error |
| DLC Center | empty/inspect/trust/install/disabled/enable pending restart/active/disable pending restart/activation failed |
| Update | checking/up-to-date/available/downloading 37%/paused-fail/ready/restart |
| Diagnostics | loading/frontend fallback/empty/log groups/long rows/**search + level filter + wrap + match count + row copy 已实现**/export/copy bundle/clear confirm/error |

## 10. DLC fixture

### 10.1 Data

- native dialog/radio 已采用；connection form invalid/test pass/test fail/save fail/Escape/outside close/focus restore；
- database disconnected/connecting/connected/failed；
- catalog empty/lazy/error；SQL validate/execute/cancel；result large/truncated/profile unsupported。

### 10.2 Workspace

- unbound/binding/permission/path missing；
- file tree empty/deep/error；file text/binary/large/stale/not found；patch Artifact failed/stale。

### 10.3 GitHub

- unconfigured/auth/permission/rate limit/offline；
- repo/branch/ref、empty/deep/pagination；file not found/binary/large/stale。

### 10.4 Music

- EmptyStudio/ScoreStudio loading/error；
- score play/pause/stop/loop/ended，measure active/selected/uncertain/focus；
- keyboard adaptive/full/active note/keyboard navigation；专业 SVG piano keys 因候选兼容性/成熟度/许可证未达门槛而保留；
- audio buffer missing、transcribing 0/37/100、cancel、no notes/error/ready；
- waveform no data/ready/playing/seek candidate/uncertain regions、A/B active source；
- score/transcription Artifact completed/failed/stale/unsupported。

## 11. 记录模板

每次比较在采用报告追加：

| 字段 | 内容 |
| --- | --- |
| Component / fixture | 组件与 fixture ID |
| Current finding | 当前优势、缺陷、测试证据 |
| Candidate A/B/C | 名称、版本/commit、Demo/source、license |
| A11y | keyboard、focus、name/state、live region、contrast |
| Runtime fit | React/Tailwind/Radix/TanStack 版本与 CSP/Electron 兼容 |
| Cost | dependency、bundle、worker/WASM、upgrade/exit |
| Authority impact | 是否新增 DTO/store/mapper/runtime；非零默认拒绝 |
| Decision | KEEP/ADAPT/ADOPT/REJECT |
| Provenance | 复制文件/代码段/概念来源、本地落点 |
| Verification | unit/axe/visual/build/bundle 结果 |

## 12. 2026-08-27 实测证据

| 范围 | 结果 |
| --- | --- |
| Browser visual | Chromium：1280×800 light、1024×768 dark、720×900 dark；本轮新增 720×800 / 200% 的 Plan、Approval、Question、Stream Notice、Run Outcome 验收；Plan determinate progress/legend 与 Run Outcome high contrast 另验；720px 无水平溢出 |
| Composer state | 有 draft 时同一主操作位发送，空 draft 运行态原位停止；无并列 stop/send |
| Select keyboard | open → ArrowDown → Enter；选中值与 trigger focus 正确 |
| axe-core | Settings 与 Agent 综合页复扫均为 0 violation |
| 自动化 | frontend 93 files / 463 tests；本轮相关 backend 14 tests；Electron 10 files / 32 tests；工程合同 39 tests；lint（0 errors）、test typecheck、production build/bundle gate 通过 |
| JSON overlay | production tree/Dialog Chromium snapshot + axe 0 violation；Dialog 打开时 HoverCard 强制关闭，避免重复可访问内容；截图 `desktop/output/playwright/data-preview-json-dialog.png` |
| Host Tree | Chromium production fixture：三级 tree/treeitem/group 名称正确；点击选中、ArrowDown roving focus、分支收起通过；Tree 内 `[style]` 为 0，console 0 error/0 warning |
| Host Tree virtualization | Chromium production 500-table fixture：448px viewport / 15,106px logical canvas 仅挂载 22–24 行；leaf 声明 `aria-level/posinset/setsize=500`；End 从首分支滚至并聚焦 `public.table_500`，Tree 内 `[style]` 为 0，console 0 error/0 warning |
| Data async Tree | production DLC fixture：首次 `catalog.tables` 失败显示原位重试，第二次加载 table treeitem；表选择与 SQL action 打开原有 Dock，未引入资源 mapper/store |
| Plan / approval / question | 直接渲染 production `AgentPlan`、`ApprovalCard` / `ApprovalAuditCard`、`AgentQuestion`；Plan 证据调用现有 Artifact selection，标准 progressbar 的 completed/max/aria-valuetext 与 blocked/skipped 图例通过；expired 不再折叠为 cancelled，审批取消不再误报 rejected |
| Stream recovery | production SSE runtime 投影 connecting/live/reconnecting/recovering_snapshot/recovered/failed；临时断线与游标恢复使用 status，终止错误使用 alert + snapshot refresh，且不自动重放 mutation |
| Run terminal outcome | production `RunOutcome` 直接读取 Run/Plan/Artifact；failed 为 alert，bounded partial/cancelled 为 status；有/无结果、阻塞/跳过、限制说明和 Artifact action 在 720×800 / 200% 及 high contrast 下通过 |
| Electron generation | 真实 Python Sidecar generation 1→2：token 轮换、旧 token 401、旧 SSE 断开、同一 Conversation 耐久快照恢复；非幂等 POST 在 401/网络失败后均只调用一次 |
| Electron + System DLC runtime | 开发 Host 与 packaged Host 均启动真实 Frozen Sidecar；Extension Host `1.0.0` 激活并加载 `dbfox.data`、`dbfox.music`、`dbfox.workspace`，三者 JS entrypoint 与 stylesheet 均经 `dlc-asset://` 返回 200，未知 digest 返回 403；packaged 证明为 `packaged: true` |
| 480px / 200% | 生产 Composer、Image Dialog、Runtime gate 与 Design Lab 模拟视口均无水平溢出；同一 Send/Stop 主按钮、Radix menu 键盘导航/焦点返回通过 |
| IME / Overlay | composing Enter 与 Shift+Enter 不提交；HoverCard 内 Image Dialog 通过 `DialogTrigger` 在 Escape 后恢复到图片触发器 |
| Message virtualization / history prepend | 采用 TanStack Virtual chat contract；80 Run 自动化确认进入虚拟分支且只挂载可见窗口。Chromium 从 80→120 Run prepend 后，原“历史问题 41”Y 坐标 469.75→469.25px，滚动自动补偿 9,690px；15 个 Run 挂载、`[style]` 为 0、console 0 error/0 warning；480px/200% 无水平溢出 |
| Problem Details disclosure | Feedback/Error 直接渲染 production `ErrorState` + 原生 `details/summary`；480px/200% 下 Enter 展开、焦点保留，status/code/request ID 可读，raw detail 不可见，组件 `[style]` 为 0、console 0 error/0 warning。Diagnostics、DLC、Projects/Resources、Conversation、Settings 与 Table/Chart 已接结构化错误 |
| Sources disclosure | Design Lab 直接渲染 production AI Elements Sources anatomy + 原生 `details/summary`；真实 Chromium 点击展开、焦点后 Enter 收起，480px 页面 `scrollWidth === innerWidth`、Sources `[style]` 为 0、console 0 error/0 warning。Radix Collapsible 因 CSP 冲突已从生产依赖移除 |
| Theme / motion semantics | Chromium dark + reduced-motion 下 Runtime status/progressbar accessibility tree 正确，旋转动画降至近零；console 0 error/0 warning |

Tree 的同步/Data async/stale-result isolation/500-node virtualized Host runtime、真实 Electron generation
change、MessageList 长历史/服务端 prepend 锚点、480px/200% scale、IME 和复杂 overlay nesting 已完成。
完整 Electron DLC runtime fixture 已完成。NVDA/VoiceOver 等真实辅助技术矩阵仍保留为人工门禁；
当前 Windows 验证环境未安装 NVDA，不以 Chromium accessibility tree 结果替代实机读屏结论。

## 13. 进入生产的门禁

1. 同 fixture 比较完成，不能只看官网 demo；
2. 来源、许可证、维护状态、版本兼容和 bundle 成本有记录；
3. 选中方案在 keyboard/high contrast/reduced motion/long content 下不退化；
4. 不改变 Project/Conversation/Run/Artifact/DLC authority；
5. 无新增 mapper、fallback chain 或第二状态机；
6. 实际采用后更新 adoption report，且候选不被生产 import；
7. lint、typecheck、unit、Electron tests、build、bundle gate 与视觉矩阵通过。
