# 2026-11-07 全局图标与界面比例诊断

> 文档类型：界面质量与选型调查
>
> 状态：当前
>
> 最后核验：2026-11-07
>
> 适用范围：仓库内 Desktop Core、Host UI、SDK、内置 DLC、应用和文件类型资产

## 结论与实施状态

当前的“小气、简陋”观感有可定位的原因：图标视觉重量偏弱、尺寸规则分散、部分图形语义偏开发工具，
同时存在字符图标和另画的通用 SVG；内容容器和 Dock 的比例又放大了这些问题。
上一轮主要整理了信息和交互，没有完成全局图标体系切换，也没有解决所有空间比例问题。

本记录保留实施前的全局盘点、源码核对和真实开源图形对照。用户随后确认全局实施，
功能图标现已切换到固定提交的 Phosphor 官方 SVG；品牌与标准文件图标分别处理。
下面的数量和截图属于实施前基线，阶段实现、验证及限制见[全局设计实施记录](../archive/reviews/global-design-20261107.md)，当前设计以 [Apple HIG 工作台](apple-hig-workbench-20261107.md)为准。

实际查看了用户当前打开的 Windows 安装版 1.0.4，其菜单仍显示“DLC 扩展”；它与上一轮开发客户端
截图不是同一个构建。下列源码问题也存在于当前工作区，不能把观感问题全部归因于安装版尚未更新。

## 全局盘点范围

以 TypeScript 编译器 API 检查 TS/JS/JSX，PostCSS 检查 CSS。排除测试、生成代码、Design Lab、
第三方 vendor 和构建副本，分别记录直接导入、Host 图标消费、SVG、字符候选、CSS 图形与本地资产。

| 项目 | 当前结果 |
| --- | --- |
| 生产源文件 | 264，包含 Renderer、Electron Main/Preload、SDK 与 DLC |
| CSS 文件 | 76 |
| 直接引用 Lucide 的生产文件 | 60 |
| 不同 Lucide 图标名称 | 105，含 `ArrowUpIcon` 等有效别名，不把类型导入计为图形 |
| Host Icon / ResourceIcon 消费文件 | 7 |
| 源码内联 SVG | 11 处、7 个文件；已区分图标、品牌渲染与专业图形 |
| 字符图形候选 | 18 处、9 个文件；包含正常尺寸乘号与快捷键符号，不等于 18 个缺陷 |
| CSS 图形/伪元素候选 | 16 处，多数为状态指示、折叠标记、滚动条或隐藏可访问标签 |
| 本地图标/品牌资产 | 64 份，含打包尺寸变体、ICO/ICNS 和既有 sprite；不是 64 种独立功能图标 |

覆盖入口包括主导航、项目/对话树、标题栏、Composer、文件引用、Dock 标签与工具栏、设置、
模型服务、状态/通知、审批/询问/弹窗、表格与文件查看器，以及 Data、Music、Story、Pixel、Comic、
Visualization、Voxel、Scene、Shader、Game、GitHub 等仓库内 DLC。

完整清单和可展开图形目录位于本地忽略目录：
`desktop/output/playwright/icon-review-20261107/inventory.json`、`index.html`、`local-artwork.json`。
动态第三方包和上游编辑器内部实现不因静态扫描而被视为逐控件验收通过。

## 已确认的问题

### 1. 小尺寸细线被进一步压缩

`desktop/src/styles/tokens.css:163` 定义 14/16/20 px 三档图标，但使用职责没有一致落地。
`components/ui/button.css:37` 将普通按钮内所有 SVG 设为 16 px，small 按钮内设为 14 px；
组件传入的 `size={20}` 仍可能被 CSS 覆盖。`coreDockViews.tsx:14` 又为部分 Dock 图标指定 13 px。

Lucide 的 24 单位图形缩到 14 px，2 单位笔画约为 1.17 CSS px；多数图标又使用次要文字颜色，
视觉形体较弱。图标库的版本新旧不能解释这些实际应用差异。

### 2. 图形语义和选中态欠缺产品层级

`settingsSections.ts` 用 CPU 表示模型服务、Bug 表示诊断日志、PackageOpen 表示扩展，
更像工程配置面板的词汇。扩展列表复用同一个包图标，专业能力之间缺少有意义的识别。
许多导航图标仅改变颜色，图形本身没有区分默认与选中状态。

### 3. 字符与手绘通用图标确实存在

- Game 的 Connector / Dock 使用字符 `▶`，Scene 使用 `◇`。
- GitHub 移除仓库按钮使用字符 `×`。
- Voxel 的方块、Shader 的代码、Visualization 的来源表格与灯泡，共 4 个通用界面图标在 DLC 中另画 SVG，笔画和尺寸与 Host 不同。
- ProviderIcon 在具备规范资源时使用 Simple Icons；缺失时使用 8 px 字母缩写。这是中性占位，不应被当成正式品牌标志。

其余内联 SVG 中，5 处属于漫画画布、钢琴键盘、波形与关系画布，2 处属于品牌/缩写渲染；
不能把这些专业内容直接替换为通用库图标。尺寸文本中的 `×`、快捷键中的 `⌘` 也属于正常内容。

### 4. 应用品牌图标缺少小尺寸设计

当前狐狸图标以近白色和浅紫轮廓为主，整体偏吉祥物气质。实际缩至任务栏/控件尺寸后，
浅色背景上的轮廓与细节较弱。应为应用/任务栏设计专用的小尺寸品牌标记，并与吉祥物插图区分职责。
这类值得定制；齿轮、搜索、关闭、复制等通用图标适合直接复用成熟图形。

### 5. 空间比例放大了“小而散”的观感

- 设置页 `.settings-page__inner` 最宽 1040 px，扣除左右 padding 后为 968 px；内部 `.settings-content` 又限制 880 px 并居中，宽窗口会增加约 44 px 的额外内缩，页面标题与内容出现不同对齐线。
- `ConversationWorkspaceLayout` 以 `max(preferredWidth, stageWidth × defaultWidthPercent)` 初始化 Dock；Core 成果视图的首选宽度是 600 px，项目视图是 560 px，工作簿视图是 680 px。设置中的默认 28% 因此并不总能成为实际比例；在约 1176 px 的主舞台中，600 px Dock 已占约一半。
- 对话正文、输入文字与多种控件默认都是 14 px，辅助说明通常 12 px；大面积留白中的主内容没有足够明确的视觉优势。
- 当前成果列表可能同时出现同一文件的读取、修改、再读取快照，默认同等展示。信息需要按最终成果与过程记录分层，同时保留版本、来源和引用身份。

这些发现支持同时调整图标规则与空间层级，不能用全局统一放大或简单减少信息替代具体设计。

## 候选比较与建议

对照稿用真实 SVG，保持三个候选的尺寸、文字、颜色和布局一致；17 类代表图形放入导航、
对话、输入区、工具栏场景。105 个现有图标另有完整目录，64 份本地资产另有实际缩放预览。

| 方案 | 实际对照观察 | 建议 |
| --- | --- | --- |
| 现有 Lucide | 统一为 20 px 后明显清晰；仍以轮廓表达，当前用法缺少状态和语义差异 | 不把“换最新版”作为解决方案 |
| [Fluent System Icons](https://github.com/microsoft/fluentui-system-icons) | 提供按尺寸绘制的 Regular/Filled，但默认轮廓较细 | 可作为克制的 Windows 方向，单换 Regular 不足以改善形体 |
| [Phosphor](https://github.com/phosphor-icons/core) | 双色与实心让语义对象更完整，轮廓操作图形也足够清楚 | 优先候选；语义对象 Duotone、选中 Fill、操作 Regular |

建议的全局规则：

1. 导航和主要对象从 20 px 起，选中用实心；工具栏 18–20 px，次要 inline 图标 16 px。平台窗口控件遵循窗口规范；点击区域与图形尺寸分别定义。
2. 双色仅用于语义对象，颜色使用已有 token；箭头、加号、关闭、复制保持清楚的操作图形。各档尺寸需要实际检查笔画与像素对齐。
3. Markdown、Excel、PDF、语言标志与服务商品牌保留正确身份、颜色、比例和许可。当前 Markdown 深色反转已有实现，不能在切换体系时丢失。
4. 通用 UI 采用同一个主图标体系，删除字符按钮和重复手绘。Core 与 DLC 继续使用现有 Host UI 边界；不添加 Lucide→新库的兼容映射包装层或第二主题。
5. DBFox 应用标记、任务栏小图及确无标准语义的专属能力才定制。不能把品牌都变成通用图标或字母占位。
6. 同步处理标题/内容对齐、主内容与 Dock 比例、正文阅读层级，保持来源与版本语义。

[Fluent 的图标规范](https://fluent2.microsoft.design/iconography)区分系统、应用与文件图标，
[字体规范](https://fluent2.microsoft.design/typography)也强调语义层级；14 px 本身是有效桌面字号，
需要评估它在整体比例里的职责。[Linear 的更新说明](https://linear.app/now/behind-the-latest-design-refresh)
同样把主内容和辅助导航的视觉权重作为重点。这些来源支持按角色设计，而非追求某个库的流行度。

## 来源、兼容与验证边界

- Fluent 图形固定在 `e15fc0de25fab983e3e42bac8798be69a85c23bf`，Phosphor Core 固定在 `2b75f3ad12b420c9504ef05df8d2564a28f8500e`。85 份候选 SVG 均有来源 URL 和 SHA-256，许可原文随对照稿保存；两者为 MIT，现有 Lucide 为 ISC。
- 已核对 [Phosphor React IconBase](https://github.com/phosphor-icons/react/blob/master/src/lib/IconBase.tsx) 和 package.json：通过原生 SVG 属性表达尺寸、颜色、镜像，peer 支持 React ≥16.8，当前源码声明 2.1.10。该核对不等于已选定 npm 包版本；Core SVG 对照与 React 包不能未经核对当作同版资产。
- 正式集成需要检查按图标/权重导入、bundle、CSP、类型、深浅色、高对比度与平台窗口行为，避免为 105 个图标引入整库多权重开销。目前没有新增依赖、兼容层或迁移债务。
- 浏览器已核对候选的尺寸切换、深浅色、右侧 Dock 方向，以及 61 份可直接渲染的本地资产加载；ICO/ICNS 与 sprite 单列，不伪装为浏览器图形验收。
- 本轮没有修改产品源代码，因此没有重复运行产品回归；前轮 721 项测试不能被用作新图标方案的集成证据。

本地证据保存在忽略目录 `desktop/output/playwright/icon-review-20261107/`，不随仓库分发：
浅色对照 `compare-light.png`、深色对照 `compare-dark.png`、资产预览 `all-local-artwork.png`
和可切换尺寸的完整对照稿 `index.html`。
