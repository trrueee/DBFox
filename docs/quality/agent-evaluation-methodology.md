# Agent 生产评测方法

> 文档类型：质量方法
>
> 状态：当前
>
> 最后核验：2026-08-11
>
> 适用范围：DBFox Agent 的 Prompt、Context、Memory、Tool、SQL、Completion 与 Provider 边界

## 目标与非目标

评测回答的是“在固定运行合同和资源预算下，Agent 完成真实数据任务的能力、稳定性和成本是否退化”，而不是证明某个模型永远正确。模型输出具有随机性，单次成功只能作为运行证据，不能替代重复测量、确定性合同和人工抽检。

本项目不以单一总分掩盖安全失败，也不把单元测试、真实 Provider 合同和产品任务测评混为一类。

## 依据与复用决策

- OpenAI 公开的数据 Agent 采用自然语言问题、人工编写的 golden SQL、实际执行结果和持续回归评测；这与 DBFox 的 SQL-first、Result Artifact 设计相符。
- OpenAI 的 Agent Evals/trace grading 强调数据集、完整轨迹和独立 grader。DBFox 保留自己的耐久 Run/Turn/Tool/Artifact 轨迹，因此直接在现有轨迹上评分，不增加第二套 Agent 或 SQL 执行链。
- Inspect 将 Task、Solver、Scorer、Metric、Eval Log 分离。DBFox 采用同样的职责分离概念，但当前不引入 Inspect 依赖：既有 pytest、RunLoop 和耐久表已经覆盖执行与日志边界，引入框架会增加双轨运行和迁移成本。

主要参考：

- [OpenAI：Inside our in-house data agent](https://openai.com/index/inside-our-in-house-data-agent/)
- [OpenAI：Agent evaluation and trace capabilities](https://openai.com/index/introducing-agentkit/)
- [OpenAI：可信评测的有效性风险](https://openai.com/index/trustworthy-third-party-evaluations-foundations/)
- [UK AISI Inspect scorer/metric contract](https://inspect.aisi.org.uk/reference/inspect_ai.html)

## 四层评测金字塔

| 层 | 环境 | 目的 | 是否合并门禁 |
| --- | --- | --- | --- |
| L0 合同测试 | 纯函数、Repository、Provider fixture | 类型、状态机、脱敏、取消、终止、Artifact 血缘 | 是，必须 100% |
| L1 确定性 Harness | 隔离 SQLite + 生产 RunLoop + scripted Provider | 工具闭环、SQL 参数绑定、恢复、跨轮上下文、注入边界 | 是，必须 100% |
| L2 真实 Provider 回归 | 隔离 SQLite + 生产 RunLoop + opt-in Provider | 工具选择、任务完成、引用、成本、稳定性 | 夜间/手动；不因一次网络抖动阻断普通 PR |
| L3 产品观测 | 脱敏耐久指标与人工标注 | 发现分布漂移、真实失败簇和数据集缺口 | 发布决策输入，不直接训练或泄漏用户数据 |

## 数据集角色

数据集必须声明角色，不能在优化后继续把同一批任务称为“未见 holdout”。

1. **development**：开发期间可反复运行，用于定位和调参。
2. **regression**：版本化、可见、每次变更重复运行，防止已知能力退化。
3. **hidden holdout**：题目和 golden 只由评测负责人持有；一个优化周期只揭晓一次。揭晓后转入 regression。
4. **production canary**：仅使用取得授权且完成脱敏/分桶的指标；不得复制原始用户消息、Cell 值、DSN、Token 或凭据。

每条任务至少记录：`case_id`、数据集版本、能力标签、自然语言请求、数据库 seed 版本、允许/禁止动作、golden SQL 或确定性结果、评分规则、资源预算和已知歧义。

## 必测能力矩阵

| 维度 | 最小场景 |
| --- | --- |
| 基础分析 | 计数、筛选、分组、比例、排名、时间边界 |
| 多表与多阶段 | Join、对账、先验证后目录 pivot、基于前次结果继续分析 |
| 大结果 | bounded preview、分页/统计、禁止把全部行注入上下文 |
| 上下文与记忆 | 长历史截断、会话检索、跨 Run Artifact、失败 Run 恢复、数据源 generation 隔离 |
| 工具恢复 | 输入合同错误、对象不存在、超时、取消、Provider 中断、可重试/不可重试分类 |
| 安全 | 写操作拒绝、行内容提示注入、引用伪造、秘密/DSN/Authorization 零泄漏 |
| 完成语义 | `phase=None` 完整文本、工具未完成、部分流、取消、明确 completed |
| 成本与体验 | Turn 数、工具调用数、失败调用率、Token、首字/总延迟、无进展终止 |

## Grader 设计

评分按可信度从高到低组合，不能让模型自行给自己的输出打唯一分数：

1. **环境/数据库状态 grader**：写操作是否发生、结果集是否与 golden SQL 等价。
2. **结构化轨迹 grader**：Run 状态、工具序列、Artifact 类型与血缘、重试/取消、敏感值零命中。
3. **答案合同 grader**：必要数值、合法引用、限制说明；优先结构化检查，不做整段字符串完全匹配。
4. **人工 rubric**：正确性、相关性、可操作性、表达质量和遗漏。
5. **LLM grader（可选）**：只评难以结构化的语义质量，必须用单独模型/配置，并用人工标注集报告 precision、recall 和混淆矩阵。

安全 grader 是 veto：任何鉴权绕过、秘密泄漏、未授权写入、错误自动重放或伪造 Artifact 引用均使该 trial 失败，不能被其他维度平均抵消。

结果正确性必须沿最终答案的证据血缘评分：先按答案顺序解析现有
`{{cite:artifact_*}}`，再由被引用的 `result_view.sourceSqlArtifactId` 找到实际
SQL。不能用“最后创建的 SQL/Result Artifact”代替答案引用，因为 Agent 可以在
主查询之后执行交叉核验；按插入顺序评分会把更严谨的行为误判为错误。

过程质量与任务正确性分开报告。最终答案正确不抵消被拒绝/失败/未知工具调用、
相同输入重复调用、Plan 步骤被跳过或异常 Token/延迟；这些指标用于优化和配对
门禁，但不得反过来把正确结果判错。

## 重复、统计与比较

- L0/L1 为确定性测试：任何一次失败都阻断。
- L2 每个任务默认至少 3 次；温度、模型别名/快照、Provider、Prompt 版本、工具 schema hash 和预算必须固定并记录。
- 报告 trial 级成功率、case 级 `pass@k`/全通过率、Wilson 95% 区间，不能只报平均分。
- 同一任务配对比较前后版本；同时报告绝对变化和相对变化。
- Token、延迟和工具数报告 median、p90、maximum；不要用平均值掩盖长尾。
- 工具失败率包含 `failed`、`rejected` 和 `unknown`，不把策略拒绝隐藏为成功过程。
- Plan 任务报告版本数、最终状态、稳定 step ID、completed/skipped/blocked 数量。
- 只有配置了可信模型价格时才报告美元成本；价格未知必须为 `null/unavailable`，
  不能把预算账本中的零占位解释为免费。
- 评测规模不足时明确写“证据不足”，不把 10/10 宣称为 100% 的总体可靠性。

建议回归阈值：

- 安全 veto：0 次失败；
- 确定性合同和 Harness：100%；
- 真实 Provider：总体成功率不得下降超过 3 个百分点，任一核心能力不得连续两次回归；
- median Token 不得增加超过 15%，p90 延迟不得增加超过 20%，除非任务成功率有经评审的实质提升；
- 工具输入错误率、重复调用率和无进展停止率不得恶化。

这些阈值是变更比较门禁，不是对所有未知任务的可靠性承诺。

## Trace 与证据合同

每个 trial 应产生一个只读证据目录，至少包括：

- commit、工作区状态、OS/架构、Python、模型配置别名和数据集版本；
- Run/Turn/Tool/Observation/Artifact ID 与状态时间线；
- Prompt 版本、工具 schema 数量/Token、输入/输出 Token、延迟；
- grader 分项、失败理由和人工复核状态；
- SQL 指纹、参数名、结果摘要和血缘，不保存秘密或无界原始行；
- 原始日志位置和内容哈希。

API Key 只能来自 OS 凭据库或 CI secret。报告只能保留 credential reference 的掩码，不得写入 Key。真实 Provider 评测必须 opt-in；未配置时应 skip，而不是伪造通过。

## CI 与发布使用

- 普通 PR：运行 `verification/tests/agent_core`，包括确定性 SQLite Harness。
- schedule/workflow_dispatch：在隔离运行目录执行真实 Responses 文本与工具闭环；配置完整时再运行版本化 regression dataset。
- 隐藏 holdout：由受控 workflow 或人工评测环境注入，不提交答案到仓库。
- CI 上传 JUnit、结构化 summary 和脱敏 trace；不可只上传“测试通过”一句话。
- 网络、配额或 Provider 5xx 与任务质量失败分开统计；基础设施失败不能被记为模型能力失败，也不能静默算通过。

## 当前实现索引

- AgentBench 实现与运行手册：`docs/quality/agentbench-implementation.md`
- 版本化 60 场景集：`verification/bench/agentbench/datasets/regression-v1.json`
- scorer 校准集：`verification/bench/agentbench/datasets/calibration-v1.json`
- 稳定 CLI：`python -m verification.bench.agentbench`
- 生产 RunLoop：`engine/agent/loop.py`
- 上下文与预算：`engine/agent/context.py`、`engine/agent/context_budget.py`
- Prompt 与工具 schema telemetry：`engine/agent/prompt.py`
- 确定性场景：`verification/tests/integration/test_sqlite_scenarios.py`
- 真实 Responses 合同：`verification/tests/agent_core/test_real_responses_contract.py`
- PR CI：`.github/workflows/ci.yml` 的 `agent-runtime`
- 定时/手动评测：`.github/workflows/agent-evaluation.yml`

## 当前限制

- 真实 Provider runner 已有版本化 CLI 和脱敏输出，但必须显式 opt-in；没有凭据、
  网络或费用授权时只能运行 L0/L1，不能伪造 L2 通过。
- 模型名称可能是可变别名；没有 Provider 提供的不可变 snapshot 时，纵向比较必须记录这一限制。
- 真实安装态 GUI/SSE 体验不由本方法单独证明，仍属于发布验证矩阵。
- OpenAI-compatible Provider 即使收到 `strict: true` 也可能返回不符合 Schema 的
  参数；生产边界仍必须验证。DBFox 使用 Pydantic 权威模型校验，并只向模型返回
  字段路径与错误类型，不回显输入值。
