# DBFox Benchmark System：Core、Capability 与 Composition

> 文档类型：质量工具
>
> 状态：当前
>
> 最后核验：2026-08-24

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
│   └── loop/                        # scripted Provider + verification tool + production RunLoop
├── capabilities/
│   └── dbfox_data/
│       └── agent/                   # 60-case Data agent dataset/scorer/runtime
└── composition/                     # 仅在存在真实跨能力 suite 时创建
```

每个 suite 的 `suite.json` 必须声明：

- `suite_id` 与语义版本；
- `subject.kind`：`core`、`capability` 或 `composition`；
- 被测 `components`；
- 仅作为支持条件的 fixtures；
- suite-owned dataset；
- 指标名称、方向、单位与解释。

Core suite 不能把 `dbfox.*` DLC 写进被测主体；Capability suite 只能有一个 capability owner；Composition suite 至少有两个被测 component。失败结果因此能先归因到明确 owner，而不是落入一个万能 AgentBench。

## 3. 当前套件

### 3.1 `core.loop.scripted`

不启用 Data/Workspace/GitHub DLC。Scripted Provider 和 `verification_read` 只是外部刺激，trial 执行生产 admission、lease、RunLoop、tool invocation 与 durable Turn。当前测量直接完成、单工具闭环和两步工具闭环的成功率、Turn、工具调用及重复调用。

这不是 Core 合同测试的替代品：`verification/tests/agent_core` 回答状态机是否符合不变量；CoreBench 回答候选 Harness 在版本化任务上用了多少 Turn/Tool、是否改善。

### 3.2 `capability.dbfox_data.agent`

原 60-case 数据集完整迁入这个 suite。被测主体是 `dbfox.data` 的 agent-mediated 能力；Core Runtime 和 SQLite seed 是支持条件。它继续使用 production DLC snapshot、Data operation/resource discovery、服务器授权、真实 RunLoop、SQL safety/execution 和 Artifact/Evidence，并由 Data-owned scorer 判断结果集、轨迹、引用与安全。

Data scorer 校准、离线 replay 和真实 Provider 重复运行仍由该 capability suite 自己拥有。Framework 不理解 SQL、Table、Catalog 或 golden SQL。

### 3.3 Composition

当前不创建空目录或占位 Runner。只有出现真实的 Data + Workspace、多数据库或跨 Capability 数据集、资源组合和 scorer 后，才增加 `verification/bench/composition/<suite>/`。Composition scorer 负责最终目标、跨能力 handoff、Artifact lineage 和 authority，不能把单 DLC 的领域规则复制到 Framework。

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

最终复用现有 Pydantic、pytest、production Session/RunLoop/DLC contracts 和旧 Data scorer；没有引入 Inspect/PyYAML 等新依赖。未采用外部 Solver，是因为它会绕开 DBFox durable Agent lifecycle，无法测到真实产品 Harness。新增的 Framework 只覆盖真实共享轴，不包含 SQL/Workspace/GitHub 语义，也没有兼容层、双写或产品测试 hook。
