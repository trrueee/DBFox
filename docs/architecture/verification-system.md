# DBFox 测试与测评系统边界

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-24
>
> 适用范围：Python 自动化测试、Core/Capability/Composition Bench、Capability DLC 合同与 CI

## 1. 结论

DBFox 的产品实现与验证系统是两个物理分离、依赖单向的代码世界：

```text
engine/ + dlcs/ + desktop/       verification/
          product  <------------- tests / bench / testkit
                   只允许这一方向
```

`verification` 可以导入并驱动生产模块；`engine`、`dlcs`、Frozen Sidecar 构建入口不得导入 `verification`。验证系统不向生产代码注入测试开关、测试 Repository、测试 Tool Runtime 或第二套 Agent loop。

“走真实链路”的含义不是必须把所有测试都变成进程级 E2E，而是被测边界以内不替换生产控制流：

```text
SessionRepository.admit
  → server-authorized ResourceScopeRef
  → Session lease / promote
  → production RunLoop
  → Provider Adapter boundary
  → Tool materialization / Policy / Approval
  → ToolDispatcher / Resource resolver
  → Observation / Artifact / Terminalizer
  → durable rows and events
  → external scorer
```

测试可以控制 Provider 返回、时钟、网络服务和数据库 fixture，因为这些位于被测系统的外部边界；不得替换上图中的内部节点后仍把结果称为闭环测评。

## 2. 目录与所有权

```text
verification/
├── conftest.py                 # 进程级隔离，必须先于 engine import 生效
├── testkit/                    # 只供验证使用的 fixture 构建和外部边界控制
├── tests/
│   ├── agent_core/             # Session/Run/Turn、Context、Policy、Tool、终态与恢复
│   ├── system/                 # API、持久化、DLC Host、产品 composition、发布与工程合同
│   ├── integration/            # 真实数据库、真实 Provider、跨进程和平台边界
│   └── bench/                  # dataset/scorer/reporting 与确定性故障场景合同
└── bench/
    ├── framework/              # 通用 manifest、统计、报告和比较
    ├── core/                   # Agent Kernel/Harness 测量
    ├── capabilities/           # 单个 DLC 的 direct/agent 测量
    └── composition/            # 真实跨能力 suite；不创建空占位实现
```

目录按“主要被测对象”归类，而不是按使用了什么 fixture 归类。一个 Agent Core 状态机测试可以使用合成 ResourceRef；只有当判断目标是 `dbfox.data` 的发现、解析或 SQL 语义时，才属于 capability/system 或 integration。

各 suite 自己拥有数据库生命周期和 fixture 组合，不从另一个 suite 的 `conftest.py` 导入隐式环境。`verification/support/` 保存无状态 metadata/迁移辅助；`verification/testkit/` 保存 Scripted Provider、synthetic resource 和基于正式 package builder 的隔离 DLC fixture。二者都只能控制被测系统的外部边界，避免 Agent Core、System、Integration 因 fixture 继承形成隐藏耦合。

## 3. 三类验证对象

### 3.1 Agent Core

Agent Core 测试回答 provider-neutral 问题：admission 是否原子、authority 是否冻结、工具是否按策略物化、租约和终态是否正确、上下文和事件是否可恢复。合成 Tool 或 scripted Provider 只能作为外部刺激，不能实现另一套调度器。

Core 测试的失败首先归因于 `engine/agent`、`engine/tools`、`engine/policy` 或 Core persistence；不能用具体 DLC 的业务正确性补偿 Core 失败。

### 3.2 Capability DLC 与产品组合

DLC 合同分别验证 package/manifest、公开 Extension API、contribution compilation、资源 discovery/resolver、operation、tool、artifact 和 Workbench contribution。first-party DLC 也必须经过与第三方 DLC 相同的 verify → install/bootstrap → compile → snapshot 路径。

跨 Core 与 DLC 的产品场景必须显式建立 Project、调用真实 DLC contribution 创建资源、通过 `authorize_project_resources()` 取得 canonical version，再把 frozen refs 交给 `SessionRepository.admit()`。禁止重新写入 Core `DataSource` 或伪造 datasource compatibility 字段。

### 3.3 CoreBench、CapabilityBench 与 CompositionBench

Bench 是产品外部的测量仪器，按 Subject Under Test 分为：

- CoreBench：测量 provider-neutral Agent Kernel/Harness；
- CapabilityBench：测量一个 DLC 的领域能力；
- CompositionBench：测量 Core 与一个或多个 DLC 组合后的用户任务。

它们共同只拥有：

- 版本化任务与受控 seed；
- 隔离 runtime 和外部服务准备；
- Provider 凭据/脚本化输出边界；
- 从耐久事实读取 trace；
- 确定性 scorer、统计、脱敏报告和 JUnit。

Framework 只理解 suite identity、subject、metric、statistics、report 和 comparison，不理解 SQL、File、GitHub 或 Memory 领域语义。各 suite 自己拥有 dataset、runner 和 scorer，但不拥有 Session 状态机、SQL executor、Resource authority、Context projection 或 Tool retry。真实评测 runner 必须使用 production RunLoop；历史接口失配直接失败，不用 compatibility adapter 继续跑分。

当前确定性测量覆盖 Core Loop、Context、Authority、Data direct operations，以及 Data + Workspace 的双资源组合。每个 manifest 还声明 provider mode 与 repetition 上限；Provider 是执行矩阵维度，不形成第四类 Bench，也不拥有另一套 Runner。

## 4. 允许替换与禁止替换

| 边界 | 允许 | 禁止 |
| --- | --- | --- |
| Model Provider | scripted adapter、真实 Responses API | 解析 Thought/Action 文本、另写 agent solver |
| 外部数据 | 临时 SQLite、隔离 MySQL、版本化 seed | 在 scorer 中伪造生产 Artifact |
| 时间/故障 | fake clock、超时、429、断流 | 跳过 production retry/cancel/terminalizer |
| Capability | 签名测试 DLC、first-party System DLC | 在 Core 注册测试专用工具 |
| Authority | 请求 identity 后由服务端授权 | 测试直接伪造更大 ResourceScopeRef 集合 |
| 观测 | 查询生产耐久表和公开事件 | 测试 hook 复制一套 trace 状态 |

## 5. 发现、构建与门禁

`pyproject.toml` 将 `testpaths` 固定为 `verification/tests`，并采用 pytest 的 `importlib` import mode。这样 pytest 不需要把测试目录隐式插入产品包，且无参数运行不会递归收集 vendored/generated tests。此选择遵循 pytest 官方对 application code 外置测试和 importlib mode 的建议。

工程合同必须验证：

1. `engine/tests`、`engine/agent/tests` 和 `dlcs/*/tests` 不存在；
2. 产品 Python import graph 不指向 `verification`；
3. pytest 唯一发现根为 `verification/tests`；
4. Frozen Sidecar 构建不包含 verification；
5. CI 分开运行 Agent Core、System、Integration 和 Bench gates；
6. 旧 `scripts.agentbench` 与 `verification.bench.agentbench` 入口都不存在，不提供兼容转发；
7. CoreBench manifest 不能把 Capability DLC 声明为被测主体。

## 6. 调研与复用决策

调查范围包括仓库现有 pytest fixtures、旧 AgentBench、CI marker、production composition、DLC operation/resource seams，以及 pytest 官方 test layout/import mode 建议。最终复用现有 pytest、SessionRepository、RunLoop、RuntimeContributionSnapshot、DLC operations 和 authority admission；没有新增测试框架或运行时依赖。

未引入 Inspect AI 等完整 eval framework：DBFox 已有耐久 Run/Turn/Tool/Artifact 事实和 scorer/reporting 合同，替换 runner 会形成第二套 solver。保留外部框架的 Dataset/Scorer/Report 分层思想，但用最小现有代码实现。

本次不新增兼容层或双入口。迁移债务只能表现为仍待重新归类的测试文件，不能表现为产品代码导入测试工具或旧命令继续转发。

## 7. 验证命令

```powershell
python -m pytest verification/tests/agent_core -q --tb=short `
  -m "not e2e and not integration and not real_llm"
python -m pytest verification/tests/system -q --tb=short `
  -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"
python -m pytest verification/tests/bench -q --tb=short
python -m pytest verification/tests/integration -q --tb=short
python -m verification.bench validate
python -m verification.bench run core.loop.scripted
python -m verification.bench run core.context.scripted
python -m verification.bench run core.authority.scripted
python -m verification.bench run capability.dbfox_data.direct
python -m verification.bench run composition.data_workspace.scripted
python -m verification.bench calibrate capability.dbfox_data.agent
```
