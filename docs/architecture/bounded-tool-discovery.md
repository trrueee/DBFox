# 多能力工具发现与上下文预算

> 文档类型：架构决策
>
> 状态：当前
>
> 最后核验：2026-11-07
>
> 适用范围：OpenAI Responses 工具投影、原生搜索历史与生产组合预算

## 问题和决定

多个创作 DLC 同时装载后，默认生产 RunLoop 会在创建资源后的后续 Turn 暴露更多工具。此前 Scene、Voxel、Pixel 场景第 4 次 prepare 的 60 个完整函数定义保守估计为 31942 token，接近默认整个 prompt 的 32768 上限，无法同时容纳系统说明与历史。提高测试专用预算不能证明默认产品可用。

采用 OpenAI 官方 hosted tool search：每个 Turn 先按既有 group、执行模式和可发现资源种类物化完整工具集合，再由 OpenAI Provider 将函数标为 `defer_loading: true` 并加入 `{"type":"tool_search"}`。模型按需加载参数定义，随后发出的原生函数调用仍经过原 ToolDispatcher。

不实现 `tool_catalog_query` / `tool_catalog_select` 控制函数，不维护客户端搜索选择状态。此前本页的自定义目录草案已被本决策替代；[原审议记录](../archive/bounded-tool-discovery-control-review.md)保留为历史调查，不能作为当前行为说明。

## 调查、复用和取舍

1. 项目已有 `ToolRegistry → materialize_tools → ToolMaterialization → ToolDispatcher`，过滤、完整 typed schema、合同 hash 和执行时当前合同核验都可复用。搜索不改变这些权威。
2. 当前锁定的官方 OpenAI Python SDK 已能解析 `tool_search_call` / `tool_search_output`，无需升级 SDK、引入索引库或修改锁文件。既有 `MODEL_OUTPUT_ITEM` 与 SQLite response item 存储能保留新增原生项，无需新表。
3. [官方 Tool search 指南](https://developers.openai.com/api/docs/guides/tools-tool-search)说明：候选工具在请求开始时已知，优先 hosted；无法预先声明候选集合时才需要客户端执行搜索。DBFox 在本轮物化完成时已经知道候选集合，因而采用 hosted。
4. 官方允许单独 deferred function。namespace 能进一步减少开销，但当前按单个函数延迟参数已可处理原始容量问题；本次不新增命名映射，不改变 DLC wire name，也不把领域分组规则写进 Core。
5. 不采用自定义目录：它额外引入模型复制合同身份、分页、选择持久化、控制预算与进度计算，现有场景没有证明这些自研成本必要。此前命名类型别名实验也未解决完整工具集合的成本，不能以削弱输入类型替代按需加载。

没有新增依赖、许可证负担、供应链组件、跨 DLC 私有调用或运行时状态机。托管搜索受所选模型和服务端支持范围约束；其质量、成本和延迟仍需要真实服务评测。所有候选 schema 仍随请求发送，延迟加载减少的是初始模型上下文，不是 HTTP 请求字节数。

## 模型支持与失败行为

官方声明仅 GPT-5.4 及后续模型支持 tool search。Provider 对明确的 GPT 系列版本、已知型号后缀和日期版本启用投影；默认 `gpt-4o-mini`、旧型号、其他提供商型号与无法识别的别名继续发送原有完整 schema。不会自动改用户选择的模型。

支持的型号名称不证明兼容端点实现了该协议。服务拒绝请求时按既有安全错误返回失败：400 为请求被拒绝，404 为模型或服务地址未找到；不输出上游原始错误和秘密。Agent 运行与模型连接测试均要求原生 Responses，不再隐式转入 Chat Completions；仅支持 Chat 的端点会明确失败。搜索调用与历史项继续按 Responses 原生结构保留，没有新增自动降级或重试路径。

旧模型在原始全量组合场景仍可能达到默认上下文上限，这是明确的支持限制；不能因此声称所有模型已经解决多 DLC 工具预算，也不能自动扩大总预算。

本地 `ContextBudgetExceeded` 属于预期容量拒绝，由 RunLoop 经现有 Terminalizer 结算为
`AGENT_CONTEXT_BUDGET_EXCEEDED`，而非逃逸后显示通用运行时错误。固定安全文案提示减少引用，或
停用不需要的扩展并重启引擎；此前已经保存的成果仍保留。创建资源后新增可发现工具同样可能触发此
边界，不能据此自动重建作品、重放写入、裁掉必要工具或提高总预算。这一错误与已消耗 Token 达到
运行上限的 `AGENT_TOKEN_BUDGET` 不同。

## 运行、权限与持久化

- 完整 `ToolMaterialization` 内容与 hash 仍冻结在 Turn 中。`defer_loading` 仅存在于 Provider 请求投影；搜索不缩小或扩大执行权威。
- 托管搜索必须是 `execution: server` 且 `call_id: null`。不把搜索作为 DLC Invocation，不在 DBFox 再执行搜索。意外返回客户端搜索按协议错误终止。
- 完成的搜索调用与输出通过既有 `MODEL_OUTPUT_ITEM` 完整保留，包括显式 null、顺序和已加载定义。它们经原 SQLite 历史路径进入后续请求；不新增持久字段或另一份工具选择事实源。
- DLC 函数调用继续经既有物化成员校验、输入校验、Project membership、canonical version、policy、approval、执行和 Observation。旧搜索结果不能使停用、升级或失去授权的工具绕过当前执行边界。
- 搜索没有改变取消、generation fence、审批或非幂等恢复语义。断流产生原有失败，未完成 Turn 不因搜索增加自动重放。

## 预算和历史裁剪

官方说明单个 deferred function 的名称和说明在开始时仍可见，参数定义在加载时才进入上下文。因此只有同时存在 `tool_search` 的工具列表才按名称、说明与其他可见元数据估算 deferred function；普通工具仍完整计费，孤立的 `defer_loading` 标志不获得折扣。

搜索输出历史中的 schema 完整计入 `estimate_input_item_tokens`。PromptAssembler 继续按完整 Turn 淘汰历史，包括该 Turn 的搜索项、函数调用及其结果；不拆分成孤立结果，不修改耐久记录。被裁剪的历史不会变成另一份未计费缓存，后续模型仍可搜索本轮候选。

Responses 的 `role/content` 简写与显式 `type: message` 使用同一个消息估算器，避免生产 planner 和 HTTP 请求核验对等价消息给出不同预算。非消息项仍按完整规范 JSON 计费。

官方说明删除加载集合会使工具不再可用，但没有明确说明“删除早期加载 Turn、保留后续同名历史调用”的所有服务端校验条件。本次不通过猜测增加补写历史或 eager schema 兼容层。当前合同测试覆盖完整 Turn 裁剪；跨 Turn 裁剪后的真实端点接受性与重新搜索表现仍是待完成的在线验证，不能以本地 MockTransport 代替这项证据。

## Frozen Kernel 七问

1. **通用问题是什么？** 多个独立 DLC 的完整 schema 累积超过生产输入预算，是运行时容量问题；没有领域名称分支。
2. **现有贡献为何不能表达？** Context、Guidance 和 Artifact 不控制模型协议中的工具定义加载时机；DLC 不能自行修改 Provider 请求。
3. **为何不能由 owner 修复？** 单个 owner 的 typed schema 未超过总预算，问题来自多能力组合；各 owner 自建发现会复制权威入口。
4. **边界如何保持？** Core 保持唯一物化与执行权威，OpenAI adapter 处理官方 wire 协议；逻辑 Run/Turn/Invocation 与 completion 不新增 provider 专属状态，能力 owner 不变，未知模式 fail-closed。
5. **是否增加中间层？** 无新的 mapper、控制工具、fallback、索引或双写；沿用既有 Provider 边界做一次请求投影。
6. **兼容影响是什么？** API v2、工具输入、注册与持久 ToolMaterialization hash 不变，无数据库迁移。旧 Run 没有搜索项时按原语义读取；旧/未知模型保留原请求模式。当前改动属于 Internal Provider/预算正确性修复，不解冻外部 authority。
7. **如何验证？** 下述 Core、生产组合和工程合同覆盖 SDK 协议、预算与架构边界；原有取消、审批、恢复、资源授权和合同变化回归继续执行。真实服务与全部 DLC 产品验收单独计证据，不能由本决策宣布完成。

## 验证入口与证据限度

```powershell
.venv/Scripts/python.exe -m pytest verification/tests/agent_core -q --tb=short -m "not e2e and not integration and not real_llm"
.venv/Scripts/python.exe -m pytest verification/tests/system/test_creative_dlc_composition.py -q --tb=short
.venv/Scripts/python.exe -m pytest verification/tests/system/test_engineering_contracts.py -q
```

`test_openai_model_adapter.py` 覆盖支持/不支持型号、完整定义不被修改、官方 SDK 搜索项往返、意外客户端执行、400/404、安全错误与带搜索历史的最终化不转 Chat。`test_context_budget.py` 覆盖可见说明成本、加载历史完整成本及整 Turn 裁剪。生产组合测试使用实际 `AsyncOpenAI` 与 `httpx.MockTransport`，只替换 HTTP 模型服务，沿用产品 RunLoop、注册、资源与耐久历史。

2026-09-07 本地确定性 Core 回归 332 passed、2 deselected；其后补充消息简写等价估算的 context 回归 9 passed。工程合同 45 passed；修改的三个生产文件 mypy 与 pyflakes 通过。该证据不包含付费真实模型、搜索相关成本测量、完整 20 DLC 的端到端验收或新的原生 Electron 截图。
