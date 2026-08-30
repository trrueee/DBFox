# DBFox 产品设计基线 · 终稿

> 文档类型：产品与交互规范
>
> 状态：已接受
>
> 最后核验：2026-08-15
>
> 版本：v2.1（评审修订版 · IA 冻结）
> 定位：产品与视觉/交互基线。当前 Shell 边界、导航所有权以 [`docs/architecture/frontend.md`](architecture/frontend.md) 和源码测试为准；已完成的迁移方案位于 `docs/archive/designs/`，本文历史方案中仍提及 `WorkspaceTabs` 的部分不再作为实现依据。
> v2.0：所有「文字 Tab 切换」升级为产品化组件；补齐视觉语言、组件规格、快捷键、动效与空状态。
> v2.1：信息架构（IA）正式冻结，不再推翻 Project / Conversation / SQL / Artifact 关系；Switcher 锁定「图标 + 短文字」；Console 执行块去卡片化，回归连续 Transcript；色彩降级为辅助线索。

---

## 0. 设计语言总纲

DBFox 的视觉气质：**「IDE 的骨架，AI 产品的皮肤」**。

> **落地第一原则（评审确认）**：所有新界面必须结合 DBFox 原有风格与设计体系做匹配——复用现有 tokens、组件与视觉模式，不另起一套视觉语言。风格目标：**简约又不简陋，不花哨，但观感舒服。** 基线约束信息架构与交互模型；视觉质感以 `desktop/src/styles/tokens.css` 现有体系为权威。

```text
克制        不用大色块、不用重阴影，信息靠层级而不是装饰
轻快        所有切换 < 200ms，无刷新感，状态永不丢失
专业        等宽字体只出现在它该出现的地方（SQL / 数据 / 错误码）
AI 感       AI 相关内容统一用 ✦ 符号 + 品牌紫标识，一眼可辨
```

### 0.1 设计令牌（以 tokens.css 为权威）

视觉令牌不在本文档另建色板，直接以 `desktop/src/styles/tokens.css` 为准：

```text
品牌紫        --color-primary #6554D9（AI / 选中 / 主操作）
控制台青      --color-console-accent #0284C7（SQL Console 专属，本基线新增）
文字三级      --color-text-primary / secondary / muted（禁止自造灰色）
边框两级      --color-border / --color-border-hover + hairline 两级
背景三级      --color-bg / --color-panel / --surface-raised
状态色        --color-success / warning / danger（只表达状态）
圆角          --radius-sm/md/lg/control/panel/pill
间距          --space-1/2/3/4/5/6/8（4px 基准，执行块间距 = --space-5）
动效          --motion-fast 150ms / --motion-normal 200ms，全局尊重 reduced-motion
密度          --density-*（侧栏行 28px、表格行 32px、控件高度分档）
图标          Lucide 唯一来源；--icon-size-sm 14px / --icon-size-md 16px
数字          表格数字 / 行数 / 耗时 / 错误码统一 .dbfox-tnum 等宽数字
```

### 0.2 两条色彩线索贯穿全产品

```text
✦ 紫色  = AI 在说话        （对话、AI 按钮、AI 生成的工件）
>_ 青色  = 数据库在说话      （Console prompt、执行状态、Query OK）
```

**颜色是辅助线索，而不是唯一线索。** 身份识别必须由多重编码共同承担：

```text
AI vs 用户 的区分至少包含：
  位置    用户靠右 / AI 靠左（或相反，全局统一）
  图标    ✦ 头像 vs 用户头像
  名称    「DBFox」vs「你」，始终标注
  色彩    紫 vs 中性灰 —— 只是强化，不是判据
```

任何关键信息（错误、成功、执行状态）都必须同时有图标 + 文字，禁止仅靠红/绿/紫传达——保证色弱用户、不同主题、灰度截图下全部可读。

---

## 1. 产品模型

```text
DBFox
  └── Project  =  Datasource（当前阶段 1:1）
```

产品语言一律使用「项目」，底层实现保留 `datasource`。

---

## 2. 三栏空间模型

```text
┌──────────────┬────────────────────────────┬────────────────┐
│  Sidebar     │      Main Workspace        │ Artifact Dock  │
│  我有什么？   │      我正在做什么？         │ AI 给了我什么？ │
└──────────────┴────────────────────────────┴────────────────┘
```

判断任何新功能归属的三个问题保持不变：

```text
左：我有什么？   中：我正在做什么？   右：AI 给了我什么？
```

---

## 3. 左侧 Sidebar（产品化版）

```text
┌──────────────────────────────────┐
│  🦊  DBFox                    ⌘K │
│ ──────────────────────────────── │
│                                  │
│  项目                        ⊕   │
│                                  │
│  ┌────────────────────────────┐  │
│  │ 🐬  creatorhub        ●    │  │  ← 当前项目：浅紫底 + 左侧 3px 品牌条
│  │     MySQL · 3 个对话        │  │
│  │                            │  │
│  │     ⌄  💬 对话    ▤ 数据    │  │  ← 资源视图：下划线式微型 Tab
│  │     ──────────────────     │  │
│  │     ＋ 新建对话             │  │
│  │                            │  │
│  │     💬 查询最近一周注册用户  │  │
│  │     💬 分析用户留存情况      │  │
│  │     💬 检查 agent_task_runs │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │ 🐬  analytics           ●  │  │  ← 折叠态：单行卡片
│  └────────────────────────────┘  │
│  ┌────────────────────────────┐  │
│  │ 🐘  test_db             ○  │  │  ← 未连接：灰点 + 悬停显示「连接」
│  └────────────────────────────┘  │
│                                  │
│ ──────────────────────────────── │
│  ⚙  设置                  v0.9.2 │
└──────────────────────────────────┘
```

### 3.1 组件规格

**Project Card（项目卡片）**

```text
结构   [数据库类型图标 32px 圆角方块] [名称 + 副标题] [连接状态点]
图标   MySQL 🐬 / PostgreSQL 🐘 / ClickHouse ⚡ → 用数据库官方色系渐变方块
状态   ● 已连接（绿，呼吸微动画）   ○ 未连接（灰）
展开   当前项目卡片纵向展开，内含资源视图；其余项目保持单行
悬停   右侧浮现 ⋯（右键菜单同内容：重连 / 编辑 / 复制配置 / 删除项目）
```

**新建项目按钮**

```text
「项目」标题右侧的 ⊕ 图标按钮（ghost，hover 变品牌紫）
点击 → 居中弹层 Popover（非页面跳转）：

  ╭─ 新建项目 ────────────────────╮
  │  连接一个数据库，开始问数      │
  │                                │
  │  [🐬 MySQL]   [🐘 PostgreSQL] │
  │  [⚡ ClickHouse] [🗄 SQLServer]│
  │                                │
  │  更多数据源 →                  │
  ╰────────────────────────────────╯
```

**资源视图切换（对话 / 数据）**

```text
不使用胶囊按钮，使用下划线式微型 Tab：

  💬 对话      ▤ 数据
  ───────
   ^ 当前项：ink.900 + 2px 品牌紫下划线；其余 ink.400

快捷键：⌘⇧D（对话）/ ⌘⇧T（数据）
```

**对话列表项**

```text
💬 查询最近一周注册用户
   2 小时前 · 12 条消息        ← 副标题 hover 才显示，保持列表干净

悬停右侧浮现 ⋯：重命名 / 置顶 / 复制对话 / 在新对话中继续 / 删除
置顶对话前显示 📌，单独成组
```

**数据树**

```text
🔍 搜索表或字段（⌘P，输入即时过滤，匹配字段名也高亮父表）

▾ 🗄 creatorhub
   ▾ ⬡ public
      ▤ account_behaviors        1.2M rows
      ▤ agent_task_runs           48K rows
      ▤ agent_tasks                3K rows

行级信息：表名 + 行数估计（ink.400，等宽数字）
悬停浮现快捷操作：👁 查看数据 · >_ 发送 SELECT · ✦ 问 AI
右键完整菜单见 §13
```

### 3.2 明确删除

```text
❌ 一级功能导航（智能问数 / 对话历史 / SQL 控制台 / 数据源管理）
❌ 顶部「＋ 新建数据源」
❌ 顶部「SQL 控制台」按钮
```

---

## 4. 顶部栏：只回答两个问题

```text
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  🐬 creatorhub  ▾        ╭──────────────────────────╮    🔍   👤  │
│     ● MySQL · 已连接      │  Workspace Switcher      │    ⌘K       │
│                           ╰──────────────────────────╯              │
│                                                                    │
│     ↑ 我在哪里                  ↑ 我在做什么               ↑ 通用能力 │
└────────────────────────────────────────────────────────────────────┘
```

**左侧 · 项目标识**

```text
项目图标 + 项目名 + ▾（点击弹出 Project Switcher，跨项目秒切）
副标题：数据库类型 + 连接状态（● 绿 / ○ 灰）
断线时副标题变为「重新连接」可点击按钮
```

**右侧 · 通用能力**

```text
🔍 全局搜索（⌘K）：项目 / 对话 / 表 / 命令，统一入口
👤 用户菜单
```

顶部从此不再是功能导航中心。

---

## 5. Workspace Switcher —— 本次设计的核心组件

**废弃「[ 对话 | SQL ]」文字 Tab。** 改为居中悬浮的**图标分段控制器（Segmented Control）**：

```text
非激活态：
╭─────────────────────────────────────╮
│  ✦ 问数  ⌘1  │  >_ 控制台  ⌘2       │
╰─────────────────────────────────────╯

激活「控制台」态：
╭─────────────────────────────────────╮
│  ✦ 问数     │ ▰▰ >_ 控制台 ▰▰ ⌘2    │
╰─────────────────────────────────────╯
              ^ 滑动指示器：白底 + 阴影 + 青色图标，200ms spring 滑动
```

### 5.1 规格

```text
容器      胶囊形（r.full），bg 为 ink.900/4% 浅灰，内边距 3px
分段      图标 + 短文字 + 快捷键提示（快捷键 hover / 按住 ⌘ 才淡入）
当前段    白色滑块浮起（shadow.sm），图标着色：
            ✦ 问数   → 品牌紫  fox.500
            >_ 控制台 → 控制台青 term.500
            ▤ 表     → ink.700（上下文模式，见下）
切换动效  滑块 200ms spring 滑动；主工作区内容 150ms 交叉淡入淡出
快捷键    ⌘1 问数 · ⌘2 控制台 · ⌘3 表详情 · ⌘` 在最近两个模式间往返
```

**文字是硬约束，永不做纯图标 Switcher：**

```text
✦ 和 >_ 没有 universal 共识，纯图标会把识别成本转嫁成每次切换前的犹豫
「问数 / 控制台」是产品核心概念，Switcher 上的文字同时承担导航和教学
DBFox 是生产力工具：识别速度 > 极简感

唯一降级时机：
  窗口 < 1100px   → 当前段保留「图标+文字」，非激活段收缩为仅图标
  按住 ⌘ 时       → 文字旁淡入快捷键（文字始终在场）
```

### 5.2 第三段是上下文式的

「▤ 表」**不是常驻段**。只有当用户点击了某张表，它才出现：

```text
╭──────────────────────────────────────────────╮
│  ✦ 问数  │  >_ 控制台  │  ▤ agent_task_runs ✕ │
╰──────────────────────────────────────────────╯
                            ^ 带着表名出现，✕ 可关闭
                              关闭后该段消失，回到两段
```

这把「Table Inspector 是临时工作状态」这个语义直接做进了组件里，而不是靠用户理解。

### 5.3 状态语义

Switcher 的每一段都**记得自己的现场**：

```text
✦ 问数    记住：当前对话、滚动位置、输入框草稿、选中的工件、Dock 开合
>_ 控制台  记住：完整 transcript、未执行输入、历史命令、滚动位置、执行状态
▤ 表详情  记住：当前表、子 Tab（数据/结构/ER）、筛选与分页
```

切换零损耗，这是「同一个 Project 的两个工作面」而不是「两个页面」。

---

## 6. 问数模式（AI Conversation）

```text
┌────────────────────────────────────────────────────────────────┐
│ 🐬 creatorhub · ● MySQL    ╭ ✦ 问数 │ >_ 控制台 ╯        🔍 👤 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  查询最近一周注册用户                            📌 ···         │
│  ──────────────────────────────────────────────                │
│                                                                │
│  ╭ 你 ───────────────────────────────────────────────────╮     │
│  │ 查询用户表最近一周的新注册用户数量                      │     │
│  ╰────────────────────────────────────────────────────────╯     │
│                                                                │
│  ✦ DBFox                                                       │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 最近 7 天共有 **1,243** 个新注册用户。                  │    │
│  │ 较上一周期 ↑ 12.4%。                                    │    │
│  │                                                         │    │
│  │ ┌─ SQL ────────────────────────────────────────────┐   │    │
│  │ │ SELECT COUNT(*) FROM users                        │   │    │
│  │ │ WHERE created_at >= NOW() - INTERVAL 7 DAY;       │   │    │
│  │ └───────────────────────────────────────────────────┘   │    │
│  │                                                         │    │
│  │ [ ⧉ 复制 ]  [ >_ 发送到控制台 ⌘⏎ ]  [ 📊 生成图表 ]      │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                │
│  ╭────────────────────────────────────────────────────────╮    │
│  │ ✦ 继续提问，或 ⌘⏎ 发送…                            ⊙ │    │
│  ╰────────────────────────────────────────────────────────╯    │
└────────────────────────────────────────────────────────────────┘
```

### 6.1 关键产品化细节

```text
SQL 卡片     AI 消息中的 SQL 是独立卡片组件：mono 字体、语法高亮、
             右上角行号/hover 复制，视觉上与正文明确分层

主操作按钮   「>_ 发送到控制台」是 AI 回复下唯一的实心按钮（品牌紫底 +
             终端图标），其余为 ghost —— 操作有主次

一键送达     点击后：Switcher 滑块滑向 >_ 控制台 → SQL 已在 prompt 就位
             → 光标闪烁等待，绝不自动执行

Conversation 原有 Timeline / Composer / Approval / Question / Artifacts
             机制全部保留，只是视觉上按上面的层级重排
```

---

## 7. 右侧 Artifact Dock

```text
┌──────────────────────┐
│  ✦ 工件           ⊟  │
│  ──────────────────  │
│                      │
│  ┌────────────────┐  │
│  │ ▤ 查询结果      │  │  ← 类型图标 + 标题 + 时间
│  │ 1,243 rows     │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ 📊 注册趋势图   │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ 📝 留存分析笔记 │  │
│  └────────────────┘  │
└──────────────────────┘
```

```text
归属   当前 Conversation / Run，与 Project 级资源严格区分
内容   Result / Chart / Note，保持现有 ArtifactDock 方向
样式   卡片列表而非 Tab；点击卡片 → 该工件在主区或 Dock 内放大查看
联动   AI 消息中引用某工件时，卡片高亮描边（品牌紫 1px）
```

**SQL 永不进入此 Dock。** 工件属于 Run，SQL Console 属于 Project，生命周期不同。

---

## 8. 控制台模式（SQL Console）

Navicat CLI 的交互，DBFox 的皮肤。核心原则：

> **逻辑上是 Block，视觉上是连续 Transcript。**
> 数据结构按「一次执行 = 一个 Block」组织（驱动 hover 操作、重新执行、问 AI 的粒度）；
> 但视觉上**不画卡片**——没有圆角大框、没有双边条、没有阴影。
> 命令之间靠极轻的间距、时间戳和 hover 背景区分；结果表格直接嵌在命令下面。
> 它必须读起来像一份连续的数据库会话记录，而不是一摞聊天卡片。

```text
┌────────────────────────────────────────────────────────────────┐
│ 🐬 creatorhub · ● MySQL    ╭ ✦ 问数 │ ▰>_ 控制台▰ ╯       🔍 👤 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  mysql › SELECT * FROM agent_task_runs                         │
│       -> WHERE status = 'failed';                    09:41:22  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  id    task_id       status  error              ran_at    │  │
│  │  4821  daily_report  failed  timeout       08-15 09:12    │  │
│  │  4820  sync_users    failed  conn refused  08-15 09:10    │  │
│  └──────────────────────────────────────────────────────────┘  │
│  24 rows · 0.01s                                               │
│                                                                │
│  mysql › SELECT * FROM not_exist;                    09:42:03  │
│  ✕ ERROR 1146 (42S02): Table 'creatorhub.not_exist' doesn't    │
│    exist                                                       │
│    [ ✦ 让 AI 修复 ]  [ ↻ 修正后重跑 ]                           │
│                                                                │
│  mysql › ALTER TABLE users ADD nickname VARCHAR(50); 09:42:40  │
│  ✓ Query OK · 0 rows affected · 0.21s                          │
│                                                                │
│  mysql › █                                                     │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  ⌘⏎ 执行 · ⇧⏎ 换行 · ▲▼ 历史                      ⠿ idle      │
└────────────────────────────────────────────────────────────────┘

整页没有任何一张「卡片」。唯一的盒形容器只有两个：
  ① SELECT 结果表格（表格本身需要边界）
  ② 底部 Live Prompt 输入行（它是操作区，需要聚焦态）
```

### 8.1 执行块（Execution Block）规格

**数据上**，每个 Block = `sql + response`，是操作粒度单位；**视觉上**遵循「连续感优先」：

```text
Block 分隔（三选一并用，全部轻量）
  间距      Block 之间 20px 垂直留白（Block 内部行距保持紧凑）
  时间戳    每条命令右侧 ink.400 小字 mono（09:41:22），hover 显示完整时间
  hover     整行命令 + 其响应出现 4% 灰底，标识「它们是一组」
  ── 禁止：圆角外框、背景色块、阴影、左右边条 ──

命令行
  Prompt    「mysql ›」青色 mono，跟随数据库类型（psql › / ch ›）
  续行      多行 SQL 用「   ->」前缀缩进，保留 CLI 原味
  高亮      SQL 语法高亮，mono
  悬停操作  行尾浮现：⌘⏎ 重跑 · ⧉ 复制 · ✎ 编辑后重跑 · ✦ 问 AI

响应（SELECT）
  表体      复用现有 Table Grid（虚拟滚动、列宽可调、单元格复制）
            这是全 Transcript 唯一允许的「盒子」，表格边界即信息边界
  底栏      「24 rows · 0.01s」单行 ink.400 mono，无框无底栏背景
  操作      hover 底栏浮现：⧉ 复制 · ↻ 重跑 · ✦ 问 AI · ⋯（导出 CSV）

响应（ERROR）
  标识      ✕ 图标 + err.500 错误码（mono 加粗），描述继承默认文字色
  排版      直接跟在命令行下方，缩进对齐 SQL 起始列，无框
  动作      错误描述下方一行内嵌按钮：「✦ 让 AI 修复」（紫实心小按钮）
            +「↻ 修正后重跑」（ghost）—— 错误场景的第一公民

响应（DDL/DML）
  标识      ✓ 图标 + ok.500「Query OK」，其余 ink.600 单行 mono
  展开      Rows matched / Changed / Warnings 在第二行，ink.400
```

### 8.2 输入行（Live Prompt）

```text
常驻 Transcript 底部，与历史执行块视觉同源（同样的 mysql › 前缀）
多行编辑     ⇧⏎ 换行，⌘⏎ 执行；输入超 3 行自动展开为编辑区
历史         ▲▼ 翻阅（当前会话内），⌘R 模糊搜索全部历史
补全         输入时浮出：表名 / 字段名 / 关键字（基于当前 Project 元数据）
执行中       输入行变为「⠿ executing…」+ 转圈，可 ⌘. 取消
```

### 8.3 视觉纪律

```text
✅ 浅色底，不是黑底 terminal —— DBFox 不做「极客 cosplay」
✅ CLI 的结构感（prompt、续行、顺序流）全部保留
✅ 结果用现代表格，不画 ASCII 边框
✅ 全程 mono 字体只出现在：prompt、SQL、数据、错误码、耗时
```

---

## 9. Console Session：Project 级、持久、独立

```text
creatorhub ── SQL Console Session
analytics  ── SQL Console Session      ← 彼此完全独立
test_db    ── SQL Console Session
```

```text
保存内容   完整 transcript（含结果与错误）、未执行草稿、
           命令历史、滚动位置、执行状态
持久化     切模式不丢、切项目不丢、刷新页面不丢（落盘）
清理       项目右键「清空控制台」单独操作，不与删除项目耦合
```

---

## 10. AI → SQL：发送到控制台

```text
问数中 AI 给出 SQL
      ↓ 点击「>_ 发送到控制台」
Switcher 滑块滑动到控制台（200ms spring）
      ↓
SQL 已填入 Live Prompt，光标就位
      ↓
用户审阅 → ⌘⏎ 执行
```

```text
铁律：AI 可以准备 SQL，执行永远是用户的明确动作。
```

---

## 11. SQL → AI：把现场带回去

命令卡 / 结果卡 / 错误卡上的「✦ 问 AI」，携带完整上下文进入（或新建）对话：

```text
来源           携带上下文
─────────────────────────────────────────────
某条 SQL       datasource + SQL 原文
某个 ERROR     datasource + SQL + 完整错误码与描述
某个 Result    datasource + SQL + 结果摘要（行数/列/样例行）
```

错误卡上的「✦ 让 AI 修复」是它的特化：预填 prompt「这条 SQL 报错了，帮我修复并解释原因」。

---

## 12. 表 → AI / SQL

表右键菜单：

```text
▤ agent_task_runs
──────────────────────────
  ✦ 问 AI                    → 以 creatorhub.agent_task_runs 为结构化上下文开问
  👁 查看数据                  → Switcher 出现「▤ agent_task_runs」段
  ⬒ 查看表结构                 → 同上，落到「结构」子 Tab
──────────────────────────
  >_ 发送 SELECT 到控制台       → SELECT * FROM … LIMIT 100;（不自动执行）
  >_ 发送 COUNT 到控制台
──────────────────────────
  ⧉ 复制表名 / 完整表名
  ↻ 刷新
```

---

## 13. 项目 / Schema 右键

```text
项目（datasource）
  ✦ 新建对话
  >_ 打开控制台
  ──────────────
  ↻ 刷新元数据
  ⇄ 重新连接
  ✎ 编辑连接 / ⧉ 复制连接配置
  ──────────────
  ⏻ 关闭连接
  🗑 删除项目（红色，二次确认）

Schema
  >_ 打开控制台 / ↻ 刷新结构 / ⧉ 复制名称 / ⓘ 查看属性
```

入口不变，变的是「打开之后是什么」——统一进入 §5 的 Switcher 模型。

---

## 14. 对话右键

```text
✎ 重命名
📌 置顶
⧉ 复制对话
↪ 在新对话中继续
──────────
🗑 删除
```

次级能力（复制链接 / 导出）后续追加，不进首版菜单。

---

## 15. 全局搜索（⌘K）

```text
╭─ 🔍 搜索或执行命令… ─────────────────────────╮
│                                              │
│  项目                                        │
│  🐬 creatorhub          打开项目        ↵    │
│                                              │
│  表                                          │
│  ▤ agent_task_runs      查看数据        ↵    │
│                         发送到控制台    ⌘↵   │
│                         ✦ 问 AI         ⇧↵   │
│                                              │
│  命令                                        │
│  >_ 打开控制台                                │
│  ⊕ 新建项目                                  │
│  ✦ 新建对话                                  │
╰──────────────────────────────────────────────╯
```

每个结果带**多动作**：同一个「表」结果，回车看数据、⌘↵ 发 SQL、⇧↵ 问 AI。这是把三条主链路（表→看、表→SQL、表→AI）压缩进一个入口。

---

## 16. 表详情（Table Inspector）

```text
┌────────────────────────────────────────────────────────────────┐
│  ▤ agent_task_runs                    数据 │ 结构 │ ER          │
│     creatorhub · public · 48,213 rows  ← 下划线子 Tab，轻量    │
├────────────────────────────────────────────────────────────────┤
│  [筛选 +]  [列显隐]                            ↻ 刷新  ⬇ 导出  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  数据网格（虚拟滚动）                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

```text
定位   上下文式工作面，由点击表触发，Switcher 中带名出现、可关闭
不做   不恢复旧式全局 Tab Bar；同一 Project 同时只检查一张表（切换即替换）
```

---

## 17. 空状态与首次体验

```text
没有任何项目时（Main Workspace）：

        🦊
   连接第一个数据库，
   开始用自然语言问数。

   [ ⊕ 新建项目 ]     ← 实心品牌紫，全页唯一焦点

   或先逛逛示例项目 →


项目内没有任何对话时（问数模式）：

   ✦ 试试这样问：
   ┌─────────────────────────────────────┐
   │ 「最近一周每天新增多少用户？」        │
   │ 「哪张表的数据量最大？」              │
   │ 「agent_task_runs 里失败最多的任务？」│  ← 基于真实元数据生成
   └─────────────────────────────────────┘


控制台为空时：

   mysql › 这里是你和 creatorhub 的直接对话。
           输入 SQL，⌘⏎ 执行。
           或者从左侧数据树把表「发送」过来。
```

---

## 18. 动效清单

```text
Switcher 滑块       200ms spring（stiffness 380, damping 30）
主区内容切换         150ms 交叉淡入 + 4px 位移（方向跟随滑块方向）
执行块出现           命令行就地落定，响应内容从其下方生长（120ms，无卡片弹入）
AI 消息             打字机流式 + SQL 卡片最后整体淡入
Artifact Dock      260ms 宽度弹簧展开；新工件卡片顶部滑入 + 紫边脉冲一次
连接状态点           已连接 2s 呼吸；断线瞬时变红，无动画
```

所有动效可被 `prefers-reduced-motion` 全局降级为瞬时切换。

---

## 19. 快捷键总表

```text
导航       ⌘1 问数 · ⌘2 控制台 · ⌘3 表详情 · ⌘` 最近两个模式往返
           ⌘⇧D 对话列表 · ⌘⇧T 数据树
全局       ⌘K 搜索 · ⌘P 搜表（数据树聚焦时）
问数       ⌘⏎ 发送 · ⌘N 新建对话
控制台     ⌘⏎ 执行 · ⇧⏎ 换行 · ▲▼ 历史 · ⌘R 搜历史 · ⌘. 取消执行
           ⌘L 清空屏幕（transcript 保留，仅视觉折叠）
```

快捷键提示的呈现纪律：**平时隐藏，hover 或按住 ⌘ 时全局淡入**（类 Linear）。

---

## 20. 状态模型（技术契约）

```ts
type MainMode = "conversation" | "sql" | "table";
type SidebarMode = "conversations" | "data";

/** Console Transcript 的最小单元：一次执行 = sql + 其响应（顺序追加） */
type ConsoleEntry =
  | { kind: "info";   text: string; at: number }                       // 连接/提示
  | { kind: "sql";    text: string; at: number; status: "ok" | "error" | "running" }
  | { kind: "result"; sqlRef: number; columns: Column[]; rows: Row[];
      rowCount: number; durationMs: number; truncated: boolean }
  | { kind: "error";  sqlRef: number; code: string; sqlState?: string;
      message: string; durationMs: number }
  | { kind: "ddl";    sqlRef: number; affected: number;
      matched?: number; changed?: number; warnings?: number; durationMs: number };

interface SqlConsoleSession {
  entries: ConsoleEntry[];   // 顺序即 transcript，永不重排
  draft: string;             // Live Prompt 未执行内容
  history: string[];         // 命令历史（▲▼ / ⌘R）
  scrollPosition: number;
  running: boolean;
}

interface ProjectWorkspaceState {
  datasourceId: string;
  sidebarMode: SidebarMode;

  mainMode: MainMode;
  /** ⌘` 在最近两个模式间往返 */
  lastMainMode?: MainMode;

  activeConversationId?: string;

  sqlConsole: SqlConsoleSession;

  /** 上下文式第三工作面；undefined = Switcher 不显示第三段 */
  activeTable?: {
    name: string;                  // 完整限定名 db.schema.table
    subTab: "data" | "schema" | "er";
    filters?: unknown;             // 表详情的筛选/分页现场
  };
}

/** 全局：每个 Project 一份，互不干扰 */
type WorkspaceStateByProject = Record<string, ProjectWorkspaceState>;
```

**读写与持久化：**

```text
内存       Zustand store，key = datasourceId
落盘       每 500ms 防抖持久化（entries 大结果集只存引用/摘要，行数据进 IndexedDB）
恢复       激活 Project 时 hydrate；恢复后滚动位置、草稿、running 态原样回来
上限       transcript 默认保留最近 500 个 Block，更早的可展开加载（不删历史文件）
```

**动作契约：**

```text
openSqlConsole(datasourceId, initialSql?):
  激活 Project → mainMode = "sql" → 复用该 Project 的 Session
  → initialSql 存在则填入 draft（不执行）
  永不创建 sql-1 / sql-2 / sql-3

openTableInspector(datasourceId, table, subTab = "data"):
  激活 Project → activeTable = { name: table, subTab } → mainMode = "table"

closeTableInspector(datasourceId):
  activeTable = undefined → mainMode 回落到 lastMainMode ?? "conversation"

sendToAi(datasourceId, payload):   // payload 见 §11：SQL / ERROR / Result 摘要
  新建或复用当前 Conversation → 注入结构化上下文 → mainMode = "conversation"
```

现有 `SqlConsoleWorkspace` 的 entries Transcript 模型直接保留复用——这次的 CLI 方向比任何 Query Editor 方案都更贴近现有实现。改造重点是：**去 WorkspaceTab 依赖 + 状态改为 datasource 维度 + 视觉按 §8 重排**。

---

## 21. 最终废弃清单（不再讨论）

```text
❌ 智能问数 / 对话历史 / SQL 控制台 / 数据源管理 作为一级导航
❌ 顶部「新建数据源」「SQL 控制台」按钮
❌ Workspace 全局 Tabs / 每对话一个 SQL Console / 每次打开新建 SQL Tab
❌ 工件 | SQL 右侧切换 / SQL 进 Artifact Dock
❌ Query Editor + 固定 Result Split / 全屏 Editor + Result Drawer
❌ DataGrip 式 Query IDE
❌「[ 对话 | SQL ]」裸文字 Tab（升级为 §5 Workspace Switcher）
```

---

## 22. 一句话定义

> **DBFox 是一个以数据库项目为中心的 AI Database Workspace：左侧组织项目中的对话与数据资源，中间通过一枚图标化的 Workspace Switcher 在「✦ 问数」「>_ 控制台」「▤ 表详情」三个工作面之间无损耗切换，右侧只承载 AI 生成的工件；每个数据源拥有一个持久、连续、Navicat CLI 风格的 SQL Console Session，并与该项目下所有对话自由互通——AI 准备 SQL，人执行 SQL，错误回到 AI。**

---

## 23. 前端改造执行决策记录（docs/quality/technical-investigation-and-reuse.md §7）

真实改造全部在现有仓库文件上原地进行；`designSample/` 仅作视觉参考，阶段 1 验收后已删除。

| 项 | 调查过的方案 | 采用 | 未采用其他方案的原因 |
| --- | --- | --- | --- |
| 设计令牌 | 新建设计系统 vs 扩展现有 `styles/tokens.css` | 扩展 `tokens.css`（控制台青、on-danger、图标/间距/动效、tabular-nums）；已废弃的 `--dbbrand-*`、`--motion-normal`、`--color-console-accent-soft` 随方案变更移除 | 新系统会形成第二份事实源 |
| Skeleton | Radix 无此组件；`react-loading-skeleton` 等第三方 | 自研约 30 行 CSS + `<span>`（`components/ui/state.tsx`） | 纯视觉占位；引入依赖不划算；受 CSP 与测试约束 |
| 分段切换器 | 新建 WorkspaceSwitcher 组件 vs 改造真实 `WorkspaceTabs` | 改造真实 `WorkspaceTabs`：胶囊分段形态、核心三模式 accent、Ctrl+1/2/3 快捷键提示，保留全部 tab 类型与关闭能力 | 真实 tab 模型承载多类型工作流，平行切换组件会造成双轨导航；应用 UI 合同禁止任意内联 layout，故不用 JS 测量滑动滑块 |
| 数据库图标 | simple-icons 包；官方商标文件 | 官方品牌标识路径内联（CC0，`features/datasource/databaseBrandData.ts` + `DatabaseBrandIcon.tsx`），中性浅底块 + 官方品牌色 | 4 个字形不值得引入 MB 级依赖；渐变方块 + 字母缩写方案被评审否决 |
| SQL Console 视觉 | 样板新写 ConsoleTranscript vs 改造真实 `SqlConsoleWorkspace` | 改造真实 `SqlConsoleWorkspace`：prompt 跟随库类型、错误内联、结果表格唯一盒形容器、等宽数字、控制台青光标；执行链路 / CodeMirror / TableArtifactView 不动 | 复用现有渲染与状态，避免第二套控制台 |
| 持久 Console | 每次新建 sql-N tab vs 每项目一个持久 Session | `workspaceStore.openSqlConsole` 按 datasourceId 复用同一 tab 与 entries；未绑定临时控制台保留顺序编号 | 本基线要求「每个数据源一个持久 Console」；沿用现有 tab/state 模型做最小语义演进 |
| 侧栏项目卡 | 新写侧栏组件 vs 改造真实 `DataSourceTree` | 项目卡列表取代单选下拉（激活项展开「对话/数据」视图）；默认「数据」保持树优先工作流；「新建对话」复用问数首页入口 | 不新增第二层导航容器；对话创建需真实提问，直接建空对话会污染数据 |
| 顶栏项目标识 | 新加 Header 组件 vs 扩展 App tabbar | 在现有 tabbar 左侧加入项目标识（品牌图标 + 名称 + 状态点） | 不引入平行导航层 |
| 核心模式快捷键 | 各组件自理 vs App 全局注册 | App 全局 keydown 注册 Ctrl+1/2/3；Tab 上 hover 淡入 kbd 提示（aria-hidden） | 快捷键是应用级合同，集中注册避免冲突 |
| 对话区表面 | 真实 `conversationWorkspace.css` 约定 | 白色 `--agent-surface` 根背景、用户气泡 `--agent-user-bg`；SQL 工件由 Data DLC 组合 Host `CodeArtifact`（复制/下载） | 与真实产品一致，不另起第二套配色 |

已知偏差与后续项：~~侧栏快速导航（智能问数/对话历史/数据源管理）暂保留作为次级入口~~（已解决：2026-08-30 侧栏重构为项目分组树，快速导航已移除）；「发送到控制台」后自动聚焦 Live Prompt 与「控制台 hover 分组高亮」列入后续打磨。
