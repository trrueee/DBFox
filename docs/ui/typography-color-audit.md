# DBFox 字体、字号与颜色审计

> 文档类型：UI 基础视觉审计
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 范围：`desktop/src/**/*.css`、`src/styles/tokens.css`、`src/boot.css`、内置 DLC CSS  
> 本轮已完成 Fluent 字体角色与默认语义颜色接入；未完成的局部硬编码清理继续按本文门禁处理。

## 1. 结论

2026-08-26 采用决策已更新：不再把现有自研字号梯度作为最终方案。生产 token 已采用 Fluent 2
官方 `fontSizeBase100–600`、对应 line-height 和 Segoe UI / Consolas / Bahnschrift 字体角色；仅为
local-first 中文桌面环境追加 PingFang SC / Microsoft YaHei UI fallback。原有 13/15/18/21px 自定义
梯度不再作为事实源。

最终方案是保留 DBFox 单一 token 边界，但用 Fluent 的成熟角色/字体语义替换无上游依据的默认值；
不引入 Web Font，不新增主题 runtime，也不增加字体或颜色 mapper。
代码、日志、SQL、JSON 才使用等宽字体；正文、控件和表格默认继续使用系统 UI 字体。

## 2. 调研与复用决策

| 方案 | 调研结果 | 决策 |
| --- | --- | --- |
| Windows / Fluent typography | Windows 推荐 Segoe UI Variable；Fluent 为 caption/body/subtitle 提供清晰字号与行高层级 | **ADOPT**：接入官方 global font tokens，只追加离线 CJK fallback |
| Carbon productive type set | 数据密集产品以 14px 为常见正文基线，强调稳定的 type token | **REFERENCE**：用于核对密度，不引入 Carbon |
| Atkinson Hyperlegible / Google Font | 单字体可读性强，但新增下载、离线、CJK fallback 和视觉漂移成本 | **REJECT**：不适合 local-first Windows/CJK 桌面应用 |
| Fira Sans / Fira Code | 技术产品常用，但当前只有零散 Fira Code fallback，无法覆盖中文 | **REJECT**：删除局部特例，不将其升级为产品字体 |
| Noto Sans SC | 中文覆盖完整，但随应用捆绑或在线加载都会增加体积和许可资产维护 | **REFERENCE**：仅在未来确有跨平台字形一致性要求时重评 |
| 当前自研字号梯度 | 已离线可用，但 13/15/18/21px 与角色命名缺少成熟上游依据 | **REPLACE** |
| Fluent 2 global font tokens | 官方源码提供 10/12/14/16/20/24px、匹配行高及 Segoe UI/Consolas/Bahnschrift 角色 | **ADOPT**；仅追加 CJK fallback |

参考：

- Windows typography：https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography
- Fluent typography：https://fluent2.microsoft.design/typography
- Carbon type sets：https://carbondesignsystem.com/elements/typography/type-sets/
- WCAG contrast：https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- WCAG text spacing：https://www.w3.org/WAI/WCAG22/UNDERSTANDING/text-spacing.html

## 3. 当前字体事实源

`src/styles/tokens.css` 已定义：

| 角色 | 当前字体族 | 用途 |
| --- | --- | --- |
| `--font-family-ui` / `--font-family` | Segoe UI Variable Text、Segoe UI、PingFang SC、Microsoft YaHei UI、system-ui | App、正文、控件、导航 |
| `--font-family-code` / `--font-mono` | Cascadia Mono、Cascadia Code、SFMono-Regular、Consolas 等 | SQL、代码、JSON、日志、技术详情 |
| `--font-family-data` | 当前权威 data stack | 数字和表格；结合 `tabular-nums` |

这一分工应成为唯一入口。业务 CSS 不再自定义 Fira Code、JetBrains Mono 或另一套
`ui-monospace` fallback。

## 4. 当前字号使用审计

静态扫描到主要 UI token 使用量如下（同一选择器可能包含多个声明，数字用于发现集中度而非
组件数量）：

| Token | 使用次数 | 当前像素值 | 观察 |
| --- | ---: | ---: | --- |
| `--ui-font-control` | 65 | 13px | 控件与紧凑文本主力，合理 |
| `--ui-font-caption` | 61 | 12px | 大量次要说明，需验证对比度与行高 |
| `--ui-font-label` | 48 | 12px | 与 caption/micro 同尺寸，层级依赖字重/颜色 |
| `--ui-font-micro` | 26 | 12px | 名为 micro 但并未更小；语义可能重复 |
| `--ui-font-body` | 25 | 14px | UI 正文基线，符合桌面产品常见范围 |
| `--ui-font-input` | 6 | 14px | 输入正文，合理 |
| `--ui-font-page-title` | 5 | 20px | 页面标题 |
| `--ui-font-title` | 5 | 16px | 卡片/表面标题 |
| `--ui-font-code` | 4 | 13px | 代码，应扩大统一使用范围 |
| `--ui-font-data` | 3 | 13px | 数据，应扩大统一使用范围 |

Agent 另有专属排版角色：caption/micro 12px、label/code 13px、UI 14px、body/input 15px、
title 16px、subtitle 18px、display 21px。这一独立 ramp 有真实变化轴：Agent 阅读流需要比密集
工作台更舒展，因此保留，而不是强行映射回 UI ramp。

### 4.1 主要问题

1. `nano`、`micro`、`caption`、`label` 当前均为 12px，命名暗示的视觉层级并不存在。
2. 12px 角色数量多，若同时使用 muted 颜色，会比字号本身更容易造成可读性问题。
3. 部分组件使用旧 fallback（例如 11px），即使 CSS variable 正常时不会生效，也会误导维护者。
4. 字号门禁只验证“用了变量”，尚未验证变量是否存在、role 是否适合组件和 line-height 是否一致。
5. 权重合同只允许 400/500/600，方向合理；应继续以层级、空间和颜色配合，不增加 700/800。

## 5. 建议的权威排版梯度

本阶段不主张整体换字号。先固定角色、用法和行高，再用 Design Lab 在密度/缩放矩阵中校验。

### 5.1 UI 工作台

| 权威角色 | 建议值 | 使用边界 |
| --- | --- | --- |
| caption / meta | 12/16 | 时间、辅助信息、表头次要说明；不得用于主要动作 |
| label | 12/16，500/600 | 控件标签、小节 eyebrow；不能只靠全大写制造层级 |
| control / data / code | 13/18 或 13/20 | 紧凑控件、表格、代码；data 使用 tabular numerals |
| body / input | 14/20 | 工作台正文、表单输入、错误说明 |
| section title | 15/20，600 | 设置与面板 section |
| title | 16/22，600 | 卡片/对话框标题 |
| page title | 20/28，600 | 页面级标题 |
| display | 24/32，600 | 极少使用的启动/空态主标题 |

`nano` 和 `micro` 不作为“更小字号”的许可。若保留别名，必须文档化其唯一语义；否则在施工
阶段将调用方迁移到 caption/label 后删除，避免继续扩散。

### 5.2 Agent 阅读流

| 权威角色 | 建议值 | 使用边界 |
| --- | --- | --- |
| caption | 12/18 | 时间、来源、状态补充 |
| label / code | 13/20 | tool label、inline code |
| UI | 14/20 | 按钮、工具动作、次要结构 |
| body / input | 15/24~26 | 助手正文与 Composer，保持阅读舒适度 |
| title | 16/24 | ToolGroup、Artifact 小标题 |
| subtitle | 18/26 | 对话内重要 section |
| display | 21/30 | 空会话或结果主标题，限制使用 |

Agent UI 内部继续使用 `--agent-font-*`。不通过 CSS mapper 在 UI/Agent token 之间来回转换。

## 6. 字体问题清单

| 文件与位置 | 现状 | 判断 | 施工动作 |
| --- | --- | --- | --- |
| `components/data-grid/CellValuePreview.css:268` | `var(--font-sans)` 未定义 | 缺陷 | 改为权威 `--font-family-ui` |
| `features/settings/UpdateSettingsPanel.css:19,26` | `--font-size-body*` 未定义 | 缺陷 | 改为合适的 `--ui-font-*` |
| `components/ui/command.css:47` | 硬编码 Fira Code | 不一致 | 技术 shortcut 使用 `--font-family-code` |
| `workspace/queryResult/MarkdownContent.css:63` | 自定义 monospace 栈 | 重复事实源 | 使用 `--font-family-code` |
| `workspace/artifacts/ArtifactViews.css:83` | JetBrains Mono 特例 | 重复事实源 | 使用 `--font-family-code` |
| `LlmConfigPanel.css`、`DangerConfirmDialog.css`、conversation CSS | variable 后保留局部字体 fallback | 旧兼容痕迹 | 核对后直接使用权威 token，不保留第二栈 |
| DataSourceTree / conversation 若干 fallback | fallback 仍为 11px | 陈旧信息 | 同步为现行值或去除不必要 fallback |

这些动作是修复源头，不需要创建 font adapter、class mapper 或第二组语义变量。

## 7. 颜色系统审计

### 7.1 已采用的成熟结构

- 基础语义：primary、info、success、warning、danger；
- 文本：primary、secondary、muted；
- 表面：app、sidebar、panel、raised、control；
- Agent 独立 surface、stage、chart 和 trust tokens；
- SQL syntax tokens；
- light/dark、高对比度、accent 和 neutral tone 覆盖；
- focus ring、overlay、border、hairline 和 shadow token。

默认 light/dark 中性表面、文本、stroke、brand 和 status 值已采用 Fluent 2
`webLightTheme` / `webDarkTheme` alias roles；可选 teal/emerald/rose 与 warm neutral 使用
Tailwind 官方成熟色阶。两者只提供值与语义依据，不引入第二主题 runtime。

这次同时修复了根因：旧 `--color-primary` 同时被当作链接/图标前景与实心按钮背景，
暗色下无法同时正确。现拆分为 brand foreground 与 `--color-primary-fill[-hover/-pressed]`；
danger 也拆分为前景、浅背景、边框与实心填充。这是源头语义修复，不是颜色 mapper。

来源：

- Fluent light/dark alias source：https://github.com/microsoft/fluentui/blob/master/packages/tokens/src/alias/lightColor.ts 、https://github.com/microsoft/fluentui/blob/master/packages/tokens/src/alias/darkColor.ts
- Fluent web themes：https://github.com/microsoft/fluentui/blob/master/packages/tokens/src/themes/web/lightTheme.ts 、https://github.com/microsoft/fluentui/blob/master/packages/tokens/src/themes/web/darkTheme.ts
- Tailwind 官方色阶：https://tailwindcss.com/docs/colors

### 7.2 绕开 token 的位置

| 类别 | 位置 | 判断与动作 |
| --- | --- | --- |
| pre-React boot | `src/boot.css` 9 处颜色 | 真实独立边界；保留独立 CSS，但建立与默认 dark boot palette 的人工同步表和对比测试 |
| 外观预览 swatch | `AppearanceSettingsPanel.css` 17 处左右 | 预览本身有真实色值需求；应从同一 accent/neutral 配置源生成或校验，避免与 token 漂移 |
| overlay/shadow | command、context menu、dialog、dropdown、hover card、popover、resizable | 重复视觉事实；改用现有 scrim/shadow token，必要时在 tokens 源头补一种真实 elevation |
| 状态/文本 fallback | LlmConfig、ArtifactViews、scroll-area | 未定义 token 时隐藏问题；移除硬编码 fallback，并由合同检查 token 存在性 |
| 固定白色 | `TitleBar.css` | 核对是否为 on-danger/on-primary；用语义 token，不直接 `#fff` |
| Toast shadow | `Toast.css` | 使用统一 elevation token |

### 7.3 语义规则

1. 正文和控件文本只用 primary/secondary/muted；tertiary 若不存在，不得通过 fallback 暗造。
2. success/warning/danger 需要图标或文字，不允许只有颜色。
3. danger 表面上的文字使用 `--color-on-danger`，primary 表面使用 `--color-on-primary`。
4. focus ring 独立于 selected/active；高对比度下使用系统可辨边框。
5. 图表色不能承担唯一分类信息；tooltip、legend 和表格 fallback 提供文字。
6. disabled 不只是降低透明度到难以辨认；状态和 affordance 都要保留。
7. 符合 WCAG 2.2：普通文本目标至少 4.5:1，大文本至少 3:1；关键非文本控件/状态边界目标 3:1。

## 8. 设计合同扩展建议

现有 `scripts/check-design-contracts.mjs` 已验证：字号使用共享变量、字重仅 400/500/600、Agent
颜色使用 Agent token、DLC CSS namespace/known tokens/无硬编码颜色。建议在施工阶段增加：

1. 所有 `var(--token)` 必须能在权威 token 集合中解析；允许显式登记的外部 runtime variable。
2. `font-family` 只能为 inherit 或 `--font-family-ui/data/code` 及其兼容别名。
3. 非 `tokens.css`、非经过登记的 boot/preview fixture 禁止硬编码颜色和 rgba shadow。
4. fallback 不得引入另一套字号、颜色或字体事实源。
5. UI/Agent/DLC 的 token 域边界继续检查，禁止双向映射。
6. 已为默认 light/dark 补充正文、muted、primary fill 和 danger fill 的 4.5:1 自动合同；disabled、focus、selected、trust states 与可选预设继续扩充。

## 9. Design Lab 验收方式

字体/颜色对比页使用完全相同内容展示 Current、Candidate，不使用营销式假数据。至少包括：

- 中文、英文、数字、SQL、路径、错误码和长 URL；
- caption/label/control/body/title/page title 全梯度；
- primary/secondary/muted、success/warning/danger、disabled、focus、selected；
- 表格密集态、Agent 阅读态、设置表单、错误 Message、日志/JSON/SQL；
- light/dark、所有 neutral/accent、high contrast；
- compact/comfortable、100%/125%/150%/200% font/OS scale；
- 浏览器测量 computed font-family/font-size/line-height/contrast，截图只作为补充。

## 10. 施工顺序与风险

1. 先修未定义 token 和硬编码字体栈，不改变视觉梯度。
2. 再统一 shadow/scrim/on-color 等明确语义，补合同检查。
3. 在 Design Lab 比较 12px 角色和 line-height；只有证据表明确认后才合并/重命名 role。
4. 做全主题 contrast 与缩放回归，再处理局部字号。
5. 最后清理旧 fallback 和不再使用的 alias。

字体/颜色接入本身新增依赖：无。新增兼容层/映射层：无。主要风险是一次性改动过多造成密度和布局回归，因此按
“合同缺陷 → 事实源收敛 → 视觉梯度”三段提交，并用截图、计算样式和自动化合同共同验证。
