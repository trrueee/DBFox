# DBFox UI 全量组件与运行时状态清单

> 文档类型：UI 运行时清单
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 范围：`desktop/src/`、四个内置 DLC 前端、Electron 启动与恢复界面  
> 目的：在恢复生产施工前，建立页面、大小组件、状态、错误恢复和验收场景的统一底图。

## 1. 使用方式

本清单不是新的 UI 状态事实源。运行状态仍直接来自既有 OpenAPI 合同、Electron 合同、
Zustand 投影和 DLC Host；本文只描述这些状态应如何被用户看见、理解和恢复。

每个可交互组件至少检查以下状态：

- 默认、hover、pressed、focus-visible、disabled；
- selected、expanded、checked、mixed（适用时）；
- loading、empty、error、success、stale、partial（适用时）；
- 长文本、长列表、窄宽度、缩放、中文与英文；
- light、dark、high contrast、reduced motion；
- 键盘、鼠标、屏幕阅读器名称与状态播报。

“错误”不等于一个红色句子。可恢复错误应同时给出：发生了什么、影响范围、首选恢复动作；
请求 ID、错误码、检查详情放在可展开的技术信息中。不可向 UI 暴露 Token、API Key、密码、
完整 DSN 或内部堆栈。

## 2. 全局运行时状态

| 区域 | 组件与权威状态 | 必须呈现的状态 | 恢复与无障碍要求 |
| --- | --- | --- | --- |
| React 前启动 | `boot.css` / 启动 DOM | 正在启动、启动失败、超时或 Host 无响应 | 独立于 React token 仍需与主题语义一致；失败提供重试或打开日志 |
| Engine 启动 | `EngineStartupGate` / Electron `EngineStartupStatus` | starting、health check、ready、failed | `role=status/alert`；失败提供重启、打开日志、技术信息 |
| Engine 维护 | lifecycle phase | recovering、migrating、maintaining | 明确当前阶段和影响；迁移中禁止误导性重试；恢复后移除 notice |
| 意外退出 | lifecycle notice | 已断开、正在恢复、恢复失败 | 不自动重放非幂等请求；说明未发送/未完成动作 |
| React 致命异常 | `ErrorBoundary` + shadcn Empty/Button | 未捕获异常 | 已采用真实 fatal fallback；动作明确为“重试渲染”，重复失败时提示重启/诊断日志；敏感 error/stack 只进日志。边界位于 Provider 外，不伪造不可用的页内日志跳转 |
| DLC 渲染异常 | `DlcErrorBoundary` | DLC 组件失败、重试中、重复失败 | 隔离到 DLC slot；不让单个扩展击穿 App；原始异常只进技术详情 |
| 路由懒加载 | `Suspense` fallback | 页面或 bundle 加载 | 短时 spinner，长时需可辨识标签；失败走可恢复错误而非永久 loading |
| 全局通知 | `Toast` | info、success、warning、error | Toast 只承载短暂、非关键反馈；关键错误留在发生表面并提供动作 |
| 离线/令牌失效 | API client / lifecycle | 网络不可达、401/403、Sidecar 不可达 | 区分“离线”“凭据/权限”“服务不可用”；不可统一显示“未知错误” |

## 3. App Shell、导航与覆盖层

### 3.1 窗口与工作区

| 组件 | 常态 | 边界与异常态 | 后续验收重点 |
| --- | --- | --- | --- |
| `TitleBar` | active、inactive、窗口可拖拽 | 最小化/最大化/关闭 hover/pressed；Windows 高对比度 | 图标按钮名称、拖拽区不吞交互、危险关闭不只靠红色 |
| `ResizableWorkspaceLayout` | 左栏/对话/工作面板 | 最小宽度、面板折叠、恢复保存尺寸、极窄窗口 | separator 键盘调整、`aria-valuenow`、125%~200% 缩放 |
| `WorkspaceShell` | ready | loading、empty、error | 空态动作明确；retry 返回原动作；不复制数据状态 |
| `WorkspaceDock` | closed、open、active view | 多 tab、tab overflow、view unavailable、DLC renderer error | 焦点进入/返回、关闭后选择邻近 tab、工具栏不换行 |
| Dock renderer fallback | 已注册 renderer | 未知 view type、DLC 未激活、schema 不支持 | 显示标题/类型/版本和可恢复动作，不静默空白 |
| `ThemeToggle` | light、dark、system | 系统主题变化、高对比度 | `aria-pressed` 或等价状态；主题切换无闪白 |

### 3.2 导航和命令

| 组件 | 状态 | 细节 |
| --- | --- | --- |
| `AppSidebar` | expanded、collapsed、active item、hover、focus | 收起时用 tooltip 保留名称；不能只靠图标差异表达选中 |
| Project resource sidebar | 无项目、加载、加载失败、空资源、部分 DLC 可用 | 区分“尚未添加”与“加载失败”；添加动作由 connector 提供 |
| `CommandPalette` / cmdk | closed、open、empty query、有结果、无结果、键盘 active | Esc 返回触发点；组合输入不误提交；shortcut 只是辅助说明 |
| Menu / Context menu | closed、open、checked、submenu、disabled | 使用现有 Radix focus/typeahead；危险项与普通项语义分离 |
| Tooltip / HoverCard / Popover | delay、open、collision、dismiss | tooltip 不承载必须阅读的错误；popover Esc/外点关闭并恢复焦点 |
| Dialog | open、busy、validation error、close blocked | 初始焦点和关闭后焦点明确；提交中禁重复提交，但保留取消策略 |

## 4. 项目、连接器与资源树

共享资源树 presentation 现在由版本化 `host.ui@1.0.0` 提供：Zag Tree View 负责 collection、
层级 ARIA、roving focus、方向键、typeahead、selection、expansion 与 async children；DLC 直接传入
原始领域对象和 accessor，不复制资源 DTO。Workspace、GitHub 与 Data 均已迁移；Data 通过 Zag
AbortSignal/loading/error 回调及 Host action/footer slot 保留 catalog refresh、分页、SQL 与 Table Dock。

### 4.1 项目

| 组件 | 运行时状态 | 错误与恢复 |
| --- | --- | --- |
| `ProjectCreateDialog/Form` | idle、字段 focus、invalid、submitting、success | 行内校验绑定字段；请求失败保留输入；重复名称说明解决方式 |
| `ProjectOverview` | 未选择项目、空项目、有资源、加载、失败 | 主要动作只能有一个；失败时不要把已有资源呈现为空 |
| Connector composition | 已加载、未安装、disabled、pending restart、activation failed | 直接使用 DLC lifecycle；等待重启与激活失败必须视觉区分 |
| Resource row | idle、hover、selected、context menu、busy、unavailable | 长名称截断但可获知全文；选择态与 focus 态同时可辨 |

### 4.2 Data DLC

| 组件 | 状态集合 | 细节 |
| --- | --- | --- |
| `ConnectionDialog` | 初始、字段 invalid、test busy/test fail/test pass、save busy/save fail | 密码不回显；DSN 不写日志；测试成功不等于已保存 |
| `DatabaseRow` | disconnected、connecting、connected、failed、selected | 连接失败给重试/编辑；不可把完整连接串放入 title |
| Catalog / schema tree | loading、empty、error、expanded、selected、stale | **已采用 Host Zag async Tree**；首次加载、局部失败重试、refresh、load-more、SQL/Table actions 保留原 operations/authority；大 schema 虚拟化仍需实测门禁 |
| `SqlConsoleDock` | blank、editing、validating、executing、cancel requested、done、failed | SQL 必须走 validate artifact → readonly execute；取消后不自动重放 |
| `SqlBlock` | draft、validated、rejected、executed、stale | 明确校验与执行不是同一状态；展示有界技术详情 |
| `ResultGrid` | loading、empty、ready、partial/truncated、paging、sort/filter、error | header/row/cell 键盘语义；大结果虚拟化；错误不覆盖仍可读的旧结果 |
| `ProfileGroup` | collapsed、loading、ready、unsupported、error | 统计含义和样本范围可见；不把缺失值当 0 |

### 4.3 Workspace DLC

| 组件 | 状态集合 | 细节 |
| --- | --- | --- |
| `WorkspaceConnector` | 未绑定、选择目录、绑定中、ready、权限失败、路径丢失 | 权限/不存在/占用分别说明；不自动改绑定目录 |
| `FileBrowser` | loading、empty、error、expanded、selected、refreshing | **已采用 Host Zag Tree**；loading/status、error/alert+retry、empty 与 keyboard/selection 已落地。当前按目录导航，后续如改 lazy nested tree 必须保留原路径 authority |
| `FileDock` | loading、text/binary/unsupported、large/truncated、changed/stale、error | 大文件有界；二进制不按文本解码；外部修改提示刷新而非静默覆盖 |
| Workspace artifact | creating、completed、failed、stale、schema unsupported | Artifact authority 和版本可见；失败保留上下文与重试入口 |

### 4.4 GitHub DLC

| 组件 | 状态集合 | 细节 |
| --- | --- | --- |
| `GithubConnector` | 未配置、鉴权中、ready、权限不足、rate limited、offline | 权限不足、限流、网络失败分开；不得显示凭据 |
| `GithubFileBrowser` | repo empty、loading、expanded、selected、pagination、error | **已采用 Host Zag Tree**；loading/status、error/alert+retry、empty 与 keyboard/selection 已落地。branch/ref、pagination/stale 和 child error 仍需真实 API fixture |
| `GithubFileDock` | loading、ready、binary、large/truncated、not found、permission error | 展示 ref/commit authority；404 与权限错误不可混淆 |
| GitHub artifact | creating、completed、failed、stale | 来源链接和版本由既有 artifact 提供，不建立第二份远程模型 |

### 4.5 Music DLC

| 组件 | 状态集合 | 细节 |
| --- | --- | --- |
| `MusicConnector` / `ResourceRow` | loading、empty、ready、importing、error | 导入按钮 busy；原音频仅内存可用的限制需提前说明 |
| `EmptyStudio` | 无乐谱/音频 | 给出可执行的 Agent 起点，不伪装为错误 |
| `ScoreStudio` | loading、ready、load error、playing、paused、stopped、loop | 播放/暂停状态可读；加载失败提供重试；卸载时终止音频 |
| `ScoreMeasure` | idle、active playback、selected、uncertain、focus | active/selected/uncertain 不只靠颜色；Enter/Space 可操作 |
| `PianoKeyboard` | adaptive/full 88、active note、focus、previewing | SVG 键盘需可见 focus；大量可聚焦键需要合理导航策略 |
| `Transport` | play/pause/stop/loop、position、selected measure | control group 命名；进度文本；不可用动作 disabled |
| `AudioStudio` | idle、source missing、transcribing、progress、ready、error | 进度有数值和文字；可取消；模型加载失败与“未检测音符”分开 |
| Waveform / A-B compare | no buffer、ready、playing、ended | 波形不是唯一进度表达；Original/Transcription 当前播放源可辨 |
| Score/Transcription Artifact | creating、completed、failed、stale | schema 校验失败进入 DLC boundary；置信度与不确定区间有文字说明 |

## 5. 对话与 Agent 运行时

### 5.1 会话与消息

| 组件 | 状态集合 | 交互与错误要求 |
| --- | --- | --- |
| `ConversationHistoryPanel` | loading、empty、ready、active、search/no result、error | 运行中会话可辨；长标题；加载更多；失败不抹除已缓存列表 |
| `ConversationWorkspace` | no conversation、loading、ready、stream reconnect、error | SSE 断线按 cursor/snapshot 恢复；不可把临时断线当运行失败 |
| `ConversationHeader` | idle、run active、cancel requested、completed/failed | 状态与取消动作一致；取消请求发出后显示等待而非立即伪装完成 |
| `MessageList` | empty、history loading、streaming、pagination | 流式内容 append 不抢滚动；用户上滚后不强制吸底 |
| User message | sent、queued、steered、cancel-and-replace | 投递策略可理解；未确认动作不显示已发送 |
| Assistant message | commentary、final、streaming、complete、bounded partial | partial 必须呈现限制原因；证据与 Artifact 引用可追溯 |
| `UnifiedComposer` | idle、focused、multiline、IME composing、disabled、sending、stopping | Enter/Shift+Enter、组合输入、引用、发送/停止、超长内容全覆盖 |

### 5.2 Run、Tool 和 Plan

权威状态直接来自 `types/conversation.ts`，UI 不建立镜像枚举。

| 对象 | 权威状态 | 呈现要求 |
| --- | --- | --- |
| Run item | pending、in_progress、waiting、completed、failed、cancelled | 图标、文字和时间线结构共同表达；失败/取消不只换色 |
| Plan step | pending、in_progress、completed、blocked、skipped | 保持顺序；blocked 给原因/下一步；skipped 不冒充 completed |
| Tool progress | indeterminate、determinate、none | determinate 使用原生/ARIA progress；未知进度不伪造百分比 |
| Tool visibility | summary、details、developer | 默认只显示必要摘要；参数/输出和错误详情按层级展开 |
| Run result | complete、bounded_partial | partial 展示 limitation code 的用户语言，不把部分完成写成成功 |
| Run terminal | completed、failed、cancelled | 终态不可回到 running；generation 变化后不重放非幂等工具 |

`AgentTimeline`、ToolGroup 和 Plan 在 running/waiting 时可默认展开，完成后允许折叠；焦点不因
状态刷新而跳走。Plan 的进度不是独立任务事实源，只从现有步骤投影计数。

### 5.3 审批与提问

| 组件 | 状态集合 | 必须协调的行为 |
| --- | --- | --- |
| `ApprovalCard` | pending、submitting approve/reject、approved、rejected、expired、cancelled、conflict/error | 风险 safe/warning/danger 有文字；提交中防重复；409 说明已被其他决策解决并刷新 |
| `QuestionCard` | waiting、option selected、free text、submitting、answered、cancelled、expired、error | 选项与自由文本互斥规则明确；失败保留输入；解决后只读呈现 |
| Danger confirm | closed、open、phrase invalid、submitting、failed | destructive action 用具体动词；默认焦点不落在危险按钮；可取消 |

### 5.4 Artifact、Evidence 与引用

| 组件 | 权威状态 | 呈现要求 |
| --- | --- | --- |
| `ArtifactCard` | creating、completed、failed、stale | creating 有界等待；failed 给原因/恢复；stale 提示版本并允许刷新 |
| `ArtifactDock` | closed/open、loading、renderer ready/error、unsupported schema | 关闭后回到来源；未知 renderer 不空白；保留 artifact identity |
| `DataReferencePanel` | empty、collapsed、expanded、missing reference | 引用 label、authority、locator 分层；丢失引用可诊断 |
| Evidence | available、value omitted、artifact unavailable | 不把“无 evidence”写成“已验证”；敏感值遵守脱敏边界 |

## 6. Artifact 与数据展示组件

| 类别 | 组件 | 状态与细节 |
| --- | --- | --- |
| 通用 | `ArtifactRenderer` fallback | type/schema/version 不支持、DLC disabled、parse error |
| 表格 | `TableArtifactView/Grid/Toolbar/Footer` | loading、empty、sort/filter、selection、virtualization、pagination、truncated、error |
| 单元格 | `CellValuePreview` | null、boolean、number、long text、JSON、image/binary、copy success/fail、truncated |
| JSON | `JsonTree` | scalar/object/array、empty、deep、large、collapsed、copy | 
| SQL | Data DLC Artifact View + Host `CodeArtifact` | readonly、validation、execution、syntax highlight、large、error |
| Markdown | `MarkdownContent` | loading、empty、long、code block、table、unsafe link/content | 
| Chart | `DeferredChart` / chart view | lazy loading、no data、invalid config、too many points、resize、error、fallback table |
| Image | `ImageCell` / image preview | loading、decode error、fit/actual、100–200% zoom、native scroll/arrow pan、alt/尺寸 metadata、URL change reset 已覆盖；missing、copy/save fail 继续验证 |
| 文件 | file/text view | encoding、binary、large/truncated、external change、not found、permission |

数据密集组件必须继续遵守“大结果留在结果后端、模型只拿有界摘要”。UI 的分页、虚拟化、
截断提示和导出动作不能把整份结果复制进 Zustand 或对话消息。

## 7. 设置、更新与诊断

| 页面/组件 | 状态集合 | 设计要求 |
| --- | --- | --- |
| `SettingsScaffold` | content、section、field、toggle、status、action bar | 保持统一 label/helper/error/dirty/save anatomy；不为每页创建新表单壳 |
| Appearance | theme、accent、neutral tone、density、font scale、system/high contrast | preview 色值应来自同一配置源；保存/恢复默认；变化即时但可撤销 |
| Model | no provider、loading、editing、testing、test pass/fail、saving、secret present | Key 只显示“已配置”；测试与保存状态分开；失败按 provider/网络/权限分类 |
| DLC Center | loading、empty、installed disabled、enable pending restart、active、disable pending restart、activation failed | 重启要求明确；信任/安装/启停各自 busy 和失败；不要合并成 boolean |
| Update | checking、up-to-date、available、downloading、progress、ready to install、failed | 下载进度和剩余动作；不可用时保留当前版本；安装前说明重启影响 |
| Diagnostics | loading、empty、ready、filtering、group selected、fallback frontend logs、error | 日志可搜索/换行/复制/下载；空日志与加载失败分开 |
| Audit clear | confirm、clearing、success、failed | 明确范围和不可逆性；默认安全焦点；失败不伪装已清理 |

## 8. 基础组件状态矩阵

| Primitive | 额外必测状态 |
| --- | --- |
| Button / IconButton | default、primary、outline、ghost、danger、loading、disabled、icon-only、long label |
| Input / Textarea | empty、filled、placeholder、focus、invalid、disabled、readonly、IME、autocomplete |
| Select / ComboBox | closed/open、typeahead、empty、no result、disabled option、long option、clear |
| Checkbox / Radio / Switch | unchecked/checked/mixed、focus、disabled；Switch 仅用于立即生效设置 |
| Tabs | active、focus、overflow、closable、dirty、disabled、keyboard traversal |
| Toolbar | normal、narrow、overflow menu、disabled group、roving focus；禁止自然换成两行 |
| Badge / Tag | neutral、info、success、warning、danger、removable、overflow；不能作为唯一状态说明 |
| Tree | Host Zag runtime 已覆盖 collapsed/expanded、selected、focus、三级 nesting、keyboard、loading child、child error/retry 与 empty branch；many nodes/virtualization 继续作为门禁 |
| ScrollArea | keyboard scroll、track hover、nested、high contrast、content resize |
| Skeleton / Spinner / Progress | short/long wait、reduced motion、determinate/indeterminate、error transition |
| EmptyState | first-use、no result、filtered empty、permission empty、true empty；动作随原因不同 |
| ErrorState | inline、section、page、fatal；retry/open settings/open logs/copy request id |

## 9. 错误分类与呈现合同

API 边界已有 RFC 9457 `ProblemDetails`：`code`、`title`、`detail`、`status`、`request_id`、
可选 `checks/errors`。UI 应直接使用这一权威合同，不新增另一套 Error DTO。

| 错误类别 | 用户层标题 | 主动作 | 技术详情 |
| --- | --- | --- | --- |
| 字段/输入错误 | 哪个字段需要修改 | 聚焦第一个错误字段 | 字段规则，不显示 request id |
| 冲突 409 | 状态已变化或动作已处理 | 刷新当前对象 | code、request id、最新状态 |
| 鉴权/权限 401/403 | 凭据失效或没有权限 | 打开相关设置/重新授权 | code、request id，不显示 secret |
| 未找到 404 | 对象已删除、移动或版本不存在 | 返回列表/刷新 | object identity、request id |
| 限流/上游限制 | 当前暂时不可执行 | 按明确时间重试或更换配置 | provider-safe code、request id |
| 网络/Sidecar 失败 | 本地服务或网络不可达 | 恢复服务/重试幂等读取 | lifecycle phase、request id |
| DLC 激活/渲染失败 | 某个扩展不可用 | 重试 DLC / 打开 DLC 设置 | DLC id/version、safe message |
| 任务/工具失败 | 哪一步失败、已有结果是否保留 | 重试允许的步骤/修改输入 | tool name、attempt、error code |
| 部分完成 | 已完成什么、未完成什么 | 继续/调整约束 | limitation codes |
| 致命异常 | 当前表面无法继续 | 重载/打开日志 | correlation id；堆栈仅诊断日志 |

重复错误应就地更新同一个状态区域，避免同时出现 inline error、toast 和全局 banner 三份相同消息。
成功 Toast 不应掩盖页面仍然失败的真实状态。

## 10. 视觉、内容与环境验收矩阵

### 10.1 视口与缩放

- 1280×800、1440×900、1920×1080；窗口最小支持宽度；
- Windows 100%、125%、150%、200% 缩放；
- 左栏最窄/最宽、工作面板关闭/打开、三栏同时存在；
- 超长中文、英文、路径、SQL、URL、错误码和 1~4 行按钮标签。

### 10.2 外观与输入

- light、dark、system、所有 neutral tone 和 accent；
- Windows high contrast，任何状态不只依赖颜色；
- reduced motion；动画暂停后仍能理解进度；
- keyboard only、screen reader name/state、IME、鼠标和触控板；
- focus 在 dialog/popover/dock/open-close、列表刷新和流式更新后保持合理位置。

### 10.3 数据和运行时 fixture

- no project / empty project / one resource / many resources；
- offline / Engine recovering / Engine failed / token invalid；
- no conversation / long conversation / streaming / reconnect / bounded partial；
- tool pending/running/waiting/failed/cancelled，Plan blocked/skipped；
- approval/question pending/submitting/resolved/expired/conflict；
- Artifact creating/completed/failed/stale/unsupported；
- empty/large/truncated table，deep JSON，large file，chart invalid/too many points；
- DLC disabled/pending restart/activation failed/render exception；
- Music no buffer/transcribing/progress/no notes/playback/uncertain ranges。

## 11. 恢复施工前的完成定义

1. 本清单中的每类组件在 Design Lab 有代表性 fixture；生产独有状态可用最小 harness 呈现。
2. 每个错误状态都有权威来源、影响范围、主恢复动作和敏感信息边界。
3. 关键组件完成 Current / Candidate A / B / C 同数据对比，而不是只比较静态截图。
4. 字体、字号和颜色问题按 `typography-color-audit.md` 收敛到权威 token。
5. 逐组件决策标记 KEEP、ADAPT、ADOPT、REFERENCE 或 REJECT，并记录依赖与退出成本。
6. 经上述基线确认后，按[现行 UI 设计与开发规范](../quality/ui-design-and-development.md)继续生产实现；
   Plan 与错误只是其中两条纵向能力，历史任务路线仅保留在
   [UI 市场驱动重构任务记录](../archive/reviews/ui-market-driven-refactor-task.md)。

## 12. 文件级组件覆盖索引

本索引用于防止“小组件未被盘点”。测试文件、hook/store、纯 registry/utility 不被误算为视觉组件，
但它们对应的行为已归入所属表面。

### 12.1 Core 与基础组件

| 文件/组件 | 所属检查项 |
| --- | --- |
| `App.tsx` | 根 composition、lazy fallback、settings/workspace route、global overlays |
| `brand/FoxIcon.tsx` | brand mark 尺寸、单色/彩色、high contrast、decorative/accessibility |
| `TitleBar.tsx` | 窗口 active/inactive 与系统按钮 |
| `ThemeToggle.tsx` | light/dark/system/high contrast |
| `Toast.tsx` | tone、queue、dismiss、duration、screen reader announcement |
| `CommandPalette.tsx`、`appShell/AppCommandPalette.tsx` | query/results/empty/keyboard/shortcut/focus return |
| `DangerConfirmDialog.tsx` | phrase validation、safe focus、busy/error/cancel |
| `EngineStartupGate.tsx` | startup/health/recover/migrate/maintain/fail |
| `ErrorBoundary.tsx` | fatal reload/log/technical detail |
| `LlmConfigPanel.tsx` | legacy/embedded model config states；与 Settings Model 的重复边界需核对 |
| `ImageCell.tsx` | loading/decode/zoom/pan/metadata/keyboard |
| `data-grid/CellValuePreview.tsx`、`data-grid/json.tsx` | type preview、deep/large/copy/truncate/error |
| `settings/SettingsScaffold.tsx` | Content/Section/Field/Toggle/Status/ActionBar |

### 12.2 UI primitives

| 文件 | 覆盖状态 |
| --- | --- |
| `ui/button.tsx` | variant/size/icon-only/loading/disabled/focus |
| `ui/badge.tsx` | tone/status/long label |
| `ui/input.tsx`、`ui/label.tsx` | value/invalid/disabled/readonly/helper association |
| `ui/command.tsx` | input/list/group/item/empty/shortcut |
| `ui/context-menu.tsx`、`ui/dropdown-menu.tsx` | item/check/radio/submenu/separator/disabled/danger |
| `ui/dialog.tsx` | overlay/content/header/footer/title/description/close/focus |
| `ui/hover-card.tsx`、`ui/popover.tsx`、`ui/tooltip.tsx` | delay/collision/dismiss/focus/long content |
| `ui/select.tsx` | trigger/value/content/item/scroll/typeahead/disabled |
| `ui/tabs.tsx` | list/trigger/content/keyboard/overflow |
| `ui/toolbar.tsx` | roving focus/group/overflow/narrow |
| `ui/panel.tsx`、`ui/separator.tsx` | surface hierarchy/orientation/high contrast |
| `ui/resizable.tsx` | panel group/handle/keyboard/min-max |
| `ui/scroll-area.tsx` | viewport/scrollbar/thumb/nested/high contrast |
| `ui/state.tsx` | EmptyState/ErrorState/LoadingState/Skeleton |

### 12.3 App Shell、项目与资源

| 文件/组件 | 所属检查项 |
| --- | --- |
| `navigation/AppSidebarPrimitives.tsx` | Header/Content/Footer/Group/NavRow/collapsed tooltip |
| `appShell/ResizableWorkspaceLayout.tsx` | three-pane layout/persistence/min-max |
| `workspace/WorkspaceShell.tsx` | loading/empty/error/ready |
| `appShell/WorkspaceDock.tsx` | tabs/view/close/overflow/empty |
| `appShell/ConversationCenter.tsx` | conversation region composition |
| `appShell/DesktopLifecycleMonitor.tsx` | recovering/restarted/failed notices |
| `dock/dockViewContent.tsx`、`dock/coreDockViews.tsx` | core view render/fallback/visibility |
| `projects/ProjectCreateDialog.tsx`、`ProjectCreateForm.tsx` | dialog/form validation/submit/error |
| `projects/ProjectOverview.tsx` | no project/empty/ready/error |
| `resources/ProjectResourceSidebar.tsx` | project/connector/resource loading/empty/error |
| `resources/resourceConnectorComposition.tsx` | DLC connector availability/failed boundary |

### 12.4 对话与 Agent

| 文件/组件 | 所属检查项 |
| --- | --- |
| `agent/UnifiedComposer.tsx`、`conversation/workspace/Composer.tsx` | input/actions/delivery/stop/reference/IME |
| `conversation/ConversationHistoryPanel.tsx` | history loading/empty/active/search/error |
| `workspace/ConversationWorkspace.tsx` | load/stream/reconnect/error/composition |
| `workspace/ConversationHeader.tsx` | title/run status/cancel requested/actions |
| `workspace/MessageList.tsx` | empty/pagination/stream/autoscroll |
| `workspace/AgentTimeline.tsx` | message/tool group/plan/run error/cancel/artifacts |
| `workspace/ApprovalCard.tsx` | requested/submitting/resolved/conflict/expired |
| `workspace/QuestionCard.tsx` | options/free text/submitting/resolved/error |
| `workspace/ArtifactDock.tsx` | artifact view loading/error/close |
| `workspace/DataReferencePanel.tsx` | evidence/saved/missing/collapsed |

### 12.5 Work Surface 与 Artifact

| 文件/组件 | 所属检查项 |
| --- | --- |
| `workspace/SmartQueryHome.tsx`、`smartQuery/AskInputBox.tsx` | first-use prompt/focus/disabled/sending/error |
| `artifacts/ArtifactCard.tsx` | creating/completed/failed/stale/actions |
| `artifacts/coreArtifactViews.tsx`、`hostArtifactViews.tsx` | Core type 与公共 Representation 视图；领域 View 由 DLC 注册 |
| `artifacts/ChartArtifactView.tsx`、`DeferredChartArtifactView.tsx` | lazy/no-data/invalid/large/resize/error |
| `artifacts/MarkdownArtifactView.tsx`、`queryResult/MarkdownContent.tsx` | safe markdown/code/table/link/long content |
| `artifacts/CodeArtifactView.tsx`、`SqlCodeBlock.tsx` | DLC 可复用的代码工件、SQL highlight、copy/download |
| `artifacts/TableArtifactView.tsx` | table orchestration/loading/empty/error |
| `table/ArtifactTableToolbar.tsx` | sort/filter/actions/overflow/narrow |
| `table/ArtifactTableGrid.tsx` | virtual rows/cell focus/selection/loading/empty |
| `table/ArtifactTableFooter.tsx` | paging/count/truncation/loading/error |

### 12.6 设置与诊断

| 文件/组件 | 所属检查项 |
| --- | --- |
| `settings/SettingsPage.tsx`、`SettingsSidebar.tsx` | route/active/focus/scroll/narrow |
| `settings/AppearanceSettingsPanel.tsx` | theme/accent/neutral/density/font scale/preview/reset |
| `settings/ModelSettingsPanel.tsx` | provider/config/secret/test/save/error |
| `settings/DlcCenter.tsx` | inspect/trust/install/enable/disable/restart/activation error |
| `settings/UpdateSettingsPanel.tsx` | check/download/progress/install/restart/error |
| `pages/DiagnosticsPage.tsx` | summary/log group/table/empty/error/fallback/export/clear audit |

### 12.7 DLC frontend components

| DLC | 组件 |
| --- | --- |
| Data | `ConnectionDialog`、`DatabaseRow`、`ResultGrid`、`SqlBlock`、`SqlConsoleDock`、`CatalogTableDock`、`ProfileGroup`、`DataConnector` |
| Workspace | `WorkspaceConnector`、`FileBrowser`、`FileDock`、`WorkspaceArtifact` |
| GitHub | `GithubConnector`、`GithubFileBrowser`、`GithubFileDock`、`GithubArtifact` |
| Music | `ResourceRow`、`MusicConnector`、`ScoreMeasure`、`ScoreView`、`PianoKeyboard`、`Transport`、`ScoreStudio`、`AudioStudio`、`EmptyStudio`、`PianoStudioDock`、`ScoreArtifactCard`、`TranscriptionArtifactCard` |

### 12.8 非视觉但必须联动的边界

- `extensionHost.tsx`、artifact/dock registries：unknown type、unsupported schema、DLC exception；
- theme/lifecycle/conversation/sql-backed hooks：loading、stale、cancel、reconnect 和 generation；
- API client/presentation：ProblemDetails 安全字段、状态文案、未知错误降级；
- design contract：token 存在、字体族、颜色域、DLC namespace 和 CSP-safe style。
