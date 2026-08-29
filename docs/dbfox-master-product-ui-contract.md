# DBFox Master Product & UI Contract

> 文档类型：产品与 UI 总纲
>
> 状态：已接受
>
> 最后核验：2026-08-28
>
> 适用范围：Desktop Core、Workbench、Conversation、Project、Settings、所有官方与第三方 Capability DLC 的用户可见体验
>
> 不适用范围：Agent Runtime 权威、Tool 执行安全、Resource Authority、DLC 生命周期与后端领域模型

## General-purpose Agent Workspace 产品与视觉总纲

**文档级别：Master / Highest Product & UI Authority**

---

# 0. 文档权威与关系

DBFox 现有的 Agent Core / Capability DLC 架构已经明确：

> Core 只拥有 Agent Runtime、Workbench composition、lifecycle 与 authority；Data、Workspace、GitHub 以及未来业务域均属于 Capability DLC。Project 是共同的 durable work context，而不是 Database、Workspace 或其他具体 Resource。

这一架构继续作为技术所有权的最高权威。

本文件新增的是：

> **所有用户可见产品体验的最高权威。**

以后文档层级固定为：

```text
1. Agent Core / Capability DLC Architecture Contract
   └─ 决定谁拥有数据、状态、Runtime、Authority

2. DBFox Master Product & UI Contract   ← 本文
   └─ 决定用户看到什么、在哪里看到、长什么样、Core/DLC 视觉权责

3. Subsystem UX Specs
   ├─ Agent Interaction
   ├─ Work Surface
   ├─ Data Grid
   ├─ Composer
   ├─ Extensions
   └─ Capability-specific specs

4. Component / Token contracts

5. Feature implementation
```

现有 `dbfox-quiet-workbench-design.md` 中仍然有效的原则继续继承，例如：

> Structure should be felt, not seen.

以及：

> DLC contributes content; DBFox owns presentation.

但其中以 **Resource Sidebar 为主要产品导航** 的信息架构不再作为未来方向。该文档降级为历史视觉规范和局部实现参考。

---

# 1. 产品重新定义

DBFox 不再定义为：

> Database Agent / AI Database Client

也不定义为：

> ChatGPT Clone

也不定义为：

> 把很多工具装进 Electron 的 Workbench

DBFox 的长期产品定义冻结为：

# **General-purpose Agent Workspace**

用户面对的不是一组工具。

用户面对的是：

```text
我的工作
   ↓
我和 Agent 协作
   ↓
Agent 使用能力
   ↓
产生实际成果
```

数据库、GitHub、本地文件、Music、Browser、Figma、Spreadsheet 等只是 Agent 可以调用的能力和上下文。

因此最终最高产品原则是：

> **DBFox 应该让用户感觉“这个 Agent 能做很多事情”，而不是“这个软件界面里有很多东西”。**

---

# 2. 外部产品给我们的核心启发

## 2.1 Claude：能力隐藏，工作突出

Claude 已经把 Skills、Connectors、Plugins 集中到统一的 Customize / Directory，而不是把每一个能力直接暴露在主导航里。([Claude帮助中心][1])

这意味着：

```text
能力很多
≠
Sidebar 很多
```

DBFox 采用同样原则：

**Capabilities 退到幕后，Work 留在前台。**

Claude Design 又明确采用：

```text
左：Conversation
右：Canvas
```

的结构，把对话和实际工作成果分离。([Claude帮助中心][2])

这直接对应 DBFox：

```text
Agent Collaboration
        ↕
Work Surface
```

---

## 2.2 Cursor：Agent 成为工作组织单位

Cursor 3 明确表示新界面是从头围绕 Agents 构建的统一 workspace，并允许多个 Agent 跨 workspace / repo 并行工作。([Cursor][3])

DBFox 应学习：

> Agent Session / Work 是导航对象。

而不是：

> Database / Tool / Connector 是导航对象。

---

## 2.3 Codex：Project → Agent Threads → Results

Codex App 将多个 Agent thread 按 Project 组织，并把 agent work、diff、skills 和长期任务放在同一个 command center 中。([OpenAI][4])

更重要的是，Skills 已经从代码扩展到研究、写作、文档、图像、部署等广泛工作。([OpenAI][4])

这进一步证明：

**DBFox 的产品骨架不能建立在某一个 Capability 上。**

---

## 2.4 Linear：解决 DBFox 当前“随意摆放感”的核心参考

Linear 2026 的 UI refresh 提出了两个原则：

> Don’t compete for attention you haven’t earned.

> Structure should be felt not seen.

它通过降低 Sidebar 对比度、减少 icon、减少不必要 separator，让用户真正工作的区域成为视觉中心。([Linear][5])

DBFox 的视觉纪律主要参考 Linear，而不是简单复制 Claude 的暖色系。

---

## 2.5 Raycast：Electron/Web 技术不应该产生 Web 产品感

Raycast 2.0 在重写时强调：

> 它不是“Web App 加一些 native hooks”，而是“使用 Web 做 UI 的 Native App”。

其团队专门处理 hover、popover、window behavior、平台 convention 和 flicker 等细节。([Raycast][6])

DBFox 同样必须遵守：

> React/Electron 是实现技术，不是产品视觉语言。

---

# 3. DBFox 用户心智模型

产品中只允许存在六种一级用户概念：

| 概念 | 用户理解 |
| ------------------------------- | -------------------- |
| **Project** | 一个长期工作上下文 |
| **Work Session / Conversation** | 我和 Agent 正在做的一件工作 |
| **Artifact** | Agent 创建、读取、修改或分析的成果 |
| **Context / Resource** | Agent 可以使用的数据和外部世界 |
| **Capability** | Agent 会做什么 |
| **System** | 模型、扩展、设置、安全、诊断 |

这里必须严格区分：

```text
Project ≠ Workspace
Project ≠ Database
Project ≠ GitHub Repository

Capability ≠ Navigation
Resource ≠ Navigation

Tool Call ≠ Product Page
```

这些原则与现有 Core / DLC 架构合同保持一致。

---

# 4. Core / DLC 的最高产品规则

冻结一句话：

# **Core owns the experience. DLC owns the capability.**

---

## 4.1 Core 永久拥有

Core 必须完全控制：

### Application Experience

```text
Window
TitleBar
Startup
Recovery
Main Shell
Main Navigation
Sidebar
Command Palette
```

### Agent Experience

```text
Home
Conversation
Composer
Message
Agent Activity
Plan
Question
Approval
Evidence
Error / Loading / Stop
```

### Work Experience

```text
Work Surface frame
Tabs
Pane resize
Artifact frame
Artifact navigation
Fullscreen / collapse
```

### System Experience

```text
Project
Settings
Extensions
Diagnostics
Dialog
Popover
Menu
Toast
Empty / Loading / Error
```

### Design Language

```text
Color
Typography
Spacing
Radius
Icon
Button
Input
Select
Tabs
Tree geometry
Focus
Hover
Selected
Motion
```

DLC 不允许重新设计以上任何部分。

---

# 5. DLC 永久拥有

DLC 负责：

```text
Domain semantics
Domain objects
Domain resource browsing
Domain-specific commands
Domain-specific form fields
Domain-specific visualization
Domain-specific workspace body
Domain Artifact body
```

例如 Data DLC：

```text
Connection
Database
Schema
Table
SQL
Data Grid
```

Workspace DLC：

```text
Folder
File
Patch
Snapshot
```

GitHub DLC：

```text
Repository
Revision
File
future Issue / PR
```

Music DLC：

```text
Score
Measure
Piano
Audio
Waveform
Transcription
```

---

# 6. DLC 视觉自由度分级

## Level 0 — Core Chrome

DLC 完全禁止修改：

```text
Sidebar
TitleBar
Work Surface tabs
Window
Dialog shell
Toast
Global navigation
Settings shell
```

## Level 1 — Application Controls

原则上必须使用 Core：

```text
Button
IconButton
Input
Select
Tabs
Field
Empty
Status
Tree Row
Toolbar
```

## Level 2 — Domain Layout

DLC 可以自主布局：

```text
SQL editor arrangement
Database browser
File explorer hierarchy
Piano Studio layout
Waveform + notation arrangement
```

但必须服从 Core typography、spacing 和 surface contract。

## Level 3 — Domain Visualization

可以最大程度自由：

```text
Chart
Waveform
Piano keyboard
Music notation
Diff syntax
Code syntax
Database type badges
```

这是真正允许“Capability personality”的位置。

---

# 7. 当前 DLC SDK 与未来视觉合同

目前 Frontend Extension SDK 只有三种主要 UI contribution：

```text
ResourceConnectorContribution
DockViewContribution
ArtifactRendererContribution
```

Extension Host 已负责：

* Project context；
* native file picker；
* credentials；
* Dock registration；
* Artifact registration；
* Error Boundary；
* `onAsk(reference)`；
* operation invocation。

因此不重新设计 DLC architecture。

要改变的是这些 contribution 的**视觉含义**。

---

# 8. Connector 新定义

今天 Connector 被直接渲染进 Sidebar。

未来：

> **Connector = Project Context contribution**

它应该出现在：

```text
Project
 └ Context / Capabilities
```

例如：

```text
DBFox Development

Context

Workspace
~/dev/DBFox

GitHub
trrueee/DBFox · main

Data
Analytics PostgreSQL

+ Add context
```

Host 拥有：

```text
section chrome
row geometry
spacing
icon
add action
remove action location
loading / error presentation
```

DLC 只贡献：

```text
title
domain body
binding semantics
add/remove behavior
```

---

# 9. DockView 新定义

现有 `WorkspaceDock` 应在产品层正式改称：

# **Work Surface**

Dock 是实现术语。

Work Surface 是用户概念。

DockView contribution 新语义：

> DLC 提供一个 Work Surface Body。

Core 提供：

```text
Tabs
Title
Icon
Close
Overflow
Resize
Collapse
Fullscreen
Context menu
```

DLC `render()` **不得再次创建顶层 Work Surface header**。

---

# 10. ArtifactRenderer 新定义

Artifact renderer 只负责：

> Artifact Body。

Core 负责：

```text
Artifact identity
title
summary
metadata
open
focus
selected
inline/workspace frame
error
loading
actions placement
```

当前 `ArtifactRendererContext` 已经区分：

```text
inline
workspace
```

这是正确方向，应继续使用。

---

# 11. `onAsk()` 成为 Core 统一交互

当前 Data Table 可以“询问 DBFox”。

Music 可以对某个 measure 提问。

它们本质都调用：

```text
DockRenderContext.onAsk(reference)
```

以后视觉必须统一。

DLC 不再自己设计：

```text
💬 小节 4
询问 DBFox
Ask AI
```

统一使用 Core：

```text
Ask DBFox
```

或者标准 Ask icon/action。

DLC 只提交：

```text
authority
object
locator
artifactId
label
```

---

# 12. App Shell 最终结构

长期稳定结构：

```text
┌────────────────────────────────────────────────────────────┐
│ DBFox                                       Window Controls │
├──────────────┬─────────────────────────┬───────────────────┤
│              │                         │                   │
│ NAVIGATION   │   AGENT COLLABORATION   │   WORK SURFACE    │
│              │                         │                   │
│ Core only    │   Core only             │ Core chrome       │
│              │                         │ + DLC body        │
│              │                         │                   │
│              │                         │                   │
│              │       Composer          │                   │
└──────────────┴─────────────────────────┴───────────────────┘
```

三栏不是核心。

核心是三个角色：

```text
Navigation
Collaboration
Work
```

---

# 13. Main Sidebar

Sidebar 永久 Core-owned。

DLC 不直接出现在主 Sidebar。

推荐：

```text
DBFox                              +

New task

Home

PROJECTS

DBFox
Personal
Research

RECENTS

重构 DBFox UI
分析销售数据
制作报告
修复项目问题

Customize / Extensions
Settings
```

注意：

目前 Artifact 仍属于 Conversation/Run 的事实，不是独立事实源，因此**暂时不要为了视觉完整性硬加 Global Artifacts 页面**。只有未来真正存在跨 Conversation Artifact index 后再加入。现有架构同样明确 Artifact 事实仍属于 Conversation。

---

# 14. Sidebar 基础几何

默认：

```text
width              264px
min                240px
max                336px
collapsed           48px

main row            32px
section label       24px
icon                16px
chevron             14px
icon button         28px

horizontal inset    8px
icon/text gap       8px
section gap         16px
row radius          6px
```

最重要的合同：

> 同层级 Row 必须共用完全相同 geometry。

禁止再出现：

```text
20px action
26px conversation
28px tree
32px header
13px icon
15px icon
```

混杂。

当前 Sidebar 确实存在这些尺寸和字号分叉。

---

# 15. Home

SmartQuery / AI 问数的产品概念正式结束。

Home 不再是 AI SaaS Hero。

不要：

```text
86px Fox
大 Gradient title
欢迎使用
大 Card 包裹整个首页
```

当前 SmartQuery Home 正采用这套模式。

未来 Home：

```text
                 What are we working on?

        ┌─────────────────────────────────┐
        │ Ask DBFox to do anything…       │
        │                                 │
        │ + Context        Auto ▾      ↑ │
        └─────────────────────────────────┘

                 Recent work
```

Home 主人：

# Composer

品牌不是首页主角。

Fox Logo 主要保留：

```text
TitleBar
Startup
About / branding
```

---

# 16. Unified Composer

Home 与 Conversation 必须共用一套 Composer。

当前 DBFox Composer 已有：

* Enter send；
* Shift+Enter；
* Reference；
* Clear reference；
* running；
* queue；
* steer；
* cancel & replace；
* stop；
* error。

这些行为全部保留。

外部 UI 只用于重新组织 presentation。

---

## 16.1 首选设计参考

第一候选：

**Prompt Kit / 用户提供的 PromptInputWithActions**

第二候选：

**Agent Elements InputBar**

Agent Elements 当前提供 InputBar、Suggestions、ModeSelector、ModelPicker、SendButton、AttachmentButton 等 25 个 Agent primitives。([Agent Elements][7])

第三候选：

**Nexus UI PromptInput + Attachments + Suggestions**。([Shoogle][8])

---

## 16.2 DBFox Composer 最终状态

Idle：

```text
┌───────────────────────────────────────────────┐
│ Ask DBFox to do anything…                     │
│                                               │
│ +   Context                    Auto ▾       ↑ │
└───────────────────────────────────────────────┘
```

Reference attached：

```text
[ users table × ] [ DBFox repository × ]

Review the current implementation…
```

Running：

```text
+   Context              Queue ▾              ■
```

运行中输入了新 draft：

```text
+   Context              Queue ▾              ↑
```

最右侧是同一个主操作按钮槽位，而不是并排的“停止”和“发送”按钮：运行中且 draft 为空时显示
Stop；运行中且 draft 非空时显示 Send，并按当前 Queue / Steer / Stop & replace 模式投递；取消请求
处理中显示不可点击的 spinner。`Escape` 与空 draft 的 Stop 按钮触发同一取消操作。

其中 Queue：

```text
Queue
Steer current task
Stop & replace
```

映射现有 delivery mode。

---

## 16.3 Composer 不应该默认放 Search

Search 是 Capability。

不是用户每条消息都要开的 mode。

默认：

```text
+
Context
Mode（只有真正存在产品模式时）
Send
```

Search、Browser、GitHub 等由 Agent 自动发现。

---

# 17. Agent Conversation

DBFox 当前 Conversation 行为层保留。

已经拥有：

* durable runs；

* streaming；

* long-thread virtualization；

* stick-to-bottom；

* reconnect；

* artifacts；

* approval；

* question。

禁止为了引入外部组件库而换掉 Conversation Store / Runtime。

---

# 18. Message Design

## User

轻 bubble：

```text
                           ┌─────────────────┐
                           │ 帮我分析一下…  │
                           └─────────────────┘
```

低对比背景。

无 shadow。

## Assistant

Assistant answer 是文档，不是聊天气泡：

```text
根据目前的数据，主要有三个原因……

### 第一

……

### 第二

……
```

直接落在 workspace surface。

---

# 19. Agent Activity

当前 Timeline 已有：

* message；
* function call；
* grouped function calls；
* Plan；
* Approval；
* Question；
* final answer；
* running phase；
* error；
* cancelled。

以后默认 presentation：

```text
◌ Working
  Inspecting project files…
```

完成：

```text
✓ Inspected 5 files · 3s
```

展开：

```text
Read App.tsx
Read Sidebar.tsx
Search Artifact
Read tokens.css
```

Tool detail 再展开才显示：

```text
Tool name
Arguments
Observation
Timing
Error
```

原则：

> Activity 是 Timeline；Tool detail 是 disclosure。

---

# 20. Tool Group

首选参考：

**Agent Elements ToolGroup**。

Agent Elements 本身已经将 Bash/Edit/Search/Todo/Plan/ToolGroup/Subagent/MCP/Question/GenericTool 等做成独立 Agent primitive。([Agent Elements][7])

DBFox 不复制它的数据模型。

只复制：

```text
grouping
density
disclosure
status presentation
loading behavior
```

---

# 21. Plan

Plan 是 Agent 的工作纲要：

```text
Plan

✓ Inspect current UI
✓ Review Core / DLC contract
◌ Build new Composer
○ Migrate Workspace DLC
```

首选参考：

Agent Elements PlanTool。

禁止做成大型 glowing AI card。

---

# 22. Approval

现有 Approval Runtime 保留：

* risk；
* reason；
* operation；
* approve；
* reject；
* audit history。

统一视觉：

```text
DBFox wants permission to:

Modify 4 files

src/...
src/...

Cancel                         Allow
```

SQL 只是 Approval 的一种。

未来：

```text
Write File
Run Command
Modify Database
Send Message
Publish
Delete
```

全部使用同一个 Core component。

---

# 23. Question

现有 DBFox Question 已支持：

* options；
* radio；
* free text；
* pending；
* response history。

首选视觉参考：

```text
Agent Elements QuestionTool
Nexus UI Questions
```

未来可扩：

```text
multi-select
multiple questions
skip
```

---

# 24. Evidence / Citation

Evidence 不降级成普通网页 Source。

它仍然具有：

```text
Artifact identity
Observed fact
Provenance
Citation
```

正文中：

```text
退款上涨主要集中在北美地区 [1]
```

Hover：

```text
Evidence 1
orders_q2
Query result
Observed Aug 26
```

点击：

> 在 Work Surface 打开真正 Artifact。

---

# 25. Work Surface

产品名：

# Work Surface

实现层仍可以叫 WorkspaceDock，迁移期间不强制立即改变量名。

Core chrome：

```text
┌──────────────────────────────────────────────┐
│ file.ts | users | Piano Studio        ···    │
├──────────────────────────────────────────────┤
│                                              │
│             Artifact / DLC Body              │
│                                              │
└──────────────────────────────────────────────┘
```

Core 永久拥有：

```text
tabs
close
overflow
active
resize
collapse
fullscreen
title/icon
```

---

# 26. Work Surface 禁止 Nested Chrome

现在 Core Dock 本身有 Tabbar。

内部 `WorkspaceShell` 又可以有 52px Header。

Data/Music 还会再画 Header。

以后硬规则：

> 一个 Work Surface 最多只有一层顶级 Chrome。

禁止：

```text
Core Tabs
DLC Header
DLC Page Header
DLC Section Header
Content
```

---

# 27. Project

Project 是 durable context。

不是 Folder。

不是 Database。

Project UI：

```text
DBFox Development

Instructions
────────────────────────

Context
────────────────────────

Workspace
~/dev/DBFox

GitHub
trrueee/DBFox · main

Data
Analytics PostgreSQL

Music
Piano Library

+ Add context

Recent work
────────────────────────
…
```

Connector contribution 从 Sidebar 迁到这里。

---

# 28. Capabilities / Extensions

Capabilities 不进入主导航树。

集中管理：

```text
Customize / Extensions

Installed
Available

Skills
Capabilities
Connectors / integrations
DLC packages
```

Claude 的统一 Customize directory 是主要产品参考。([Claude帮助中心][1])

“DLC”保留为架构术语。

用户侧尽量使用：

```text
Extensions
Capabilities
```

---

# 29. Command Palette

当前 Palette 仍包含：

> 智能问数（AI 问数）

新结构：

```text
New task

Go to
  Home
  Project …
  Recent work …

Actions
  Add context
  Open extensions

Settings
```

DLC action 未来可以贡献到 Actions。

但分类、row 和视觉全部属于 Core。

---

# 30. ContextDrawer

当前 ContextDrawer 只有：

```text
AI 建议
对象属性
```

并且仍带有明显 Database-era 文案。

状态：

# Legacy / Migration Candidate

其中有价值的信息分别迁入：

```text
Project Context
Work Surface inspector
Composer reference
```

完成迁移后删除。

---

# 31. Design System 默认方向

关键词：

# Calm / Neutral / Precise / Spatial / Agentic

禁止把风格定义成：

```text
Futuristic
Cyber
AI Gradient
Glass
Dashboard
Database UI
```

---

# 32. Color

默认 Accent：

```text
Light   #2563EB
Dark    #7AA2FF
```

这套 Blue 已经存在于当前 tokens。

默认 Appearance 建议：

```text
accentColor    blue
neutralTone    neutral
uiFontSize     13
```

当前默认仍是 violet / cool / 12。

核心原则：

> Neutral UI + Blue interaction signal.

95% neutral。

5% accent。

Blue 只表达：

```text
selected
focus
primary action
link
active agent
progress
primary data series
```

不要把普通 icon 全涂蓝。

---

# 33. Surface

Light 基准：

```text
Canvas             #F6F7F9
Navigation         #F3F4F6
Workspace          #FFFFFF
Auxiliary          #F8F9FB
Hover              #ECEEF1
Selected           #EAF1FF

Border             #E2E5E9
Border Strong      #D2D6DC
```

Dark 保持同样的相对层级：

```text
Canvas
Navigation
Workspace
Auxiliary
Elevated
```

而不是一系列几乎一样的黑。

---

# 34. Typography

只保留少量 semantic role：

| Role            |     Size | Weight |
| --------------- | -------: | -----: |
| Metadata        |  12 / 16 |    400 |
| Section label   |  12 / 16 |    500 |
| Navigation      |  13 / 20 |    400 |
| Control         |  13 / 20 |    500 |
| UI body         |  14 / 22 |    400 |
| Agent answer    |  15 / 24 |    400 |
| Component title |  16 / 22 |    600 |
| Page title      |  20 / 28 |    600 |
| Home display    |  24 / 32 |    600 |
| Code / Data     | 13 / ~20 |    400 |

只允许常规 weight：

```text
400
500
600
```

不再使用 550。

Feature 不拥有 font-size 决策权。

---

# 35. Icon

继续使用 Lucide。

只允许常规尺寸：

```text
14px   chevron / tiny secondary
16px   standard icon
20px   empty / larger object
```

特殊专业 visualization 例外。

当前 Sidebar 使用 12/13/14/15px 混合 icon 的做法结束。

---

# 36. Radius

```text
Row            6
Button         6
Input          8
Composer       12
Popover        10–12
Dialog         12
Card           12
Pill           only chip/status
```

一级 workspace 永远不 Card 化。

---

# 37. Shadow

```text
Shell          none
Sidebar        none
Toolbar        none
Work Surface   none
Normal Card    usually none

Popover        yes
Menu           yes
Dialog         yes
Floating Composer subtle only
```

结构来自：

```text
spacing
surface
typography
```

不是 shadow。

---

# 38. External Component Resource Policy

外部 UI 不作为 Runtime dependency 的设计权威。

原则：

> Browse → Compare → Copy source/idea → Adapt → DBFox owns final implementation.

DBFox 已经具备 TypeScript + Tailwind + shadcn 结构，并将 UI alias 指向 `@/components/ui`。

但 DBFox 自己的 `Button` 已经拥有自己的 class contract。

因此：

> 禁止 registry install 覆盖 DBFox existing primitives。

---

# 39. 外部 UI 资源分级

## S — Primary references

### shadcn/ui

使用于：

```text
Sidebar anatomy
Dialog
Tabs
Resizable
Menu
Form primitives
```

其 Sidebar 已经把 Header、Content、Group、Menu、Footer、Rail 等组成部分明确拆开，非常适合 DBFox 建立自己的 Sidebar contract。([Shadcn UI][9])

其 Resizable 继续基于 `react-resizable-panels`，与 DBFox 当前技术路线一致。([Shadcn UI][10])

[shadcn/ui Components](https://ui.shadcn.com/docs/components?utm_source=chatgpt.com)

### Agent Elements

使用于：

```text
InputBar
ToolGroup
Plan
Question
Tool
Thinking
Streaming
```

当前提供 25 个 role-based Agent primitives。([Agent Elements][7])

[Agent Elements](https://agent-elements.21st.dev/docs?utm_source=chatgpt.com)

### AI Elements

主要用于：

```text
Message
Conversation
Tool
Sources
Confirmation
AI-native presentation
```

registry.directory 当前持续收录 AI Elements。([registry.directory][11])

---

# 40. A — Strong references

### Prompt Kit

Composer 第一候选来源之一。([Shoogle][12])

[Prompt Kit directory](https://shoogle.dev/directory/prompt-kit?utm_source=chatgpt.com)

### Nexus UI

特别参考：

```text
PromptInput
Attachments
Suggestions
Questions
Citation
```

([Shoogle][8])

[Nexus UI directory](https://shoogle.dev/directory/nexus-ui?utm_source=chatgpt.com)

### assistant-ui

主要作为行为参考。

当前 registry 提供成熟的：

```text
Thread
Composer
Auto-scroll
Markdown
Reasoning
Voice
```

([registry.directory][13])

### ReUI

Data / Tree / dense application UI 强参考。

它建立在 TanStack Table 等成熟 React 库之上，并支持 Tailwind 3+。([Shoogle][14])

这意味着 DBFox DataGrid 可以主要借 presentation，不需要更换当前 TanStack 数据引擎。

---

# 41. Discovery Resources

### registry.directory

作为 shadcn registry 总检索入口。

当前聚合 shadcn、Dice UI、Coss UI、AI Elements、ReUI、React Aria、assistant-ui、Agent Elements 等大量 registry。([registry.directory][11])

[registry.directory](https://registry.directory/?utm_source=chatgpt.com)

### Shoogle

作为整个 shadcn ecosystem 的发现层。

当前目录约 289 registries。([Shoogle][15])

[Shoogle directory](https://shoogle.dev/directory?utm_source=chatgpt.com)

### 21st.dev

用来进行视觉筛选和 Agent component research，而不是把所有组件直接装进生产环境。

其平台目前已经扩展到大型设计组件目录。([21st][16])

---

# 42. Uiverse 使用限制

Uiverse 只允许作为：

```text
Loader
Recording pulse
Waveform micro interaction
Progress animation
Tiny interaction
```

的灵感来源。

禁止使用 Uiverse 决定：

```text
Sidebar
Shell
Work Surface
Settings
Agent Thread
DataGrid
Navigation
```

否则非常容易重新形成：

> 每个组件单看都漂亮，整个软件像 UI 菜市场。

---

# 43. Core Component Catalog

最终 Design System 必须至少拥有：

## Foundation

```text
Color
Typography
Spacing
Icon
Motion
Surface
```

## Primitive

```text
Button
IconButton
Input
Textarea
Select
Checkbox
Radio
Switch
Badge
Tooltip
Popover
Menu
Dialog
Tabs
```

## Application

```text
Sidebar
NavRow
SectionLabel
PaneHeader
Toolbar
Tree
TreeRow
DataGrid
CommandPalette
EmptyState
ErrorState
Status
```

## Agent

```text
Composer
ReferenceChip
Attachment
UserMessage
AgentAnswer
AgentActivity
Tool
ToolGroup
Plan
Question
Approval
Evidence
ArtifactLink
```

## Work

```text
WorkSurface
WorkTabs
ArtifactFrame
ArtifactBody
AskAction
Inspector
```

---

# 44. DLC Visual Contract

所有 DLC CSS 必须遵守：

禁止：

```text
:root overrides
html/body styles
global button/header/input selectors
fixed app-level font sizes
own primary color
own global typography
own app tabs
own top-level dialog chrome
own toast
own sidebar UI
own Work Surface frame
```

允许：

```text
namespaced domain CSS
domain layout
domain visualization
semantic DBFox tokens
chart colors
syntax colors
waveform/music colors
```

---

# 45. 当前工程必须修复的设计检查漏洞

当前 `check-design-contracts.mjs` 只扫描：

```text
desktop/src
```

因此 DLC CSS 没有进入设计 merge gate。

而 GitHub、Workspace、Music 等 DLC 当前都会动态将自己的 stylesheet 注入页面。

必须扩展 Design Contract Scanner 到：

```text
desktop/src/**/*.css
dlcs/*/frontend/**/*.css
```

新增检查：

```text
no global selector
no hardcoded app font size
no hardcoded primary/accent color
no top-level fixed layout
no custom app-level box shadow
no unnamespaced CSS
```

---

# 46. Future DLC UI API

不要求第一天马上改 SDK。

实施分两步。

## Stage A

先建立：

```text
DLC CSS contract
shared semantic tokens
Host-owned outer chrome
visual conformance tests
```

## Stage B

稳定后增加版本化：

```text
host.ui
```

候选：

```text
host.ui.Button
host.ui.IconButton
host.ui.Input
host.ui.Select
host.ui.Field
host.ui.Tabs
host.ui.Toolbar
host.ui.Tree
host.ui.TreeRow
host.ui.Status
host.ui.EmptyState
host.ui.AskAction
```

必须 versioned。

不能随意把整个 `desktop/components` 作为 DLC 公共 ABI。

---

# 47. 官方 DLC 迁移顺序

严格：

## 1. Workspace

最简单。

验证：

```text
Context
Tree
File Body
Artifact Body
Ask
```

目标：

> Workspace DLC 不再拥有 Button/Header/Tree chrome。

---

## 2. GitHub

验证：

```text
Binding
Repository Context
Tree
File
Artifact
```

Workspace + GitHub 成功后，应证明两个完全不同 DLC 可以共享同一 Tree / Work Surface grammar。

---

## 3. Data

复杂度最高之一。

验证：

```text
Connection Dialog
Resource browser
Tree
Tabs
Toolbar
Code editor
Data Grid
Results
Ask
```

Data DLC 现有 SQL Console、Table Inspector 和 Connection management 都保留，只迁视觉 ownership。

---

## 4. Music

最后迁。

这是视觉自由度极端案例。

保留：

```text
Notation
Piano
Waveform
Transport
Measure selection
Transcription
```

但：

```text
Tabs
Buttons
Tooltip
Dialog
Typography base
Status/Error
Ask DBFox
```

必须来自 Core。

如果 Music 都能自然融入 DBFox，说明 DLC Visual Contract 成功。

---

# 48. 实施总原则

这轮严禁：

> UI 重构 + Runtime 重构 + Store 重构 + API 重构一起做。

Agent / DLC architecture 已经成熟。

UI 只做 presentation migration。

现有数据通过 adapter 进入新 UI。

不创造第二份状态模型。

---

# 49. Phase 0 — Master Contract + Design Lab

第一步不改生产 UI。

建立：

```text
/docs/dbfox-master-product-ui-contract.md
/design-lab
```

Design Lab 固定 fixture：

```text
Sidebar
Home
Composer idle
Composer context
Composer running

Normal conversation
Streaming
Tool
ToolGroup
Plan
Question
Approval
Error

Work Surface
Artifact
Tree
DataGrid
Settings

Light
Dark
Small window
```

外部候选组件全部只先进入 Design Lab。

---

# 50. Phase 1 — Foundation

优先修改：

```text
desktop/src/styles/tokens.css
desktop/src/lib/appearance.ts
desktop/src/components/ui/*
```

完成：

```text
Blue default
Neutral default
Typography
Icon scale
Row geometry
Surface
Button
Input
Tabs
Toolbar
Tree primitive
```

然后冻结。

Feature 不再自行修改这些东西。

---

# 51. Phase 2 — Core Shell

修改目标：

```text
TitleBar
ProjectResourceSidebar
App shell
Command Palette
```

新 Sidebar 首先只接：

```text
New task
Home
Projects
Recents
Extensions
Settings
```

DLC Connector 从 Sidebar 移出。

这一阶段可以暂时用假的 Project Context 页面承载 Connector。

---

# 52. Phase 3 — Home + Unified Composer

涉及：

```text
SmartQueryHome
AskInputBox
Conversation Composer
```

删除：

```text
Smart Query
AI 问数
Hero Card
large Fox hero
gradient title
```

建立唯一：

```text
UnifiedComposer
```

用户提供的 `PromptInputWithActions` 作为第一视觉候选。

但是：

* 不覆盖 DBFox Button；
* 不直接复制 shadcn Button；
* 不引入模拟 API state；
* 不保留 Search/Mic 等不存在的功能；
* 映射现有 Queue/Steer/Replace/Stop。

---

# 53. Phase 4 — Agent UI

主要修改：

```text
AgentTimeline
ApprovalCard
QuestionCard
Message presentation
Evidence
```

顺序：

```text
Assistant flat answer
ToolGroup
Working state
Plan
Approval
Question
Evidence
```

Runtime 数据类型不改。

---

# 54. Phase 5 — Work Surface

修改：

```text
WorkspaceDock
WorkspaceShell
Artifact frame
```

目标：

```text
one top chrome
tabs
resize
collapse
fullscreen
DLC body slot
```

消除 nested headers。

---

# 55. Phase 6 — Project Context

建立：

```text
Project Overview / Context
```

将：

```text
Data
Workspace
GitHub
Music
```

Connector contribution 从 Sidebar 迁到此处。

仍然使用现有 Connector API，第一阶段不强制改 SDK。

---

# 56. Phase 7 — DLC Visual Contract

修改：

```text
desktop/scripts/check-design-contracts.mjs
desktop/src/features/dlc/extensionHost.tsx
sdk/frontend/index.d.ts
```

第一阶段：

```text
CSS scanning
namespaced styles
host-owned wrappers
visual lint
```

第二阶段再研究：

```text
host.ui v1
```

---

# 57. Phase 8 — 官方 DLC 迁移

严格：

```text
Workspace
↓
GitHub
↓
Data
↓
Music
```

每迁一个 DLC：

必须通过：

```text
Light
Dark
100%
125%
150%
small window
keyboard
error/loading
```

之后才进入下一个。

---

# 58. Phase 9 — Legacy Cleanup

完成后删除或迁出：

```text
SmartQuery visual language
Resource-centric Sidebar
ContextDrawer
duplicate headers
duplicate primitive CSS
legacy purple defaults
database-centric wording
AI 问数 wording
```

但不随便删除底层 domain 能力。

---

# 59. Visual Merge Gates

每一个 UI PR 必须满足：

1. 同层级 Row 同高。
2. 一屏主要字号不超过 3–4 个。
3. 普通 icon 使用统一尺寸。
4. Accent 不用于装饰。
5. Main workspace 比 navigation 更醒目。
6. Capability 不污染主 Sidebar。
7. Work Surface 只有一层顶级 Chrome。
8. Tool call 默认不抢主回答注意力。
9. DLC 不拥有 Core chrome。
10. 不添加新的 Feature-specific design tokens。
11. 不覆盖 shared primitive。
12. Light / Dark 同时通过。
13. 中文和英文都没有 layout break。
14. 125% / 150% Windows scaling 可用。

---

# 60. Screenshot Baseline

固定：

```text
1280 × 800 Light
1440 × 900 Light
1920 × 1200 Light

1440 × 900 Dark

1440 × 900 running
1440 × 900 approval
1440 × 900 work surface
1440 × 900 long sidebar
1280 × 800 small window

125% Windows
150% Windows
```

Fixture 数据必须稳定。

任何核心 UI PR 对比同一组截图。

---

# 61. 最终禁止事项

禁止：

```text
再做一套 Feature Design System
再为某 DLC 做一套 Button
再做 Resource-centric Main Sidebar
再把 Project 当 Workspace
再加大型 AI Hero
再添加 Decorative Gradient
再把所有 Tool Call 卡片化
再把每一个 Capability 都放导航
再把工作区套成 Card
再直接安装 registry 覆盖 primitives
再同时重构 Runtime + UI
```

---

# 62. Definition of Done

这轮设计升级只有同时满足以下条件才算完成：

### Product

用户打开 DBFox 第一感觉是：

> “这是一个 Agent 工作空间。”

而不是：

> “这是一个数据库工具。”

或：

> “这是一个聊天机器人。”

### Visual

缩小到 25% 看截图时：

即使看不清文字，也能明确看到：

```text
Navigation
Primary work
Secondary work
```

### Core

Core 所有区域视觉一致。

### DLC

Workspace / GitHub / Data / Music 明显属于不同专业能力，但仍然一眼看出：

> “它们都运行在 DBFox 里。”

### Agent

用户首先看到：

```text
我的请求
Agent 的回答
当前需要我的事情
最终成果
```

而不是：

```text
Agent 调用了多少工具。
```

### Architecture

UI 改造不创造第二 Runtime，不破坏：

```text
Project
Conversation
Run
Artifact
Evidence
Resource authority
DLC authority
```

现有事实源。

---

# 63. 最终北极星

DBFox 的长期设计方向不是：

> Clone Claude.

不是：

> Clone Codex.

不是：

> Clone Linear.

而是吸收各自最成熟的原则：

**Claude**
→ 能力隐藏、工作突出、Conversation + Canvas。

**Cursor / Codex**
→ Agent-centered workspace、Project + parallel work。

**Linear**
→ 视觉纪律、Sidebar 后退、Structure should be felt not seen。

**Raycast**
→ 桌面产品质感、Web 技术不能产生 Web 行为感。

**shadcn**
→ 稳定的 Application primitive anatomy。

**Agent Elements / AI Elements / Nexus**
→ 成熟 Agent interaction patterns。

最终 DBFox 自己的设计语言冻结为：

# **Neutral Shell**

# **Blue Signal**

# **Task-first Navigation**

# **Unified Composer**

# **First-class Work Surface**

# **Core-owned Experience**

# **Capability-owned Domain**

# **Quiet by Default**

整个产品只围绕一个目标：

> **让复杂能力变得安静。**

用户不应该看到系统有多复杂。

用户应该感觉：

> 我告诉 DBFox 我要做什么，然后工作在这里发生。

这份可以作为真正的总纲。最重要的实施变化不是再去改某个 CSS，而是先把 **Design Lab、Core component contract 和 DLC visual gate** 建起来；否则即使这一轮 Sidebar、Composer 做漂亮了，DLC 仍然有能力重新把视觉体系带散。

下一步执行顺序已经可以直接锁定为：**Master Contract 入库 → Design Lab → Foundation → Core Shell/Sidebar → Unified Composer → Agent primitives → Work Surface → Project Context → DLC Contract → Workspace/GitHub/Data/Music 迁移。**

[1]: https://support.claude.com/en/articles/14328846-browse-skills-connectors-and-plugins-in-one-directory?utm_source=chatgpt.com "Browse skills, connectors, and plugins in one directory | Claude Help Center"
[2]: https://support.claude.com/en/articles/14604416-get-started-with-claude-design?utm_source=chatgpt.com "Get started with Claude Design | Claude Help Center"
[3]: https://cursor.com/blog/cursor-3?utm_source=chatgpt.com "Meet the new Cursor · Cursor"
[4]: https://openai.com/index/introducing-the-codex-app/?utm_source=chatgpt.com "Introducing the Codex app | OpenAI"
[5]: https://linear.app/now/behind-the-latest-design-refresh?utm_source=chatgpt.com "A calmer interface for a product in motion"
[6]: https://www.raycast.com/blog/a-technical-deep-dive-into-the-new-raycast?utm_source=chatgpt.com "A Technical Deep Dive Into the New Raycast - Raycast Blog"
[7]: https://agent-elements.21st.dev/docs?utm_source=chatgpt.com "Introduction · Agent Elements"
[8]: https://shoogle.dev/directory/nexus-ui?utm_source=chatgpt.com "nexus-ui | Shadcn Registry Directory - Awesome shadcn UI | shoogle.dev"
[9]: https://ui.shadcn.com/docs/components/base/sidebar?utm_source=chatgpt.com "Sidebar - shadcn/ui"
[10]: https://ui.shadcn.com/docs/components/base/resizable?utm_source=chatgpt.com "Resizable - shadcn/ui"
[11]: https://registry.directory/?utm_source=chatgpt.com "registry.directory - The explorer for shadcn/ui registries"
[12]: https://shoogle.dev/directory/prompt-kit?utm_source=chatgpt.com "prompt-kit | Shadcn Registry Directory - Awesome shadcn UI | shoogle.dev"
[13]: https://www.registry.directory/assistant-ui/assistant-ui?utm_source=chatgpt.com "assistant-ui — 139 shadcn/ui components & blocks | registry.directory"
[14]: https://shoogle.dev/directory/reui?utm_source=chatgpt.com "reui | Shadcn Registry Directory - Awesome shadcn UI | shoogle.dev"
[15]: https://shoogle.dev/directory?utm_source=chatgpt.com "Shadcn Registry Directory - Awesome shadcn UI | shoogle.dev"
[16]: https://21st.dev/plans?utm_source=chatgpt.com "Plans — The UI Library for You and Your AI Agents | 21st"
