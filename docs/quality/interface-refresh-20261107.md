# 2026-11-07 界面调研与信息层级重构

> 文档类型：UI 调研与验证记录
>
> 状态：当前
>
> 最后核验：2026-11-07

## 范围与结论

本轮处理设置页面、扩展管理、对话成果列表和 Dock 的辅助操作。采用现有 Fluent/DBFox tokens、
Radix/shadcn primitives、Lucide 与 ResourceIcon；没有新增依赖、网络字体、另一套主题或布局状态。
基线为 `7670e346` 的工作区，包含前轮功能修复；本记录只解释本轮 UI 改动，不表示全部页面已经重新设计。

实际 Electron 页面表明，扩展页的主要问题是默认展示运行指纹、所有版本、权限与多个重复按钮，
而不是缺少新的图标库。系统字体实际落在 Segoe UI Variable 与 Microsoft YaHei UI，继续使用现有字体栈。

## 调查与复用决策

先检查现有组件、[UI 开发规范](./ui-design-and-development.md)、
[组件采用报告](../ui/component-adoption-report.md)，以及 `c5e8208e` / `c992b58f` 的共享 token、quiet shell 历史。

| 来源 | 采用的设计依据 | 决策 |
| --- | --- | --- |
| [Linear 2026 设计更新](https://linear.app/now/behind-the-latest-design-refresh) | 导航降低视觉权重，稳定操作位置，用较少分隔表达信息层级 | 学习布局取舍，不复制产品资源 |
| [VS Code Views UX](https://code.visualstudio.com/api/ux-guidelines/views) | 清晰的视图职责、有限的主操作、已有标准图标 | 保留项目/对话与专业 Dock 的分工 |
| [shadcn Radix Item](https://ui.shadcn.com/docs/components/radix/item) | 将图标、名称、说明和操作组成简洁列表项 | 使用项目现有组件组合，无需引入另一个 UI 框架 |
| [Radix accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility) / [Tabs](https://www.radix-ui.com/primitives/docs/components/tabs) | 复用焦点、键盘与受控激活原语 | 保留既有 Radix，不重写 Tabs/Switch/Dialog 状态机 |
| [WAI-ARIA Tabs Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) | Tab/方向键导航、可关闭标签的 Delete 与关闭后焦点恢复 | 操作按钮移出 tablist，保持标准标签语义 |
| [shadcn MIT 许可](https://github.com/shadcn-ui/ui/blob/main/LICENSE.md) / [Lucide ISC 许可](https://lucide.dev/license) | 现有开源组件和图标具备明确来源 | 不新增素材下载或 vendoring |

`ui-ux-pro-max` 的通用建议只用于信息密度、渐进展开、键盘与动态效果核对；其 newsletter/OLED、
Lora/Raleway 推荐与本项目的桌面生产力场景不符，未采用。
[APG 的 aria-actions 示例](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/examples/tabs-actions/)
明确处于实验阶段，未用于生产。没有新增兼容层、mapper 或迁移债务。

## 已实施行为

- **设置基础排版**：统一页面标题、分区标题、正文、说明和字段标签的层级；内容宽度、分区留白与操作栏对齐共享调整。颜色继续使用现有浅/深色语义 token。
- **扩展列表**：默认显示名称、单行说明、发布者/版本数量、权威运行状态与启用开关。名称按钮展开版本、权限、完整指纹及卸载操作；支持按名称、说明、发布者、ID 本地搜索。
- **扩展生命周期**：开关直接反映 `desired_enabled`；徽标继续来自真实激活状态。待重启只保留页面级提示和重启入口；加载、失败、激活错误和安装前信任审查保留，不用折叠掩盖错误。
- **对话成果**：一个列表承载同轮成果。点击名称进入原 Dock，独立箭头展开 inline 预览；图表/图片/音频的默认展开策略保持。数据来源与完成证据继续使用原选择合同，不能按结果 ID 随意删去来源。
- **Dock**：方向键仍由 Radix 管理。关闭当前标签的按钮位于标签列表外；聚焦可关闭标签后可按 Delete。关闭后回到权威 Store 选定的活动标签；固定标签不响应关闭。
- **焦点与辅助功能**：取消扩展弹窗后返回发起操作的控件，发起行被移除时回到搜索/安装入口。成果、输入区及扩展详情增加正确的分组语义。强制颜色模式使用 OS 高亮色的真实 outline，避免 shadow 焦点环被系统移除后不可见。
- **动态与窄窗口**：展开箭头采用轻量状态动画，遵守 reduced-motion；扩展详情在容器变窄时自动改为两列/纵向版本操作。

旧 `.dlc-card` 布局、常驻诊断提示、每行重复重启按钮、旧成果 `<details>` 样式及标签内关闭按钮样式已删除，
不是在旧布局上叠加一套覆盖主题。Core/DLC 的权限、签名、指纹、资源身份与后端生命周期合同未改动。

## 验证证据

使用隔离的 Electron 开发客户端与真实已安装扩展、历史会话、Markdown 文件成果；没有替换用户已安装客户端。
证据位于本地忽略目录 `desktop/output/playwright/ui-refresh-20261107/`。

| 验证 | 结果 |
| --- | --- |
| 完整前端回归 `npm test -- --maxWorkers=1` | 最终工作区 115 个文件、721 项通过 |
| 扩展、Dock、Composer、成果与辅助功能聚焦回归 | 5 个文件、55 项通过，包含焦点返回、Delete、来源合同、展开/关闭与 Dock 打开互不干扰 |
| `npm run typecheck:test` | 通过 |
| `npm run lint` | 0 错误，23 项现有警告；设计 token 合同通过 |
| `npm run build` | 通过，生产 Token 检查及 bundle 预算通过；主入口约 651.7 kB，仍有既有 650 kB chunk 提示 |
| 实际页面 axe WCAG 2 A/AA + 2.1 A/AA | 动画结束后的浅/深色扩展详情、确认弹窗与工作区均为 0 violations、0 incomplete，见 `native-a11y-final.log` |
| 真实交互 | 搜索/无结果/清除；Enter 折叠；取消弹窗焦点恢复；成果预览开关；同一文件进入 Dock；方向键切换及 Delete 关闭/焦点恢复 |
| 响应与动态效果 | 960×780 无横向溢出；额外 720×780 压力检查也无横向溢出、详情两列；reduced-motion 下新增展开动画为 none |
| 强制颜色媒体模拟 | 键盘聚焦的开关/按钮存在 2 px OS 高亮 outline，截图保留 |

截图：

以下文件保存在本地忽略目录 `desktop/output/playwright/ui-refresh-20261107/`，不随仓库分发：

- 扩展页改前 `extensions-before.png` / 改后 `extensions-light-final.png`
- 外观设置 `appearance-light-final.png`
- 深色扩展详情 `extensions-dark-details-final.png`
- 对话成果与 Dock `workspace-light-final.png`
- 高对比度键盘焦点 `workspace-high-contrast-focus.png`

截图来自实际 Electron 页面；窗口尺寸与 forced-colors/reduced-motion 的部分检查使用 renderer viewport/media 模拟，
不等于修改 Windows 系统设置。未在本轮验证真实 NVDA/JAWS、Windows 系统 125%/150%/200% 缩放、macOS/Linux、
Frozen Sidecar 或安装包发布。没有新素材/依赖的供应链增量；余下风险主要为未覆盖页面的布局与辅助技术组合。
