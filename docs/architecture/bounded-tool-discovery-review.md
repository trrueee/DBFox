# 有界工具发现：独立审议交接

> 文档类型：架构审查
>
> 状态：草案
>
> 最后核验：2026-09-06
>
> 适用范围：Runtime 工具物化容量、原生控制函数、Turn 冻结与恢复；候选未实现、未验证、未正式批准

## 当前裁决

接受“问题需要通用 Runtime 解决”的证据；暂不批准根草案直接进入实现。根草案路径为 `D:/Project/DBFox/docs/architecture/bounded-tool-discovery.md`。本轮不会修改该草案；本文是独立意见，用户要求停止开发后保存为交接。

建议继续比较一个 Runtime 原生函数提供目录与显式选择、下一 Turn 加载完整 schema 的最小方案。无需另建调度器、MCP 服务、向量检索库、registry 镜像数据库、DLC facade 或 SDK 服务定位器。控制预算/进展及持久兼容尚未验证，不能宣称候选已成立。

## 已核对的生产链

| 边界 | 当前事实 | 对设计的约束 |
| --- | --- | --- |
| `materialization.py:75` | 按可见性、group、execution mode、资源 kind 过滤；已有 `allowed_names` | 预算选择发生在这些过滤之后，不能旁路它们 |
| `materialization.py:49,59` | `provider_schemas` 输出工具 schema，`require` 只允许当前 tools 集合 | deferred 工具不能因为目录中存在就可调用 |
| `materialization.py:196` | 合同 hash 含 typed 输入/输出、policy、execution、semantics、presentation；记录 owner/digest | wire name 相同不能替代合同和包身份核对 |
| `loop.py:797` | 每轮重建上下文、资源 kind、工具与 guidance，然后保存 Turn | 下一轮选择可重新投影，不改已冻结 Turn |
| `repositories/session.py:492` | Turn 保存 materialization JSON/hash、context 和 prompt 身份 | 复用现有耐久记录，无需新选择表 |
| `repositories/tool.py:67` | 请求检查传入 hash 与持久 Turn hash | 新字段必须参与明确的 hash 方案，不能只比较一个未经重算的字符串就声称防篡改 |
| `tool_dispatcher.py:245,289` | 先拒绝本轮不可用工具，再独立做输入、Artifact、资源、policy 等检查 | 目录和选择不授予 ResourceRef 或 Artifact 可用性 |
| `tool_dispatcher.py:405` | ControlCommand 在原 Invocation 事务内执行并结算 Observation | 可读取自己的冻结 Turn 和保存选择，不需要扩 ControlCommandContext |
| `materialization.py:149` | reconcile 允许原有有限合同差异，但严格限定原包/owner 和显式只读恢复 | 新加载选择不能改变旧 Invocation 的 reconcile 或自动重放规则 |
| `prompt.py:79` | 整批淘汰旧 Responses Turn，必要时用证据账本 | 不把新目录页展开到 system，不拆散 function call/output 配对 |

以上路径相对根仓库 `engine/tools/` 或 `engine/agent/`；完整路径见[审计报告](../quality/creative-platform-pattern-audit.md)。调查使用根 CodeGraph 当前磁盘源码，联合基线为 `36224475`。

## 官方方案与候选比较

[OpenAI Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)支持延迟加载，并有 client 模式：模型返回 `tool_search_call`，应用返回匹配 call ID 的 `tool_search_output`，随后工具可以正常调用。这验证了按需完整 schema 的方法可行。直接采用该协议仍要扩展 DBFox Provider 事件、持久 history 与恢复合同；本次没有证明它比既有原生 function/ControlCommand 更小，也不能把专用事件伪装成普通工具输出。该来源仅用于设计比较，不表示已集成。

[Pydantic 命名类型](https://pydantic.dev/docs/validation/latest/concepts/types/#named-type-aliases)可以把重复类型放入 `$defs`。它是 owner 内合理建模优化，但根草案记录的实验仍无法装入默认总预算；本轮没有重跑或保留该实验。禁止删约束、将 typed 操作改成自由 JSON 或手写第二套 schema 来节约 token。

静态 AgentDefinition group 适合真正受限的 Agent；按用户话语硬选 owner 会把领域知识带进 Runtime，也无法支持同 Run 跨能力切换。仅缩短 context/history 无法消除所有 schema 的刚性成本。候选应保持 provider-neutral 的普通原生函数路径，但必须诚实记录多出来的目录/选择轮次与成本。

## 最小合同草图：不是已冻结 API

可暂用 `tool_catalog` 作为讨论名称，注册归属 `dbfox.core`，只提供两种严格 typed 操作：

```text
query(query_text, cursor | null)
select(catalog_hash, selections[{wire_name, contract_hash, owner_id, package_digest}])
```

实际输入须由已有 ToolInputModel 和官方 strict schema 生成；未知字段、错误类型、过量条目拒绝，声明 nullable 的字段需兼容官方 required + null 形状。不能让 select 接受客户端 schema、函数实现、ResourceRef、任意 registry key 或私有 object ID。空 selections 明确表示只保留必要 Runtime 函数，不与 query 混淆。

目录返回固定排序、原 wire name、owner、contract hash、package digest、有限描述、schema 成本与可装入状态。描述用于发现，执行仍加载原完整 schema。query 是确定性文本过滤，不能偷偷改变 active 集合。select 原子替换显式集合，不无限累加；超预算/重复项/目录身份错误均整批拒绝，返回有界理由和预算，不能悄悄丢其中几项。

建议实现前评估的边界值：query 最多 128 字符、选择最多 16 工具、目录每页最多 16 项、完整观察最多 8 KiB。还需有有限 registry 快照总字节/条目上限；超过应在准备时显式失败，不能只截断目录并假称工具都可发现。这些是待测值，不是已通过规模合同。

## 预算与模式切换

总 prompt 预算保持默认 32768，沿用 `estimate_tool_schema_tokens`，不可新增更乐观估算器。建议先测 schema 子预算 `min(16384, floor(max_prompt_tokens / 2))`；这是为上下文预留空间的候选策略，不是证明完整 prompt 一定能装下。系统、当前请求、guidance 与证据仍由原 PromptAssembler 统一核算；超大必要内容仍应显式失败。

必要 Runtime 函数、目录函数本身都占子预算。现有 `register_core_functions` 只有 clarification 与 plan control；不能把 Conversation recall 或 RemoteJob 简单因“内置”而全部固定加载。finalization 继续遵守原白名单，不应此时重新开放目录选择。单工具加必要函数也放不下时，目录应明确 unavailable-by-budget，不能接受永远无法履行的选择。

全量 schema 足够小时可以保持原物化。进入有界模式后，首轮如何选择、目录变化如何稳定保持已选集合、目录缩小后是否回到全量，必须确定且可恢复。建议只恢复最近一次有效显式选择；工具新出现不自动加入。当前草案没有证明“全量→仅必要工具”的首轮转换及原任务进展能正常完成，接手者必须先做该正例。

不能 catch `ContextBudgetExceeded` 后静默裁掉工具。接受 select 后下一轮因更新或过滤变化无法兑现，也不能保留其中一部分而不说明；建议整组失效、回到必要函数并给出有限失效原因，要求重新选择。这样不产生新的执行权限。

## Turn、目录身份与恢复

当前 `ControlCommandContext` 已有 db、lease、run_id、turn_id、invocation_id。命令可以读取属于自己的冻结 Turn，通过原事务保存 Observation；下一 prepare 查询同 Run 的成功选择。没有证据需要给 SDK 增加 registry、callback、可调用 service 或新 ControlContext 字段。

两种快照方案的取舍：

- 只保存目录描述与成本较省空间，但命令若没有完整 schema 就不能用现有估算器精确核算整个候选集合；又会诱发把 registry 注入 ControlContext 或使用近似成本之和。不能把单项估算之和当成已证明的整体编码成本。
- 在既有 Turn materialization 中把 active `tools` 与完整 `deferred` 划成不相交集合，可直接使用冻结 schema 核算，也更容易证明目录身份。代价是每 Turn 的 SQLite 记录较大；必须测量和限制序列化体积，不应把同一工具同时保存在两组或再建一份 registry 数据库。

当前倾向第二种最小实现方向，但未冻结。active/deferred 分区和预算身份需要进入 materialization hash；目录另有与 active 选择无关的 catalog hash，覆盖全部候选工具身份及 schema。不能因为切换 active 就使一个未变化目录的分页全部失效。

分页必须绑定当前 Run、目录 hash、规范化 query 和排序位置；变化时拒绝旧 cursor，不让旧 offset 静默指向新工具。可用有界编码 cursor，不能把随机 UI 状态作为证明。显示简述的截断需标记；不得截断身份。是否将原 Turn ID 固定在 cursor 内需与跨 Turn 翻页语义协调：冻结同一目录内容可以翻页，但不能读取另一 Run 的目录作为当前权限。

恢复的选择来源只能是同 Run、正确 control Invocation、成功且输出合同有效的 Observation，按现有持久 sequence 排序。不能扫描自然语言历史猜测选择，不能跨 Session/Run 继承。目录 query、失败选择、未结算 Invocation 不改变当前选择；多次 select 在同一 Turn 按耐久顺序确定最后一次成功结果，依然只影响下一 Turn。

恢复时重新按当前可发现性、group、mode、owner/digest/hash 验证。控制处理无需读取实时 registry 时，其“成功”必须解释为“冻结候选选择已记录”，而非承诺未来包仍可执行。下一 prepare 和实际执行的 current-tool fence 各自保留。

旧 Turn 没有 deferred 时必须解释为旧的全 active 集合，不重写旧事实。不得用新默认字段的序列化结果覆盖旧 hash。接手者须明确版本化 hash 算法或受控旧格式读取策略，并验证旧格式只读恢复；这不是允许添加通用猜测兼容层。数据库当前已有 JSON 字段，是否需要 migration 取决于最终格式决定，目前未证明需要新列或表。

同一模型 Turn 中即使 select 先结算，随后调用尚未加载工具也必须由原 `materialization.require` 拒绝。不得修改传给当前 Dispatcher 的 frozen 对象。ActionRun 原有显式单工具装配无需经过模型目录选择。

## 必须先解决：控制成本与进展

当前控制函数不计入 `max_tool_invocations`，成功观察也不贡献进展。已有领域成果后 query 一轮、select 一轮可能正好触发默认两轮停滞门禁。这是本轮新增的源码级阻断发现，尚未跑新反例。

优先比较复用现有事实的方案，不加第二计数源：

1. 若 discovery 应消耗工具预算，在当前预算分类与重启后的 `tool_budget_usage` 同时计入它；使用原 Invocation 行恢复次数。其他 clarification/plan 默认行为保持，不一概改变所有控制函数。是否能用已有 semantics 表达，需读取并验证其全链消费者；本轮未作最终选择。
2. 对真实新目录内容/新加载身份提供有限的发现进展，利用 Observation 与去重证据集合。不能直接将全部 query/select 标成领域进展；重复 query、空 query、无结果、重复选择、只改变 query 文本/游标/时间戳，都不能刷新进展。
3. 当前 ProgressGuard 会读取整个 facts，其中包括 `output`。因此仅设置 `contributes_progress=True` 仍可能把变动的目录 hash、查询回显或 cursor 当作新成果。必须明确一个有限的身份投影/去重规则，并与既有证据签名复用；选择 A→B→A 不应不断新增意义相同的证据。
4. 现有 max_turns、timeout、finalization reserve 仍生效；不为目录另加可重置的轮次预算，也不提高 stalled 上限来掩盖问题。分页和调用的真实成本要写入报告。

可接受的最小实现尚未裁决。保留控制观察不贡献进展的另一选择，必须证明 query→select 的完整路径不会提前 finalization；单靠提示模型在同一 Turn 猜出未看过目录的选择不是可行证明。

## Guidance 与 history 的隐藏成本

`engine/agent/guidance.py:100` 按 resource kind、artifact type 或已加载 tool 的任意匹配激活整段 instructions，只有工具名映射按 active 过滤。因此 deferred schema 不等于相应 guidance 自动消失；不能只统计 schema 然后宣布预算解决。

先保留现有语义并测量实际 prompt 峰值；若 guidance 仍导致必要系统内容过大，应单独审议通用激活/预算，不偷偷按 owner 名称截断。目录页是有界工具观察；恢复选择读耐久事实，不依赖页面仍在 prompt。原 Responses 配对淘汰与 evidence ledger 保持，不能把所有历史目录重新注入 system。

## Frozen Kernel 七问

1. **真实共性？** 三个独立 owner 的默认生产工厂暴露同一容量问题；不是单领域建模喜好。候选属于 D。
2. **现有接点不足？** Context/Guidance 可减少内容但不选择 schema；静态 group 无法表示同 Run 动态跨能力切换。现有 materialization/ControlCommand/Observation 足以承载候选基础，不需另造执行链。
3. **为什么不能 owner 修？** 官方 schema 复用实验仍不足，删操作或弱化约束不满足用户任务；各 owner 不拥有全局预算、Turn 和恢复事实。
4. **中性与 fail-closed？** 只处理真实 ToolKey/合同/包身份，所有现有过滤、policy、ResourceRef、Artifact availability 和审批保留。目录不调用 resolver，不授予 authority。
5. **兼容/双写？** 不建 selection 表、registry 镜像、第二 Runner 或 provider 分支。旧格式读取只为已有冻结事实，必须给出精确 hash 合同，不能包一层 fallback 猜测。
6. **SDK 与旧事实？** 当前看不需要扩 ControlCommandContext 或 API v2。新增原生 Core 控制函数、Turn 物化格式和进展语义是实际 Kernel 行为变化，仍需明确批准、版本与恢复测试；“没有 SDK 改动”不等于无需审议。
7. **证明？** 见下面门禁。当前仅有原失败、成本调查和源码推导，没有候选实现通过证据。

## 接手者必须验证

| 门禁 | 必须证明的行为 |
| --- | --- |
| 默认工厂组合 | 原签名 Scene/Voxel/Pixel，在不改默认限制下完成 create→跨 owner edit→inspect→export；模型从正式目录取得名字，并实际检查下一请求的原完整 schema |
| 预算 | 边界等于/超 1、最大单工具、必要函数成本、目录页实际 UTF-8 字节、完整快照体积、guidance/ledger/history 之后总 prompt；不偷偷截断选择 |
| 控制循环 | query→select→execute 正例；多页正常继续；空结果/同页/重复选择/A→B→A/任意 query 文本不能无限制造进展；取消、重启仍计费，不提高原限制 |
| 冻结与身份 | 同 Turn 未加载调用拒绝；伪 wire/hash/owner/digest、旧目录 cursor、跨 Run/Session 选择拒绝；选择后升级/停用/group/mode 变化失效 |
| 权威隔离 | 选中 schema 后仍无额外 ResourceRef；私有 object selector、Artifact-only 输入、跨 project 资源不能获得新权限；原审批与 CAS 保持 |
| 耐久恢复 | select 事务提交前 crash 无选择、提交后恢复不重复处理领域写入；失败/query 不覆盖选择；同 Turn 多 select 的 sequence；旧 Turn hash 和 active/deferred 破坏拒绝 |
| 原链兼容 | ActionRun 单工具、finalization 白名单、只读 reconcile、原 native Responses 历史配对与预算淘汰；已有 Core 控制默认行为不变 |
| 工程与独立审议 | SDK surface、builtin registry/materialization 合同、Core/工程检查、组合报告与独立攻击；明确新增 turns、invocations、token 峰值和耗时 |

用户停止开发后，本轮不启动这些测试。完成合同裁决、实现、恢复兼容及上述验证前，联合默认预算门禁保持未完成；本交接不应被用作放行依据。
