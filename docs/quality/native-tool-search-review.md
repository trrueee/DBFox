# 原生工具搜索独立审查

> 文档类型：质量审查
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：OpenAI hosted tool search、Core 执行权威、默认生产组合与确定性协议验证

## 结论

接受当前 hosted tool search 作为本次多 DLC 工具容量问题的架构方案。受审实现复用完整工具物化、官方 Responses 协议和既有执行链，未引入自定义目录控制工具、第二套执行权威或新的领域状态机。本轮独立反例没有复现搜索绕过注册、审批、包版本 fence 或取消的缺陷。

这是限定范围的架构与确定性实现审查。它不证明真实模型能稳定选择正确工具，不证明全部 20 个 DLC 已完成，不批准安装包发布，也不将 HTTP MockTransport 视为真实 OpenAI 服务。后文列出的在线证据缺口仍须保留。

审查者 `/root/shader_evidence_finish` 未编写受审 Core 实现及 Director 的组合测试。本轮只新增独立测试与本报告。受审根分支基础提交 `df6a91fe`；当时 Core 改动尚未提交，因此记录 Git blob 身份：

| 文件 | 受审内容 Git blob |
| --- | --- |
| `engine/agent/providers/openai.py` | `03f1fbe328b753219b8b6746c9db0269d5f5d19d` |
| `engine/agent/context_budget.py` | `50bce32c4a39bc92b427024a4bb01817543b8104` |
| `engine/agent/loop.py` | `30c018e73345e66ac0428aa969c958a0e2654dca` |
| `verification/tests/system/test_creative_dlc_composition.py` | `e562c69a02b3748957d12ae7d5da726378fd26f3` |

## 调查与边界判断

按照项目要求先查 CodeGraph，读取现有 Provider、RunLoop、PromptAssembler、ToolDispatcher、ToolMaterialization 与 SessionCoordinator 的实际源码，并核对当前[架构决策](../architecture/bounded-tool-discovery.md)。

同时检索并完整获取 [OpenAI 官方 Tool search 指南](https://developers.openai.com/api/docs/guides/tools-tool-search)。官方说明候选工具在请求开始时已知可优先 hosted；单独 deferred function 仍暴露名称与说明、延迟参数 schema；搜索项通过原生历史保留；仅 GPT-5.4 及后续模型支持该工具。这些事实符合当前每 Turn 先物化候选、再在 Provider 投影的选择。namespace 是进一步降低名称/说明开销的选项，当前使用单独函数在官方合同内，没有必要为本次修复新建名称映射。

执行权限继续来自完整 `ToolMaterialization`，不来自 `tool_search_output.tools`。`ToolDispatcher.request` 先检查本 Turn 成员，执行时再检查已安装合同、owner 与 package digest；资源绑定与 policy/approval 仍在同一链路。Provider 专属字段留在原始 Response item 与请求投影中，逻辑 Run、Invocation 和 completion 未新增搜索专属状态。预算模块已有 Responses item 语义，此次仅按真实可见内容估算，不增加另一套调用状态。

## 独立反例及结果

独立测试文件：[test_native_tool_search_review.py](../../verification/tests/agent_core/test_native_tool_search_review.py)。前四场景经过真实 `AsyncOpenAI`、`httpx.MockTransport` 或真实 SessionCoordinator；后两项直接检查当前实现 fence，明确不冒充签名包生命周期端到端验证。

| 独立刺激 | 实际检查 | 结果 |
| --- | --- | --- |
| 搜索结果伪造未注册函数并紧接调用 | 真实 Dispatcher 记录 `UNKNOWN_TOOL`；工具实现禁止执行 | 通过 |
| 搜索结果加载注册的需审批工具并请求执行 | Run 与 Invocation 停在 `waiting_approval`，只发一轮模型请求；工具实现未运行 | 通过 |
| `gpt-4o-mini` 加载超过默认预算的参数 schema | 真实 Coordinator 捕获 prepare 失败并持久化 Run failed；零 Provider 请求；后继 worker 可 claim 租约 | 通过 |
| 原生搜索请求已到 HTTP 边界时取消 | 抛出取消；HTTP 路径只有一次 `/v1/responses`，没有重放或 Chat 请求 | 通过 |
| 旧已加载 schema 对应的工具被移出当前 registry | 原有 `require_current_tool` 拒绝旧耐久调用，当前请求不再投影该工具 | 通过 |
| 相同 wire name 与 schema 已换新包 digest | 原有 fence 拒绝旧包调用；当前投影可提供新包工具，旧搜索历史未被当成执行凭据 | 通过 |

`6 passed in 3.92s`；新增独立测试 pyflakes 通过。首次 collection 因测试探针漏声明必填 `presentation` 失败，修正测试工具定义后再运行；该 fixture 错误不计作产品缺陷。

## 对既有验证的独立复核

实际重新执行 Provider adapter、上下文预算、三/四签名 DLC 组合测试：`49 passed in 29.15s`。其中组合测试仅替换外部模型 HTTP，使用真实 SDK、产品 RunLoop、资源解析、Tool Runtime、SQLite Observation 与 Artifact；当前三个领域先创建再局部编辑与导出，第四 Shader 验证创建、重命名和历史导出。跨 owner 私有 ID 的三次请求被拒绝。Shader 组合项不含 GPU 编译与渲染，不应据此声称其 GPU 行为新验收。

adapter 测试检查 400/404 固定安全错误、含搜索项的请求及带搜索历史的最终化请求均不走 Chat fallback；未知或旧模型保留完整 schema，未替换用户选型。预算测试检查名称/说明仍计费、历史 `tool_search_output` 全量计费，以及整 Turn 裁剪保持该 Turn 内搜索/调用/结果顺序，不修改耐久记录。

可复跑命令（仓库根）：

```powershell
.venv/Scripts/python.exe -m pytest verification/tests/agent_core/test_native_tool_search_review.py -q --tb=short
.venv/Scripts/python.exe -m pytest verification/tests/agent_core/test_openai_model_adapter.py verification/tests/agent_core/test_context_budget.py verification/tests/system/test_creative_dlc_composition.py -q --tb=short
```

## 未闭合证据及精确限制

1. **真实服务的历史裁剪接受性尚未验证。** 当前按完整 Turn 裁剪，但可能移除早期加载定义的 Turn，同时保留后续调用同名工具的 Turn。官方说明加载集合参与后续工具可用性，却未在已读页面完整规定该组合的所有服务端校验。现有本地测试只证明数据顺序与预算，不能证明真实端点必然接受，亦不能据此断言端点必然拒绝。应使用受控、获授权的在线只读任务验证此路径；本轮不调用付费 API。
2. **历史定义与新包 schema 并存的模型表现未验证。** 当前执行 fence 已验证拒绝旧包耐久调用，但旧搜索输出仍能存在于历史中。官方指出从已加载集合移除工具会改变可用性并破坏该处缓存。不能将执行拒绝等同于模型端已忘记旧定义。禁用/升级后重新搜索的行为需真实服务验证；暂不根据推测增加清洗历史或双份工具状态。
3. **旧模型失败消息仍过于泛化。** 直接调用 RunLoop 的原组合测试只期待 `ContextBudgetExceeded`，不检查终态；本轮补真实 Coordinator 后未复现产品长期 running 或租约泄漏。当前通用捕获将这种已知容量失败标为 `AGENT_RUNTIME_ERROR`，用户难以判断是模型工具容量限制。这是已有错误分类/可用性改进点，不是原生搜索新增的权限漏洞；不要将直接 loop 的异常误报成生产任务永不结算。
4. **容量估算不是服务计费。** 单函数 deferred 仍随 HTTP 请求传输完整 schema；省的是初始模型上下文，不是请求大小。托管搜索在一个 Response 内可能加载多个工具，实际 usage、延迟和选择准确率均不由当前保守静态估计证明。模型名称识别也不保证兼容端点支持协议；已验证拒绝时失败，不自动降级。

无需为上述尚未证实的服务行为自行引入索引器、Core 搜索命令或 fallback。当前实现可作为后续 DLC 开发的基础，在线接受性与完整产品验收应继续独立追踪。
