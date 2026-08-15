# 可扩展 Runtime 与 Workbench 分阶段实施指南

> 文档类型：跨 ADR 开发计划 / 实施指南
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 上位 RFC：[DBFox 可扩展 Runtime 与 Workbench 架构计划](./extensible-runtime-workbench-program.md)

## 1. 目标

本指南将 Runtime Extension、Memory v4 和 Workbench Shell 三条架构线拆成可审查、可回滚、可独立验收的 PR 序列。

禁止三条线各自形成长期大分支后再集成。每个 PR 必须：

- 保持 main 可运行；
- 不把目标 ADR 描述成已实现能力；
- 有 characterization/contract test；
- 明确新增 seam 与本阶段非目标；
- 同步更新受影响当前状态文档；
- 有 feature flag、shadow path 或兼容读取时，写清退出条件和删除时间。

## 2. 总体依赖图

```text
P0 RFC / ADR / characterization
        ↓
P1 minimal Extension bootstrap
        ↓
P2 Memory v4 shadow ──────────────┐
        ↓                          │
P3 Artifact envelope + Completion │
        ↓                          │
P4 Workbench Shell V2              │
        ↓                          │
P5 InvocationContext / Environment │
        ↓                          │
P6 isolated_process protocol       │
        ↓                          │
P7 Workspace read-only Extension ◄─┘
        ↓
P8 Patch write
        ↓
P9 Terminal / Tests
        ↓
P10 second Extension proof
```

P2 是当前产品 P0，不应被全套 Registry 或前端迁移阻塞。P4 可以与 P2 的后半段并行，但共享 wire contract 的改动必须先进入 P3。

Native/API/MCP/Command Binding 的架构合同在本轮文档中冻结，但不会为了理论完整性预先实现一个通用 MCP client 或万能 Terminal。外部 Provider adapter 按第一个真实集成需求进入 P5 之后的实现阶段，并必须复用同一 Tool materialization、Policy、Observation、Artifact、Effect 和 recovery contract。

## 3. Phase 0 — RFC、ADR 与 characterization

### 目标

冻结共同术语、两个 Kernel、Canonical truth、Extension contribution、ContextSnapshot/PromptBundle、Effect 非事实源、Workbench ownership、Tool execution binding 和 isolated-process 威胁模型。

### PR 切片

1. 合入本 RFC/ADR/指南；
2. 给当前 Tool registry/materialization、Artifact contract、CompletionPolicy、Memory v3、Context budget 和 frontend Workspace 建 characterization tests；
3. 记录当前 AgentBench continuity baseline 和 frontend workflow baseline。

### 退出条件

- 文档 review 通过；
- 所有现有核心测试绿色；
- baseline report 保存 commit/model/provider/test data；
- 团队确认旧 review 不再是独立实施合同。

## 4. Phase 1 — 最小 Extension bootstrap

### 目标

建立 Manifest、namespaced ID、依赖/冲突校验、确定性注册顺序和 freeze，不改变产品行为。

### PR 切片

1. `ExtensionId`/version/dependency/manifest 基础模型；
2. `register_builtin_data_extension()` 包装现有 `register_dbfox_tools()`；
3. Registry fingerprint 基础设施，仅计算实际启用贡献；
4. contract tests：duplicate、dependency mismatch、order、freeze、current Tool schema parity。

### 约束

- 不一次实现所有贡献 Registry；
- 不改变 Tool 名、version、input/output schema、Policy 或 materialization hash，除非有显式 migration；
- 不引入动态发现、第三方加载或 Extension Host；
- 不实现自动发现任意 MCP Server 并把所有 Tool 直接透传给模型。

### 回滚

保留旧 `register_dbfox_tools()` facade，直到所有启动路径切到 manifest 且 parity tests 稳定。

## 5. Phase 2 — Memory v4 P0

### 2.1 Catalog revision

PR：

- DataSource migration 增加 `catalog_revision`；
- 所有 search-visible Catalog mutation 同事务 bump；
- Catalog Tool Observation/Effect 记录执行时 revision；
- 失败不 bump、Run 外 mutation、AI enrichment 和 read-time fence 测试。

### 2.2 Effect/Projection contracts

PR：

- Effect envelope/registry/storage；
- Catalog Effect payload models；
- Memory v4 envelope/models/policy；
- pure Catalog Projector；
- Repository/Service/Rebuilder 边界；
- no rows/secret/schema-copy tests。

### 2.3 Terminal consolidation

PR：

- completed/failed/cancelled 共用 projection service；
- fold eligible succeeded Effect；
- unknown/failed/cancelled/rejected exclusion；
- Run recovery independence；
- terminal transaction rollback test。

### 2.4 Shadow projection/rebuild

PR：

- v3 正常写入；
- v4 shadow 增量计算；
- compare-mode full rebuild；
- hash/watermark/fingerprint telemetry；
- strict missing-projector semantics；
- migration/repair command 或内部 service。

### 2.5 Context integration

PR：

- typed Context Memory；
- read-time datasource/generation/revision fence；
- prior Observation bounded digest；
- SESSION_WORKING_STATE/SESSION_EVIDENCE_INDEX renderer；
- token cap/priority/source telemetry；
- feature flag 切 v4 Context。

### 2.6 Cutover

切换条件：

- deterministic tests 100%；
- shadow incremental/rebuild hash match 100%；
- continuity baseline 不回归；
- no secret/result-value violations；
- long-session tokens 进入平台期；
- failed/cancelled continuation 场景通过。

切换后停止写 v3；保留一个明确回退窗口，再删除 raw dict compatibility。

## 6. Phase 3 — Artifact envelope 与 Data Completion Rule

### 3.1 Artifact expand

PR：

- 添加 `type_id/schema_version` compatible read；
- Kernel envelope validator；
- Data Artifact contracts 注册；
- existing enum/API adapter；
- unknown historical Artifact fallback；
- payload limit/rows/secret/ownership tests。

### 3.2 Wire/frontend compatible read

PR：

- OpenAPI/wire 使用 string `type_id` + schema version + JSON payload；
- 旧 known type adapter 保持现有 UI；
- unknown Artifact metadata projection；
- generated client synchronized。

### 3.3 Completion split

PR：

- Core Completion 保留 lifecycle、pending work、answer/citation/ownership/budget；
- 当前 QUERY_RESULT 逻辑迁为 DataCompletionRule；
- PASS/MISSING/VETO aggregation；
- Rule exception fail-closed；
- decision/evidence parity tests。

### 退出条件

现有 Data Artifact 和完成行为无回归，旧 Conversation snapshot 可读，未知 Artifact 不破坏 Session。

## 7. Phase 4 — Workbench Shell V2

Shell 通过 feature flag 演进，具体细节见 Workbench migration guide。

### PR 切片

1. ShellStore、Navigation adapter、Project-scoped UI state；
2. Project Sidebar 与 Conversation/Data lists；
3. Settings Mode 和 Main Surface；
4. DockView/ArtifactRenderer contribution 基础；
5. Workspace Dock shell/identity/fallback；
6. SQL migration；
7. Table/MultiTable migration；
8. Artifact migration；
9. Project Create/Edit migration；
10. commands/shortcuts/context menu cutover；
11. default-enable Shell V2；
12. legacy deletion。

### 质量门禁

- 每个迁移 PR 运行相邻 component/store/integration tests；
- SQL/Table/Conversation/Datasource/Settings parity；
- same-target dedup；
- Project switch/Settings round trip；
- no duplicated business implementation；
- production build。

### 回滚

在默认切换前保留旧 Shell feature flag。默认切换后只接受 bug fix；达到稳定窗口后删除旧路径，禁止长期双 Shell。

## 8. Phase 5 — InvocationContext、Environment 与 Grant

### PR 切片

1. `ResourceScopeRef` 和 serializable `ToolInvocationContext`；
2. Capability Grant model/authority binding；
3. `ToolExecutionEnvironment` protocol；
4. in-process Database Environment；
5. ToolRuntime/Dispatcher 传递新 context；
6. 现有 `ToolRunContext.require_database()` compatibility facade；
7. Data Tool parity 和 recovery tests；
8. 删除 DB-specific request/context fields 的直接依赖。

### 外部 Binding 规则

从本阶段开始，真实业务若需要外部平台，可以实现 ApiBinding、McpBinding 或 CommandBinding，但必须：

- 先有稳定 DBFox ToolSpec；
- 通过 Policy/Approval/Capability Grant；
- MCP Tool 经过 allowlist/admission/materialization；
- Command 使用固定 executable/subcommand 和结构化 args；
- provider response 经过严格 DBFox output/Artifact/Effect validation；
- Secret 通过 resolver/broker；
- schema/protocol drift 有 frozen version 和 unknown/replan 行为。

不建立与 RunLoop 平行的 MCP Session/Runtime。

### 退出条件

当前 DB Tool 无行为/安全回归；Tool implementation 不接触全局 Service Locator；Grant scope/version/input binding 可测试。

## 9. Phase 6 — isolated_process protocol

### PR 切片

1. parent/worker message schema 和 version/schema-hash handshake；
2. worker lifecycle、heartbeat、deadline、cancel；
3. process group/tree kill 和 late-result suppression；
4. environment allowlist、workspace grant、secret broker refs；
5. structured output、Artifact/Effect envelope、stdout/stderr limit；
6. retry/reconcile/unknown 映射；
7. Windows/macOS/Linux contract tests；
8. executor backend registration 和 saturation/cleanup telemetry。

### 安全门禁

任何 filesystem/network/subprocess Tool 在 backend 完成前不得绕到 `in_process`。不得以普通子进程为第三方 hostile-code sandbox 做产品承诺。

stdio MCP 或 CLI CommandBinding 如果需要本地子进程执行，从本阶段后才可正式启用 isolated execution；网络 MCP/API Provider 仍必须通过 Network Gateway、Grant 和 Secret boundary。

## 10. Phase 7 — Workspace read-only vertical slice

先证明读取链路：

```text
file_read / file_search
→ Observation + FileSnapshot Artifact + FileRead Effect
→ Workspace Projection
→ Next Run Context
→ File Renderer / Dock View
```

### PR 切片

1. Workspace scope/root/version model；
2. filesystem read grant/path/symlink policy；
3. `file_read` bounded window；
4. `file_search` bounded match context；
5. FileSnapshot Artifact contract；
6. Workspace Effect/Projection；
7. prior file digest/Context lane；
8. File renderer/Dock contribution；
9. Extension e2e and long-session tests。

第一种 Extension 可以补充通用 seam，但任何修改必须同时解释 Data 和 Workspace，并禁止 Tool-name/domain branch。

## 11. Phase 8 — Patch write

```text
file_write_patch
→ expected file/workspace version CAS
→ atomic replace
→ CodePatch Artifact
→ Workspace Effect/Projection
→ Diff Renderer
```

### 必须实现

- root/path/symlink/reparse-point fence；
- expected hash/version；
- conflict response；
- temp write + atomic replace；
- crash/reconcile/unknown contract；
- changed-file provenance；
- write approval/policy；
- Secret/result-size scan；
- concurrent external modification tests。

模型不能直接打开 Diff View；用户从 Artifact reference 打开。

## 12. Phase 9 — Terminal 与 Tests

文件读写稳定后才增加 subprocess：

```text
command_exec
run_tests
build
CommandLog Artifact
TestReport Artifact
dbfox.tests.result semantic proof
TestsCompletionRule
```

命令必须是 registered operation 或严格 Policy contract，不默认暴露任意 shell。非幂等命令不使用 retry-safe；进程丢失且结果不可证明时结算 unknown。

这里的 Generic Terminal 与 CommandBinding 分开：稳定外部 CLI 集成优先使用结构化 Command-backed Tool；Generic Terminal 只处理自由度更高的 coding/build/test/排障。

## 13. Phase 10 — 第二 Extension 证明稳定性

使用 GitHub 或 Web read-only Extension 验证：

- 可以选择 Native/API/MCP/Command 中最合适的 Binding，而不改变上层 Tool contract；
- 不修改 RunLoop；
- 不增加 ContextSnapshot domain field；
- 不修改 Memory 根 envelope；
- 不修改 Completion Core；
- 不修改 WorkspaceDock central dispatch；
- 只注册 Tool/Artifact/Semantic/Projection/Renderer/Command contributions。

如仍需新增 seam，必须说明为何 Workspace Extension 未暴露该通用需求，并补充跨 Extension contract test。

## 14. 通用测试层级

### L0 静态/合同

- namespaced IDs、dependencies、freeze；
- schema/model validation；
- forbidden imports/domain switches；
- no rows/secrets；
- wire generation；
- Markdown/internal links。

### L1 deterministic integration

- terminal transaction；
- Memory rebuild；
- Context budget；
- Tool recovery/backend；
- Artifact compatibility；
- Shell identity/state；
- Extension missing modes；
- MCP admission/schema drift 和 Command argument builder。

L0/L1 必须 100%。安全失败是 veto，不能用成功率补偿。

### AgentBench

- continuity；
- duplicate Tool calls；
- topic switch/return；
- result reuse；
- failed/cancelled continuation；
- Catalog invalidation；
- token/latency/tool count；
- Real Provider 重复 trials。

### Desktop

- store/component tests；
- Conversation/SQL/Table/Artifact/Datasource/Settings flows；
- feature flag parity；
- production build；
- 平台差异记录。

## 15. Observability

统一记录：

```text
extension manifests/fingerprints
Tool binding/provider type
Tool backend/capability grants
MCP server/tool materialization hashes
worker protocol/version/exit/timeout/cancel
Effect type/version/bytes
projection version/hash/lag/rebuild status
working-state bytes/tokens
cross-run duplicate calls
Artifact type/schema/fallback
Completion rule decisions/errors
Dock view type/canonical key/dedup/fallback
Shell feature flag and migration state
```

不得记录 Secret、完整文件、结果行、长 stdout 或未脱敏网络/MCP 内容。

## 16. Rollout 与回滚

- Schema 迁移使用 expand/compatible-read/switch/delete；
- Memory 使用 shadow projection 和 Context feature flag；
- Artifact 使用旧 known type adapter + 新 envelope compatible read；
- Workbench 使用 Shell V2 feature flag，稳定后删除旧 Shell；
- Backend 在注册新 Tool 前完成 protocol/platform gate；
- External Binding 出现 schema/protocol mismatch 时 fail-closed/replan，不自动猜兼容；
- Extension 缺失不得静默 drop state；
- 每个临时兼容层必须有 owner、删除条件和最晚删除 phase。

回滚不能恢复已被删除的 canonical 数据，因此所有 destructive migration 在严格 rebuild/backup/compatibility 验证前禁止执行。

## 17. PR Review 模板

每个实现 PR 至少说明：

```text
问题与当前代码事实
本 PR 所属 Phase/ADR
新增或迁移的所有权 seam
行为变化与不变量
兼容/迁移/回滚
执行的测试和平台
新增 telemetry
本 PR 明确不做什么
临时 compatibility 的删除条件
```

Code review 必须检查：

- 是否新增领域 Kernel branch；
- Tool Binding 是否绕过 materialization/Policy/settlement；
- Effect 是否复制事实或 authority；
- Artifact/Context/Memory 是否泄露大结果或 Secret；
- Registry fingerprint 是否过宽；
- ShellStore 是否复制业务对象；
- View identity 是否由 contribution 生成；
- unknown/missing Extension 行为是否明确；
- 文档是否把目标错误描述为当前能力。

## 18. Program 完成定义

本 Architecture Program 完成，不等于所有未来 Extension 已实现。它完成时至少满足：

1. Memory v4 正式切换并通过 rebuild/continuity；
2. Artifact envelope 和 DataCompletionRule 完成迁移；
3. Workbench Shell V2 默认开启，Legacy Shell 删除；
4. InvocationContext/Environment/Grant 生效；
5. isolated backend 通过平台和安全合同；
6. Workspace read/write Extension 端到端可用；
7. Terminal/Test 具备受限、安全、可恢复合同；
8. 至少一种 External Binding（API/MCP/Command）通过真实 Extension 验证 provider-neutral Tool contract；
9. 第二种 Extension 无 Kernel 领域分支接入；
10. 当前架构文档同步为已实现状态，临时 compatibility 已清理。
