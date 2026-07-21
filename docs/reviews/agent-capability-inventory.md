# DBFox Agent 能力资产清单

> **历史能力对照，不是当前文件清单。**
> 本文用于解释 v1.0.1、重写分支和 OpenCode 中哪些思想被保留、删除或重组。表格里的 `engine/agent_runtime`、`agent_core` 和 Graph 路径已被删除，目标形态已经落在 `engine/agent`、`engine/agent/repositories` 与 `engine/tools/runtime`。当前能力以 [当前系统架构](../architecture-design-document.md) 为准。

状态：历史架构评审基线
评审对象：`v1.0.1@53e3774`、当前工作树、OpenCode `dev`

关联文档：

- [架构链路评审](./agent-architecture-review.md)
- [产品与运行规范](../specs/agent.md)
- [技术与交互设计](../designs/agent.md)
- [实施任务](../plans/agent.md)

## 1. 判定规则

每项能力只允许进入以下结论之一：

- **直接继承**：语义与边界正确，可以迁入唯一生产链路；
- **抽取重组**：业务行为有价值，但状态所有权、依赖或协议边界错误；
- **明确淘汰**：会造成双状态源、不可恢复、前端猜测或框架耦合；
- **补齐缺口**：三个来源都没有满足 DBFox 目标，需要正式设计和实现。

“继承”表示保留被验证的语义和测试，不表示保留原文件、Graph 节点或旧 API。

## 2. 能力总表

| 能力 | v1.0.1 | 当前工作树 | OpenCode 参考 | 最终决定 | 最终归属与验证 |
|---|---|---|---|---|---|
| 数据分析 ReAct 行为 | Policy、Tool、Observe、Progress、Repair、Answer、Finalize 闭环较完整 | Graph 主体仍保留这些行为 | 显式 session loop，每 Turn 根据消息和工具结果继续 | **抽取重组** | `RunLoop` + `CompletionPolicy`；Golden Scenario 验证主动探索、修复和继续 |
| System Prompt | 数据分析师定位、主动深入、证据化回答完整 | 核心内容基本仍在，仅工具说明有小幅调整 | Agent prompt 与运行循环解耦 | **直接继承语义** | `AgentDefinition` + `PromptBundle`，版本/hash 与 prompt eval |
| 输入接纳 | 请求与 SSE 生成器耦合，断线会影响执行 | Run、用户/助手消息和首事件可原子创建 | 输入进入 session loop | **抽取重组** | `SessionInput` 原子接纳、幂等 ID、Session sequence；断调度故障测试 |
| Session 调度 | 请求线程直接驱动 | 单一全局 FIFO worker，所有会话串行 | 每 Session runner 串行，不同 Session 可并行 | **抽取重组** | `SessionCoordinator`；同 Session 单写、跨 Session 并行测试 |
| 多轮消息历史 | Graph thread 以 Session 为边界，能延续部分上下文 | Graph `thread_id=run_id` 且初始 `messages=[]` | 每轮重载持久消息 | **补齐缺口** | `ContextAssembler` 从持久消息、Run 摘要和工件构建 ContextSnapshot |
| Session Memory 写回 | 完成后有 memory projection，但 fail-open | memory coordinator 存在，生产执行链没有写回调用 | 消息/摘要持久化后下轮重载 | **抽取重组** | terminal transaction 写 Session memory delta；多轮 Golden Scenario |
| Context 压缩 | 旧 memory summary | 无正式 ContextEpoch | compaction 后继续使用持久化历史 | **补齐缺口** | `ContextEpoch`；压缩失败保留旧 Epoch，来源/version/hash 测试 |
| 工具声明 | 已有 DBFox 工具组和安全属性 | `BaseTool`、五类 Spec、结构化输入输出较强 | Registry 按 Agent/模型/provider 动态组装 | **直接继承并增强** | 统一 `ToolDefinition`/`ToolMaterialization`；快照/hash 与契约测试 |
| 工具物化 | Graph/工具组固定绑定 | 每个 Run 基本把安全工具组全部启用，模型调用时再建 LangChain tools | 每 Turn 动态物化 | **抽取重组** | 按 Agent、provider、datasource、permission、mode 物化，不改 RunLoop 即可加工具 |
| 工具执行 | 节点内同步执行 | `ToolRuntime` 有验证和 Observation，但 timeout/retry/idempotent 仅是声明 | tool part 有 pending/running/completed/error | **抽取重组** | leaf executor 真正执行 timeout/retry/output bound；故障注入 |
| Durable ToolInvocation | 无 | 工具副作用前没有事务 intent，崩溃边界不可判定 | 运行状态有持久 tool parts，但不等于 DB 事务结算 | **补齐缺口** | 副作用前写 intent，状态机、幂等 key、recovery policy、reconcile |
| Policy | 有 Policy gate、只读和修复语义 | ordered policy rules 和 generation fence 可用 | permission/tool filtering 可参考 | **直接继承语义** | `PermissionPolicy`，物化和 leaf 双检查；deny 优先 |
| Approval | 旧中断能力依赖 Graph | 原子消费、version 和 datasource generation 检查可靠 | permission request/response 可参考交互 | **抽取重组** | Durable Approval 绑定 ToolInvocation；拒绝产生 Observation 并继续 Agent |
| 普通用户提问 | 澄清通常终止本轮 | 无 durable pause；澄清后是新 Run | session prompt 支持继续消息，但不是 DBFox durable request | **补齐缺口** | `QuestionRequest` + `waiting_input` + 单次消费回答 |
| Provider 流式 | SSE 直接随 Graph 执行，低延迟但不可靠 | model chunk 被节点聚合；主要只有最终答案 delta 可见 | provider stream 直接驱动 message parts | **抽取重组** | `ModelAdapter` + `TurnStreamAssembler` + `LiveStreamHub` |
| 事件持久化 | fail-open event store | 业务状态、outbox event 和部分 projection 同事务，基础较好 | message parts 持久化 | **直接继承并改名** | `RuntimeEventLog`；Session sequence、cursor replay、commit notification |
| 公共事件映射 | ResponseBuilder/事件类型较分散 | `AgentRuntimeEventMapper` 是正确边界思想，但硬编码 Graph 节点、工具名和阶段 | parts/events 接近产品语义 | **抽取重组** | 唯一 `RuntimeEventProjector` 从领域事件穷尽映射，禁止 Graph 名称进入协议 |
| Answer 流式 | Answer node 可流式合成 | final answer delta 可用 | text/reasoning/tool parts 分频道 | **直接继承语义** | Answer channel 使用 turn/channel/offset；断线去重测试 |
| 最终回答组合 | `build_response` 能形成较完整产品响应 | 后端无唯一 Composer；前端和 evaluation 各自重建响应 | session message 是主要结果 | **抽取重组** | 后端 `ResponseComposer` 是唯一权威组合器 |
| 终态事务 | memory/event 多处 fail-open | Run terminal 与部分事件可靠，但 Answer/Evidence/Memory 没有统一事务闭环 | 不提供 DBFox 所需关系事务 | **补齐缺口** | answer/message/evidence/memory/run/session/events 原子提交 |
| Artifact 模型 | SQL、Result、Chart 和 Canvas 产品链较完整 | `Artifact` 类型、依赖、preview/result ref 基础强 | tool parts 可关联输出 | **直接继承并增强** | `ArtifactRepository`；不可变 ID、版本关系、provenance、payload ref |
| Artifact 生成 | Observe/Finalize 中生成 | observation 能产出 SQL/Safety/ResultView/Chart，但绑在 Graph state | 工具输出随 part 更新 | **抽取重组** | `ObservationProjector` 原子结算 Artifact candidates |
| Evidence | 旧 ResponseBuilder 也有 semantic ID 猜测 | Finalize 优先写 semantic ID，前端用 id/semantic_id 模糊匹配 | 无 DBFox 精确数据证据模型 | **明确淘汰并补齐** | Evidence 只能引用真实 artifact_id + locator；全量解析门槛 |
| 页面刷新恢复 | 旧 UI 闭环较完整，持久可靠性弱 | committed event replay 可恢复部分状态 | 持久 message parts 可恢复 | **抽取重组** | conversation snapshot + ordered events；视觉一致性测试 |
| Activity/过程展示 | 用户能看到较完整步骤 | 固定 phase、node/tool 推断和“调试细节”较重 | reasoning/tool/message parts 是自然活动源 | **抽取重组** | 领域 Activity Feed，动态出现，不展示隐藏 chain-of-thought |
| Artifact Dock 选择 | 工件工作区产品感更完整 | Workspace 和 Dock 各自用 latest/type 猜选中项 | 非核心参考 | **明确淘汰** | 后端持久 selection 与 selection suggestion；用户选择优先 |
| Composer 运行中输入 | 未形成 queue/steer 契约 | 只有 running/cancel，连续输入语义不完整 | 同 Session loop 可接收后续输入 | **补齐缺口** | `queue`、`steer`、`cancel_and_replace`、`respond` |
| 取消 | 连接断开会取消，边界错误 | cancel/version/generation fence 基础可靠 | session abort/runner state 可参考 | **直接继承并增强** | 持久取消、safe Turn boundary、迟到 worker fence |
| 重启恢复 | Graph checkpoint 能保留部分状态，但事件/副作用可靠性弱 | `running` Run 在启动恢复时统一改为 failed | runner state 主要进程内，不满足 DBFox durable 要求 | **补齐缺口** | 按 Turn/ToolInvocation 恢复；不可判定副作用进入 reconcile/unknown |
| Evaluation | 有工具轨迹、SQL、Artifact、Answer 检查 | 仍依赖旧 `AgentRunResponse`，没有完整纵向恢复场景 | repo 自身测试可参考 | **抽取重组** | Golden Scenario 按产品结果验收，不依赖 Graph 节点名 |
| 错误与凭据边界 | 有基础脱敏 | RequestContext、vault ref、safe error 边界可靠 | provider/tool error parts 可参考 | **直接继承** | 错误 code + diagnostic ref；secret serialization tests |

## 3. 必须保留的当前代码资产

以下内容不是“v2 全错”，应在新边界中保留语义和测试：

1. 原 `engine/agent_runtime/repository.py` 中 CAS、短事务、终态栅栏和事件同事务投影的设计语义；当前实现位于 `engine/agent/repositories/`；
2. Approval 的原子消费、版本前置条件和 datasource generation fence；
3. `engine/tools/runtime/base.py` 的 Tool Spec 体系与 Pydantic 输入/输出约束；
4. Policy 层“确定性规则优先于模型决定”的原则；当前入口为 `engine/policy/engine.py` 与 Agent PolicyGate；
5. 原 Artifact 类型、依赖和结果引用思想；当前入口为 `engine/agent/artifact.py` 与 `engine/agent/repositories/artifact.py`；
6. query cancellation、结果服务、凭据 vault reference 和安全日志；
7. `engine/agent/model/system_prompt.py` 的数据分析师核心行为；
8. 原独立最终答案合成的产品语义；当前唯一组合器为 `engine/agent/response.py`。

## 4. 必须删除的错误边界

在唯一生产链通过 Golden Scenario 后，删除而不是长期适配：

- LangGraph state、thread、checkpointer、Command、node route；
- Graph node/tool name 到产品阶段的硬编码 mapper；
- semantic ID、前缀或 latest/type 的 Artifact/Evidence 猜测；
- 前端和 evaluation 各自拼装 terminal response；
- 单一全局 worker；
- 固定 200ms SSE 主轮询；
- 没有生产调用者的 memory 写回空壳；
- `agent_core`、`agent_runtime`、Graph types 之间重复的 Agent 类型；
- 只声明但不执行 timeout/retry/idempotency 的工具契约；
- 把运行中重启统一结算为失败的“伪恢复”。

## 5. OpenCode 参考边界

参考的是显式运行思想，而不是复制它的产品和持久化假设：

- [session prompt loop](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/prompt.ts)
- [stream/message processor](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/processor.ts)
- [per-session run state](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/run-state.ts)
- [tool registry](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/tool/registry.ts)

采用显式循环、每轮重载、动态工具和 message parts；不采用仅进程内 runner 作为恢复依据，也不把 provider finish reason 当成 DBFox 的完成策略。
