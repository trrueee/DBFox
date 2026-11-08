# 三栏工作区统一设计验证

> 文档类型：开发与验证记录
>
> 状态：当前
>
> 最后核验：2026-11-03
>
> 适用范围：文件夹项目、对话引用与输入框、通用 Dock、Workspace / Data 前端

## 交付行为

左侧只展示文件夹项目与对话，项目右键和更多菜单在右侧打开能力工作台。消息、输入框、成果与引用使用共享图标、卡片和操作语义。附件添加保留按钮忙碌状态及发送保护，删除“正在添加文件…”文字，处理期间仍可输入。

Workspace 在 Dock 内组合 lazy 文件树与只读代码/Markdown；Markdown 默认渲染，支持源码和分栏。Data 在 Dock 内组合数据库树、表结构、数据样例与内嵌连接表单。视图支持预览替换、固定、全屏和折叠，文件/表可加入对话，引用按精确身份返回对应视图。

浅色中性表面已统一调浅：默认侧栏 `#F7F8FA`、辅助面 `#FAFBFC`、工作区白色；同步调整悬停、按下、分隔线、Tab 分组及 neutral/warm 预设。字体颜色保持原值，默认主/次/辅助文字分别为 `#1B202A` / `#47505E` / `#5F6875`。树只在键盘焦点实际位于内部时显示焦点环，离开后不残留。

同名文件夹允许建立不同项目；canonical folder 的 opaque 创建 key 防止重复项目。Alembic `f8a9b0c1d2ee` 放开 Project name 唯一约束，保留既有项目/会话身份；降级遇到同名记录会明确拒绝，要求先改名。

## 复用与边界

沿用现有 Radix、shadcn Sidebar、Zag Tree、TanStack Virtual、Lucide、Markdown sanitize、owner operations、凭据存储及 SQL 执行链。新增官方 `@codemirror/language-data@6.5.2`（MIT），与现有 CodeMirror/Lezer 组合，Host 查看器和语言包按需加载。未引入 Monaco、手写 parser、资源镜像 Store 或跨 DLC 私有访问。决策与当前合同见 [前端架构](../architecture/frontend.md#31-设计系统与复用决策)。

文件浏览沿用 Workspace 的有界 UTF-8 读取。续读按 Unicode code point 计数，与 Python operation offset 一致；内容 SHA 改变时拒绝拼接。二进制、非 UTF-8、超大文件仍显示 owner 的明确错误；Excel 附件沿用 Data workbook viewer，本次未实现任意二进制文件预览或代码编辑保存。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| `cd desktop; npm test -- --maxWorkers=1` | 全量回归 110 文件、664 项通过 |
| Workspace / Data fixture、Tree、master UI 目标回归 | 4 文件、19 项通过，包含新增 Unicode 续读与精确引用用例 |
| `npm run typecheck:test` | 通过 |
| `npm run lint` | 通过，0 errors、12 warnings；保留 Fast Refresh 和既有 effect 提示 |
| `npm run test:electron` | 11 文件、33 项通过 |
| `npm run build` | 通过，生产 Token 与 bundle 预算检查通过；初始入口 raw 630,999 B / gzip 189,744 B |
| Project API + folder migration | 9 项通过，覆盖重开、冲突、并发创建、同名与保留会话 |
| `test_migrations.py` | 40 项通过；3 条既有 sqlite datetime 弃用提示 |
| Engineering contracts（排除下述既有文档状态用例） | 44 项通过 |
| Node dependency governance | 1039 个锁定组件通过；新增条目使用官方 npm registry 与 integrity |
| 变更 Python 文件 pyflakes | 通过 |
| Playwright 实际组件交互与视觉检查 | 17 项流程检查 + 2 项键盘焦点检查通过 |

全量前端回归后补充了 Unicode 分块续读用例，相关目标回归、测试类型检查与最终生产构建均重新通过。

浏览器验收挂载真实 Sidebar、AgentTimeline、UnifiedComposer、WorkspaceDock、Workspace 与 Data 前端贡献，仅在既有 operation 边界注入示例数据。覆盖 Markdown 三种模式、实际 Python grammar 高亮、嵌套目录恢复、预览固定、文件/表加入对话、数据库导航/样例/内嵌配置、项目菜单、1100px 窗口、窄 Dock 分栏和深色主题；另验证键盘焦点可见且离开树后清除。未连接或修改真实用户数据库，未运行真实模型任务。

截图保存在本地忽略的 `desktop/output/playwright/`：`unified-files.png`、`unified-database.png`、`unified-connection.png`、`unified-narrow.png`、`unified-dark.png`，均为实际组件与示例数据。

## 既有检查问题

当时的完整 engineering contracts 因附件第四阶段实施记录在非 archive 目录使用“历史”状态而失败。2026-11-04 提交前已将该记录移入[历史归档](../archive/reviews/conversation-attachments-implementation.md)，同步修复引用，并补齐工作区界面优化记录的共享页头；历史测试结果保持原样。

当前工作区存在大量先前改动；本次未回退、提交或发布它们。临时浏览器、Vite 验收服务及临时验收入口已关闭/清理，截图保留供核对。

## 2026-11-03 图标与输入操作

文件身份采用微软官方 Fluent `fabric-cdn-prod_20261014.001` 的 16/20px 文件图标；Markdown 使用现有 Simple Icons 标准标志，常见代码语言使用固定版本的 VS Code Icons 原始素材。40 个本地 SVG 的来源、许可说明和 SHA-256 随安装包保存，全部校验通过；没有新增 npm 依赖、远程图标请求或自绘品牌标志。CSV 使用中性表格符号，文件夹/数据表语义不会因名称带扩展名而变成文件标志。

添加按钮为无常驻底色、边框和阴影的加号，发送/停止共用圆形主按钮；标准密度为 40px，图标 20px，停止方块为 14px。保留上传期间输入、IME、Enter/Shift+Enter、禁用、忙碌、停止与键盘焦点反馈。数据库、音乐、故事中的字符按钮改用 Host 提供的 Lucide SVG；Dock 更多标签菜单显示对应图标，固定按钮补充操作提示。

| 验证 | 结果 |
| --- | --- |
| 前端完整回归 | 111 个文件、669 项通过；最终输入框和 CSV 调整后，6 个目标文件、22 项重新通过 |
| 测试类型检查、lint、生产构建 | 通过；lint 0 errors、20 warnings；入口 raw 633,268 B / gzip 190,660 B，Token 与 bundle 预算检查通过 |
| 浏览器实际组件 | 8 项检查通过：本地图标、圆形按钮、Markdown 源码切换、固定标签、深色 Markdown 标志、窄 Dock 收起、无页面横向溢出、加号键盘焦点 |
| System DLC bootstrap | 7 项通过 |
| Frozen Sidecar smoke | 健康、鉴权、旧 Token 拒绝、只读查询、耐久结果、重启恢复、隔离 Worker 与扩展生命周期通过 |
| Packaged Electron smoke | 五个系统 DLC 的脚本、样式和注册均加载，未激活资源访问仍为 403 |
| 现有安装升级副本 | 从本机旧扩展注册表升级成功，扩展拥有的数据文件哈希保持一致 |
| 实际桌面配置 | 原项目与会话保留；从系统凭据库恢复先前成功使用的 DeepSeek 配置，获取服务端模型列表并验证连接可用，未记录密钥内容 |

安装验证暴露了既有 System DLC 同版本不同内容的冲突。沿用不可变包合同，递增有变化的四个扩展：Data `2.2.9`、Workspace `3.0.1`、Music `0.3.2`、Story `0.2.1`；未变化的 Visualization 保持 `1.0.0` 和原 digest。没有删除旧注册表、扩展版本或资源数据，也没有放宽签名、digest 或启动检查。

本轮截图仍放在本地忽略的 `desktop/output/playwright/`：`icons-modern-light.png`、`icons-modern-dark.png`、`icons-modern-narrow.png`、`icons-modern-composer.png` 是生产组件配示例数据；`dbfox-installed-model-ready.jpg` 是实际安装后的连接成功界面，`dbfox-installed-ready.jpg` 是最终安装后的真实工作区。演示输入已清除，没有提交 Agent 任务。测试日志和安装包 SHA-256、安装资源比对证据保存在同目录；重装后再次确认 DeepSeek 服务、模型选择及模型列表凭据仍有效。本地构建版本为 1.0.4，未作为公开 Release 发布。

## 2026-11-03 顶部与工作区外壳

按实际 Codex 和 DBFox 窗口对照，删除独立灰色品牌行：导航从顶部开始，品牌只出现在侧栏首行；工作区顶部沿用同色表面，以 48px 首行容纳当前对话标题及窗口控制。独立 ConversationHeader、失效的标题/操作 CSS 与对应滚动状态已删除。主题选择仍在外观设置中，系统字体优先 Segoe UI Variable Text，导航去掉常驻树线和底部分隔线，使用统一行高与中性选中态。输入框焦点改为中性边框和轻阴影，加号、圆形发送按钮及键盘焦点保持原有交互。

复用当前 Electron IPC、Lucide、Sidebar、Prompt Kit 和 resizable panels；没有新增依赖、窗口桥接或标题状态副本。Dock 全屏对齐共享 chrome 高度，并改为 `height: auto`，消除原 100% 高度与上下 inset 冲突导致的底部裁切。没有修改 Backend、SDK、系统 DLC 内容或版本。

| 验证 | 结果 |
| --- | --- |
| Shell、原生窗口按钮、Sidebar、Composer、Conversation、Dock 目标回归 | 9 文件、59 项通过；覆盖最大化状态投影、最小化/关闭及按钮双击不触发标题栏最大化 |
| 测试类型检查 / lint | 通过；lint 0 errors、19 个既有 warnings |
| 生产构建与 Token / bundle 门禁 | 通过；入口 raw 633,374 B / gzip 190,702 B |
| 浏览器实际 App 与示例数据 | 首行从 y=0 开始且同高 48px；当前对话标题只出现一次；收起/展开导航保留输入草稿；加号键盘焦点可见；深色、reduced-motion、960px 窗口无横向溢出；Dock 全屏 y=48、底部不超出窗口，系统控制按钮未被覆盖 |
| 实际桌面 | 本机新版窗口最大化/还原正常；检查了首页、项目菜单、已有对话、数据库 Dock 与外观页，没有发送新任务或修改连接 |

本地构建仍为 1.0.4。首次打包遇到 Windows 对解压临时目录的 rename 占用，后续使用 electron-builder 已有的 `electronDist` 选项复用本机同版本 43.4.1 运行时，保留原 fuses、ASAR integrity 和 Sidecar 校验；没有修改构建依赖或绕过发布门禁。SQLite 在线备份完整性为 ok，备份放在用户目录 `DBFox-ReinstallBackup/20261103-chrome`。安装和资源一致性证据保存在本地忽略的 `desktop/output/playwright/chrome-install-proof.json`。

截图 `chrome-home-preview.png`、`chrome-dark-preview.png`、`chrome-narrow-preview.png`、`chrome-dock-fullscreen-preview.png` 是生产 App 与示例数据；`chrome-installed-ready.jpg` 为实际安装窗口。项目菜单、数据库、对话与外观检查图另存为 `chrome-review-*.jpg`。视觉评估中发现的重复新任务/主页入口、数据库三层标题、过长对话标题及设置页密度问题仅作为后续设计建议，本轮没有扩展修改这些功能。
