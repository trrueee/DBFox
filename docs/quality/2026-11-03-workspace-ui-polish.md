# 工作区界面优化

> 文档类型：开发与验证记录
>
> 状态：当前
>
> 最后核验：2026-11-03
>
> 适用范围：工作区导航、输入、引用、持久布局与桌面界面

## 采用范围

统一项目与对话导航、输入框上下文、短标题和重命名、引用/成果卡、数据库 Dock、工作区恢复、外观设置与局部加载/重试。保留已有浅色 Fluent Token、标准图标、无边框添加按钮、圆形发送按钮及融入工作区的窗口控件。

调查并复用了现有 PATCH conversation API、模型列表 API、Zustand persist、Zod、Radix 菜单/对话框、react-resizable-panels 的公开 imperative API，以及既有 ResourceIcon / ReferenceCard / ArtifactViewHost。没有增加依赖、另建领域 Store、复制 Artifact payload 或修改 Agent Kernel。

UI/UX skill 的 landing page 字体与配色建议不适合本机 CJK 工作区，未采用；排版、密度和交互沿用项目已有 Fluent 2 基线。图标使用已采用的 Lucide、标准文件类型与品牌资产。

## 状态和资源边界

- 保存 UI 导航身份与布局，排除输入内容、References、API Key、租约、消息、SQL、payload 与执行状态；未知字段在保存/恢复边界剥离。
- 重新打开工作区由资源原 owner 读取内容，不自动执行任务；无效存储与容量错误不阻止导航。
- 当前项目/对话/Tab 在保存数量达到上限时优先保留；各项目的临时新任务草稿保持隔离。
- Data 2.2.11 / Workspace 3.0.2 使用新版本签名包，避免复用已有版本的不可变 digest。

## 验证记录

生产组件预览使用独立 Vite 配置与虚构数据，只替换 API/Host 边界。截图保存在 `desktop/output/playwright/modern-*.png`。预览入口与配置在验证完成后移除，不进入安装包。

验证覆盖导航、模型选择、标题、局部错误、持久布局字段白名单、各项目草稿隔离、明暗主题、宽/窄 Dock 和外观预览。

- 前端完整回归：114 个文件 / 684 个测试通过。随后补充的历史引用短标签和树标签优化按影响范围重跑，引用/时间线/工作区 34 项及 Data/Markdown 12 项通过。
- `npm run typecheck:test`、`npm run build`、设计令牌契约通过；lint 无错误，保留 23 个既有/备份目录告警。
- Electron 单测 11 个文件 / 33 项通过；System DLC bootstrap、Workspace package 和 Data domain model 的 Python 回归共 29 项通过。
- 生产入口 raw 652,016 B / gzip 197,680 B，通过原有预算，未放宽限制。Dock 只由延迟加载的实际 registry 上报宽度建议，避免把专业 Renderer 提前装入启动入口。
- 浏览器实际交互确认数据库表默认 640px、拖动后记住 600px；1100px 窗口切换浏览器/详情，980px 窗口保留挂载并进入紧凑布局；模型菜单按需获取、选择后立即更新。
- 包装后的 Electron smoke 确认 5 个默认 System DLC 的脚本/样式全部为 200，非活动包拒绝访问（403）。

实机检查补齐：缺少元数据的历史引用使用标准文档图标与“数据来源”短标签，完整结论保留在提示中；有元数据时优先展示真实资源名。MySQL 同库表树省略重复的库名前缀，导航 target 仍保留完整 qualified locator。表结构在局部滚动区保持类型/约束单行。

重装前在线 SQLite 备份位于 `%LOCALAPPDATA%/DBFox-ReinstallBackup/20261103-modern-1032`，完整性检查通过，原有 3 个项目 / 30 个对话保留。最终安装哈希和实际截图记录在 `desktop/output/playwright/modern-install-proof.json`。
