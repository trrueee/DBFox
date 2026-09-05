# Artifact 的 Invocation 权威审议

> 文档类型：质量审议
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Tool 成果结算、Agent 内成果读取与来源校验；Extension API v2

## 结论与证据范围

**结论：accepted。采用“持久 Invocation 证明直接来源；显式 `DERIVED_FROM` 证明同 Run 派生来源”的完整修复。** 现有公开关系合同足以保留 Visualization，无需新增 SDK。只将写侧改成 Invocation 子集、导致现有 Visualization 退化的方案为 needs_revision，不接受集成。不能用 Run 初始引用、历史 Invocation 的并集、空引用或新建 Run 掩盖问题。

本页保留架构阶段的决定与核验范围；后续角色转任、实际实施范围及结果见[实现验证](artifact-invocation-authority-verification.md)。

本次为独立 Host correctness Architecture 审议。审议者此前没有实现本 Host 修复；此前的 Scene Backend、Voxel Workbench 身份不算这些 DLC 的独立红队。本阶段只读生产代码、历史与合同，只新增本报告，不修改源码、测试、公共 SDK 或用户基线。

源码基线为 `codex/creative-artifact-authority`，HEAD `f934f997e14f4e47fb24e3907dfcb13f4251dde0`，叠加 Director 保留的用户未提交基线。工作树没有 CodeGraph 索引。Scene、Voxel 各自正式 RunLoop 已复现“领域提交成功，成果结算报 `TOOL_OUTPUT_CONTRACT_FAILED`”，这两项运行证据来自 Director 与领域验证者，**不是本审议者重跑的测试**。本次独立证据是以下源码及 Git 调查；修复后的运行结果仍待验证。

| 已核验入口 | 当前行为及意义 |
| --- | --- |
| [现行权威合同](../architecture/agent-core-capability-dlc-contract.md)，第 1、6 节 | 调用时按 Project discovery 与 selector 绑定精确 Invocation refs；Input 只是不可变 admission fact。 |
| [Dispatcher](../../engine/agent/tool_dispatcher.py)，`request` 附近 295–336 | 每次调用重新 discovery；Artifact selector 从同 Run Artifact 取 refs；结果写入 Invocation。 |
| [Invocation Repository](../../engine/agent/repositories/tool.py)，`request` | 验证 Turn/Run/Session、冻结 materialization、owner/package、wire tool identity、input 与 refs。 |
| [Artifact Repository](../../engine/agent/repositories/artifact.py)，`persist_drafts` / `_prepare_drafts`，约 216–293 | 已收到 Invocation ID/Turn/tool，却仅按 `resource_refs_for_run()` 验证成果 refs。 |
| [ToolSettlement](../../engine/agent/tool_settlement.py)，约 51–141 | Artifact、Observation、Invocation 成功结算在同一 metadata transaction；不能回滚已独立提交的 DLC store。 |
| [Dispatcher](../../engine/agent/tool_dispatcher.py)，约 538–576 | draft 合同异常转为不重试的 `TOOL_OUTPUT_CONTRACT_FAILED`。 |
| [Artifact Repository](../../engine/agent/repositories/artifact.py)，`available_artifact`，约 382–433 | 同时以生产 Run 与消费 Run 的初始 refs 校验，写侧修完仍会拒绝合法同 Run 后续读取。 |
| Git `132a29fb1b27e60ca927c03ce67314e4b4bc8776` | 2026-08-25 引入按 Invocation 绑定，包括持久列、Dispatcher、resolver 及测试，但没有修改 Artifact Repository；这是未闭合的迁移，不是新领域需求。 |

## 冻结的最小写入规则

1. `persist_drafts` 保持现有入口，不增加调用方可传的 trusted refs。非空 batch 必须先在同一 metadata 写事务中，从 `AgentToolInvocation` 按 ID 读取持久行；复用 `begin_agent_write` 和现有 Session lease 校验，不自建锁或重试机制。
2. 在第一条 Artifact 插入前证明以下等式：Invocation ID 存在；`invocation.session_id == lease.session_id == run.session_id == turn.session_id`；`invocation.run_id == supplied run_id == turn.run_id`；`invocation.turn_id == supplied turn_id`；`invocation.tool_name == supplied wire tool_name`。Run、Turn 本身必须存在，Run lease 也必须通过既有 token fence。不能仅靠外键证明这些交叉归属。
3. Tool owner/package/contract 的权威仍为持久 Invocation 与该 Turn 的冻结 materialization；执行端继续复用 `_prepare_execution` 的 `require_current_tool` / `require_reconciliation_tool`。不要查询“目前同名 tool”替代冻结身份，不向 DLC 开放来源覆盖字段。
4. 从持久行严格解码 `resource_refs_json`。无效 JSON、非法 ref、重复 `(kind,id)`、缺失行或身份错配均拒绝；不回退 Input、Project 当前列表、传入 domain object 或其他 Invocation。`[]` 是明确无资源权限，不是未知权限。
5. 每条 draft 的精确 `(kind,id,version)` 必须来自该持久 Invocation，或下文规定的显式、可信 `DERIVED_FROM` 来源。保留 `str | int | None` 的正式值语义，不改写为当前 version，也不把 `1`、`"1"` 或缺 version 视作等价。整个 batch 的 key、payload、relation、draft pointer 与 refs 先验证，再写入。
6. Host 从已核验持久行生成 `provenance.tool_invocation_id/tool_name`；不采用 DLC payload 声称的生产者。DLC 的 relation 只是依赖声明，必须由 Host 读取真实来源逐边证明后才可继承。允许同一领域内容在新 revision 重复；结果 payload 的版本与 envelope 的来源版本是不同事实，不能凭空互换。
7. 状态必须兼容真实恢复：普通成功结算发生在 `running`；`reconcile` 可发生在恢复后的 `requested`。不可统一要求写前 `succeeded`，也不可允许已完成 Invocation 再生成一批 Artifact。沿用现有生命周期及最终 settlement 的原子状态转换，回归测试覆盖恢复状态。
8. 身份/refs/批次合同错误统一用 `ArtifactDraftContractError` 进入现有安全错误路径；lease/cancellation 保持自己的控制错误。整个事务失败后没有部分 Artifact、选中状态或成功 Observation。已提交领域写入不得重放；恢复只由该工具既有 receipt/reconciliation 证明原结果。

新建文档工具通常以 library 为输入权威；它的成果不能宣称未冻结的新 document ref。随后同 Run 的编辑 Invocation 可通过重新 discovery 取得新 document/version。此规则不要求改变 Run 的初始 Input。

## 来源继承与执行权限分开

[Artifact/Representation 主合同](../architecture/artifact-representation-visualization.md)第 6.1 节已将 `resource_refs` 定义为精确来源，规定 `Result → SQL`、`Visualization → Result` 的 child→parent `DERIVED_FROM` 关系。不能把所有来源依赖都当作派生工具的私有资源执行权限。

冻结的来源证明为：每个输出 ref 必须精确存在于生产 Invocation refs，或该输出**明确声明的**可信同 Run `DERIVED_FROM` 父成果 refs。这是对单个成果依赖边的校验；不是所有 Run refs 的合并，也绝不能写回 Invocation、Input、`context.scopes()` 或 ResourceHandle resolver。

### 逐边验证规则

1. 现有来源必须 completed，Session/Run 与派生成果相同；其 Host provenance 定位真实生产 Invocation，Invocation/Artifact/Turn/Run 归属和 wire tool 身份相符。生产者已成功结算，来源 refs 自身也要按相同规则证明。跨 Turn 的同 Run 来源合法，不错误要求父子 Turn 相同。
2. 只有 `DERIVED_FROM` 可贡献继承 refs。`SUPPORTS`、`VALIDATED_BY`、payload 字符串、被 Tool 声称读过或任意已知 Artifact ID 都不贡献权限。`DERIVED_FROM` 本身也不是充分证明：目标不存在、跨 Session/Run、失败、缺 Invocation、损坏 provenance 或未经证明的 refs 均不能作为来源。
3. 仅能继承父成果实际持久 refs 的精确版本，不能继承其生产 Invocation 中没有写入该父成果的其他 scope。多个显式父成果可贡献不同 refs；仍执行已有 16 ref 与唯一 `(kind,id)` 约束，不合并同 ID 的不同版本。
4. 同一 batch 的 `draft_key` 来源按依赖次序验证；可以拓扑验证非循环引用，再一次提交，不要求先落盘或创建伪 Invocation。Visualization 的 inline dataset→visualization 两 draft 必须继续成功。payload pointer 仅替换 ID，不能替代正式来源关系。
5. 对需要作为证明的派生链用 visiting/verified 集合检测循环与重复访问，同一操作内 memoize；不保存新的权限缓存。自循环、互循环、缺可信叶节点不能自举出权限。新 batch 的 `DERIVED_FROM` 图应无环；其他关系不因为这个修复被改成新协议。
6. 验证须有确定预算；建议本次内部上限为每次证明最多 256 个不同 Artifact/draft 节点、256 个来源边、深度 64，超过则显式合同失败，不能截断后放行。这些是拟冻结的安全预算，需测试边界并核查已有 fixture；若真实合法场景超过，调高同一实现的有界常量，不新增旁路。每个节点仅取需要的行，避免指数遍历。
7. 若输出 ref 已由自己的 Invocation 证明，不必借无关历史 relation 扩大来源。旧的跨 Run relation 可保留为血缘记录，但不能贡献继承权限；读取该关系也仍遵循跨 Run 原有约束。

伪造关系只能声明一个系统已经允许该 Run 读取的公开成果，不能伪造目标行或根生产证明；它不授予私有 handle。Host 证明的是来源依赖合法，不能证明任意 DLC 的输出语义确实使用了来源；领域 payload 校验、Representation provider 和 DLC 信任边界仍承担各自职责。

## 读取：公开成果与当前资源授权各有边界

同 Run 的 `context.artifact()` / JSON Representation 是正式公开成果消费，不是获取其他 owner 的私有资源。读取必须证明当前 Session/Run 归属、Artifact completed、生产者及其上述派生链合法；**不要求无资源 Composition Tool 将来源 refs 冻结为私有执行 scope**。因此 `available_artifact` 应移除同 Run 两边对初始 Input 的错误检查，先做来源证明；不是将检查简单删掉。

跨 Run 读取继续保留消费者初始 Input 的精确 refs、先后顺序、owner Run terminal、同 Session 与非 INTERNAL 约束。生产侧改用真实生产证明。`resource_refs_for_run()` 本身不改，它仍正确表达不可变 Input；不猜“最近 Invocation”，不把历次 scope 做并集。

没有 provenance 或对应 Invocation 的历史资源成果不能凭 Run/Project/其他 Invocation 获得新权限；可继续通过既有用户历史展示路径显示 envelope，但不得冒充可执行来源。无资源历史成果也不能推导任何资源权限。损坏 JSON 不能经 `_domain()` 的展示 fallback 被当作空权限事实；权威校验应严格解码。

**执行资源仍只来自当前消费 Invocation。** `SqlExecuteReadonlyTool` 当前用 `database_id` selector 取得当前 discovery ref，[sql_admission](../../dlcs/dbfox_data/backend/sql_admission.py)精确比较 SQL/Safety Artifact refs；不能因公开成果可读而跳过这一步。`ResultInspect/Profile` 使用 `artifact_selector_field`；当前 binder 仅提取 Artifact ref，未比对 discovery。应补同 `(kind,id,version)` 的当前成员校验，不将旧版本替换为新版本，之后继续 owner resolver 的二次 fence。Data resolver 对过期 generation 的拒绝必须保持。

读取 immutable 旧成果本身可以合法；将旧 SQL 校验用于执行则必须失效。创作 DLC 的历史 Representation 仍由 owner 解析固定 revision；公开成果继承不能变成对历史或当前资源的写权限，领域写入继续 CAS。两者是不同边界，不能用“历史可读”放宽当前执行版本。

### Admission、关联与 Representation

- Dispatcher 的 `get_for_run` 目前只做同 Session/Run envelope 查找。它可作为候选定位，但用于绑定 Artifact selector 前，必须证明 completed 和上述生产链，再验证当前 discovery 的 exact ref；不能从伪造、缺生产者或失败成果导出 Invocation refs。复用 repository 生产校验函数，避免重复规则。
- `artifacts_relating_to_for_run` 当前只检查 Session/Run 与 relation。用于 Tool context 时，source 与每个返回 Artifact 都应再经过相同公开成果 loader 的 provenance 检查；否则 relation 将旁路新 fence。不要机械限制所有历史 provenance relation 的写入范围；“可以记录来源关系”不等于“有权限读取来源”。
- Agent 的 `read_artifact_representation` 及其 provider context 已共同使用 `load_artifact`，修正这个 loader 即覆盖根 Artifact 与 related Artifact，不新建 Representation 协议。只读、JSON 类型、取消、deadline、冻结 provider snapshot 和 provider 版本校验保持现状。
- `referenced_artifacts_for_run` 用于 Context/Plan/Terminalizer，当前扫描 Observation IDs，再以初始 Input 检查。不能为修同 Run Tool 而变为历次 Invocation 的资源并集。若要让已合法消费的跨 Run 成果进入上下文，应从引用它的具体 Observation→Invocation 证明当时合法消费，另附回归；本 P1 不新增这种能力。
- HTTP [agent_results](../../engine/api/agent_results.py) 走用户鉴权、root completed、同 Session 的 bounded relations 与 active provider，**没有此处的 Run 初始 refs 检查**。不能把 Agent 执行 fence 生搬到用户历史浏览，也无需修改前端 Artifact navigation。用户只读历史可用不意味着 Agent 获得资源执行权。
- isolated worker 当前没有注入 Artifact loader/Representation reader；本修复不凭空承诺其读侧能力。其输出仍由 Host 同一 settlement 校验。测试要分别标明 in-process 读侧与 isolated 输出结算，不能混称全覆盖。

## 现有 Composition 的完整兼容路径

[VisualizationCreateTool](../../dlcs/dbfox.visualization/backend/tool.py) 的 `execution` 没有 `required_resources`；读取 `source.artifact_id` 的公开 DataFrame Representation，然后把来源 `resource_refs` 复制到新成果。Dispatcher 因此持久化 **空 Invocation refs**。现有输入还把选择放在嵌套 `source.artifactId`，既有 owner-only `ToolResourceRequirement` 也不能直接表示任意其他 DLC 的公开成果来源。

源码已经显式声明 `DERIVED_FROM` 并继承 source refs；上述规则正好覆盖这一现有行为。无需嵌套 selector 扩展、跨 owner ResourceRequirement、新 SDK 字段或 Visualization 特判。工具仍没有其他 owner 的私有 handle，读取走已冻结 provider 的正式 Representation，写入仅继承经 Host 逐边证明的公开成果依赖。

禁止扫描任意输入字符串猜 Artifact ID、借 `publishes_artifact_references` 推断资源需求、把全部同 Run Artifact 变成 authority，或为空 Invocation 回退 Input。必须以 Data Result→Visualization 的真实 RunLoop 作为集成门禁，不能先合入退化版本再承诺未来修复。

## 宪章七个问题

以下对应 [Core Kernel 宪章](../architecture/core-kernel-constitution.md)第 6 节的七问；第 5、7 节也将 Runtime correctness 与持久化归属 Core。

| 问题 | 审议回答 |
| --- | --- |
| 1. 正确性问题或两项真实能力需求？ | 是 Core authority 正确性问题；Scene 与 Voxel 正式 RunLoop 为两个独立复现来源，另有 Data 的 Artifact selector 读侧路径。 |
| 2. 现有贡献点为何不够？ | Tool 已提交合法 draft，错误在 Host 内部用错事实源。DLC operation、context、Representation 都不能修 Host repository 结算权限。 |
| 3. 为何不能在能力 owner 修复？ | owner 无权改冻结 Input/Invocation 或 Host Artifact row。清空 refs、新开 Run、假成功会损坏可追溯性和同 Run 能力。 |
| 4. 中立、owner bound、fail closed？ | 只比较通用身份、ResourceScopeRef 与已有 DERIVED_FROM；没有领域名/provider 分支。缺行、错配、坏 JSON、版本不符、非法来源链拒绝；派生依赖不授予私有 handle。 |
| 5. 是否新增中间层、双写或 fallback？ | 不新增存储、权限缓存或兼容层。复用现有 repository 的少量验证函数、write transaction 和 lease。Invocation 行是唯一执行事实；Input 保持原职责。 |
| 6. API v2、冻结 Run 与历史兼容？ | 不改公开符号、数据列或 envelope；复用既有 DERIVED_FROM 保留 Visualization 无私有 scope 的派生行为。现有冻结 Invocation 可直接用，历史无证据不扩权；必须以真实组合测试证明。 |
| 7. 需要哪些证明？ | 下表的 repository/RunLoop/恢复/SQL stale/Representation/Composition，以及 API v2 surface 与工程合同；迁移不新增 schema，但验证旧行拒绝扩权与 envelope 可读。 |

现行主合同已明确 Invocation authority，宪章 3.2 和主合同约 314 行残留的“Run authority”应在实现批次澄清：Input 是 admission fact；Invocation 是私有资源执行与直接成果来源的权威；公开成果可沿正式 DERIVED_FROM 继承经证明的同 Run 依赖，不能反向扩大执行 scope。这是闭合既有合同，不是批准任意扩大权限。

## 最小实现范围与复用决定

| 范围 | 允许的具体改动 |
| --- | --- |
| `engine/agent/repositories/artifact.py` | 写前持久 Invocation/归属验证；显式 DERIVED_FROM 的有界来源证明；公开同 Run 成果与跨 Run 精确 Input 边界；关联读取复用同规则。 |
| `engine/agent/tool_dispatcher.py` | Artifact selector admission 采用生产证明；execute/reconcile 与关联读取统一 loader；不把公开成果来源注入 scope。 |
| `engine/tools/runtime/resource_authority.py` | Artifact selector 分支补当前 discovery 成员与 exact version 校验；普通 selector 与 owner resolver 不放宽。 |
| `engine/agent/tool_settlement.py` | 仅若需要提前整批核验或复用持久身份，可作小改；不创建第二套 settlement/retry。现有参数足以完成写侧修复。 |
| 现行宪章和主合同的旧句 | 仅澄清上述语义；不另写重复的大合同。 |
| 定向验证文件 | `test_artifact_repository.py`、`test_tool_invocation_repository.py`、`test_run_loop.py` 与相关 system/DLC/composition 测试；更新虚构 Invocation ID 的旧 fixture，不能放宽生产校验迁就 fixture。 |

不需要修改 `engine/models.py`、Alembic、公共 `dbfox_dlc_api.py`、前端 SDK、生成 HTTP 客户端或共享锁文件；既有关系合同足以闭合 Composition，不另开授权或导出通道。

调查并复用现有 SQLAlchemy repository、`begin_agent_write`、Session lease、strict `load_resource_refs`、materialization、DERIVED_FROM、ToolRuntime recovery 与 Representation dispatch。小型有界图遍历属于这些实际关系的校验，不值得引入图数据库或权限框架。无新依赖、无双写、无权限缓存；主要风险是遗漏派生链和把公开来源错误变成私有执行 scope，须由以下负例验证。

## 必须执行的验证矩阵

| 层次/场景 | 必须断言的事实 |
| --- | --- |
| Repository：合法 Invocation 与初始 Input 不同 | draft 在 Invocation refs 内则成功；Input 不变；持久 provenance 精确。 |
| 正式 RunLoop：library→create→edit→edit | 同一 Session/Run，后续调用 discovery 新 document 和新 version；领域与 Artifact 均成功，引用未清空、未暗建新 Run。Scene、Voxel 各走真实包和生产 Loop。 |
| 同 Run Artifact selector→领域读取→JSON Representation | 生产证明、当前成员/版本、resolver 与领域 scope 校验正确；初始 Input 无该 document 也能完成合法链。 |
| 精确 version 与坏 scope | v1 公开成果可读不意味着可按 v2 执行；另一 Invocation 不扩大执行权限；字符串/整数版本不互换；坏 JSON、重复 ID、空 scope 不能扩权。 |
| SQL generation 改变 | validation Artifact 不能执行；既有 Data resolver 与 approval fence 原样生效，不把旧 ref 改成新 generation。 |
| 伪造/外国/缺 Invocation | ID 不存在、不同 Session、不同 Run、不同 Turn、Turn 自身指向别的 Run、wire tool 错配逐一拒绝；损坏/缺 provenance 不能被 selector 绑定。 |
| lease 与冻结身份 | 过期/替换 lease、Run token 不同、owner/package/contract 已变均拒绝；在执行前/结算前的检查保持现有恢复语义。 |
| 原子 batch | 第二条越权、非法 payload/pointer/relation 时，第一条也不落盘；selected Artifact 和成功 Observation 无部分提交；合法 sibling 派生一并提交。 |
| 来源继承攻击 | 伪造/失败/foreign/跨 Run 来源、SUPPORTS 冒充 DERIVED_FROM、未声明来源、父 Invocation 多余 refs、改版本、缺 provenance 均不能继承；自环/互环/传递链/预算上限与超限有明确结果。 |
| 派生隔离 | 空 scope Tool 可读取合法同 Run 公开来源并显式派生；其 Invocation refs、context.scopes 与 ResourceHandle 集合仍为空，不能调用私有资源执行。 |
| execute 成功后崩溃→reconcile | 用原 Invocation ID/input/refs 查 receipt；领域 revision/副作用计数不增加；只结算一次 Artifact batch；未知结果保持 unknown，不自动执行。 |
| consume / relation / related Representation | 不能通过无生产证明的同 Run 成果、外部 Session、INTERNAL 跨 Run、未来 Run 或非法关联 Artifact 绕过加载器。 |
| 历史行 | 无 Invocation/旧空 refs 不因 owner Run 当前数据、Project discovery 或其他 Invocation 获得权限；旧 envelope 展示不被误称重新授权。 |
| 既有 API v2 | surface fixture、签名包激活/停用/恢复、已冻结工具版本与 unknown historical envelope 合同保持；不靠改测试删除旧消费能力。 |
| Composition | Visualization inline 与 Data Result→Visualization 均走真实 RunLoop 成功；来源 refs 精确继承，Visualization Invocation 仍无 Data scope；来源 generation 改变时实时 Representation 明确 stale/source-changed。 |

实施后的最小检查建议：

```powershell
python -m pytest verification/tests/agent_core/test_artifact_repository.py verification/tests/agent_core/test_tool_invocation_repository.py verification/tests/agent_core/test_run_loop.py -q --tb=short
python -m pytest verification/tests/system/test_engineering_contracts.py -q
python -m pytest verification/tests/agent_core -q --tb=short -m "not e2e and not integration and not real_llm"
python -m pyflakes engine/agent/repositories/artifact.py engine/agent/tool_dispatcher.py engine/agent/tool_settlement.py engine/tools/runtime/resource_authority.py
git diff --check
```

以上为后续验证要求，本阶段没有运行这些修复测试，也没有宣称 P1 已解决。本阶段只完成源码/历史审议及文档链接、格式核对。
