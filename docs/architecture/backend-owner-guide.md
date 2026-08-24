# Python Engine 代码导览

> 文档类型：维护者导览
>
> 状态：当前
>
> 最后核验：2026-08-24

## 1. 先理解所有权

DBFox 后端不是一个包含所有业务领域的单体：

```text
Electron Host
  └─ FastAPI Sidecar
       ├─ Agent/Workbench Core
       ├─ DLC verifier/compiler/snapshot host
       └─ Capability DLCs
            ├─ dbfox.data
            ├─ dbfox.workspace
            └─ dbfox.github
```

Core 拥有生命周期、authority 和通用 envelope；DLC 拥有领域语义和领域状态。判断代码归属时先问：它是否理解 SQL、文件路径、GitHub repository 等 capability 名词？如果是，它不应进入 Core。

## 2. Core 入口

| 路径 | 职责 |
| --- | --- |
| `engine/main.py` | FastAPI 应用装配与进程入口 |
| `engine/api/` | Core HTTP/SSE 边界、Conversation、Agent、DLC operation 与 Artifact view |
| `engine/agent/` | Session/Input/Run/Turn、Context、Artifact/Evidence、Provider adapter、RunLoop 与终态 |
| `engine/tools/runtime/` | Tool registry、materialization、admission、policy、approval、attempt 与 observation bounds |
| `engine/dlc/` | package verification、安装/激活、contribution compiler 和 immutable snapshot |
| `engine/runtime_composition.py` | 只按 typed contributions 组合 Resource、Tool、Context、Artifact View 和 Workbench |
| `engine/models.py` | Core durable ORM；不得出现 Data/Workspace/GitHub domain model |
| `engine/migrations/` | Core schema 迁移与一次性历史领域数据 cutover |

应用由 `python -m engine.main` 启动。HTTP/SSE 只绑定 loopback 并统一校验 Host 注入的短期 Token。Electron Main 的 `EngineSupervisor` 是生产 Sidecar 生命周期权威。

## 3. Agent 真实链路

```text
Conversation resource intent + message selection
  → discover_project_resources(project_id)
  → authorize_project_resources(...)
  → canonical, version-fenced ResourceScopeRefs
  → SessionRepository.admit()
  → SessionCoordinator lease/promote
  → production RunLoop
  → native provider function calling
  → Tool materialization/admission/dispatch
  → Observation + Artifact + durable events
  → Terminalizer
```

`AgentSessionInput.resource_refs_json` 是 Run authority 的唯一事实源。Project membership、左栏 focus、Conversation intent 都不能直接执行 Tool。资源运行时使用 `ResourceKey(kind, id)`；需要单资源的 Tool 必须调用 `require_one(kind)` 并在歧义时失败。

## 4. Artifact、Evidence 与 Context

Core Artifact 只保存通用 envelope、opaque payload、资源 refs 和 capability-owned type。Evidence 通过 `artifact_id` 指向耐久来源，不镜像 SQL fingerprint 等领域数据。Artifact View 由当前 snapshot 中的 provider 解析，Core API 返回 `resourceVersion`、`sourceFingerprint` 等通用字段。

Context assembler 组合 Conversation history、授权资源摘要、Capability context fragments、相关 Artifact/Evidence 和受控历史召回。完整结果留在 capability store；Context 只承载有界摘要。已退役的 Data Catalog Memory v4 projection 不属于当前 Runtime。

## 5. Capability DLC

first-party Data/Workspace 与第三方 DLC 使用同一条：

```text
.dbfox-dlc package
  → signature/manifest verification
  → immutable install snapshot
  → public Extension API
  → typed contributions
  → RuntimeContributionSnapshot
```

主要目录：

| DLC | 领域所有权 |
| --- | --- |
| `dlcs/dbfox_data/` | ConnectionProfile、DatabaseResource、Catalog、SQL、结果、备份与 Data Workbench |
| `dlcs/dbfox.workspace/` | Workspace binding、文件资源、文件工具与 Workspace Workbench |
| `dlcs/dbfox.github/` | GitHub binding、repository/resource、operations 与 Workbench |

DLC durable state 放在自己的 state store，只引用 Core `project_id` identity，不与 Core SQLite 建跨库 FK，也不建立万能 `ProjectResourceBinding(config_json)`。

## 6. 事务与安全

- SQLite/Alembic 是 Core 耐久事实源；事件先持久化再发布。
- 秘密只进 OS 凭据库；业务状态只保存 opaque credential ref。
- DLC Tool 只得到窄化 `ExtensionToolRunContext`，不能拿 ORM Session、Application container 或全局 vault。
- Policy/Approval 只理解 tool risk、capability 和冻结资源；SQL AST policy 属于 Data DLC。
- 取消、断线、resource generation 变化后不自动重放非幂等动作。
- 公开错误使用固定 safe catalog；日志和 Problem Details 不包含 SQL、路径、secret 或异常正文。

## 7. 修改时的定位规则

1. 先查 `docs/architecture/implementation-map.md`，仓库存在 `.codegraph/` 时先用 CodeGraph 定位真实调用链。
2. 修改 Core authority/lifecycle 时，在 `verification/tests/agent_core/` 用合成 namespaced resource 验证，不依赖 Data。
3. 修改 capability 语义时，在对应 DLC 实现，并在 System/Integration suite 通过公开 package/snapshot 链验证。
4. 不在产品包中加入 fixture、fake provider、测试 Repository 或 benchmark hook。
5. API 合同变化后运行 `desktop/npm run generate:api`，提交生成结果。

## 8. 验证架构

产品代码位于 `engine/`、`dlcs/`、`desktop/`；测试与测评位于 `verification/`。依赖只能从 verification 指向 product。Agent Core、System、Integration 各自拥有 fixture 生命周期，只共享 `verification/support/` 中的无状态辅助。

Bench 是外部测量仪器：CoreBench 测 Kernel/Harness，CapabilityBench 测单 DLC，CompositionBench 测真实组合；它们准备数据和 Provider 边界、调用 production RunLoop、读取耐久 trace、在运行后评分，不复制 Session 状态机、Tool retry、Resource authority 或 capability executor。完整命令和 marker 规则见 [`verification-system.md`](./verification-system.md) 与仓库 `AGENTS.md`。

## 9. 历史代码边界

旧 Core DataSource/SQL/Catalog/Backup 模块已删除。Alembic migration 与安全 retirement cleanup 可以读取旧表名，因为它们承担一次性迁移/删除；这一例外不得被生产调用方引用，也不得演变成双读或 fallback。旧设计讨论保存在 `docs/archive/`，只用于追溯决策。
