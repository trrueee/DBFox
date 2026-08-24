# DBFox Benchmark System：Core、Capability 与 Composition

> 文档类型：质量工具
>
> 状态：当前
>
> 最后核验：2026-08-24
>
> 适用范围：`verification/bench/`、`verification/tests/bench/` 与 Agent evaluation workflow

## 1. 目标

DBFox 的 Bench 与产品代码物理分离，并按真实架构边界归属结果：

```text
CoreBench         → Agent Kernel / Harness
CapabilityBench   → 单个 Capability DLC
CompositionBench  → Core + 一个或多个 DLC 的用户任务
```

三类 Bench 共享薄的 Manifest、统计、报告和比较合同，但不共享第二套 Agent Runner。需要 Agent 闭环的 trial 必须经过生产 `SessionRepository`、resource authority、Session lease、`RunLoop`、Tool Runtime、Observation/Artifact 和 Terminalizer。

## 2. 目录与 Subject Under Test

```text
verification/bench/
├── framework/                       # domain-neutral manifest/statistics/report/comparison
├── core/
│   ├── loop/                        # completion and tool efficiency
│   ├── context/                     # current-request priority and durable recall
│   └── authority/                   # same-kind selection and fail-closed access
├── capabilities/
│   └── dbfox_data/
│       ├── direct/                  # operations/resources/catalog, no LLM
│       └── agent/                   # 60-case Data agent dataset/scorer/runtime
└── composition/
    └── data_workspace/              # one Run, two frozen capability resources
```

每个 suite 的 `suite.json` 必须声明：

- `suite_id` 与语义版本；
- `subject.kind`：`core`、`capability` 或 `composition`；
- 被测 `components`；
- 仅作为支持条件的 fixtures；
- Provider mode 与 repetition 上限组成的 execution matrix；
- suite-owned dataset；
- 指标名称、方向、单位与解释。

Core suite 不能把 `dbfox.*` DLC 写进被测主体；Capability suite 只能有一个 capability owner；Composition suite 至少有两个被测 component。失败结果因此能先归因到明确 owner，而不是落入一个万能 AgentBench。

## 3. 当前套件

### 3.1 `core.loop.scripted`

不启用 Data/Workspace/GitHub DLC。Scripted Provider 和 `verification_read` 只是外部刺激，trial 执行生产 admission、lease、RunLoop、tool invocation 与 durable Turn。当前测量直接完成、单工具闭环和两步工具闭环的成功率、Turn、工具调用及重复调用。

这不是 Core 合同测试的替代品：`verification/tests/agent_core` 回答状态机是否符合不变量；CoreBench 回答候选 Harness 在版本化任务上用了多少 Turn/Tool、是否改善。

### 3.2 `core.context.scripted`

使用生产 ContextAssembler、Conversation Search/Read Tool、Session admission 和 RunLoop，测量当前请求优先级、被裁剪历史的显式召回、Turn/Tool 预算以及最终回答的敏感值暴露。长历史 fixture 和 Scripted Provider 只控制外部刺激，不替代上下文组装或召回实现。

### 3.3 `core.authority.scripted`

使用 capability-neutral `verification.resource` 与 probe tool，测量单资源、同 kind 多资源显式选择和未授权 ID 的失败关闭。ResourceRef 冻结、工具物化、Dispatcher 和 resolver 全部是生产实现；synthetic resource 只提供不带 Data/Workspace 语义的外部句柄。

### 3.4 `capability.dbfox_data.direct`

不经过 LLM，直接通过正式 System DLC package → verify/bootstrap → contribution snapshot → public operation/resource provider 链测量 ConnectionProfile 与 DatabaseResource 分离、catalog refresh/browse 和源数据库只读性。它判断 Data DLC 自身的领域合同，不判断 Agent Core 是否聪明。

### 3.5 `capability.dbfox_data.agent`

原 60-case 数据集完整迁入这个 suite。被测主体是 `dbfox.data` 的 agent-mediated 能力；Core Runtime 和 SQLite seed 是支持条件。它继续使用 production DLC snapshot、Data operation/resource discovery、服务器授权、真实 RunLoop、SQL safety/execution 和 Artifact/Evidence，并由 Data-owned scorer 判断结果集、轨迹、引用与安全。

Data scorer 校准、离线 replay 和真实 Provider 重复运行仍由该 capability suite 自己拥有。Framework 不理解 SQL、Table、Catalog 或 golden SQL。

### 3.6 `composition.data_workspace.scripted`

首个 CompositionBench 创建一个 Project、一个 Data database resource 和一个 Workspace resource，由服务器冻结 canonical ResourceRefs 后交给同一个生产 Run。Scripted Provider 依次调用 `file_read` 和 `schema_list`，suite scorer 检查最终 handoff、双资源 authority、Workspace Artifact lineage、源数据库与工作区无写入，以及 Turn/Tool 预算。

后续 Composition suite 只在具有真实数据集、资源组合和 scorer 时创建，不增加空目录或占位 Runner。Composition scorer 负责最终目标、跨能力 handoff、Artifact lineage 和 authority，不能把单 DLC 的领域规则复制到 Framework。

## 4. Tests 与 Bench

```text
verification/tests/agent_core/  → 确定性 PASS/FAIL 合同
verification/tests/system/      → Capability/DLC/composition 合同
verification/tests/bench/       → Bench 自身 manifest/scorer/report/runner 合同
verification/bench/             → 可执行、版本化、可比较的测量套件
```

测试代码与测评代码都只能单向依赖产品公开边界。`engine/`、`dlcs/`、`desktop/` 和构建入口不得导入 `verification`；Frozen Sidecar 不包含 Bench。

## 5. 命令

```powershell
# 列出或校验所有 suite
python -m verification.bench list
python -m verification.bench validate

# Data-free CoreBench，确定性真实 Loop
python -m verification.bench run core.loop.scripted --repetitions 3

# Context 与 Authority CoreBench
python -m verification.bench run core.context.scripted
python -m verification.bench run core.authority.scripted

# 不经过 LLM 的 Data DirectBench
python -m verification.bench run capability.dbfox_data.direct

# Core + Data + Workspace 的真实组合链
python -m verification.bench run composition.data_workspace.scripted

# Data suite scorer 校准
python -m verification.bench calibrate capability.dbfox_data.agent

# opt-in 真实 Provider Data CapabilityBench
python -m verification.bench run capability.dbfox_data.agent `
  --tag real_provider --tag nightly --repetitions 3

# Data suite 离线重评分
python -m verification.bench replay capability.dbfox_data.agent `
  --trials <trials.json> --output <new-dir>
```

旧 `verification.bench.agentbench` 模块和命令已删除，不提供兼容转发。

## 6. 调研与复用决策

实现前调查了仓库现有生产 RunLoop、pytest fixtures、DLC snapshot/resource authority、旧 60-case runner、CI 和历史设计；也参考了 [pytest 的外置测试与 importlib 建议](https://docs.pytest.org/en/7.1.x/explanation/goodpractices.html)、[Inspect 的 Task = Dataset + Solver + Scorer](https://inspect.aisi.org.uk/tasks.html) 与 [scorer/metric 分离](https://inspect.aisi.org.uk/standard-scorers.html)、[OpenAI Evals 的 data source + grader 合同](https://platform.openai.com/docs/api-reference/evals)。

最终复用现有 Pydantic、pytest、production Session/RunLoop/DLC contracts、System DLC package builder 和旧 Data scorer；没有引入 Inspect/PyYAML 等新依赖。未采用外部 Solver，是因为它会绕开 DBFox durable Agent lifecycle，无法测到真实产品 Harness。新增的 Framework 只覆盖真实共享轴，不包含 SQL/Workspace/GitHub 语义，也没有兼容层、双写或产品测试 hook。`verification/testkit/system_dlc_fixture.py` 只最小组合正式签名与 System DLC 构建入口，避免触碰用户 app runtime。
