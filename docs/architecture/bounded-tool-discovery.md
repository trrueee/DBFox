# 多能力工具发现与上下文预算

> 文档类型：架构调查
>
> 状态：草案
>
> 最后核验：2026-09-06
>
> 适用范围：多个DLC同时可发现时的通用工具物化；未实施

## 已确认问题

Scene、Voxel、Pixel在同一Project创建文档后，默认生产工厂第4次prepare暴露60个原生函数schema，保守估计31942 token；整个prompt上限32768，无法容纳系统说明和已有结果。旧联合测试手工使用128000，掩盖了默认装配问题。可复现测试与详细证据保存在 `D:/Project/DBFox-worktrees/creative-composition` 的 `verification/tests/system/test_creative_dlc_composition.py` 和 `docs/quality/creative-dlc-composition-verification.md`。

## 调查与复用

现有 `materialize_tools` 已按policy可见性、execution mode、tool group和可发现resource kind过滤；`RunLoop._prepare_turn` 在每轮取得Project目录，冻结当轮完整 `ToolMaterialization`。`ToolDispatcher.request` 只接受当轮物化函数，随后独立绑定Invocation资源、执行policy/approval。现有 `allowed_tool_groups` 来自静态AgentDefinition，没有耐久、按需的工具schema加载操作。历史132a29fb将Project发现与Invocation authority分离；不能重新引入资源选择命令授予整个Project权限。

SDK生成已复用 `openai.pydantic_function_tool`。按[Pydantic命名类型文档](https://pydantic.dev/docs/validation/2.12/concepts/types/#named-type-aliases)做过已有标量/向量类型 `$defs` 复用实验，估计仅降至30068，仍不足；全部实验已撤回。没有采用删约束、删用户要求的增量工具、自由JSON参数、调大默认预算或自制token估计规则。

[OpenAI Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)支持先显示工具目录，再加载所需参数schema，并区分服务端和客户端发现。可以复用这种按需加载方式；直接依赖其专用 `tool_search_call/tool_search_output` 会改变DBFox当前只处理原生function calling的provider边界，不能未经验证加入。引入另一个Agent框架、MCP服务、索引数据库或模型路由器也没有必要。

## 待审议方案

在当前单一RunLoop内，通过一个Runtime所有的原生控制函数请求有界工具集合。候选目录仅来自同轮通过现有可发现性过滤的真实registry；加载时保留原始完整typed schema，不改工具输入与执行合同。下一轮冻结实际加载的集合，领域调用继续走原Dispatcher。目录本身有分页/字节预算，不能用无限目录替代无限schema。

加载选择必须在现有SQLite Invocation/Observation内留下耐久证据；恢复只重新投影选择，不重放领域写入。旧Run/其他Session选择、伪造owner/contract hash、停用或升级后的旧选择不得使工具可调用。已加载工具仍需当前Project成员关系、冻结版本、policy和approval；模型参数与DLC私有selector不能产生新权限。未加载调用仍按现有不可用工具规则拒绝。

该方案尚未实现或通过独立审查，具体函数合同、目录分页、预算分配和选择失效规则必须先收敛。不得把本草案作为已支持的产品行为。

## Frozen Kernel 变更评估

1. 这是至少三个独立能力共同暴露的通用容量问题，Kernel不得识别Scene/Pixel/Voxel名称或其他领域模型。
2. 已有Context/Guidance/Artifact只能减少内容，不会限制当前完整工具schema；静态group不能表达同一Run中的跨能力切换。
3. owner约束复用不足以解决同时加载；削弱必需操作或各DLC重复实现发现会产生不一致的第二入口。
4. 发现集合与执行权威必须继续分离，保持capability-neutral、provider-neutral、owner-bound及fail-closed。
5. 预期复用registry、物化、ControlCommand、Invocation和Observation；不新增兼容层、领域wrapper、私有跨DLC访问或第二调度器。
6. 保持已安装API v2工具合同；新增Host控制函数与物化投影属于Kernel行为变化。任何持久化字段变更必须声明旧Run的默认/恢复语义，不能静默迁移事实。
7. 必须覆盖完整默认生产工厂三DLC联合、无资源/错误mode/不可见工具、升级/停用、跨Run选择、预算边界、取消/重启、未加载调用拒绝、tool hash以及全部Core和工程合同。之后仍需独立审查；未通过前保持联合门禁未完成。

维护责任属于通用工具物化边界。主要风险为选择额外消耗模型轮次、目录不完整、预算估计保守与恢复时沿用旧合同；验证应明确记录这些成本，不能只统计最终领域工具成功。
