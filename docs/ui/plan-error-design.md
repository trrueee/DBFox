# DBFox Plan 与错误反馈协同设计

> 文档类型：UI 状态与错误设计
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 位置：这是全量 UI 路线中的两条纵向能力，不缩减[现行 UI 规范](../quality/ui-design-and-development.md)
> 的页面、DLC、Work Surface 与组件范围。

## 1. 设计目标

Plan 回答“现在要做什么、做到哪里、为什么停住、产出了什么”；错误反馈回答“哪里失败、影响了
什么、还能保留什么、用户下一步做什么”。两者必须协调，否则会出现 Plan 显示仍在进行、下方却
显示失败，或者错误覆盖了已经完成的结果。

本设计直接消费现有 Run/RunItem/PlanStep/Artifact/ProblemDetails，不建立第二状态机、不新增 DTO、
不把 UI 状态写回 Agent 事实源。

## 2. 权威状态与当前实现

### 2.1 Plan 权威状态

- Run item：`pending / in_progress / waiting / completed / failed / cancelled / expired`；
- Plan step：`pending / in_progress / completed / blocked / skipped`；
- step metadata：`evidence_required`、`artifact_ids`、`note`；
- payload：`objective`、`steps`、`summary`；
- Engine `TaskPlan` 另有 `active / blocked / completed / partial / failed / cancelled`，并保证至多一个
  in-progress step；终止时会把未完成步骤规范化为 blocked/skipped。

### 2.2 当前 UI 已有能力

`AgentTimeline` 当前直接渲染采用 Agent Elements PlanTool/TodoTool anatomy 的 `AgentPlan`。组件直接消费
`PlanItem`，呈现 objective、summary、step note、blocked/skipped 及 item 状态 icon；pending、in-progress、
waiting、failed 自动展开，终态允许用户保持折叠。Header 分别表达准备、进行、等待、受阻、完成、部分
完成、失败与取消，并把 completed 和 skipped 分开计数。完成步骤直接使用 `artifact_ids` 匹配现有
Conversation Artifact 并调用既有选择动作；必需证据尚未加载或不存在时明确显示不可用。
Plan 现在还使用标准 HTML determinate progress；value 只取 completed，max 取总步骤，skipped/blocked
以独立 Lucide 图标和文字图例表达。`aria-valuetext` 汇总 completed/in-progress/blocked/skipped/pending；
实现不使用 shadcn 示例中的 inline transform，满足 Electron CSP。

Approval 采用 AI Elements Confirmation，Question 采用 Agent Elements QuestionTool + Radix RadioGroup。
两者区分 approved/rejected/expired/cancelled，提交失败就地呈现；失败后只刷新权威快照，不自动重放写操作。
SSE 连接状态由现有 runtime 投影为 connecting/live/reconnecting/recovering_snapshot/recovered/failed，
临时断线、游标失效、快照恢复与 Plan 失败保持分离。

Run 终态采用 shadcn Alert composition 与 Fluent MessageBar 的 impact → cause → recovery 顺序。生产
`RunOutcome` 直接读取 Run、最新 Plan、终态回答和主要 Artifact：failed、bounded partial、cancelled
分别使用 alert/status 与 danger/warning/neutral 语义，汇总完成/受阻/跳过步骤、首个受阻步骤、限制原因、
保留工件入口和安全错误 code；已有结果不会被失败表面遮盖，也不提供可能重放副作用的“重试全部”。

### 2.3 当前缺口

已完成 Chromium dark/reduced-motion 与 accessibility tree 复核；NVDA/VoiceOver 等真实辅助技术矩阵
仍需补齐。generation change、旧 SSE 断开、耐久快照恢复与非幂等请求不重放已有真实 Frozen FastAPI
Sidecar 集成证据；完整 Electron 开发/packaged Host + System DLC runtime fixture 也已通过。

## 3. Plan 信息架构

### 3.1 收起态 Header

从左到右：

1. Plan 图标；
2. 固定名称“执行计划”；
3. 一行状态摘要；
4. disclosure chevron。

状态摘要不只显示比例，按优先级表达：

| 条件 | Header 文案示例 | Tone |
| --- | --- | --- |
| waiting | `等待你的确认 · 2/5 已完成` | warning |
| blocked step 存在 | `1 个步骤受阻 · 2/5 已完成` | warning/error，取决于 run terminal |
| item failed | `计划未完成 · 已保留 2 个结果` | error |
| item cancelled | `计划已停止 · 2 个步骤未继续` | neutral |
| completed 且有 skipped | `计划完成 · 4 完成，1 跳过` | success |
| completed | `5/5 已完成` | success |
| in_progress | `第 3/5 步进行中` | info |
| pending | `5 个步骤待开始` | neutral |

这里是直接展示条件，不创建另一份 plan status。`completed` 数只计算 completed；skipped 单独计数。

### 3.2 展开态

顺序固定：objective → summary（存在时）→ ordered steps → evidence/Artifact actions。

| 元素 | 规则 |
| --- | --- |
| Objective | 说明本次计划目的，不用“Objective:”开发者标签；最长 1000 字需自然换行/折叠 |
| Summary | 终止或整体结论；completed/partial/failed/cancelled 时放在步骤前并使用相应 icon/text |
| Step number | 保留顺序语义；icon 不能替代有序列表编号 |
| Step title | 主信息；最多 240 字，长文本换行，不截断关键内容 |
| Note | blocked/skipped/failure 原因或完成说明；不是 raw exception |
| Evidence marker | `需要证据`只在未完成时提示；完成时转为可打开的 Artifact links |
| Artifact links | 使用已有 `artifact_ids` 和 Artifact workspace，不复制 payload，不创建 citation model |

### 3.3 Step 状态 anatomy

| 状态 | 图标/文本 | 动画 | 用户含义 |
| --- | --- | --- | --- |
| pending | 空心圆 + `待开始` | 无 | 尚未执行 |
| in_progress | spinner/progress + `进行中` | reduced-motion 下静态 | 当前唯一活动步骤 |
| completed | check + `已完成` | 无庆祝动画 | 已完成；需要证据时必须有 Artifact |
| blocked | warning/stop + `受阻` | 无 | 当前不能继续；note 说明原因 |
| skipped | minus/forward + `已跳过` | 无 | 明确决定不执行，不等于失败或完成 |

颜色只是辅助。图标、可见文字、列表结构三者共同表达状态。

### 3.4 展开策略

- 首次进入 in-progress、waiting、blocked 或 failed 时自动展开一次；
- 用户手动折叠后，同一状态持续更新不得反复打开；
- 新 run/new plan identity 可以重新应用自动展开；
- completed 且无异常时不强制收起，保留用户选择；
- 动态更新不移动焦点，不对每次 revision 都播报完整列表；`aria-live=polite` 只播 header 状态摘要。

## 4. 进度表达

参考 PatternFly/Carbon 的 stepper/progress 行为，但不引入其 runtime。

1. 步骤数 1~12 时，ordered list 是主要进度表达。
2. 可选 determinate bar 的 value 只等于 `completed / total`，skipped 不进入完成百分比。
3. 若存在 skipped/blocked，在 bar 旁显示分项文本，不能用同一种填充色吞掉语义。
4. waiting 不推进进度；显示“等待确认/回答”。
5. partial 不是 success；同时展示完成数、跳过数和限制原因。
6. 屏幕阅读器文本示例：`5 个步骤，2 个已完成，1 个进行中，1 个受阻，1 个待开始`。

参考：

- PatternFly Progress Stepper：https://pf6.patternfly.org/components/progress-stepper/
- PatternFly Progress：https://www.patternfly.org/components/progress/
- Carbon Progress Indicator：https://carbondesignsystem.com/components/progress-indicator/usage/

## 5. 错误反馈信息架构

### 5.1 权威合同

HTTP API 已返回 RFC 9457 `ProblemDetails`：`status`、`code`、`title`、`detail`、`request_id`、
`checks`、`errors`。前端 `ApiError.detail` 当前保存完整 payload，`userFacingErrorMessage` 负责安全
文案降级。这一链路继续作为唯一错误事实源。

此前多数调用方只取最终字符串，丢失 code/request ID/checks。当前生产 `ErrorDetails` 已直接读取
现有 `ApiError`/ProblemDetails，并覆盖 Diagnostics 的加载/导出/清理、DLC 加载与生命周期动作、
Projects/Resources、Conversation 加载/历史/发送/审批/提问、Model/Update 设置以及 Table/Chart 数据加载；
只展示白名单化的 status/code/request ID 和 checks/errors 数量，不渲染 raw payload。仅字段校验、剪贴板等
本地瞬时反馈继续使用就近文案或 toast，不新建平行 Error DTO、全局错误 store 或业务规则映射。

### 5.2 错误表面层级

| 层级 | 使用条件 | Anatomy |
| --- | --- | --- |
| Field | 单字段可修正 | field label + specific error；提交后聚焦首错 |
| Inline | 一个动作失败但内容仍有效 | icon + concise message + retry/alternate action |
| Section | 当前 section 无法加载或部分降级 | title + impact + action + details disclosure |
| Page/Panel | 当前表面没有安全可用内容 | error state + primary recovery + secondary logs/settings |
| Fatal gate | Engine/React 无法继续 | phase + restart/reload + open logs + technical details |

Toast 只用于非关键、瞬时反馈。持续错误在发生表面保留；同一错误不再同时弹 Toast 和重复 inline
alert，除非 Toast 只是跨区域动作的入口提示。

参考：

- Fluent Message Bar：https://fluent2.microsoft.design/components/web/react/core/messagebar/usage
- Fluent Toast：https://fluent2.microsoft.design/components/web/react/core/toast/usage
- Carbon Notification：https://carbondesignsystem.com/components/notification/usage/

### 5.3 标准内容顺序

1. **Title**：`诊断日志加载失败`、`扩展无法启动`、`查询未完成`；
2. **Impact**：旧结果是否仍可读、哪个步骤未完成、是否影响其他 DLC；
3. **Safe cause**：使用 code catalog 或安全中文 detail，不回显 raw provider/exception；
4. **Primary recovery**：只给当前最有效动作；
5. **Secondary action**：打开设置、日志、保留结果；
6. **Technical details**：code、request ID、安全 checks、版本/phase；支持复制；默认折叠。

### 5.4 恢复动作表

| 状态/错误 | 主动作 | 不允许的行为 |
| --- | --- | --- |
| GET/读取网络失败 | 重试读取 | 清空旧内容 |
| 401/403 Engine token | 重启应用/Engine | 要求用户手输运行时 token |
| Provider auth/config | 打开 Model 设置 | 把 API key 或 endpoint secret 放进错误正文 |
| 404/stale artifact | 刷新/返回来源 | 静默展示旧版本为最新 |
| 409 approval/question | 刷新最新状态 | 继续重复提交同一 decision/version |
| 429/provider limit | 按可用信息稍后重试/调整模型 | 无上限自动重试 |
| Engine recovering | 等待恢复/打开日志 | 自动重放非幂等请求 |
| DLC activation failed | 打开 DLC 设置/重试激活 | 让 DLC 异常击穿 App Shell |
| renderer exception | 重试该 renderer/打开技术详情 | 显示 raw stack 给普通用户 |
| tool failed | 修改输入或重试允许步骤 | 重跑已产生副作用的 invocation |
| bounded partial | 继续或放宽约束 | 显示绿色“全部完成” |

## 6. Plan 与错误的协同规则

### 6.1 Run failed

- Plan header 变为“计划未完成”；
- 当前 in-progress step 由 Engine terminalizer 变为 blocked，note 显示安全原因；
- 其他 pending step 变为 skipped；
- run error 卡先说明保留的 Artifact/结果数量，再给安全错误与恢复动作；
- 已完成步骤、证据和 Artifact 保持可打开。

### 6.2 Run cancelled

- Plan 显示已完成/跳过数量和 cancellation summary；
- 取消不使用 danger tone，不写“失败”；
- cancel requested 与 terminal cancelled 分开，等待期间禁重复取消；
- 不自动继续剩余步骤。

### 6.3 Waiting approval/question

- Plan header 和 timeline working status 都写明“等待确认/回答”，但只保留一个主要 live announcement；
- 相关 step 保持 in-progress 或权威状态，不在 UI 自行改为 blocked；
- Approval/Question action failure 就地呈现并保留选择；409 刷新最新 resolution；
- 到期/拒绝后，由 Engine 后续事件决定 Plan terminal state，UI 不提前推断。

### 6.4 Bounded partial

- 最终回答和 Plan summary 同时使用“部分完成”语义；
- 展示 limitation codes 的用户语言；
- completed、blocked、skipped 的数量和已有 Artifact 可见；
- 后续动作是“继续分析/调整约束”，不是无脑“重试全部”。

### 6.5 SSE reconnect / generation change

- 临时断线只显示连接恢复状态，不把 Plan 标成 failed；
- cursor/snapshot 恢复后以耐久事件投影为准；
- generation 变化后，读取可恢复，非幂等提交和工具调用不可自动 replay；
- 若状态无法确认，明确“正在确认最新状态”，而不是同时显示 running 与 failed。

## 7. 共享组件边界

允许的最小公共能力：

- 扩展现有 `ErrorState`：可选 `actions`、`details`、`tone/level`，前提是至少三个真实表面需要；
- 扩展现有 `SettingsStatus`：设置页 inline status；
- 一个纯展示的 ProblemDetails technical disclosure，可直接接收生成类型；
- Plan 内部的小型 `PlanStepIcon`/summary functions，留在 AgentTimeline 范围。

不允许：

- 新的 `UiError`、`PlanViewModel`、status mapper、Error service 或全局错误 store；
- 将 ProblemDetails 改名复制到另一数据结构；
- 让 toast queue 成为错误事实源；
- UI 自己推进 Plan、审批或工具状态；
- 为每个页面包一层只转发 props 的 Error wrapper。

## 8. Design Lab 对比与验收

### 8.1 Plan fixtures

- pending、single active、waiting approval、waiting question；
- completed、completed + skipped、blocked、failed、cancelled、bounded partial；
- 12 步上限、240 字 step、1000 字 objective/summary；
- evidence required missing/present、多 Artifact；
- streaming revisions、手动折叠后继续更新；
- light/dark/high contrast/reduced motion、键盘与屏幕阅读器摘要。

候选：Current、Agent Elements anatomy、PatternFly vertical stepper、Carbon progress indicator。只适配
信息架构和行为，不复制 runtime 状态。

### 8.2 Error fixtures

- field 422、conflict 409、auth 401/403、not found 404、rate limit、500/503、network；
- 有旧结果/无旧结果、单 DLC exception、Artifact renderer failure、Engine fatal；
- code/request ID/checks 折叠与复制；长中文、英文 fallback、敏感字符串测试；
- retry busy/success/repeat failure；键盘 focus recovery 与重复 alert 去重。

候选：Current ErrorState、Fluent MessageBar anatomy、Carbon inline/actionable notification、fatal gate。

## 9. 自动化验证基线

1. Unit：所有 Plan step/item/run 组合得到正确可见文案，不把 skipped 算 completed。
2. Unit：objective、summary、note、evidence/artifact actions；动态 revision 不抢焦点。
3. Unit：ProblemDetails code/status/request ID 安全读取；未知/非法 payload 降级。
4. Unit：错误动作矩阵，409/401/503/DLC/Engine 不走相同 recovery。
5. Accessibility：details/summary、ordered list、progress value/text、alert/status/live region、button names。
6. Integration：SSE reconnect、cancel requested、approval conflict、run failed with preserved results。
7. Visual：完整主题/密度/缩放/长内容矩阵。

## 10. 实施顺序

1. 先在 Design Lab 建 Plan/Error 全状态 fixture，确认信息层级和动作。
2. 补安全的 ProblemDetails 字段访问与错误测试；不先改业务页面。
3. 扩展已有 `ErrorState`/`SettingsStatus` 的真实共同能力。
4. 完成 Plan summary、blocked/skipped、evidence 和 a11y。
5. 按 surface 层级迁移 Engine、DLC、Settings、Diagnostics、Projects、Conversation、Artifacts。
6. 清理重复 toast/inline 和 raw exception 呈现。
7. 完成全矩阵验证后，按[现行 UI 规范](../quality/ui-design-and-development.md)继续其他组件施工。

新增依赖：无。兼容层/mapper：无。主要风险是错误详情暴露敏感内容和 Plan 展示与耐久状态不一致；
分别用固定错误目录/脱敏合同、直接消费权威事件和状态组合测试控制。

## 11. 2026-08-27 实施记录

- 已完成 Plan pending/active/waiting/blocked/skipped/completed/partial/failed/cancelled，以及 1/5/12 步、
  长内容、Artifact present/missing 和 revision 折叠保持的生产 fixture 与测试；
- 已完成 Approval/Question submitting、terminal、expired/cancelled 与 conflict 后权威快照刷新；每次 mutation
  只提交一次；
- 已完成 SSE reconnecting/cursor rejected/snapshot recovered/failed 的来源表面提示，以及成功刷新终态
  快照后清除旧连接错误；
- 已完成 production `RunOutcome` 的 failed/failed without result/bounded partial/partial without result/cancelled
  状态；直接汇总权威 Plan 与 Artifact，提供具体 Artifact 打开动作和安全技术详情，不自动重放运行；
- 已完成 Plan determinate progress 与 blocked/skipped 图例；标准 progressbar 提供完整 `aria-valuetext`，
  skipped 不计入完成值，CSS 无 inline style；
- Chromium 在 720×800、200% 缩放下复核 Plan、Approval、Question 与 Stream Notice；修正 Plan 目标和摘要
  并排导致的窄列问题，控制台 0 error/0 warning；
- Chromium 继续在 720×800、200% 与 high contrast 下复核 Run Outcome 全终态；页面无水平溢出，控制台
  0 error/0 warning；
- frontend 93 files / 463 tests、相关 backend 14 tests、Electron 10 files / 32 tests、typecheck、
  lint（0 errors）和 production build/bundle gate 通过；
- 未完成项仍按 2.3 与全量 Design Lab 矩阵继续，不把本纵向能力当作全量 UI 路线终点。

## 12. 2026-08-28 运行时与窄视口补充证据

- 真实 Python Sidecar 在 Host generation 1→2 重启后轮换 token、关闭旧 SSE，并从 SQLite 耐久事实源
  恢复同一 Conversation；旧 token 返回 401，新 generation 可读取同一快照；
- 前端明确验证旧 token 401 与网络失败都不会自动重放非幂等 POST，恢复只重新取得 runtime config
  并刷新权威读取；
- Composer 在 480×800 / 200% 下保持同一主操作位：运行中有 draft 为发送、空 draft 为停止；IME
  composing Enter 与 Shift+Enter 均不误提交；
- Image Dialog 改由 Radix `DialogTrigger` 建立触发器关系，复杂 HoverCard→Dialog 嵌套在 Escape
  关闭后由 Radix 恢复焦点，不新增自定义 focus manager；
- MessageList 采用已安装 TanStack Virtual 官方 chat 配置（end anchor、append following、scroll-to-end
  threshold），并直接接通现有生成 history endpoint 与 Store cursor/merge；loading、失败重试、耗尽
  状态已进入生产和 Design Lab。Chromium 80→120 Run prepend 保持既有消息 Y 锚点，只挂载 15 行；
  CSP CSSOM 改用 React `useInsertionEffect` 在 TanStack layout sync 前更新 canvas，不新增滚动算法；
- Host Tree 采用 Zag 1.43.3 官方 virtualized contract（`getVisibleNodes` / `scrollToIndexFn`）组合
  已安装 TanStack Virtual；500-table Chromium fixture 只挂载 22–24 行，End 可滚至并聚焦末项，
  并按 WAI-ARIA 虚拟树要求声明 level/posinset/setsize；root 切换期间完成的旧 async child 请求按
  权威 root identity 丢弃，错误也不会污染新 collection；
- Chromium dark + reduced-motion 下 Runtime status/progressbar 的名称与状态可读，动画降至近零时长，
  480px 页面和 Design Lab 组件视口均无水平溢出。
- ErrorState/SettingsStatus 已接现有 RFC 9457 `ApiError`；Diagnostics、DLC、Projects/Resources、
  Conversation、Approval/Question、Model/Update 与 Table/Chart 显示安全 correlation metadata；结果失败
  不清空旧数据，服务错误不再同时 toast 与 inline 重复播报。Chart 数据读取改为既有 TanStack Query，
  获得统一 pending/error/refetch 生命周期；Conversation 显式重试保留同一 conversation 与 idempotency key，
  但网络恢复不会自动重放非幂等提交。
- Radix Collapsible 在 Chromium 实测会写 inline 尺寸变量，因 Electron CSP 被所有 Renderer disclosure
  边界拒绝并从依赖移除；ErrorDetails 与 Sources 改用 WHATWG `details/summary`。480px 下点击/Enter、
  焦点、无敏感文本、无水平溢出、`[style] = 0` 与 console 0 error/0 warning 均通过。
