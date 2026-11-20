# Agent 对话、引用与查证合同

> 文档类型：交互与投影合同
>
> 状态：当前
>
> 最后核验：2026-11-20
>
> 验证：[对话信息流实施与验证](../quality/agent-conversation-flow-verification.md)

## 信息组织

同一条时间线按既有 RunItem 的顺序呈现用户目标、公开进展、紧凑工作记录、必要介入与最终回答。`commentary` 使用较轻的字号与文字层级；最终回答保留正文、比较表、代码、图表和工件嵌入的表达能力。连续工具调用汇入默认折叠的工作记录；消息、计划、审批和问题构成分组边界。分组身份绑定第一条调用，不随调用数量改变，展开后不会因为后续调用到达而收回。

理解与研究、分析与判断、创作与交付、开发与修复、执行与操作、探索与协作是答案组织的参考，并非新增模式或任务状态机。Prompt 4.3 根据目标决定说明深度，要求结论、实际变更、已做验证和重要限制；简单回答仍应简洁。事实引用贴近对应论断，工具成功、批准、进程启动或打开视图不等于用户目标完成。

## 状态与所有权

| 内容 | 权威来源 | 前端职责 |
| --- | --- | --- |
| Run 与工具状态 | 原有 SQLite、RunItem、事件和快照 | 呈现进展、终态与部分完成，不推断成功 |
| 输入回执 | `AgentSessionInput.delivery_mode/status` | 区分接纳、排队、补充已提交与补充已采用 |
| 待批准或待答复 | 当前 Run 的 waiting Approval/Question Item | 输入区上方一处完整操作，正文保留上下文入口 |
| Evidence | 助手消息中的 canonical evidence | 每处引用保留 Evidence ID，不按 Artifact ID 合并 |
| 工件内容 | 既有 Artifact repository 与 owner Representation | Dock 标签只保存导航身份，按需读取 |
| 展开、阅读与焦点 | 组件与浏览器局部展示状态 | 不进入 Harness，不另建耐久事实源 |

`MessagePayload.delivery` 为可空的 `InputDeliveryReceipt { input_id, mode, status }`，直接投影已有 SessionInput。接纳时与用户消息一并保存；promote、consume、cancel、complete、fail 的原事务在同一条用户 RunItem 上递增 revision，并发布既有 `run.item.updated`。消息 ID、sequence、内容和引用不变。数据库快照与 SSE 复用同一个持久化 Item；回滚时输入状态、回执、Run 与事件一起回滚。没有新增表、事件种类、调度器或输入队列。

这一扩展解决实际的可观察性缺口：界面原先只能知道一条用户消息已经存在，无法知道中途补充是否进入下一次处理。Data 任务的排队输入和 Workspace 开发任务的中途补充均使用同一 Session 合同，无领域分支。历史消息缺少 delivery 时保持无回执展示；旧字段和入口不变。

## 介入与输入

- 运行时始终保留独立停止按钮；填写后续消息不会将停止替换成发送。添加文件使用无边框加号，发送使用圆形向上箭头。
- 停止请求提交期间保留可编辑草稿，等待真实 Run 状态；失败时说明请求未确认。刷新读取原会话，不自动重发取消、发送或业务写入。取消 mutation 的回执与错误绑定其原 Run 和 Conversation。
- queue、steer、cancel_and_replace 沿用原有 admission/idempotency 链。steer 的 admitted 回执仅表示补充已提交；只有 consumed 投影到达才显示已纳入后续处理。
- admission 返回后只清理仍与已提交快照一致的输入。后来编辑的草稿或后来添加的引用保留；引用集合由其 Workbench owner 检查，不由受控输入组件猜测。
- 当前最早的 waiting Approval/Question 在输入上方显示完整操作。正文入口可将焦点带到该区域；历史审批默认折叠。批准已收到与操作实际执行分别呈现。
- 连接提示独立于 Run 结算。断线显示当前可能不是最新、任务可能仍在运行；技术原因按需展开。

## 正文引用与 Dock

正文 `{{cite:artifact_id}}` 由已有 remark AST 插件转换为短来源链接。链接支持键盘激活及悬停/聚焦摘要；未知来源不产生可操作链接，流式未闭合标记不直接露出协议文本。代码示例保持代码内容。

同一工件的多处引用根据 canonical `citation_index` 及原始 Markdown 中的引用次序匹配各自 Evidence。使用 remark 的原始位置识别文本节点，不把 Python 的字符偏移当作 JavaScript UTF-16 偏移；代码示例、实体转义和 emoji 不应让后续链接指向其他论断。

点击引用打开既有 Artifact Dock 预览标签。SDK `WorkspaceDockTab` 的 artifact target 增加可选 `evidenceId`，`sessionId` 继续使用既有字段；两者只定位 canonical 消息中的依据，不保存 Evidence 内容副本。重复查看复用标签，已固定标签保留固定状态。没有 evidenceId 的旧标签行为不变。

Dock 展示对应论断与来源结果。当前通用 Evidence locator 为 artifact 级，明确说明没有更细位置；不生成猜测的行号、单元格、页码或“已定位”效果。源内容及一致性仍由 owner Representation 提供。若历史依据不在已加载的消息中，面板说明上下文暂不可用，仍可读取有权访问的来源成果。

查看来源不会调用 `selectArtifact`，也不会改下一轮输入的引用。只有显式“引用到输入框”才添加 WorkbenchReference；原草稿保留。“返回原文”收回 Dock 并按 Evidence ID 重新定位当前 DOM 链接，恢复键盘焦点。

## 材质、阅读与实现边界

复用系统字体、现有语义 token、Phosphor/文件类型图标、Radix Tooltip/菜单与已有 Workbench。正文宽度沿用阅读栏，进展与来源弱于正文，介入保留清楚的局部层级。发丝边界、轻阴影与短进入动效共同表达层次；减少动态效果与减少透明度沿用全局 token 和媒体设置。Markdown 小表格按可用宽度排布，不再被统一 560px 最小宽度撑开。

MessageList 仅在原本贴近底部时跟随。查证操作暂停跟随；读历史时保留“回到最新”入口。尺寸变化同时观察视口与正文，重算入口是否需要显示。长历史继续使用 TanStack Virtual 的稳定 Run key 与现有 end anchoring，不替换游标、revision 或恢复规则。

Markdown renderer 使用稳定的模块级组件，通过局部 React Context 接收当次渲染回调与元数据。该 Context 没有状态、缓存或持久化；其必要性在于 ReactMarkdown 的渲染器边界只传递链接/节点属性，避免父级回调变化导致来源链接及内嵌视图重新挂载、失焦。

删除仅识别 DataFrame 的旧 DataReferencePanel/dataReferences，统一由 ArtifactSources 展示 canonical Artifact。没有新增依赖、兼容映射链、owner 数据副本或第二套 Runtime。
