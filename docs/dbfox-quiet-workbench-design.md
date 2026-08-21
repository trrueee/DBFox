# DBFox Quiet Workbench — 前端视觉架构与实现规范

> 文档类型：前端视觉架构与实现规范（Design Contract）
>
> 状态：已接受，作为本轮前端视觉重构的执行规范与 merge gate；P0.1–P6、P7（synthetic 部分）、P8（token/CSS 清理部分）已实施（2026-08-21），P0 截图基线与真实 DLC（dbfox.github / acme.echo）的 Electron 级 conformance 待补
>
> 最后核验：2026-08-21
>
> 适用范围：`desktop/src` React 工作区的视觉层——Workbench Shell、Resource Sidebar、Conversation、Dock、Settings、Motion、DLC 视觉契约。不改变信息架构、Agent Runtime、DLC Runtime、状态模型与后端 API。
>
> 与现行基线的关系：本规范描述目标形态与实施顺序，**不描述当前实现**，不覆盖 [`dbfox-design-baseline.md`](dbfox-design-baseline.md)；Shell 边界仍以 [`architecture/workbench-shell-workspace-dock.md`](architecture/workbench-shell-workspace-dock.md) ADR 为权威。若本规范与该 ADR 冲突，以 ADR 为准并先修订本文。

它不是一次“换皮”，也不是重新做一套前端架构，而是在现在已经完成的 **Agent Runtime + Workbench Shell + Runtime DLC** 上，建立长期稳定的产品视觉语言。

核心目标冻结成一句话：

> **Structure should be felt, not seen.
> 结构必须存在，但用户不应该持续看到结构本身。**

同时有一个重要的工程前提：

> **现有信息架构、Agent Runtime、DLC Runtime、状态模型和后端 API 都不重写。**

当前 `App.tsx` 已经形成 `ProjectResourceSidebar → ConversationCenter + WorkspaceDock` 的主结构，Settings 也复用同一个 Workbench layout，所以这轮是“提纯”，不是再造 Shell。

## 现状锚点（2026-08-21 核验）

以下现状问题已在源码中确认，是本规范要修的对象：

| 现状 | 位置 |
| --- | --- |
| `.app-main` 是 `margin + border-radius + box-shadow` 的 raised card | `desktop/src/App.css`（`.app-main`），且被 `__tests__/appShell.test.ts` 断言固化 |
| 结构背景存在装饰性 radial gradient | `desktop/src/App.css` |
| `ConversationCenter` 以 `!activeDatasource` 作为会话前置 gate，显示“连接一个数据库”空态 | `desktop/src/features/appShell/ConversationCenter.tsx` |
| Sidebar 使用 connector selector tabs 承载 Data / Workspace / DLC connectors | `desktop/src/features/resources/ProjectResourceSidebar.tsx` |
| Dock 为 border + radius 独立容器，CSS 采用 browser-style tabs | `desktop/src/features/appShell/WorkspaceDock` 及其样式 |
| `ResourceConnectorContribution`（id/title/icon/render/addLabel/onAdd）已存在并被 Host 组合 | `desktop/src/features/resources/types.ts`、`resourceConnectorComposition.tsx` |

注意：P2 删除 `.app-main` raised-card 时，必须同步修改 `appShell.test.ts` 中固化该样式的断言。

---

# 一、最终产品形态

长期布局固定为：

```text
┌──────────────────────────────────────────────────────────────────┐
│               Electron Window Chrome / Context Actions           │
├───────────────┬──────────────────────────────┬───────────────────┤
│               │                              │                   │
│   RESOURCE    │         CONVERSATION         │       DOCK        │
│               │                              │                   │
│ Project       │ Human + Agent                │ Result            │
│ Conversations │ Messages                     │ SQL               │
│ Data          │ Activity                     │ Table             │
│ Workspace     │ Approval / Question          │ Artifact          │
│ DLC Resources │                              │ DLC Views         │
│               │                              │ DLC Views         │
│ Settings      │       Floating Composer      │                   │
└───────────────┴──────────────────────────────┴───────────────────┘
```

推荐基准：

| 区域 | 默认尺寸 | 性质 |
| --- | ---: | --- |
| 左栏 | 248–272px | Navigation / Resources |
| 中央 | flex，优先获得空间 | Primary Workspace |
| Dock | 420–460px | Auxiliary Workspace |
| Dock 最小 | 320px | 保证复杂内容可用 |
| 左栏 collapsed | 36–40px | icon rail |
| Dock collapsed | 40–44px | view rail |

重点不是具体 260/440，而是：

```text
视觉权重：

Conversation
    >
Resource / Dock
    >
Window Chrome
```

中央永远是最干净、最安静、视觉对比最强的区域。

---

# 二、第一条硬规则：彻底去掉“白条 / 框感”

这是整个设计规范最重要的约束。

当前 `.app-main` 本身仍是 `margin + border + radius + shadow` 的 raised card，外部还有背景渐变；Dock 也是 border + radius 的独立容器。

最终不应该是：

```text
背景

  ╭──────────────────────────────────────╮
  │ Header                               │
  ├──────────────────────────────────────┤
  │ Toolbar                              │
  ├──────────────────────────────────────┤
  │                                      │
  │        Conversation Card             │
  │                                      │
  ╰──────────────────────────────────────╯

  ╭────────────────────╮
  │ Dock Card          │
  ╰────────────────────╯
```

而应该是：

```text
Navigation     Conversation                   Dock
surface        clean workspace                auxiliary surface

               Project / context
               Conversation title

               Messages
               Activity

                    Composer
```

因此冻结以下规则：

| 元素 | 规则 |
| --- | --- |
| 一级工作区域 | **禁止 Card 化** |
| 左栏 | 无外边框、无圆角 Card |
| Conversation | 无整体 border、无整体 shadow |
| Dock | 无四边 Card border |
| Settings 主区 | 无大 Card |
| Header | 默认无永久 bottom border |
| Toolbar | 能不存在就不存在 |
| Divider | 只有真的需要区分层级时出现 |
| Shadow | 只属于 floating/elevated UI |
| Radius | 只属于 controls/floating enclosure，不属于整个 workspace |

尤其禁止：

```css
.panel {
  background: white;
  border: 1px solid #ddd;
  border-radius: 12px;
  box-shadow: ...;
}
```

然后所有东西都套这个 `.panel`。

这是最容易重新产生 SaaS Dashboard 感的模式。

---

# 三、Surface 层级

当前已经有完整 token 系统，但 alias 较多，比如 `color-bg / bg-primary / surface-base / surface-workspace` 等并存。

不要再增加另一套 token。

应逐渐收敛成这几个真正有产品语义的层级：

```css
--surface-canvas
--surface-navigation
--surface-workspace
--surface-auxiliary
--surface-elevated
--surface-overlay

--line-subtle
--line-strong

--text-primary
--text-secondary
--text-muted

--intent-accent
--intent-success
--intent-warning
--intent-danger
```

Light 模式关系建议：

```text
Canvas
  ↓
Navigation      略暗

Workspace       最干净、最接近内容背景

Auxiliary       比 Workspace 稍微后退

Elevated        明显高一级

Overlay         Popover / Menu / Dialog
```

不是要求某几个固定 HEX，而是要求**相对关系稳定**。

Dark Mode 同样遵循层级，而不是：

```text
黑
黑
深黑
更黑
```

---

# 四、禁止装饰性 Gradient / Glass / Glow

当前 `App.css` 仍存在结构背景 radial gradient。

Quiet Workbench 应移除这种结构性装饰。

以下默认禁止：

```text
大面积渐变背景
玻璃拟态 panel
blur 到处用
紫色 glow
发光 active state
彩色阴影
彩色边框环绕 panel
```

例外是：

* Chart 数据表达；
* 极少数 loading/visualization；
* 用户内容本身。

结构 UI 不靠这些东西建立高级感。

---

# 五、颜色：DBFox Purple 从“主 UI 色”退成“意图色”

紫色继续保留。

但是不应该：

```text
每个 active item 都是紫色块
每个 icon 都是紫色
每个 header 都带紫色
每个 button 都带 primary
```

它应该主要表达：

```text
Selected
Focused
Primary intent
Running
Current action
```

普通导航、普通 icon、普通标题：

```text
currentColor
muted / secondary
```

只有：

```text
active
running
warning
error
success
```

才得到语义颜色。

所以左栏装 20 个 DLC 后仍然应该主要是灰阶结构，而不是：

```text
GitHub 黑
Slack 紫
Jira 蓝
CSV 绿
Browser 橙
```

拼成插件商城。

---

# 六、Typography

DBFox 是生产工具，不是展示型产品。

保持小而清晰的层级：

```text
Window / Section title      17–20
Conversation answer         15–16
Standard UI                 13–14
Tree / tabs / metadata      12–13
Code                        12.5–13.5 monospace
```

减少：

```text
24 / 22 / 20 / 18 / 16 / 15 / 14 / 13 / 12
```

每个地方都自己定义字体大小的现象。

尤其不要通过巨大标题制造层级。

Workbench 的层级主要来自：

```text
位置
留白
font weight
surface
```

而不是 Hero typography。

---

# 七、左侧 Resource Sidebar

“Resource 是 Contribution Container”这个判断非常重要。

当前项目已经真的拥有 `ResourceConnectorContribution`，而不是等待未来设计：

```ts
id
title
icon
render()
addLabel?
onAdd?
```

生产 composition 也是：

```text
Data
Workspace
+ Runtime DLC connectors
```

所以：

> **绝对不要重新创建 ResourceContribution API。**

## 当前结构建议改成

不要继续当前 connector selector tabs：

```text
[ Data ] [ Workspace ] [ GitHub ] ...
```

因为 DLC 多以后扩展性不好。

也不要让所有 DLC 内容永远全部展开。

推荐：

```text
My Project
────────────────

Chats
  为什么退款率上升
  最近订单异常

RESOURCES

▾ Data
    Production
    Analytics

▾ Workspace
    src
    reports

▸ GitHub

▸ Slack

▸ Browser

+ Add Resource

────────────────
Settings
```

Host 拥有：

```text
section chrome
section order
expand/collapse
spacing
icon size
add-resource UI
hover/selected state
```

DLC 拥有：

```text
title
icon
resource content
add action
domain interaction
```

这样才是真正：

> DLC contributes content; DBFox owns presentation.

---

# 八、Sidebar 不能变成大型 Tree Framework

不要为了支持未来资源设计：

```ts
UniversalResourceTreeNode {
  type
  children
  payload
  icon
  badge
  actions
  ...
}
```

Data、Workspace、GitHub 的内部树完全不同。

现在的 DLC 架构已经正确选择：

```text
Host 给一个 slot
DLC 自己 render 内容
```

继续保持。

---

# 九、Conversation 是视觉绝对主角

这一点完整保留。

现有组件已经足够：

```text
ConversationHeader
MessageList
AgentTimeline
ApprovalCard
QuestionCard
Composer
ArtifactDock
```

所以这里不是架构重写。

## Assistant Message

不要：

```text
╭────────────────────────╮
│ AI                     │
│                        │
│ 回答正文               │
╰────────────────────────╯
```

应该：

```text
DBFox

过去 30 天退款率主要受到……

第二个原因是……

来源……
```

正文直接落在 Workspace 上。

## User Message

可以保留轻 bubble：

```text
               ┌──────────────────────┐
               │ 帮我分析退款率变化   │
               └──────────────────────┘
```

但：

```text
低对比背景
小 radius
无 heavy shadow
```

---

# 十、Agent Activity 不应该是一堆 Tool Cards

默认：

```text
◌ 正在检查相关数据
│
✓ 找到 4 张相关表
│
◌ 执行查询
```

而不是：

```text
┌ ToolCall Card ┐
└───────────────┘

┌ ToolCall Card ┐
└───────────────┘

┌ ToolCall Card ┐
└───────────────┘
```

Tool detail 展开后才出现：

```text
Tool
Arguments
Observation
Timing
Error
```

也就是说：

> **Activity 是 timeline；Tool details 是 disclosure。**

---

# 十一、什么时候允许 Card

不是彻底禁止 Card。

Card 只用于真正需要 enclosure 的内容：

```text
Approval
Question
Dangerous operation
DLC package
OAuth/provider setup
Artifact preview
Error requiring action
```

判断方式：

> 删除这个外框以后，内容是否会失去语义边界？

如果不会，就不该是 Card。

---

# 十二、Conversation Header

当前 `ConversationHeader` 本身非常简单，只显示 title。

不要重新做一个 56px 白色 Toolbar。

推荐：

```text
Project / Active resources                    History ···

订单异常分析
```

总高度：

```text
36–44px contextual chrome
```

默认：

```text
transparent
no border
```

只有内容滚过 header：

```text
slightly opaque workspace surface
+
subtle backdrop blur（可选）
+
0.5–1px hairline
```

所以：

> Divider 是状态，而不是装饰。

---

# 十三、Composer

保留 floating composer，这个方向是对的。

但是减轻：

```text
radius       16–18
border       subtle
shadow       非常轻
surface      workspace + 1 level
focus        subtle accent ring
```

不要：

```text
24px 巨大胶囊
很重阴影
独立底部白色 toolbar
```

布局：

```text
回答内容
回答内容
回答内容


          ┌───────────────────────────┐
          │ 继续问 DBFox…             │
          │ context             ↑     │
          └───────────────────────────┘

          20px breathing space
```

背景自然衔接 Conversation。

---

# 十四、修掉一个和当前架构不一致的真实问题

当前 `ConversationCenter` 仍然：

```ts
if (!activeDatasource) {
  return ...
}
```

并显示“连接一个数据库，开始问数”。

这已经和现在的 Project-scoped Session / Workspace / Runtime DLC 架构冲突。

应该独立修成：

```text
activeProject 是否存在？
       ↓
不存在 → 创建 Project

存在
       ↓
Conversation 可以运行

可用 ResourceRefs
决定哪些 tools materialize
```

而不是：

```text
没有 Database
→ 没有 Agent
```

这个问题单独一个小 PR 完成，不要和大量 CSS diff 混在一起。

---

# 十五、Dock：Auxiliary Workspace，不是 Browser

当前 CSS 明确采用的是 browser-style tabs。

新的 Dock：

```text
Result   SQL   Table   GitHub   ···                ‹
──────
```

Active：

```text
font/text emphasis
+
2px soft indicator
```

而不是：

```text
╭ Result ╮ ╭ SQL ╮ ╭ Table ╮
```

## Dock 本体

不要：

```css
border: 1px solid;
border-radius: 10px;
```

推荐：

```text
auxiliary surface
+
subtle left separator/resizer
```

Conversation │ Dock 是两个平级工作区域。

---

# 十六、Dock 扩展性

当前 Dock 已经能消费 Runtime DLC Dock Views。

第一阶段只解决真正存在的问题：

```text
visible tabs
+
overflow menu
```

不要现在同时实现：

```text
Pinned
Recent
Move left
Move right
Hide
Reset
Groups
Multiple docks
```

没有真实需求前不要建立这些状态。

当前隐藏 scrollbar 横向滚的方案可以退出。

---

# 十七、Artifact

Artifact 应该有两种表达：

```text
Conversation inline
→ compact reference / preview

Dock
→ full workspace renderer
```

不要在 Conversation 里直接塞完整 SQL Result Workspace。

也不要让 Artifact renderer 决定：

```text
外层 padding
外层 tab
Dock background
Dock border
```

Host 控制这些。

---

# 十八、Settings

现有 Settings 已经基本是：

```text
Settings Sidebar
+
920px centered content
```

这个信息架构不改。

视觉改成：

```text
Appearance

Theme
System                                   ▾

Density
Normal                                   ▾

Agent font size
15                                       −  +

────────────────────────────────────────────

Motion

Interface animation                     On
Reduce motion                            System
```

而不是：

```text
┌ Appearance Card ┐

┌ Typography Card ┐

┌ Motion Card ┐
```

Card 保留给：

```text
DLC package
complex Provider
Danger Zone
preview
```

---

# 十九、不要新增 DLC Settings Contribution

当前公开 Runtime frontend SDK **没有这个 contract**。

这轮不要因为 UI redesign 顺手增加：

```ts
host.settings.register(...)
```

未来至少两个真实 DLC 都证明需要以后再设计。

---

# 二十、DLC Visual Contract

这次设计系统真正应该补充的是这个。

当前 Runtime DLC 已经可以贡献：

```text
Connector
Requested Resource
Dock View
Artifact Renderer
Operation
```

所以视觉契约定义成：

| Contribution | DLC 拥有 | Host 拥有 |
| --- | --- | --- |
| Connector | resource content | Sidebar section/chrome |
| Dock View | domain content | Dock/frame/tab/resize |
| Artifact Renderer | payload presentation | Artifact envelope |
| Tool | semantics/status content | Agent activity shell |
| Operation | behavior | notification/loading/error presentation |

DLC 不应该决定：

```text
workspace width
main background
global font
global spacing
global animation
global z-index
global navigation
Dock tab style
Sidebar section style
toast style
```

---

# 二十一、但不要把 Visual Contract 宣称成安全边界

现在 frontend DLC SDK 只暴露 React/ReactDOM 和 typed contribution API，并没有完整 UI primitive SDK。

因此：

```text
“DLC 必须视觉一致”
```

现阶段属于：

```text
design contract
+
official SDK convention
+
conformance testing
```

而不是：

```text
sandbox enforcement
```

Trusted frontend JavaScript 理论上仍然可以自己写 CSS/DOM。

不要做虚假的隔离声明。

---

# 二十二、不要现在建设完整 DBFox UI SDK

长期可以有：

```text
Foundation
Primitives
Workbench
Agent
DLC UI helpers
```

这个方向没问题。

但这轮不要一次造：

```text
DBFoxButton
DBFoxPanel
DBFoxCard
DBFoxTree
DBFoxDock
DBFoxSettings
DBFoxForm
DBFoxMotion
...
```

先从两个真实使用者提炼。

第一批真正值得抽的可能只有：

```text
ResourceSection
ContextualHeader
DockTabStrip
SettingsSection
AgentActivityRow
```

甚至如果没有两个真实消费者，继续留在 feature 内部。

组件化边界的完整判断标准见[第四十一节](#四十一组件化的边界产品语言组件化业务语义保持自由组合)。

---

# 二十三、Motion Grammar

Motion 应该是 Host-owned。

建议：

```text
fast       110–130ms
normal     160–180ms
spatial    210–240ms
```

Motion 只用于：

```text
Sidebar collapse
Dock collapse
Tab indicator
Popover/Menu
Disclosure
Approval/Question appearing
View reorder
```

原则：

```text
enter     opacity + <=4px
exit      opacity
panel     transform / size
press     <= .98 scale
```

禁止：

```text
bounce
spring overshoot
glow
large zoom
parallax
decorative shimmer
700ms animation
```

普通 hover 直接 CSS。

第一阶段也**不要引入大型 Motion framework**。

CSS 足够完成大部分需求。

---

# 二十四、Reduced Motion

必须第一版就处理：

```css
@media (prefers-reduced-motion: reduce) {
  transition-duration: 0ms /* 或 very short */;
}
```

状态变化不能依赖动画才能被理解。

---

# 二十五、Border Strategy

### 没有 Border

```text
Workspace
Sidebar
Dock body
Conversation
normal sections
normal messages
```

### Hairline

```text
Sidebar ↔ Workspace
Workspace ↔ Dock
sticky header after scroll
section separator
```

### Real Border

```text
Input
Button where necessary
Popover
Menu
Dialog
Approval
Danger
selected editable object
```

避免：

```text
border around everything
```

---

# 二十六、Radius Strategy

Radius 不能滥用。

```text
Workspace region       0
Sidebar region         0
Dock region            0

Tree row               4–6
Button                  6–8
Input                   8–10

Composer                16–18

Popover/Dialog          10–14
```

不要：

```text
everything 12px
```

这也是 Card 感的重要来源。

---

# 二十七、Shadow Strategy

只允许：

```text
Composer
Popover
Dropdown
Dialog
Command Palette
floating preview
```

不要：

```text
App Main shadow
Dock shadow
Sidebar shadow
Settings content shadow
every card shadow
```

---

# 二十八、Icons

统一：

```text
14px resource/navigation
15–16px controls
16–18px prominent action
```

默认：

```text
currentColor
strokeWidth around 1.5–1.75
```

不要让 DLC 用巨大品牌图标抢占导航。

Brand identity 最多出现在：

```text
小 icon
DLC detail
specific content
```

而不是改变整个区域颜色。

---

# 二十九、Density

DBFox 是高信息密度工具。

默认：

```text
Tree row       26–30
Tabs           30–34
Toolbar        34–40
Control        32–36
```

不要为了“现代”把所有内容都放大到 44–48px。

现代感不等于移动端 density。

---

# 三十、Empty / Loading / Error

必须保持 Quiet。

Empty：

```text
简短标题
一句说明
一个主要动作
```

不要大型 illustration。

Loading：

```text
local skeleton
small progress
```

不要整页 spinner。

Error：

```text
固定、安全、可操作
```

不要红色巨型 Card。

---

# 三十一、Command Palette

Command Palette 可以成为唯一明显 elevated 的全局导航工具之一。

它应该承担：

```text
open resource
open conversation
open Dock
settings
commands
```

而不是继续往顶栏增加越来越多按钮。

---

# 三十二、Electron Title Bar

生产 Host 已经是 Electron。

Title Bar 只负责：

```text
drag region
window controls
少量全局 context/actions
```

不能重新成为：

```text
Project Header
Toolbar
Search Bar
Context Bar
Status Bar
```

全部叠进去的大白条。

---

# 三十三、响应式策略

这是 Desktop，不需要做 Mobile。

### ≥ 1600

```text
Sidebar expanded
Conversation full
Dock 440–520
```

### 1280–1599

```text
Sidebar 248
Conversation flex
Dock 380–440
```

### 较窄窗口

优先：

```text
Dock collapse
```

再：

```text
Sidebar collapse
```

永远先保护 Conversation。

不要通过：

```text
scale()
zoom()
整体缩小 UI
```

解决空间。

---

# 三十四、DLC × 20 Stress Test

这次设计必须直接测试：

```text
0 DLC
1 DLC
5 DLC
10 DLC
20 DLC
```

重点不是实际安装 20 个真实插件。

可以用 synthetic contributions 验证：

```text
long title
duplicate-looking icons
many resources
Dock view overflow
broken DLC
loading DLC
empty DLC
```

同时真实使用：

```text
dbfox.github
acme.echo
```

作为 Runtime conformance。

---

# 三十五、Accessibility

必须作为视觉系统的一部分，而不是最后补。

要求：

```text
keyboard access
visible focus
correct tab semantics
ARIA label
minimum usable hit target
contrast
reduced motion
not color-only state
```

Dock active：

```text
underline + text weight
```

而不仅：

```text
purple
```

Error：

```text
icon + text
```

而不仅红色。

---

# 三十六、明确禁止清单

下面这些直接写进 Design Contract：

```text
禁止 SaaS Dashboard 风格

禁止把一级区域设计成 Card

禁止 App Main raised-card

禁止 Sidebar / Conversation / Dock 三个独立圆角盒子

禁止永久大白色 Header

禁止 Header + Toolbar + SubToolbar + SectionHeader 连续堆叠

禁止到处 border-bottom

禁止 Card 套 Card

禁止所有 section 都加 background

禁止所有 panel 都 radius: 12px

禁止所有 panel 都 shadow

禁止 decorative gradient

禁止大面积 glass / blur

禁止 glow

禁止大量 brand color

禁止 DLC 自己改变 Host chrome

禁止每个 DLC 一个顶级彩色入口

禁止 Universal Resource Tree

禁止 Browser-style Dock tabs

禁止依赖隐藏横向 scrollbar 处理大量 Dock views

禁止为了未来一次性实现 Pin/Recent/Hide/Groups

禁止为了 redesign 重写 WorkspaceStore

禁止修改 Agent Runtime 状态模型

禁止修改 DLC Runtime activation semantics

禁止修改 backend API 以迁就视觉

禁止重新建立 Resource/Dock/Artifact contribution system

禁止在这轮新增 DLC Settings seam

禁止在这轮建立完整 UI SDK

禁止在这轮引入大型 Motion framework

禁止页面级大量 magic-number CSS override

禁止新增第二套 color/token system

禁止直接写大量 hex 而绕开 semantic tokens

禁止在 component 内实现 Light/Dark 两套 CSS

禁止用动画制造“高级感”

禁止把 loading/error/empty 都做成大 Card

禁止通过 scale/zoom 解决桌面布局
```

这部分视为 merge gate。

---

# 三十七、实现顺序

严格按下面推进，而且每一步单独 PR：

1. **P0 — Visual Characterization**：冻结 1280/1440/1920、Light/Dark、Sidebar/Dock expanded/collapsed、Conversation/Settings/DLC 的现有截图和 DOM 行为，不改业务。
2. **P0.1 — 修 ConversationCenter 的 datasource gate**：让 Project-scoped / Workspace-only / DLC-only Conversation 与当前 Agent 架构一致。
3. **P1 — Semantic Token Cleanup**：只收敛 Surface、Border、Elevation、Radius、Motion；不重做所有 token。
4. **P2 — Workbench Shell**：删除 `.app-main` raised-card、decorative radial gradient、stage gap/card separation，建立 Canvas/Nav/Workspace/Auxiliary surface hierarchy。
5. **P3 — Resource Sidebar**：保持现有 Connector contract，把 connector selector 改成 Host-owned collapsible Resource Sections；加入 DLC scale test。
6. **P4 — Conversation / Agent UI**：Assistant prose、User bubble、Activity timeline、Tool disclosure、Approval、Question、Composer。
7. **P5 — Dock**：删除 Browser tabs 和外 Card；做 auxiliary workspace、active indicator、overflow menu、subtle resizer。
8. **P6 — Settings**：扁平 section/rows，卡片只保留真正需要 enclosure 的地方。
9. **P7 — DLC Visual Conformance**：`dbfox.github + acme.echo + synthetic DLC ×10/20`；验证 Host chrome 不被污染。
10. **P8 — Visual Regression / Cleanup**：Light/Dark、分辨率、long text、loading/error/empty、reduced motion；删除 transitional CSS 与旧 token aliases。

“先做真实 Vertical Slice，再从真实页面抽设计系统”的思想保留。

---

# 三十八、每个 PR 的硬边界

每个前端重构 PR 都应该回答：

```text
BUSINESS LOGIC CHANGED?
必须 NO，除非 PR 明确是 functional fix。

BACKEND API CHANGED?
NO。

AGENT RUNTIME CHANGED?
NO。

DLC RUNTIME CONTRACT CHANGED?
NO，除非独立 architecture PR。

NEW GLOBAL STATE?
尽量 NO。

NEW DESIGN TOKEN?
为什么现有 semantic token 不能表达？

NEW COMPONENT ABSTRACTION?
至少哪两个真实调用点需要？

NEW DEPENDENCY?
为什么 CSS / existing primitives 不够？

REMOVED LEGACY CSS?
必须说明删除了什么。
```

---

# 三十九、测试策略

这轮不把 Storybook 当最终 gate。

更有价值的是：

```text
real Electron window
+
real Workbench composition
+
deterministic screenshots
```

测试矩阵：

| 状态 | 必测 |
| --- | --- |
| Resolution | 1280 / 1440 / 1920 |
| Theme | Light / Dark |
| Sidebar | expanded / collapsed |
| Dock | empty / one / many / collapsed |
| Conversation | new / long / running Agent |
| Agent | approval / question / error |
| DLC | 0 / 1 / 10+ |
| Settings | Appearance / Model / DLC |
| Accessibility | keyboard / focus / reduced motion |
| Text | 中英混合、长标题、长 resource name |

Storybook 以后可以用于：

```text
Button
Menu
Approval
Question
Agent Activity
Settings row
```

但不是 Workbench shell 的权威验证环境。

---

# 四十、这次重构的最终验收标准

最后不通过“看起来更漂亮”验收。

通过下面这些判断：

```text
用户第一眼注意到 Conversation，而不是 UI chrome。

左、中、右能被清晰感知，但没有三张 Card。

没有连续多层白色 Header。

没有区域因为大量 border 被切成表格感。

Dock 和 Conversation 是自然相邻的工作空间。

安装 10 个 DLC 后，界面仍然像 DBFox。

DLC 的品牌不会改变 Host 的整体视觉语言。

Agent Activity 默认安静，必要时才能展开细节。

Composer 有存在感，但不会形成底部白条。

Settings 仍属于 Workbench，而不是后台管理站点。

Light 和 Dark 是同一层级体系，而不是两套设计。

1280 窗口优先保护 Conversation。

新增 DLC 不需要修改 Shell 的领域 switch。

视觉改动没有产生第二套 Runtime/Store/Contribution 架构。
```

做到这些以后，“Quiet Workbench”才算成功。

最准确的最终定位不是：

> **重新设计 DBFox UI。**

而是：

> **给已经成熟的 DBFox Agent + Runtime DLC Workbench 建立一套稳定的视觉架构，让功能继续增长时，产品界面反而越来越安静，而不是越来越像插件拼盘。**

这也正好把“结构存在，但尽量看不到结构本身”从一句审美描述，变成真正可执行、可测试、可做 code review gate 的工程规范。

---

# 四十一、组件化的边界：产品语言组件化，业务语义保持自由组合

组件化的终点不是“重构完以后所有页面还是一堆 `div + className + CSS`”，但也**不应该走到“任何 8px 间距都抽成一个组件”**。

理想结果是：

> **DBFox 最常见、最有产品辨识度、最容易失控的 UI，被收敛成一批精致且有完整状态语义的组件；具体业务内容仍然允许局部组合。**

也就是说，最终应该从现在这种：

```text
页面
 ├─ 自己写 header
 ├─ 自己写 section
 ├─ 自己写 icon button
 ├─ 自己写 selected
 ├─ 自己写 hover
 ├─ 自己写 border
 ├─ 自己写 empty
 └─ 自己调 spacing
```

变成：

```text
Design Tokens
    ↓
Primitives
    ↓
Workbench Components
    ↓
Agent Components
    ↓
Feature / DLC Content
```

## 最终应该有一批“DBFox 味”的精美组件

控制在几类，而不是造一个 Element Plus。

### 1. Foundation

不算 React 组件，但所有组件统一消费：

```text
Surface
Typography
Spacing
Radius
Hairline
Elevation
Motion
Focus
Semantic colors
Density
```

以后不能某页面突然：

```css
border-radius: 11px;
box-shadow: 0 8px 25px ...;
background: #f8f9fb;
```

自己发明一套。

### 2. 基础 Primitives

已有的 Radix/shadcn 类行为层可以继续用，不需要重新发明。

真正应该打磨好：

```text
Button
IconButton
Tooltip
Menu
Popover
Dialog
Input
Textarea
ScrollArea
EmptyState
LoadingState
Divider
```

重点不是组件数量，而是每一个都完整支持：

```text
default
hover
active
focus-visible
disabled
loading
error
dark
reduced-motion
```

以后 feature 不再自己实现：

```tsx
<button className="xxx-icon-button">
```

然后另一个地方又写一套 `.yyy-action-button`。

### 3. Workbench 组件

这是这次重构真正应该新增/提炼的核心。

最后至少应该形成：

```text
ResourceSection
ContextualHeader
WorkbenchPane / PaneChrome（很薄）
DockTabStrip
DockOverflowMenu
DockCollapseRail
ResizeHandle
SettingsSection
SettingsRow
SettingsGroup
```

例如左侧以后不是每个 Connector 自己搞：

```tsx
<div className="ds-resource-section">
  <div className="ds-resource-header">
    ...
  </div>
  ...
</div>
```

而是类似：

```tsx
<ResourceSection
  title="GitHub"
  icon={<GithubIcon />}
  collapsed={...}
  onCollapsedChange={...}
  action={...}
>
  {connector.render(...)}
</ResourceSection>
```

这样：

```text
Data
Workspace
GitHub
Slack
Browser
```

全部天然拥有同样的：

* 字号
* section spacing
* icon 大小
* 展开箭头
* hover
* collapse
* divider
* focus
* dark mode

这就是“组件精致化”的实际意义。

### 4. Agent UI Kit

这一层应该做得尤其精致。

最后应该有类似：

```text
ConversationMessage
AssistantAnswer
UserMessage
AgentActivity
AgentActivityItem
ToolDisclosure
ApprovalCard
QuestionCard
Composer
Citation
ArtifactReference
RunLimitation
```

注意不是：

```text
AgentCard
AgentCard2
AgentCard3
```

而是每个组件有明确产品语义。

例如：

```tsx
<AgentActivity>
  <AgentActivityItem
    state="completed"
    label="找到 4 张相关表"
  />
  <AgentActivityItem
    state="running"
    label="正在执行查询"
  >
    <ToolDisclosure ... />
  </AgentActivityItem>
</AgentActivity>
```

以后不用每一个 ToolCall 页面重新写：

```css
padding
icon circle
status color
timeline line
spinner
expanded border
```

### 5. Dock 也应该成为真正的 Host Component

现在 `WorkspaceDock` 还是一个大组件，同时自己：

* 查 contribution
* filter visibility
* 算 active
* render tabs
* close button
* collapse
* empty
* content

重构之后可以逐渐变成：

```tsx
<WorkspaceDock>
  <DockTabStrip
    tabs={...}
    activeKey={...}
    overflow="menu"
  />

  <DockViewport>
    {contribution.render(...)}
  </DockViewport>
</WorkspaceDock>
```

DLC 完全不关心：

```text
Tab 长什么样
Active indicator 怎么画
Overflow 怎么做
Dock 背景什么颜色
Resize 怎么显示
```

它只交内容。

这才符合前面定的 DLC 原则。

### 6. Settings 也会明显减少“到处写”

各 Settings panel 不再自己组织 section。

统一：

```tsx
<SettingsSection
  title="Motion"
  description="控制界面动画行为"
>
  <SettingsRow
    label="Interface animation"
    control={<Switch ... />}
  />
  <SettingsRow
    label="Reduce motion"
    control={<Select ... />}
  />
</SettingsSection>
```

这里的：

```text
row height
label style
description style
separator
control alignment
responsive
```

全部由 Host 组件负责。

### 7. 但业务内容仍然会写 JSX，这是正常的

不应该追求最终代码变成：

```tsx
<DBFoxEverything />
```

比如 GitHub DLC 内部：

```text
repository tree
branch
file
pull request
```

这些本来就是 GitHub 的领域内容。

它仍然可以：

```tsx
<div>
  ...
</div>
```

也仍然需要它自己的局部 CSS。

区别是它不能自己决定：

```text
整个 Sidebar 长什么样
整个 Dock 长什么样
Tab 怎么长
全局字号
全局 motion
大 panel border
全局 elevation
```

所以最终应该是：

```text
Host component
┌──────────────────────────────┐
│ GitHub                       │ ← DBFox ResourceSection
│                              │
│  repo-a                      │
│    src/                      │ ← GitHub 自己的 domain UI
│    README.md                 │
│                              │
└──────────────────────────────┘
```

而不是：

```text
GitHub DLC
┌══════════════════════════════┐
║ 自己的 header                ║
║ 自己的 card                  ║
║ 自己的紫色                   ║
║ 自己的 tabs                  ║
└══════════════════════════════┘
```

## 最关键的判断标准

以后 code review 用这个规则：

### 应该抽成组件

满足任意一个：

* 两个以上真实位置重复出现；
* 有明确交互状态；
* 是 DBFox 产品语言的一部分；
* Host 必须控制它才能保证 DLC 一致性；
* accessibility 很容易被各页面写错；
* Light/Dark/Motion/Density 需要统一。

例如：

```text
ResourceSection
DockTab
SettingsRow
ToolDisclosure
IconButton
Composer
```

应该抽。

### 不应该抽

只有：

```text
一个页面的一次性排版
一个 domain 独有的小内容
纯粹为了少写 5 行 JSX
只有一个消费者且没有复杂状态
```

这种不要抽。

否则就会变成：

```text
Panel
PanelBody
PanelInner
PanelContent
PanelContentInner
```

这种抽象灾难。

## CSS 最后也不会消失，但性质会完全不同

现在比较容易是：

```text
App.css
Conversation.css
DataSourceTree.css
WorkspaceDock.css
各种历史 class
```

互相叠 override。

理想状态是：

```text
styles/
  tokens.css
  foundation.css

components/ui/
  Button
  IconButton
  Menu
  ...

features/workbench/
  ResourceSection
  ContextualHeader
  DockTabStrip
  SettingsSection

features/conversation/ui/
  Message
  Activity
  ToolDisclosure
  Composer
```

然后 feature CSS 主要只描述：

> **这个业务内部是什么。**

而不是反复定义：

> **DBFox 的按钮、标题、section、panel 应该长什么样。**

## 所以最终应该达到这种效果

现在开发一个新 DLC：

```text
开发者：
“我要一个 GitHub Dock View。”
```

不应该需要设计：

```text
Dock
Tab
selected
hover
close
overflow
resize
background
border
font
motion
```

只需要设计：

```text
GitHub View 内部的信息结构。
```

开发一个新 Settings 页面：

不应该重新设计：

```text
Section
Row
Label
Control alignment
Divider
```

只需要填：

```text
有哪些设置。
```

开发新的 Agent 状态：

不应该重新设计一张 Card。

只需要决定：

```text
这个状态是 running / complete / warning / error，
用户能否展开，
展开以后有什么信息。
```

这才是这轮重构真正应该得到的结果。

**不是“所有东西组件化”，而是“所有产品语言组件化，所有业务语义保持自由组合”。**

如果做完之后新功能还是经常需要写：

```css
background
border
border-radius
box-shadow
font-size
hover
active
focus
```

来定义它自己的基本 UI 语言，那这次 Design System 重构就还没有成功。
