# 对话信息流实施与验证

> 文档类型：实施与质量记录
>
> 状态：当前
>
> 最后核验：2026-11-20

## 基线与范围

基于 main `d7f45a8b` 的已有未提交工作区完成本轮改动。既有 Computer、Local Execution、DLC 及其他功能修改均保留；本记录只证明对话、输入回执和 Evidence/Dock 交互的实施情况。源码的分批提交与推送于 2026-11-21 单独整理，已安装客户端未重装。

## 复用与设计决定

- 复用唯一 RunLoop、SessionInput、事件、快照、revision、Artifact/Representation 和工作台导航。输入采用状态原来已存在，只补齐公开可空投影；没有新增事实表、事件种类或任务状态机。
- 复用 ReactMarkdown/remark/rehype-sanitize、Radix Tooltip、现有文件图标与设计 token。没有新增依赖或另一套材质系统。稳定的 Markdown renderer 以局部 React Context 传入当次回调，解决真实重渲染失焦；该 Context 不存储领域事实。
- 用通用 ArtifactSources 替换 DataReferencePanel/dataReferences，移除仅识别 DataFrame 的旧列表和多余模型。成果已在正文或成果区展示后，不重复放进“已保存结果”。
- SDK artifact target 只向后兼容增加可选 evidenceId；标签仍只保存身份。点击来源与显式引用到下一轮输入分别处理。
- 调研基础采用项目已有的 Radix、remark 和 TanStack 方案，以及上一阶段核对的 Apple progress indicators、VS Code 运行中消息交互与 TanStack chat anchoring 文档；本期没有引入其他 Agent 框架或渲染协议。

## 已完成

1. 区分公开进展与最终文档；连续调用默认收起，稳定分组 key，保留真实参数和输出。
2. 单处待办区承载正式审批/问题，正文保留跳转；停止独立可见，停止确认与请求失败分别反馈，草稿保留。
3. 输入 admitted/promoted/consumed/cancelled 沿用原事务投影到同一用户 Item。补充已接收与已采用有不同回执，回滚和重放复用现有机制。
4. 每处正文引用保留 Evidence ID；同一文件多处依据分别打开。原始 Markdown 次序与 citation_index 对齐，代码示例、emoji、实体和转义字符不应将引用错配。未闭合流式标记隐藏，未知来源不能触发查证动作。
5. Dock 展示 canonical 依据和来源，支持显式引用到输入框与返回原引用焦点；查证不暗改下轮上下文。
6. 保留阅读位置与“回到最新”，观察正文及视口尺寸。Markdown 小表按宽度排布，移除 560px 最小宽度造成的横向滚动。
7. Prompt 4.3 指导按请求组织有依据的答案和实际验证，不强制固定报告模板。

## 自动化验证

| 验证 | 结果 |
| --- | --- |
| 前端完整串行测试 `npm test -- --maxWorkers=1` | 124 文件、787 项通过 |
| Agent Core 确定性回归 | 380 通过，2 个外部场景标记排除 |
| Prompt / Conversation API / Agent architecture | 59 通过 |
| 新增焦点、停止失败和 Evidence Dock 定点测试 | 25 通过 |
| TypeScript 测试类型检查 | 通过 |
| ESLint / token 与图标合同 | 通过，工作区保留原有 20 条 warning |
| 六个修改的 Python 源文件 pyflakes / mypy | 通过 |
| 生产 build、Token 扫描、bundle 预算 | 通过 |
| OpenAPI client | 使用正式 generate:api 生成，未手改生成文件 |
| 工程合同 | 42 通过，3 项既存文档治理失败，见下文 |

关键回归入口包括 `test_session_repository.py`、`test_conversation_projection.py`、`test_event_contracts.py`，前端的 UnifiedComposer、AgentTimeline、MessageList、ConversationWorkspace、MarkdownContent、ArtifactSources、ArtifactEvidenceDock 与 Artifact navigation 测试。

最后一次并行构建曾遇到 Windows 对 workbook vendor 文件的映射占用。测试全部退出后，独立重跑完整 build 通过；未修改或跳过 vendor、Token 或预算门禁。后续本地验证应将读写这些共享输出的测试与构建顺序执行。

当轮工程合同的三项失败来自既存文档治理问题：评审记录缺少统一页眉、使用本机绝对路径，以及 HTML/JPEG 位于只接受规范文档文件的目录。2026-11-21 提交前已补齐页眉、改为仓库相对链接，将可运行的静态原型移至 `desktop/prototypes/`，预览图片无损转换为 `docs/images/` 下的 PNG。工程合同与迁移合同合跑 85 项通过，未放宽文档门禁。首次复核遇到旧系统临时目录权限错误，改用仓库内独立 pytest 临时目录后完成。

## 实际界面验收

在 Windows 上启动隔离的真实 FastAPI、SQLite 与 Vite/React 工作台，使用明确标为“固定示例”的消息和 Markdown Artifact。不读取用户业务数据，不调用付费或本地模型，不执行开发任务；这轮实机结果证明交互和读取路径，不证明模型任务完成率。

- 1280×800：正文短来源链接、进展/回答层级、来源说明和 Markdown Dock 正常呈现；同一文档两处引用显示各自论断，复用同一预览标签。
- 输入草稿“继续核对剩余两项的交付时间”在查证、收回与宽度切换中保留。查看时不添加上下文；点击“引用到输入框”后出现正确的文件引用。
- 发送过程中新增引用的并发场景另由 ConversationWorkspace 回归覆盖：接纳完成后保留后来加入的上下文，引用 owner 只清理未改变的提交快照。
- “返回原文”实际恢复至被查看的 Evidence 链接，键盘聚焦摘要可见。实屏发现的 renderer 重挂载问题已修复并加回归。
- 960×780：详情使用现有紧凑布局，返回对话后输入框实测约 563px；示例表格横向溢出为 0。来源与输入草稿保持。
- 已保存桌面查证、窄窗口和完整阅读三张实际界面截图；预览进程和临时浏览器标签在验收后关闭。

## 明确限制

当前 Evidence 的通用 locator 关联整份 Artifact；本轮没有新增表格行、单元格、PDF 页或代码行的 owner 定位合同。Dock 如实说明细位置未记录。没有以答案中的字符偏移冒充源位置，也没有将 Evidence 的记录时间冒充源数据采集时间。

本轮未验证真实模型持续流式输出时的输入延迟/帧率、所有 DLC 视图的定位、Electron 安装包实机或 macOS/Linux。生产前端构建已通过，当前安装版未重装。
