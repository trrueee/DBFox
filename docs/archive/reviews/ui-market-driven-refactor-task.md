# DBFox UI 市场驱动重构任务记录

> 文档类型：历史任务记录
>
> 状态：历史
>
> 最后核验：2026-08-28

> 本文记录 2026-08 的 UI 市场驱动纠偏任务，已由
> [`../../quality/ui-design-and-development.md`](../../quality/ui-design-and-development.md) 的当前开发规范和
> [`../../ui/component-adoption-report.md`](../../ui/component-adoption-report.md) 的实际采用结果替代。
> 本文不再是新增 UI 的逐项执行门禁，不得据此重复调研或替换已经采用的成熟组件。

> 当前执行口径（2026-08-26）：候选和生产替换都必须使用可核验的真实上游包、registry
> 源码或官方源码。仅模仿外观、重新手写同类组件、用“概念 anatomy”包装自研实现，不算采用。
> 现有自研呈现默认进入替换范围；只有已经由成熟依赖实现的基础能力，或属于 DBFox 权威
> runtime / data / security / state contract 的部分可以保留。Design Lab 中无法对应真实上游实现的
> 手写 A/B/C 不得作为采用证据，应删除或标为无效历史草稿。

> 调研不是只运行 `ui-ux-pro-max`。它只能作为候选发现和 UX/a11y 检查清单，可能把桌面产品误判成
> landing page，也可能推荐与 local-first、CJK、现有品牌不相容的在线字体或配色。每项采用必须同时
> 经过：项目实现/历史、官方平台与框架、成熟开源源码/许可证、真实产品交互、UI/UX Pro Max 检查。
> 任一来源都不能单独决定采用；结论必须说明接受与否的证据。

你上一轮执行方向不正确。

虽然你完成了大量 UI 重构、测试和设计合同，但你没有完成我最重要的要求之一：

我明确提供了大量 UI Component Marketplace / Registry / Open-source Component Sources，要求你针对 DBFox 每一种视觉功能真正去这些市场搜索、浏览 Demo、阅读源码、横向比较，然后优先完整采用或基于成熟实现扩展，而不是只学习风格以后继续自己造组件。

上一轮你主要使用项目已有 Radix / TanStack / Lucide，再参考少数 shadcn / assistant-ui / Agent Elements 的思想后自行重构，这不符合要求。

这次任务的目标不是“再重构一遍 UI”，而是：

对已经完成的 DBFox vNext UI 进行一次完整的 Market-driven Component Review & Replacement。

你必须把当前实现与大量成熟外部组件逐项比较，真正选择优秀组件，并在明显优于现有实现时采用其源码、结构、交互和行为，而不是继续凭感觉自己写。

一、必须先阅读的本项目权威文件

开始任何修改之前，完整阅读并遵守：

docs/dbfox-master-product-ui-contract.md
Agent Core / Capability DLC architecture contract
当前 frontend architecture 文档
CONTRIBUTING.md
desktop/scripts/check-design-contracts.mjs
当前 Design Lab
当前 Core UI primitives
当前 Workspace / GitHub / Data / Music DLC frontend

Master Product & UI Contract 是产品/UI最高权威。

不允许为了引入第三方组件改变已经接受的：

Agent Runtime
Project / Conversation / Run authority
Artifact / Evidence authority
Core / DLC ownership
Backend API
Store 事实源

这是 Presentation / Interaction Component 选型和实现任务，不是 Runtime 重构任务。

二、必须真正访问和调研这些组件市场

以下不是“可选参考”，而是本任务要求检查的采购来源。

必须实际访问、搜索、查看 Demo / Preview / Documentation / Source：

General component marketplaces
21st.dev
Uiverse
Component System Directory
registry.directory
Shoogle
Agent / AI UI
21st.dev Agent Elements
AI Elements
Prompt Kit
Nexus UI
assistant-ui
Manifest UI
agentcn / 其他在 registry.directory / Shoogle 中发现的高质量 Agent UI registry
Application / Core UI
shadcn/ui
Dice UI
ReUI
React Aria based registries
blocks.so
Origin UI / Coss UI / Tailark 等高质量 application component sources

如果 Component System Directory、registry.directory 或 Shoogle 中发现比以上列表更适合的库，也要继续深入。

不要因为已经知道某个库，就跳过其他市场。

目的就是做横向比较。

三、不要先写代码。先建立完整 UI 采购清单

对 DBFox 当前所有用户可见 UI，按产品意义而不是代码目录重新建立清单。

至少必须覆盖：

Core / Shell

Sidebar、Project switch/navigation、Recent work、Command Palette、Tabs、Resizable Pane、Work Surface、Dialog、Dropdown、Popover、Tooltip、Toast、Empty、Loading、Error、Settings scaffold。

Composer

Prompt input、textarea autosize、context/reference chips、attachments、suggestions、left/right actions、send、stop、running mode、Queue / Steer / Replace selector、error。

Agent Interaction

User message、Assistant answer、Streaming、Thinking/Working、Tool、ToolGroup、Plan、Question、Approval/Confirmation、Evidence/Citation、Sources、Error、Cancelled。

Work Surface

Tabs、Artifact frame、Artifact preview、File viewer、Code/Diff、Tree、Toolbar、Inspector。

Data capability

Resource tree、connection form、database/table browser、schema view、SQL editor/query block、DataGrid/result table、cell selection、loading/error/empty。

Workspace/GitHub capability

File/Repo tree、binding UI、file viewer、patch/diff、context entry。

Music capability

Resource browser、Studio shell body、transport、waveform、piano、notation、progress/loading。

四、每一个类别至少要做候选比较

对重要组件，不能看到第一个能用的就采用。

一般至少找 3 个候选。

对 Composer / Sidebar / ToolGroup / Plan / Approval / Question / Tree / DataGrid / Work Surface 这几个关键组件，尽量比较 5 个候选。

每一个候选必须记录：

来源
具体组件名称
具体 URL
Demo / Preview
是否能看到源码
技术栈
Tailwind 版本
React 版本
Radix / Base UI / React Aria 等依赖
Accessibility
Keyboard behavior
Responsive behavior
Loading / disabled / error states
API / state model
License
是否容易适配 DBFox design tokens
是否会引入另一套 Button/Input/Dialog
是否依赖 Vercel AI SDK 或自己的 Runtime
和当前 DBFox 实现相比好在哪里
缺点

最后明确标记：

ADOPT

ADAPT

REFERENCE ONLY

REJECT

不能只写“参考了 XXX 的设计思想”。

五、必须提供可验证的 Candidate Matrix

在开始大规模修改代码以前，先生成一份实际调研结果文档，例如：

docs/ui/component-market-review.md

示例：

DBFox component Candidate Source Decision Why
Composer PromptInputWithActions 21st / Prompt Kit ADAPT 最符合布局，保留 DBFox runtime
Composer Agent Elements InputBar Agent Elements ADAPT actions API 优秀
Composer Nexus PromptInput Nexus REFERENCE attachment 处理优秀
ToolGroup Agent Elements ToolGroup Agent Elements ADOPT/ADAPT 正好对应 FunctionCall grouping
Thread assistant-ui Thread assistant-ui REFERENCE auto-scroll 行为成熟，但不能换 Runtime

这个文档必须有真实 URL，而不是只有库名称。

如果没有完成这份 Matrix，不允许宣称开始完整实现。

六、重点：优先复用成熟源码，不要继续重复造轮子

对选中的组件，要检查源码。

如果源码质量高且许可证允许：

优先 copy source into DBFox → 去除不需要的依赖 → 改用 DBFox primitives/tokens → 接入 DBFox state。

而不是：

“看懂它长什么样以后自己重新写一个相似组件。”

例如我之前提供的：

PromptInputWithActions

和：

PromptInput

就是明确要求你作为 Composer 候选实际研究和采用的源码。

但是不要盲目复制它附带的标准 shadcn Button。

DBFox 已经有自己的：

Button
Dialog
Input
design tokens

所以应该是：

保留成熟组件的高级 composition / interaction，实现 DBFox 化。

七、必须记录源码来源 Provenance

每一个真正 ADOPT / ADAPT 的第三方组件，在 review 文档里记录：

upstream project
component
source URL
license
adaptation summary
copied or concept-only
local destination

如果适当，在源码文件顶部保留简短 attribution / upstream reference。

不要以后让人不知道代码到底是自己写的还是从哪里演化来的。

八、Composer 是本轮第一优先级

先对当前 Unified Composer 做真正的外部候选比较。

至少研究：

我提供的 PromptInputWithActions
Prompt Kit PromptInput
Agent Elements InputBar
Nexus UI PromptInput
AI Elements prompt/composer
assistant-ui Composer
21st.dev 上其他高质量 prompt input variants

然后选择最佳组合。

DBFox 必须保留现有语义：

reference/context
clear reference
Queue
Steer current task
Cancel/Stop and replace
Stop
Send
Running state
Error

不要把 Demo 里的虚假功能带进来：

如果 Voice 尚不存在，不显示 Mic
Search 如果由 Agent 自动处理，不默认显示 Search mode

目标不是复制 ChatGPT。

九、Agent UI 第二优先级

对以下组件逐项市场调研并替换/改造：

ToolGroup

优先深挖 Agent Elements ToolGroup、assistant-ui tool group、AI Elements Tool 等。

Plan

优先研究 Agent Elements PlanTool 以及其他 Agent plan components。

Question

Agent Elements QuestionTool、Nexus Questions 等。

Approval

AI Elements Confirmation / Agent approval implementations。

Thinking / Working

至少比较多个实现，选择最克制的一种。

Evidence

Nexus Citation、AI Elements Sources、assistant-ui Sources 等。

仍然保持 DBFox Artifact/Evidence Runtime 为唯一事实源。

十、Core Application UI 第三优先级

Sidebar 不允许再靠自己凭感觉设计。

实际调研：

shadcn Sidebar
blocks.so sidebar variants
Dice / Origin / ReUI / Tailark / Coss 中成熟 sidebar/application shell
Component System Directory 中优秀 desktop/productivity systems

研究它们的：

row anatomy
section
collapsed rail
action placement
alignment
hierarchy
hover
selected
keyboard

最终仍然遵守 DBFox：

Task-first navigation

DLC 不进入 Main Sidebar。

十一、Tree / DataGrid 必须真正采用成熟模式

Tree 至少比较：

ReUI
React Aria Tree
Dice/shadcn ecosystem 中成熟 Tree
其他 registry.directory / Shoogle 高质量 Tree

DataGrid 至少比较：

ReUI
shadcn/TanStack based data table implementations
mature enterprise/application systems

不要求更换 DBFox 的 TanStack data engine。

但 row/column/header/selection/empty/loading/filter/resize/keyboard 等 presentation 和 interaction 应尽量采用成熟实现。

十二、Core / DLC 视觉合同不能破坏

牢记：

Core owns the experience. DLC owns the capability.

DLC 可以拥有：

SQL editor
database hierarchy
waveform
piano
chart
music notation
domain layout

DLC 不得拥有：

App Sidebar
Work Surface tabs
top-level dialog chrome
Button system
global typography
global accent
Toast
Core status UI

现有 SDK 的：

Connector
Dock View
Artifact Renderer

三个 contribution seam 保留。

不重新发明 Core/DLC architecture。

十三、不要全部推倒重写

当前版本已经有大量正确实现。

对每一块先判断：

KEEP

当前实现已优于/等于市场方案，不动。

REFINE

当前逻辑正确，只替换 presentation。

ADAPT

采用外部成熟实现的一部分。

REPLACE

外部实现显著更优秀，完整迁移 interaction/component structure。

不能因为这是“组件市场任务”就为了证明做了工作而乱换成熟代码。

十四、Design Lab 是强制比较环境

所有候选首先进入 Design Lab。

关键组件需要能并排比较：

Current DBFox
Candidate A
Candidate B
Candidate C

使用相同 fixture。

至少覆盖：

Light
Dark
Chinese
English
1280×800
1440×900
125%
150%
disabled
loading
error
long content

必须实际视觉查看，不得只读源码以后自己判断。

十五、采用标准

外部组件只有同时满足大多数以下条件才采用：

明显优于当前 UI。
interaction 已经成熟。
accessibility 良好。
keyboard 行为完整。
状态设计完整。
可以适配 DBFox neutral + blue tokens。
不强迫 DBFox接受另一套 Runtime。
不引入另一套 design system。
不增加不必要依赖。
能服务 Core/DLC visual contract。

如果只是截图好看、代码质量差：

REJECT。

十六、不要未经评估增加依赖

每一个新 dependency 都必须解释：

为什么现有依赖不能解决；
bundle cost；
maintenance；
license；
是否值得。

如果只需要 150 行优秀源码：

优先 vendor/adapt source，而不是增加一个庞大 runtime dependency。

十七、每完成一个类别都要留下证据

例如 Composer 完成后报告：

Composer

researched: 8
shortlisted: 4
adopted: Prompt Kit PromptInput structure
adapted: Agent Elements action composition
referenced: Nexus attachment UX
rejected: X because ...

upstream:
...

local:
...

behavior preserved:
Queue / Steer / Replace / Reference / Stop

ToolGroup、Plan、Sidebar、Tree 等都这样。

十八、绝对禁止再次这样报告

不允许：

“参考了 shadcn / Claude / Agent Elements 的风格，然后重新实现。”

这句话不能作为本任务完成证据。

必须回答：

具体看了哪些组件？

URL 是什么？

比较了什么？

选了哪个？

复制/适配了哪些源码？

本地文件在哪里？

为什么没选其他候选？

十九、测试不是唯一完成条件

即使：

100% tests pass
lint pass
TypeScript pass
build pass

如果没有完成广泛组件市场 research / comparison / source adoption，

任务仍然没有完成。

这正是上一轮的问题。

二十、完成条件

只有以下所有条件同时满足，才允许写“完整完成”：

当前 UI inventory 完成。
所有指定市场都实际调研过。
关键组件存在真实 Candidate Matrix。
每个关键组件至少比较 3–5 个实现。
Design Lab 做过真实视觉比较。
明确 KEEP / ADAPT / REPLACE / REJECT。
选中的成熟实现已经实际集成，而不是只学习外观。
保留源码 provenance。
Core / DLC visual contract 完整保持。
DLC visual lint 生效。
Workspace / GitHub / Data / Music 都通过新的 Core visual grammar。
所有测试、TypeScript、lint、build、bundle gate 通过。
Light / Dark / 125% / 150% / small window 视觉验收通过。
最终提供一份完整的 component-market-review.md 和 adoption report。
工作方式

不要再次直接进入“大规模写代码”。

第一阶段必须先完成研究和 Candidate Matrix。

研究过程中可以逐步把候选放入 Design Lab，但在没有横向比较前不要直接替换 production component。

如果现有组件经过比较后确实已经最好，可以保留，但必须有比较证据。

这次我要的不是“设计师风格模仿”。

我要的是：

成熟组件采购 + 源码审查 + 交互比较 + DBFox 化集成。

开始执行。

---

## 当前调研与采用证据

- 组件市场与逐类候选矩阵：[`../../ui/component-market-review.md`](../../ui/component-market-review.md)
- 全量组件和运行时状态清单：[`../../ui/ui-runtime-inventory.md`](../../ui/ui-runtime-inventory.md)
- 字体、字号、颜色与 token 审计：[`../../ui/typography-color-audit.md`](../../ui/typography-color-audit.md)
- Plan 与错误反馈协同设计：[`../../ui/plan-error-design.md`](../../ui/plan-error-design.md)
- Design Lab 全状态与对比矩阵：[`../../ui/design-lab-state-matrix.md`](../../ui/design-lab-state-matrix.md)
- 已实际接入的采用记录：[`../../ui/component-adoption-report.md`](../../ui/component-adoption-report.md)

扩展审计阶段暂停新的生产接入。候选只有完成同 fixture 的 Design Lab 对比、明确采用决策和
provenance 后，才进入生产实现；Plan 与错误反馈是完整路线中的两条纵向能力，不替代 Core、
Workspace、Data、GitHub、Music 和设置等其余范围。
