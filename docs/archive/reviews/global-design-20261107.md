# 2026-11-07 全局图标、比例、材质与动效实施

> 文档类型：界面实施与验证证据
>
> 状态：历史
>
> 最后核验：2026-11-07

用户确认在整个产品统一图标、空间比例、阴影、适量玻璃材质和动态反馈。
实施前的范围和候选对照见[图标与比例诊断](../../quality/icon-system-review-20261107.md)。

此阶段的视觉方向已由 [Apple HIG 工作台](../../quality/apple-hig-workbench-20261107.md) 替代。窗口、协议、状态与图标来源的修复证据仍保留；当前设计只以新规范和生产实现为准。

## 已落地的共享设计

- 功能图标：Core、Host UI 和 DLC 统一使用 Phosphor。对象默认 duotone，普通动作 regular，
  明确的选中/状态可用 fill。控制图标通常 20px，紧凑动作 16/18px，标题 22px；窗口控件沿用平台比例。
  删除 Lucide 与 Phosphor React runtime 依赖，不保留旧名称运行时映射。
- 标准身份：保留 Markdown、Excel/PDF、代码语言等正确文件图形；模型服务补齐 OpenAI、Zhipu、
  xAI、SiliconFlow、Hunyuan 的开源品牌标志。未知服务使用连接图形，移除微小字母方块。
  品牌插画、乐谱、波形、关系图与漫画页面属于品牌/领域内容，没有替换成通用功能图标。
- 比例：新默认 UI 15px、Agent 16px，数据和代码 14px。字号调整量和默认基线同时更新，
  已保存的合法数值保持原值。设置标题与内容共享 1120px 容器，首页内容最大 760px、标题 32px。
- Dock：初始请求宽度采用舞台 38% 与视图 preferredWidth 的较小者，手动宽度优先；
  对话至少 520px、Dock 至少 340px、分隔条 8px，不足 868px 时切换紧凑视图。
  分栏沿用 react-resizable-panels，不新建布局状态。冷启动文件标签直接订阅规范 Artifact，
  文件类型到达后正确更新图标；文件成果已有身份标题时，FileContent 可省略重复标题。
- 表面：固定工作区域使用实色；菜单、提示、通知和弹窗统一使用共享表面与 key/ambient 阴影。
  支持 backdrop-filter 且未要求减少透明度时，菜单为 86%、弹窗为 96% 表面混色，20px 轻微模糊。
  高对比度、forced colors、减少透明度使用实色。没有叠加整页玻璃或第二主题系统。
- 动效：120/180/220ms 共享时长用于浮层进入/退出、首页进入、导航折叠和发送按压。
  不动画化分栏宽度与流式文本；系统/应用减少动效约束所有 Core/DLC 动画。

## 调查与采用依据

采用了项目既有 Radix、shadcn、系统字体和 Fluent 角色语义，没有更换组件框架。
参考 [Fluent elevation](https://fluent2.microsoft.design/elevation)、
[Windows Acrylic](https://learn.microsoft.com/en-us/windows/apps/design/style/acrylic)、
[减少透明度媒体查询](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-transparency)
及原生 [SVG use](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/use)。
Fluent System Icons 的细线候选在实际对照中仍偏弱；Phosphor 的分角色重量更符合本次要求。

直接导入 `@phosphor-icons/react@2.1.10` 的生产实验得到入口 731,784 B raw / 215,288 B gzip，
超过仓库原有预算。因此选择其官方原始 SVG，在构建时合并为原生 symbol 资产，没有提高预算或
用额外分块掩盖体积。最终入口为 **645,843 B raw / 195,109 B gzip**，另有
**134,420 B（gzip 22,176 B）** 本地图形资产。

来源与维护：

| 资产/能力 | 事实源与约束 |
| --- | --- |
| Phosphor 100 个图形、300 个重量状态 | [官方仓库](https://github.com/phosphor-icons/core)，固定提交 `2b75f3ad12b420c9504ef05df8d2564a28f8500e`；`desktop/assets/phosphor/manifest.json` 保存来源和每个文件 SHA-256，原始路径未自行改画；MIT 声明随包 |
| 五个补充品牌标志 | [Lobe Icons](https://github.com/lobehub/lobe-icons)，`@lobehub/icons-static-svg@1.102.0`；`assets/lobe/manifest.json` 保存版本、来源和 hash，MIT 声明随包；其他品牌继续复用 Simple Icons |
| XML 构建解析 | 提升已有传递依赖 `@xmldom/xmldom@0.8.14` 为显式开发依赖，MIT，仅处理 hash 校验的本地 SVG，不进入 Renderer runtime |
| 生成和校验 | `npm run generate:icons` / `npm run check:icons`；predev/prebuild 生成，lint 检查陈旧产物、源 hash 与受限 SVG 结构 |

长期成本是固定素材与构建工具的维护；升级时审查原始资产差异、许可证、清单和实际渲染。
没有新增业务 mapper、镜像数据、双写、fallback 链或迁移兼容层。SDK 仅增补共享图标名称和
FileContent 的标题展示选项；字节读取与权限仍属于 DLC owner。

## 使用过程中修正的边界问题

1. `TitleBar` 在异步读取窗口状态之后才订阅，卸载可能早于订阅，导致 IPC 监听累积。
   改为同步订阅与清理；初始读取不能覆盖已到达的新事件。新增两个独立时序回归场景。
2. 收起 Dock 的 lazy fallback 原先把完整加载文案挤成竖排；现按真实开合状态使用紧凑占位。
3. Electron 会把 SVG `#symbol` 传给自定义协议。原 `parseAppUrl` 拒绝 fragment，造成生产协议下
   图形空白，而 Vite 预览正常。现在 fragment 只作客户端图形选择，不参与磁盘路径；固定来源、
   查询拒绝、目录包含性、大小上限和 CSP 不变。协议回归覆盖实际 SVG 响应。
4. 故事工作台内层 grid 的隐式列按内容最小尺寸撑到 488px，使约 447px 的 Dock 中表单被截断。
   显式使用 `minmax(0, 1fr)` 后，实际内容宽度与滚动宽度同为 422px。Scene、Visualization 的
   宽度规则改用既有容器边界，避免用整个窗口宽度判断窄 Dock。
5. 快捷键命令面板没有 DialogTrigger，关闭后焦点落到 body。使用 Radix 官方自动聚焦回调保存、
   恢复仍连接且可操作的原控件，移除争抢焦点的 autoFocus；条件挂载与常驻挂载分别覆盖。
   命令面板同时移除覆盖共享表面/阴影的旧样式，避免嵌套背景与模糊。

## 首轮验证结果

- 前端：116 个文件、**730 项通过**，串行运行；包括真实 DLC 源码 fixture、布局草稿保持、
  外观偏好、图标与窗口状态时序。早期失败的旧字号/旧图标合同和缺少 Host Icon 的 Game fixture
  已按新合同修正，之后完整重跑通过。
- Electron：12 个文件、**38 项通过**；包括图形生成产物和真实 appProtocol 合同。
- `npm run lint`：0 errors，25 个组件导出/React hook 等 warnings；`npm run typecheck:test` 通过。
- `npm run build`：通过 TypeScript、生产令牌和原 bundle 预算；未放宽 CSP 或预算。
- 真实 Electron 开发客户端：浅/深色、项目菜单、模型品牌选择、首页、设置、文件成果、源码/渲染
  切换和分栏操作；1440/1280/960/720px 无页面横向溢出。窄视图的隐藏对话通过原生 inert
  退出焦点范围，回到宽屏保留未发送草稿和文件模式。
- 隔离 QA runtime 中通过正常扩展开关和重启启用 Data、Story、Piano；检查连接表单、已有故事
  关系图与已有乐谱的只读视图。未发起新模型调用或数据库连接；检查后将可选扩展 desired state
  恢复为未启用并关闭客户端。Scene 等未逐一在真实业务数据中完成端到端验收，仍由源码与现有 fixture 覆盖。
- 命令面板在真实客户端中验证 Tab 焦点约束、Escape 关闭与恢复输入焦点，实际表面为 97% 混色，
  使用共享阴影；不是仅靠测试文件判断。
- 系统减少透明度模拟得到实色、无 blur；应用增强对比度同样实色；减少动效为 0ms 令牌，
  CSS 的可见动画周期归零。不是物理辅助技术或所有 Windows 缩放等级的认证。
- 使用实际 `registerAppProtocol`、原生产 CSP 和 scheme privileges，在独立 Electron 窗口下
  检查 **300/300 个原生 SVG 状态绘制成功**，303 个本地请求均为 200，无控制台错误。
  这验证本次图形的桌面协议边界，不冒充完整 Frozen Sidecar 发布包验收。

截图和机器输出位于忽略目录 `desktop/output/playwright/global-design-20261107/`，包括
`home-light.png`、`home-dark.png`、`settings-default.png`、`project-menu-light.png`、
`provider-marks.png`、`workspace-final-light.png`、`workspace-720.png`、`story-dock.png`、
`music-dock.png`、`command-dialog.png`、`protocol-icons.png`。
此目录是本机证据，不提交截图、运行数据库、日志或临时脚本。

本次使用隔离 QA runtime，未替换用户已安装的客户端，也未修改其凭据。

## 后续精简与统一材质

按用户进一步反馈，删除首页“最近工作”、副标题、输入区长占位文字，以及引用卡中重复的泛化类型说明。
历史仍在左侧和命令搜索中；模型、发送方式、审批和错误保留能影响决策的信息。
添加、发送、返回对话、加入上下文等通用操作用标准图标与悬停提示表达，保留可访问名称。
输入区文件引用改为单行，保留名称、类型图标、打开和移除操作。

材质依据 [Fluent Material](https://fluent2.microsoft.design/material) 和
[Windows Acrylic](https://learn.microsoft.com/en-us/windows/apps/design/style/acrylic)：
长期并列内容区使用稳定底色，临时浮层使用轻透表面，避免相邻大面板反复模糊。
这里复用现有 CSS 材质令牌与 Radix 浮层，没有引入原生 Mica、着色器、图片纹理或动效依赖。
导航、设置、Dock 标签、文件模式与资源树共享中性选中表面、8px 行圆角、细边和高光。
删除左侧蓝色竖边与 Dock 蓝色下划线；当前项目用位置语义和字重表达，避免与当前对话同时出现两个选中块。
系统强制颜色仍有明确的系统色选中轮廓和键盘焦点。

动效继续使用共享 120/180/220ms 与既有缓动，浮层按开合方向进入/退出，页面进入只移动 4px；
不对分栏宽度、输入内容或流式文本做装饰性动画。
参考 [Fluent Motion](https://fluent2.microsoft.design/motion) 的反馈与空间连续性原则，
渐变由原生 CSS 绘制，不生成背景图片。高对比度和减少透明度关闭渐变与模糊，减少动效关闭持续旋转。

工具记录默认折叠，参数与结果仅在展开后挂载；手动展开不随运行结束自动收回。
右栏仍沿用已有工作台开合状态，未创建第二套抽屉状态；紧凑视图新增返回箭头并恢复输入焦点。
保持原组件树的做法用于保留编辑状态，未把文件编辑器重新挂到另一个 portal。
对话阅读栏统一为最大 820px；窄输入区缩小内部留白。

## 实机发现并修正的状态与图标合同

实机打开旧线程时发现，前端声明了 `run_status`，但既有摘要接口没有返回，未打开的线程被显示为未运行。
修复在既有列表读投影完成：一次 SQL 返回真实状态与耐久会话 cursor；未结束 Run 优先，排队输入不能隐藏先前的审批。
列表与已加载快照/SSE 按同一个 cursor 比较新旧，不用较旧内存覆盖较新服务端事实。
复用已有 Session event sequence、终态集合与
[SQLAlchemy 相关标量子查询](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#scalar-and-correlated-subqueries)，
不用逐线程读取完整快照，也不加载 Run 的请求/结果正文。OpenAPI 客户端已用正式命令重新生成。
没有数据库迁移、第二套运行状态、后台轮询或 Kernel 状态机变更；当前窗口恢复焦点和 Engine generation 变化复用列表读取。
完成标记使用中性的“本轮已结束”，不把有界部分结果解释为整个任务成功。

把真实 Markdown 成果加入输入区时又发现，图标退化成通用成果标志。
输入区现在订阅规范 Artifact 的真实类型，复用与 Dock 相同的类型选择规则，保持显示信息与资源身份分离。
未加载的未知成果仍用通用成果图标，不把文件形状的名称误判为其业务类型。

## 后续验证结果

- 完整前端串行回归：117 个文件、**737 项通过**；更新旧文案断言后完整重跑。
- 后端会话读投影与 HTTP 合同：**17 项通过**；包含无 Run、待审批后有排队、已结束、删除过滤、cursor 与单条 SQL 的真实 SQLite 场景。
- Lint 0 errors、25 warnings；测试类型检查通过；修改的两个 Python 源文件通过 Pyflakes 与 Mypy。
- 最终 `npm run build` 通过 TypeScript、生产令牌与原 bundle 预算；入口 **647,893 B raw / 195,894 B gzip**。这是本机生产构建，未冒充已安装版或完整 Frozen Sidecar 发布包。
- 真实 Electron 客户端中，历史线程显示 completed/failed，7 条真实工具记录默认折叠。
  审批、待输入与排队状态另外由源码与确定性回归覆盖，本轮没有额外发起模型调用。
- 1440px 实测：界面 15px、输入/正文 16px、首页标题 32px、添加图标 20px、圆形发送按钮 40px。
  CDP 字体检查确认实际中文使用 Microsoft YaHei UI，拉丁字符使用 Segoe UI Variable。
- 720px 实测：输入框扣除内边距后的有效宽度 **323px**；返回对话保留未发送草稿、引用并恢复焦点；无页面横向溢出。
- 真实 Markdown 成果加入输入区后使用标准 Markdown 图标，仅显示一行文件名。
- 浅/深色菜单实测为 86% 表面混色与 20px 模糊；减少透明度稳定后为实色、无模糊、无渐变；减少动效与强制颜色选中轮廓已检查。
- 隔离客户端已正常关闭，未替换已安装版，未修改用户凭据。

本轮截图仍在忽略目录 `desktop/output/playwright/global-design-20261107/`，以
`followup-material-` 开头，包含首页浅/深色、工作区浅/深色、菜单浅/深色、设置、720px Dock 和输入区。
完整前端日志为 `followup-tests-verified.log`，后端日志为 `followup-backend.log`。
