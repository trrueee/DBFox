# Artifact、Visualization 与 Dock 重构证据

> 文档类型：质量与架构证据
>
> 状态：当前
>
> 最后核验：2026-08-28

## 结论

本轮已经把产品链路收敛为：

```text
Agent / DLC Tool
  → durable Artifact
  → optional Representation
  → DLC/Core View (inline | workspace)
  → Core-owned Dock Tab 或正文块
```

Core 不理解 SQL、DataFrame、图表或 Vega。Data DLC 保留 SQL 安全链、reference-only Result、显式
Snapshot 与 DataFrame Representation；独立 Visualization DLC 消费任何兼容 Representation。同一
Artifact ID 在正文和 Dock 中只产生不同 View，不复制事实。

## 验收证据

| 需求 | 当前权威实现与证据 |
| --- | --- |
| 正文 `text → Artifact → text` | `engine/agent/artifact_embed.py`、Completion/Terminalizer 校验、Markdown AST 与 `ArtifactViewHost`；伪造 ID、非独立块、重复和 fallback 测试 |
| 保持统一 Runtime | Artifact embed 仍通过 Message `content + artifact_refs` 与现有 RunItem/SSE；Core 无 Chart/Visualization RunItem 或工具名分支 |
| 通用 Artifact/Representation | `engine/representation.py`、DLC snapshot contribution 与三条通用 HTTP 路由；Provider 独占领域校验和读取 |
| SQL Backend 不丢失 | Result schema v2 只保存 SQL source identity、ResourceRef、generation、fingerprint 和摘要；页面读取返回 `live_reexecution`，Snapshot 才返回 `durable_snapshot` |
| Visualization 独立可复用 | `dbfox.visualization` 不导入 Data 私有模块；支持 metric/chart/table/text、多列布局、Vega-Lite、受限 Vega、字段/预算/表达式/交互校验和 PNG/SVG 导出 |
| 无外部数据来源 | 小型 `model_knowledge` / `user_provided` 输入原子物化为 supporting `authored_dataset`；Visualization schema v2 只保存 Artifact source binding 和 `derived_from` |
| View 与 Tab 分层 | DLC 注册 Artifact View；Dock Tab 只保存 `viewType + target identity + selectedViewId + scope`，canonical Artifact 内容仍在 Conversation/后端投影 |
| 正文与 Dock 联动 | inline 的“在工作区查看”打开同一 Artifact；Dock 可把 canonical Artifact identity 加入 Composer，不创建第二份对象 |
| 多上下文引用 | Composer 支持最多 12 个去重、可移除的 typed Workbench Reference；提交成功后清空，Backend 合并 attached Artifact 到受限上下文目录 |
| 成熟 UI 基线 | Fluent 2 字体/颜色 token、shadcn/Radix、TanStack Table/Virtual、react-resizable-panels 与 Vega 运行时；业务 CSS 不再保留 Fira/JetBrains 私有字体栈 |
| 错误与生命周期 | Representation 公开错误、AbortSignal、重试、空/加载/错误状态、Renderer/ErrorBoundary 与 Vega View/ResizeObserver 释放路径 |

## 调研与复用决定

- **采用**现有 Message/Markdown AST/Artifact View 链，不新增 `ResponseComposition`、第二套 Event 或图表 RunItem。
- **采用** Vega-Lite 6.4.3 作为默认声明语法、受限 Vega 6.4.0 作为高级语法、Vega Interpreter 2.3.2
  满足严格 CSP；版本固定、离线打包并携带 BSD-3-Clause license 文本。
- **采用** Host TanStack DataFrame View 处理完整表格；Visualization 的 table block 只承担有界叙事组合。
- **保留**固定右栏的 Radix Tabs + react-resizable-panels。只有真实多组拖拽需求及 Electron/CSP/键盘门禁通过后，
  才整体采用 Dockview/FlexLayout；不双写两个布局模型。
- **拒绝** Data DLC 与 Visualization DLC 强依赖、ECharts/Vega 双新建链、模型生成 JS/React/ECharts option、
  Dock 保存 payload，以及正文/Dock 两份 Artifact。

## 兼容与退出

没有新增长期 mapper、双写或 fallback 链。仅保留两条精确历史读取：Result schema v1 的 durable rows 和
`dbfox.data.chart` v1。它们不能被新 Tool 创建；产品确认不再需要读取对应历史 Artifact 后即可删除。
Visualization schema v1 inline rows 同样只读，所有新创建文档均为 schema v2。

## 本地验证（2026-08-28）

- Backend Core/Data/Visualization/Representation 聚焦回归：`102 passed`；后续边界回归 `66 passed`、`46 passed`。
- Visualization package 安全与交互合同：`19 passed`。
- Frontend inline/Dock/Composer/Visualization/CSP 聚焦回归：`91 passed`；后续相关回归 `35 passed`、`14 passed`。
- Electron Host：`32 passed`。
- Python `pyflakes` 通过；mypy 对 241 个相关源文件报告 `Success: no issues found`。
- Frontend ESLint 与设计令牌合同通过（仅保留 8 条 Fast Refresh 组织性 warning，无 error）。
- `npm run generate:api`、`npm run typecheck:test`、`npm run build`、生产 Token 与 bundle budget 门禁通过。
- `git diff --check` 通过。

未在本次聚焦验证中执行真实 LLM、真实外部数据库、安装包签名/公证或全平台 GUI 场景；这些仍由发布矩阵
负责，不能从上述本地证据推断为已验证。
