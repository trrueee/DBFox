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

## 源码核对后的候选边界（仍待独立审议）

`materialize_tools` 已有 allowed_names，`ToolMaterialization.require` 已拒绝本轮未加载工具。`ControlCommandContext` 已携带 db、run_id、turn_id、invocation_id；ControlCommand 由同一 Dispatcher 在既有事务结算为 Observation。因此候选无需向 DLC 注入 registry、增加可调用 service locator，或让控制函数执行领域工具。

1. 当全部 schema 足够小，保持既有完整物化。超过明确的 schema 子预算时才启用按需目录；保留控制/完成所必需的函数，并由现有估算器计算预算。不得捕获 ContextBudgetExceeded 后无声丢工具，也不得调整总体预算来掩盖容量问题。
2. 一个 Runtime 原生控制函数分别接受有界目录查询与显式工具集合选择。目录仅包括当轮按 group、mode、可见性和可发现资源过滤后的真实工具；条目提供原 wire name、owner、简短说明和合同身份。查询和选择只改变后续 schema 投影，不授予 ResourceRef，不调用 DLC resolver。
3. 可考虑在既有 Turn 工具物化记录内明确区分 active/deferred 集合，保留原完整 MaterializedTool schema；provider_schemas/require 只使用 active，完整 registry 仍是当前能力事实源。旧持久 Turn 没有 deferred 时读为无延迟集合。是否需要持久 deferred 全模型及其字节成本，须由审议比较只保留描述索引的方案。
4. 控制函数读取自己的冻结 Turn 集合并通过现有 Observation 保存选择；后续 prepare 只投影同 Run 最近成功且带明确选择的控制结果。目录查询、失败选择和其他 Run 不改变选择。候选选择必须核对当前 owner、contract hash、package digest 和过滤条件；恢复不得重新执行领域写入。
5. 每次显式选择应原子替换有界集合，避免无限累加；超预算请求返回可操作的拒绝，不能偷偷保留其中一部分。目录分页具有固定排序、查询/目录身份与条目/字节上限，目录变化不能把旧 offset 对应为不同事实。Tool ActionRun 仍按既有显式单工具装配执行，finalizing 的既有白名单继续生效。
6. 测试必须证明：未加载工具即使模型知道名字也被原 Dispatcher 拒绝；加载请求与领域调用在同一旧模型 Turn 时不会提前生效；多次控制结果按耐久顺序恢复；上游停用/升级、group/mode改变和跨 Run 不继承旧选择。实际三 DLC 测评要让受控模型根据真实目录输出选择工具，再按新 provider schema 调用，记录增加的轮次与全部 prompt 峰值。

待解决项包括：子预算占比与至少一个大工具能否装入、保留的 Runtime 函数范围、目录选择本身的进展/循环预算、默认全量到按需模式的稳定切换、旧 Turn hash 的兼容校验。独立架构审议通过前，以上内容不是产品合同，不能直接据此声明门禁通过。
