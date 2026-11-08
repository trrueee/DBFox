# DBFox 源码功能审查与修复设计

> 文档类型：质量审查与修复验收设计
>
> 状态：当前
>
> 最后核验：2026-11-07
>
> 适用范围：7670e346基线审查及本地修复工作区
>
> 源码基线：`codex/creative-program` / `7670e3461c26f9b5338b432435380ad6a452d59c`

## 0. 2026-11-07修复实施

后续授权的真实模型与客户端操作另记于[培养方案学分分析真实客户端验收](business-journey-20261107.md)。以下22项台账及其“未调用真实模型”范围仍指该批源码修复。

用户已授权修复这22项问题。当前代码已落地，聚焦回归与整体验证分别记录；不把“已改代码”当成“全部功能已验收”。以下新增用例在涉及真实文件、SQLite或生产Store时均使用隔离数据，未迁移用户数据、调用真实模型或重装客户端。

### 0.1 修复台账

| 缺陷 | 源头修复 | 正式回归入口 |
|---|---|---|
| [FND-01](#fnd-01) | 按Host终态结束等待，保留结构化原因 | [engineStartup.test.ts](../../desktop/src/lib/__tests__/engineStartup.test.ts) |
| [FND-02](#fnd-02) | 按实体版本归并，分页/发送提交时读取最新投影，cursor单调 | [conversationStore.test.ts](../../desktop/src/stores/__tests__/conversationStore.test.ts) |
| [FND-03](#fnd-03) | 调度与维护复用可运行输入谓词，正式waiting不自唤醒 | [test_session_coordinator.py](../../verification/tests/agent_core/test_session_coordinator.py) |
| [FND-04](#fnd-04) | 重启/关闭共享收尾并按epoch隔离旧操作；清理失败仍保留child所有权供重试 | [engine.test.ts](../../desktop/main/__tests__/engine.test.ts) |
| [FND-05](#fnd-05) | 授权父目录并保留最终目录项，删除/移动链接不改目标 | [test_workspace_mutation_safety.py](../../verification/tests/system/test_workspace_mutation_safety.py) |
| [FND-06](#fnd-06) | 复用owner SQLite写锁保护hash检查至文件提交，覆盖独立进程 | [test_workspace_mutation_safety.py](../../verification/tests/system/test_workspace_mutation_safety.py) |
| [FND-07](#fnd-07) | 二进制、解码失败和读取工作量计入文件/字节预算 | [test_workspace_mutation_safety.py](../../verification/tests/system/test_workspace_mutation_safety.py) |
| [FND-08](#fnd-08) | 读取行前拒绝重复列；SQLite按位置保留大小写不同别名的独立值 | [test_data_generation_fencing.py](../../verification/tests/system/test_data_generation_fencing.py) |
| [FND-09](#fnd-09) | 官方backup progress与校验共用截止时间，锁超时沿原路径清理 | [test_data_generation_fencing.py](../../verification/tests/system/test_data_generation_fencing.py) |
| [FND-10](#fnd-10) | 按实际邻居交换排序，不依赖连续序号 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-11](#fnd-11) | 只迁移缺少文件元数据的章节，普通重启保留reconcile比较证据 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-12](#fnd-12) | 批关系决定先校验全量、单事务提交，失败整体回滚 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-13](#fnd-13) | 关系可用from_id/to_id精确绑定；旧名称输入必须唯一，歧义拒绝 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-14](#fnd-14) | 无变化只比较head，Music v4移除历史hash唯一索引 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-15](#fnd-15) | 按音符发声起止时间扫描峰值，端点按半开区间处理 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-16](#fnd-16) | 运行与连接测试仅使用Responses，删除不成立的Chat回退及死代码 | [test_openai_model_adapter.py](../../verification/tests/agent_core/test_openai_model_adapter.py) |
| [FND-17](#fnd-17) | 事件批已满立即读取下一页，追上耐久尾部才等待 | [test_conversation_stream_backpressure.py](../../verification/tests/system/test_conversation_stream_backpressure.py) |
| [FND-18](#fnd-18) | 按官方判别属性识别transform，忽略对象键顺序 | [test_creative_function_regressions.py](../../verification/tests/system/test_creative_function_regressions.py) |
| [FND-19](#fnd-19) | Agent和ActionRun复用同一续租循环；失租接取消，exit始终回收资源 | [test_action_run_lifecycle.py](../../verification/tests/system/test_action_run_lifecycle.py) |
| [FND-20](#fnd-20) | Data v5目录绑定源版本，旧反射拒绝；前端换源重置树状态，同源刷新保留加载 | [test_data_generation_fencing.py](../../verification/tests/system/test_data_generation_fencing.py)、[dbfoxDataFixture.test.ts](../../desktop/src/features/dlc/__tests__/dbfoxDataFixture.test.ts) |
| [FND-21](#fnd-21) | 终态计划不变；相同输入幂等，重开返回领域输入错误而非中断Run | [test_plan_repository.py](../../verification/tests/agent_core/test_plan_repository.py) |
| [FND-22](#fnd-22) | 恢复UPDATE按精确connection/resource generation做CAS，冲突无切换记录 | [test_data_generation_fencing.py](../../verification/tests/system/test_data_generation_fencing.py) |

### 0.2 重要行为与复用决定

- **文件修改：** 复用Workspace owner已有SQLite文件的短写事务，保护检查至替换，并覆盖隔离worker与Dock。它会串行化该owner内的文件修改，读取不受此写锁约束；这是以短、小于等于1MiB的修改换取跨进程一致性的克制方案。未增加平台锁实现、依赖或用户项目内锁文件，也不承诺保护外部编辑器的并发写入。项目已有Engine迁移OS锁无法由DLC私有导入，故未复制整套OS锁或扩大SDK。[SQLite事务](https://www.sqlite.org/lang_transaction.html)
- **链接语义：** 删除/移动操作最终目录项，父路径仍验证containment；读取和编辑继续解析授权范围内的目标。Windows symlink和junction均有真实文件系统回归。[Python pathlib](https://docs.python.org/3.12/library/pathlib.html)
- **数据目录与恢复：** Data私有schema升级至5，旧目录无法证明来源，升级时只清理可重建目录缓存；连接、资源、查询结果、备份身份均保留。反射提交事务内验证generation，恢复使用条件UPDATE并检查行数。没有新增业务镜像或双写。
- **乐谱历史：** Music私有schema升级至4，删除旧的历史hash唯一索引；旧修订不重写，回到旧内容产生新修订。升级后的数据不能假定旧客户端可读，发布降级前要验证owner schema支持范围。
- **续租：** 从Coordinator抽出既有续租循环，供Agent与手工ActionRun共同使用；保留精确owner/token与失租栅栏，没有放宽租约有效性或增加第二调度器。
- **关系身份：** Data-free Story合同新增可选from_id/to_id；名称字段保持兼容，提供ID时以项目内实体ID为权威，名称只是标签。未提供ID时名称必须唯一，歧义转为可修复工具输入错误。
- **计划生命周期：** 当前选择“全部步骤完成即关闭该计划”；同内容重复更新不增版本，重开被明确拒绝，模型应在全部工作完成前保留待办。没有重开已终态RunItem，也没有新增Core计划表或重写耐久历史。
- **模型协议：** 删除约400行隐式Chat回退/翻译路径，连接测试与运行均要求Responses；仅支持Chat的端点会明确失败。没有声称实现新的Chat兼容，也没有新增供应商锁定层。[官方协议迁移说明](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- **备份：** 继续调用标准库backup，progress回调负责锁等待截止，完整性校验和checksum共享操作预算；失败继续使用原有staging清理与记录结算，没有文件复制fallback。[官方backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)

### 0.3 Core稳定边界说明

1. Coordinator、ActionRun、Plan和SSE改动修复通用调度/生命周期/终态不变量，现有DLC接口无法修复Host租约或耐久投影本身。
2. 文件、数据库、故事、音乐与图表规则全部在owner DLC修复；Engine未增加领域分支或导入DLC私有模块。
3. Core职责与SDK API v2公开表面保持不变；共享续租是Internal实现复用。没有新增SDK mapper、wrapper、fallback、兼容协议或Core Alembic迁移。
4. 事件先持久化再发布、只读SQL Artifact执行链、精确冻结authority、非幂等不自动重放继续保留；终态计划通过领域拒绝保护原有不变规则。
5. 兼容影响集中在显式Responses支持范围、Story可选参数和Data/Music私有schema；不创建长期新旧双轨。
6. 验证范围包括保护性用例、Core/System确定性回归、工程合同、前端/Electron、类型与构建；真实厂商、外部数据库、GPU/音频和安装态仍须单独验收。

### 0.4 验证记录

验证以源码推导出的不变量和隔离反例为起点，自动化结果只覆盖各自断言。当前记录如下；日志保留于本机忽略目录`desktop/output/functional-fixes-20261107/`，不作为仓库中长期依赖的链接。

| 验证范围 | 实际结果 | 证据与说明 |
|---|---|---|
| Core + System 确定性集合首轮 | 1568通过、2失败、139排除，1026.80秒 | `backend-regression.log`；排除e2e/integration/real_llm/migration/engineering_contract/platform_contract |
| 最终后端影响范围回归 | 168通过，114.67秒 | `backend-final-targeted.log`；含首轮两失败文件、全部新增后端回归及Workbook主流程 |
| 最终前端全套，单worker | 115文件、695项全部通过，148.63秒 | `frontend-final.log`；首轮691通过、1项Pixel分页等待超时，原文件单独28项通过，最终独占串行全套通过；未据此认定当时超时的根因 |
| Electron全套 | 11文件、37项全部通过 | 包含重启/关闭交错、清理失败后保留child所有权及再次清理 |
| 真实32秒ActionRun | 正常completed，32.05秒，lease已释放 | `action-lease-after.json`；生产ActionRun/Dispatcher/Executor与隔离SQLite，工具仅受控等待32秒；invoke/complete/exit均无异常 |
| 工程合同 | 45项通过 | 包含当前文档状态、可移植链接和工程治理 |
| 类型、静态检查 | `typecheck:test`、pyflakes通过；mypy检查241个文件通过 | 最终日志为`typecheck-final.log`、`pyflakes-final.log`、`mypy-final.log` |
| 前端lint | 0错误、23条既有warning | `lint-final.log`；不把现存React effect/refresh建议记为本轮已清理 |
| 生产构建 | `npm run build`通过，生产Token与bundle预算检查通过 | `production-build.log`；仍有大于650kB的chunk提示，初始入口gzip 197675字节，在项目预算内 |

首轮两个后端失败均已处理，并纳入最终168项回归：新增Plan工具描述改变了冻结materialization hash，现已撤回该描述改动，保留原合同与原hash；既有迁移测试把head硬编码为旧revision，改用Alembic官方`ScriptDirectory.get_current_head()`，保留数据复制、提交顺序与幂等断言。没有改迁移实现或放宽数据断言。修正后未再重跑17分钟整套，因此不能把以上两次执行合写成“全量1570通过”。

关键回归实际触及Windows symlink/junction目录项、两个独立进程竞争同一文件hash、SQLite独占锁下的备份超时、恢复版本交错、旧catalog反射迟到、React换源与同源刷新、历史hash回归和SSE 1201条事件追赶。它们验证已确认问题的修复，不代替所有边界的全覆盖。

本轮未进行Frozen Sidecar/安装包运行、已安装客户端升级、真实模型和外部网络数据库、GPU/音频或271项完整UI验收；没有改用户凭据和业务数据。Responses-only与Data/Music私有schema变更须随版本说明发布，不能宣称旧客户端降级已验证。

## 1. 结论、范围与证据规则

本轮从实现代码和真实调用关系出发，确认22处缺陷，其中高9处、中13处。问题主要落在异步状态归并、租约生命周期、版本提交、文件操作身份和领域事务。它们能够解释部分“明明执行了却卡住”“显示内容与实际资源不同”“操作成功但结果不对”的现象，不能据此认定所有既往客户端故障都已找到原因。

现有相关76个后端、18个前端和9个Electron测试均通过；独立反例仍成立。测试通过只能说明对应断言在该环境成立。报告先分析源码，再构造反例，最后对照测试遗漏，没有以测试数量推导功能正确。

2026-11-06审查阶段产品源码未改动；当时没有修复、迁移、安装升级或读写用户业务数据。仅增加本报告与功能清单，并更新质量导航；复现脚本、合成SQLite和日志保留在本机忽略目录`desktop/output/functional-audit-20261106/phase2/`，不进入产品包或提交。所有复现使用隔离数据；外部网络、进程或时间边界受控时，下文逐项注明。

271项清单是28组用户动作及状态转换的核验范围，并非271项已经通过。创作DLC多数已读私有Store及版本提交，部分领域算法、导出和UI尚未完整追踪。动态生成的Scene/Comic工具也未全部展开为独立产品入口。详细状态见[逐功能清单](functional-checklist-20261106.md)，不得把本报告当成全功能发布验收。

### 1.1 基线与调查方法

- 根目录`D:/Project/DBFox`；开始时已跟踪工作树干净。既存未跟踪`desktop/.electron-packaged-smoke-Au80Fw/`排除，未删除或作为权威实现。
- 先读`CONTRIBUTING.md`、实现图、既有质量报告、依赖与Git历史；再使用CodeGraph探查具体符号、调用方和下游。CodeGraph CLI1.0.1，初始索引最新，1379文件/22803节点/64928边；打包副本用Git跟踪列表排除，无强制重建。
- 追踪顺序：用户入口→HTTP/Operation→身份/权限/输入→领域规则→持久提交与副作用→事件/Artifact→前端归并。重点核对等待、异常、取消、版本变化、并发交错和收尾。
- 开发`.venv` Python3.12.7；Frozen解释器固定3.14.6/build20260610，未执行其安装态验证。Node24.13.0/npm11.6.2；项目CI版本与本机有差异。已安装FastAPI0.139.0、SQLAlchemy2.0.51、Pydantic2.13.4、DuckDB1.5.6、openpyxl3.1.5、Vitest4.1.10、Vega-Lite6.4.3。
- 行号来自上述源码基线；独立复现是缺陷证据，不是正式回归套件，尚未纳入CI。无真实供应商、MySQL/PostgreSQL、SSH/TLS、音频/GPU执行器、安装升级和全部UI端到端结论。

### 1.2 核心路径与事实所有者

| 路径 | 实际调用及唯一事实 | 本轮关键问题 |
|---|---|---|
| 桌面启动 | Electron EngineSupervisor→Sidecar→健康检查→Renderer等待 | 终态被吞、跨await重启所有权 |
| 对话执行 | 持久接纳→SessionCoordinator lease→RunLoop→Tool Runtime→DLC→持久事件 | waiting空转、手工ActionRun失租、计划终态冲突 |
| 界面恢复 | SQLite committed事件→snapshot/SSE cursor→Zustand投影 | 旧对象覆盖新完成态、积压分页等待 |
| 文件工作区 | Host授权→Workspace绑定→路径/版本→真实文件操作 | 链接目录项身份丢失、同路径写入不原子、扫描预算漏计 |
| 数据分析 | 精确DatabaseResource→SQL校验Artifact→只读执行→结果Representation | 重复列信息损失、目录源版本缺失、恢复CAS失效 |
| 创作资源 | DLC私有Store→修订/幂等回执→Artifact→Dock | Story恢复/批事务/实体身份；Music修订与统计；Viz语法判别 |

### 1.3 值得保留的实现

- SQL手工入口和模型工具复用校验Artifact与只读执行链，没有发现另建接受原始模型SQL的执行链。应在结果schema和源版本处修复，保留安全链。
- Core把耐久事件与实时通知分开，先提交再发布；SSE有cursor、snapshot和背压恢复基础。FND-02/17针对归并与追赶条件，不需要替换事件系统。
- 资源冻结身份、owner边界和创作DLC修订/CAS/幂等回执提供了可复用基础；不能因个别边界遗漏而建立第二套通用Store或执行器。
- 凭据边界使用opaque引用和OS vault，DLC目录数据、文件及结果有明确所有者。本轮未读取真实秘密；这不是对全部凭据路径作安全认证。
- SQLAlchemy、SQLite事务/备份、Pydantic、openpyxl、DuckDB与官方Vega编译器均已在项目中使用。修复优先复用这些能力，未发现本轮需要新增依赖的理由。

## 2. 优先处理的五项

| 缺陷 | 结论 / 程度 | 位置 | 风险与首要动作 |
|---|---|---|---|
| FND-05 链接删除/移动 | 已确认 / 高 | [service.py:282](../../dlcs/dbfox.workspace/backend/service.py) | 操作alias会改真实目标；先明确目录项语义，再修实际操作边界 |
| FND-06 同路径并发写 | 已确认 / 高 | [service.py:219](../../dlcs/dbfox.workspace/backend/service.py) | 两次旧hash写入均成功；保护检查到提交的完整临界区 |
| FND-22 恢复版本切换 | 已确认 / 高 | [store.py:1051](../../dlcs/dbfox_data/backend/store.py) | 覆盖已成功换源且复用generation；在权威事务中执行精确CAS |
| FND-19 Dock手工任务租约 | 已确认 / 高 | [action_runs.py:158](../../engine/dlc/action_runs.py) | 超30秒工具完成却无法结算；复用续租和失租取消直至收尾 |
| FND-02 旧投影覆盖完成态 | 已确认 / 高 | [conversationStore.ts:130](../../desktop/src/stores/conversationStore.ts) | 已完成任务在UI变回运行；按当前状态与单调版本归并 |

以上“高”表示下一正式发布应优先处理；未发现这些缺陷正在破坏用户数据的现场证据，不把它们描述为正在发生的生产事故。其余高风险启动、结果列、Story历史和catalog问题同列下一阶段修复队列。

## 3. 已确认缺陷与逐项验收设计

下列位置标签保留基线行号，源码链接指向当前文件；当前行为与验证以第0节和正式回归为准。

以下保留7670e346基线的已确认缺陷及原始复现；当前修复状态见第0节。严重程度反映影响，优先级另结合数据风险和主流程可用性。以下回归均是建议新增的保护行为，不能理解为当前已通过。

<a id="fnd-01"></a>

### FND-01：启动失败的结构化错误被轮询层吞掉

- **缺陷标题：** 启动失败的结构化错误被轮询层吞掉。
- **位置：** [desktop/src/lib/api/client.ts:186](../../desktop/src/lib/api/client.ts)；[desktop/src/lib/api/client.ts:200](../../desktop/src/lib/api/client.ts)；[desktop/preload/index.ts:24](../../desktop/preload/index.ts)；[desktop/src/components/EngineStartupGate.tsx:111](../../desktop/src/components/EngineStartupGate.tsx)；符号：`waitForEngineConfig / preload.engine.onStatus / EngineStartupGate`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 错误传播/启动生命周期｜高；**修复优先级：** 高。
- **证据与复现：** 引擎先于Renderer订阅失败时，已失败状态仍被无限轮询；需结合无初始重放的IPC订阅。 原始证据：`desktop/output/functional-audit-20261106/phase2/startup-fatal-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_frontend_state.mjs`。
- **触发条件与根因：** 仅特判两个通用错误码，已失败的DBFOX领域错误落入catch后继续轮询；Renderer只订阅未来通知，缺少可靠的初始终态交付。
- **影响范围：** 启动错误发生早于订阅时，用户可能一直停在加载页；复现设置有限轮询次数以免真实挂起，最终错误还被改写为超时。
- **建议修复方案：** 在现有等待函数按failed/stopped终态直接抛出保留原始code/detail的错误；订阅与初始状态读取保持一致。
- **建议回归测试：** 让Host先进入failed再挂载Renderer，保留原始错误码与detail并结束等待；再验证失败事件恰好发生在订阅/初读之间，以及显式重试后的新generation可就绪。

<a id="fnd-02"></a>

### FND-02：旧投影覆盖新终态，历史加载可使界面恢复为运行中

- **缺陷标题：** 旧投影覆盖新终态，历史加载可使界面恢复为运行中。
- **位置：** [desktop/src/stores/conversationStore.ts:130](../../desktop/src/stores/conversationStore.ts)；[desktop/src/stores/conversationStore.ts:266](../../desktop/src/stores/conversationStore.ts)；[desktop/src/stores/conversationStore.ts:432](../../desktop/src/stores/conversationStore.ts)；[desktop/src/stores/conversationStoreReducer.ts:112](../../desktop/src/stores/conversationStoreReducer.ts)；符号：`loadOlderHistory / sendMessage / preserveLiveProjection / projection merge`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 异步投影一致性｜高；**修复优先级：** 高。
- **证据与复现：** 请求await期间SSE推进状态，随后返回的旧对象覆盖更高版本run、完整回答和cursor；若cursor已推进，后续重复事件无法修复。 原始证据：`desktop/output/functional-audit-20261106/phase2/projection-stale-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_frontend_state.mjs`。
- **触发条件与根因：** await前捕获完整detail，响应后把旧完整对象当作新事实归并；实体版本与cursor缺少单调性约束。完成后也不再受部分live保护。
- **影响范围：** 后端已经完成，UI仍可变回running、缩短回答或回退cursor；另一路径保留较大cursor却回退实体，旧事件被忽略后难以自动恢复。
- **建议修复方案：** 在提交时读取当前state；按run版本和event cursor合并；分页只补历史实体与分页元数据，禁止重新提交请求前捕获的完整detail。
- **建议回归测试：** 延迟history/admission响应，期间输入cursor50、run v8 completed及完整文本，再释放cursor10/v2响应；断言状态、文本、版本和cursor均不回退；再测换会话后的迟到响应。

<a id="fnd-03"></a>

### FND-03：等待澄清且有排队输入时调度器连续空转

- **缺陷标题：** 等待澄清且有排队输入时调度器连续空转。
- **位置：** [engine/agent/coordinator.py:173](../../engine/agent/coordinator.py)；[engine/agent/coordinator.py:311](../../engine/agent/coordinator.py)；[engine/agent/coordinator.py:320](../../engine/agent/coordinator.py)；符号：`SessionCoordinator._has_work / _finished / waiting scheduling`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 调度/等待/性能｜中；**修复优先级：** 中。
- **证据与复现：** 真实QuestionRepository和队列接纳后，0.016秒进行了12次无执行的claim/release，lease token从1递增到13；复现主动停止防止无限循环。 原始证据：`desktop/output/functional-audit-20261106/phase2/coordinator-waiting-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_coordinator_waiting.py`。
- **触发条件与根因：** 继续调度只看到admitted输入，未把正式waiting作为不可运行条件；claim/release后完成回调又立即调度同一会话。
- **影响范围：** 用户等待回答澄清时出现CPU和数据库空转、lease token快速增加；并没有执行排队输入，不是有效进展。
- **建议修复方案：** 让唤醒和继续调度使用相同的可运行工作判断；正式waiting阻塞时停止自唤醒，由响应、取消或到期事件唤醒。
- **建议回归测试：** 真实创建待答问题并接纳下一条消息，观察固定窗口内没有重复claim；提交答案只恢复一次；同样验证取消、问题到期和新输入不会丢失。

<a id="fnd-04"></a>

### FND-04：并发restart/stop没有统一生命周期栅栏

- **缺陷标题：** 并发restart/stop没有统一生命周期栅栏。
- **位置：** [desktop/main/engine.ts:145](../../desktop/main/engine.ts)；[desktop/main/engine.ts:167](../../desktop/main/engine.ts)；[desktop/main/engine.ts:186](../../desktop/main/engine.ts)；[desktop/main/index.ts:146](../../desktop/main/index.ts)；符号：`EngineSupervisor.restart / stop / start`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 并发生命周期/资源回收｜中；**修复优先级：** 高。
- **证据与复现：** 两个restart重叠会启动三个子进程，随后stop只关闭最新进程，中间子进程未收尾；较早restart还能覆盖已完成stop的状态。 原始证据：`desktop/output/functional-audit-20261106/phase2/engine-lifecycle-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_engine_lifecycle.mjs`。
- **触发条件与根因：** epoch只保护局部启动回调，未覆盖restart跨await的整次操作；较早restart在较新stop/restart之后仍继续生成进程。
- **影响范围：** 可能覆盖用户已完成的关闭意图；重叠重启遗留中间子进程。复现使用受控EngineChild，证明所有权竞争，不声称真实进程已在用户机器泄漏。
- **建议修复方案：** 复用现有epoch实现操作级失效检查和唯一转换；旧操作恢复await后必须退出并收尾自己拥有的子进程，不能直接开始新一轮启动。
- **建议回归测试：** 让FakeChild.stop保持pending，交错restart→stop、restart→restart；释放await后断言只保留最新操作状态、最多一个活进程，所有非当前子进程均stop一次。

<a id="fnd-05"></a>

### FND-05：删除或移动符号链接实际操作真实目标

- **缺陷标题：** 删除或移动符号链接实际操作真实目标。
- **位置：** [dlcs/dbfox.workspace/backend/service.py:134](../../dlcs/dbfox.workspace/backend/service.py)；[dlcs/dbfox.workspace/backend/service.py:282](../../dlcs/dbfox.workspace/backend/service.py)；[dlcs/dbfox.workspace/backend/service.py:296](../../dlcs/dbfox.workspace/backend/service.py)；符号：`WorkspaceService.resolve / delete_path / move_path`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 文件操作身份/数据保护｜高；**修复优先级：** 高。
- **证据与复现：** Windows junction和文件symlink均使用真实文件系统复现；alias仍在，真实文件被删除、真实目录被移动。 原始证据：`desktop/output/functional-audit-20261106/phase2/workspace-link-mutation-repro.json`（直接真实文件系统操作，未保存独立可重跑脚本；操作与结果已记录）。
- **触发条件与根因：** 同一个resolve同时承担安全containment与返回操作对象的职责，返回realpath后，删除/移动失去了原始目录项身份。
- **影响范围：** 在工作区内链接的真实目标被意外删除或移动，别名却留下；这是用户文件操作语义错误。未证明任何工作区外越权，不据此扩大为路径逃逸。
- **建议修复方案：** 区分逻辑目录项和已解析的安全目标；删除/移动最终链接时操作链接自身，或在明确合同中拒绝最终链接；父目录containment仍须验证。
- **建议回归测试：** 分别建立目录junction和文件symlink，删除/移动alias后断言目标内容保持、目录项按合同变化或操作明确拒绝；同时保留父路径逃逸、断链和替换竞态检查。

标准库明确区分解析目标与操作目录项；修复应保持这一区分，不能删除路径安全验证。[Python Path.resolve](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.resolve)

<a id="fnd-06"></a>

### FND-06：同一路径并发写入只做提交前哈希检查，不能阻止丢失更新

- **缺陷标题：** 同一路径并发写入只做提交前哈希检查，不能阻止丢失更新。
- **位置：** [dlcs/dbfox.workspace/backend/service.py:219](../../dlcs/dbfox.workspace/backend/service.py)；[dlcs/dbfox.workspace/backend/service.py:239](../../dlcs/dbfox.workspace/backend/service.py)；[engine/tools/runtime/executor.py:350](../../engine/tools/runtime/executor.py)；符号：`WorkspaceService.write_text_file / same-path write ownership`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 文件并发/丢失更新｜高；**修复优先级：** 高。
- **证据与复现：** 两个真实写入都携带同一旧hash，在tempfile创建处控制合法调度交错后，两次均成功，后者覆盖前者。 原始证据：`desktop/output/functional-audit-20261106/phase2/workspace-write-scan-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_workspace_bounds.py`。
- **触发条件与根因：** expected hash检查与os.replace之间没有跨Run共享的同路径串行边界；每Run的工具锁不能保护两个会话对同一文件写入。
- **影响范围：** 两次带旧版本的编辑均宣称成功，第二次静默覆盖第一次，造成应用内部并发丢失更新。首次无控制调度遇到Windows占用，最终复现使用合法、可控交错。
- **建议修复方案：** 在实际共享工作区/路径边界保护同应用写操作，锁内校验到提交完成；不能依赖每Run锁；外部编辑的竞态边界应明确。
- **建议回归测试：** 两个Session写同一路径，屏障使两者都到达旧hash检查后；修复后只能一个成功、另一明确版本冲突；另测不同路径仍可并行、异常后释放锁。

<a id="fnd-07"></a>

### FND-07：二进制或非UTF8文件不计入搜索预算

- **缺陷标题：** 二进制或非UTF8文件不计入搜索预算。
- **位置：** [dlcs/dbfox.workspace/backend/service.py:329](../../dlcs/dbfox.workspace/backend/service.py)；[dlcs/dbfox.workspace/backend/service.py:349](../../dlcs/dbfox.workspace/backend/service.py)；[dlcs/dbfox.workspace/backend/service.py:354](../../dlcs/dbfox.workspace/backend/service.py)；符号：`WorkspaceService.grep_text_files`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 工作量预算/性能｜中；**修复优先级：** 中。
- **证据与复现：** 实际读取2100个二进制文件、8,601,600字节，超过2000文件/8MiB限制，却报告0个扫描、truncated=false。 原始证据：`desktop/output/functional-audit-20261106/phase2/workspace-write-scan-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_workspace_bounds.py`。
- **触发条件与根因：** 扫描数量和字节量在成功文本解码后才累加；二进制和非UTF8分支已实际读文件，却跳过计费。
- **影响范围：** 包含依赖、图片或二进制产物的项目可突破声明的工作量上限，搜索耗时与反馈不一致；用户看到0扫描也无法解释等待。
- **建议修复方案：** 在打开/读取时消耗扫描和字节预算；无效编码、二进制和过大文件仍计入工作量；搜索循环接入取消检查。
- **建议回归测试：** 构造超过文件数/字节上限的二进制、非法UTF8、超大文本和混合目录；总读取与计数均有界，返回真实截断原因，取消后不继续扫描。

<a id="fnd-08"></a>

### FND-08：SQL重复输出列名在字典序列化时静默丢失

- **缺陷标题：** SQL重复输出列名在字典序列化时静默丢失。
- **位置：** [dlcs/dbfox_data/backend/connection.py:355](../../dlcs/dbfox_data/backend/connection.py)；[dlcs/dbfox_data/backend/sql/row_serializer.py:102](../../dlcs/dbfox_data/backend/sql/row_serializer.py)；[dlcs/dbfox_data/backend/sql/row_serializer.py:172](../../dlcs/dbfox_data/backend/sql/row_serializer.py)；[dlcs/dbfox_data/backend/result_view.py:410](../../dlcs/dbfox_data/backend/result_view.py)；符号：`DataConnectionBoundary / row_serializer / ResultView schema`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 结果schema/信息损失｜高；**修复优先级：** 高。
- **证据与复现：** 实际SQLite SELECT 1 AS duplicate_name,2 AS duplicate_name通过EXPLAIN，返回两列表头但仅一个键值1，truncated=false；结果Representation又拒绝重复schema，工具成功与Dock可读性不一致。 原始证据：`desktop/output/functional-audit-20261106/phase2/data-result-backup-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_data_result_backup.py`。
- **触发条件与根因：** SQL列是有序序列，结果被过早转为按名称索引的dict；重复名称在序列化时丢值，而下游Representation才拒绝该schema。
- **影响范围：** SQL工具返回成功但数据已经缺一列，Dock无法打开；模型进一步汇总可能基于不完整结果。实测值1被保留，不能把丢值描述成固定总是保留最后一列。
- **建议修复方案：** 在权威结果schema边界检测重复列名并要求显式唯一SQL别名，避免先转字典丢值；结果与Representation使用同一列合同。
- **建议回归测试：** SELECT 1 AS x,2 AS x必须在生成成功结果前明确拒绝并要求唯一别名；显式x/y应保留两值；对SQLite及工作簿DuckDB分别验证统一schema合同。

<a id="fnd-09"></a>

### FND-09：SQLite备份等待锁没有整体截止时间

- **缺陷标题：** SQLite备份等待锁没有整体截止时间。
- **位置：** [dlcs/dbfox_data/backend/backup.py:54](../../dlcs/dbfox_data/backend/backup.py)；[dlcs/dbfox_data/backend/backup.py:58](../../dlcs/dbfox_data/backend/backup.py)；[engine/api/dlc_operations.py:320](../../engine/api/dlc_operations.py)；符号：`sqlite online backup / DLC operation invocation`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 截止时间/取消｜中；**修复优先级：** 中。
- **证据与复现：** 在独立测试数据库持有排他锁，设置connect timeout=5后，实际backup在6.3秒仍等待，释放锁后才完成；源码没有progress截止回调，RPC也无该操作截止。 原始证据：`desktop/output/functional-audit-20261106/phase2/data-result-backup-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_data_result_backup.py`。
- **触发条件与根因：** SQLite连接timeout不能当作整个backup的deadline；官方备份循环没有接入progress取消或截止回调。
- **影响范围：** 数据库长时间被锁时备份请求可能一直等待，UI无明确完成或失败出口；6.3秒观察仅证明已超过配置的5秒连接timeout，不代表测出了无穷等待。
- **建议修复方案：** 继续使用官方backup API，以progress回调检查实际整体deadline及取消条件，异常时沿现有staging清理结算，不引入文件复制fallback。
- **建议回归测试：** 持有排他锁超过操作deadline，断言有界返回、staging清理和失败记录；再测锁及时释放成功、取消及部分复制后错误，不影响原数据库。

标准库backup已有progress回调，可在现有边界适配截止与取消；没有必要以文件复制另建备份链。[Python sqlite3.Connection.backup](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)

<a id="fnd-10"></a>

### FND-10：删除章节留下序号缺口，随后上移/下移静默无效

- **缺陷标题：** 删除章节留下序号缺口，随后上移/下移静默无效。
- **位置：** [dlcs/dbfox.story/backend/store.py:827](../../dlcs/dbfox.story/backend/store.py)；[dlcs/dbfox.story/backend/store.py:849](../../dlcs/dbfox.story/backend/store.py)；符号：`StoryStateStore.delete_chapter / move_chapter`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 排序不变量｜中；**修复优先级：** 中。
- **证据与复现：** A1/B2/C3删除B后，C上移查询seq=2不存在，成功返回但顺序仍为A1/C3。 原始证据：`desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_story_order_history.py`。
- **触发条件与根因：** 删除保留seq缺口，而移动用seq±1定位邻居；两个操作对排序不变量的理解不一致。
- **影响范围：** 删除中间章节后，上移/下移会成功返回却不改变可见顺序；后续自动化也无法区分达到边界与错误空操作。
- **建议修复方案：** 在权威排序操作中查询实际相邻章节，或事务内维护连续排序；不要让缺失序号成为成功的空操作。
- **建议回归测试：** A/B/C删除B后，C上移必须得到C/A；验证首尾、连续删除、反向移动与并发修改冲突，不能产生重复排序。

<a id="fnd-11"></a>

### FND-11：故事初始化覆盖章节摘要，绕过外部修改/崩溃恢复版本

- **缺陷标题：** 故事初始化覆盖章节摘要，绕过外部修改/崩溃恢复版本。
- **位置：** [dlcs/dbfox.story/backend/store.py:188](../../dlcs/dbfox.story/backend/store.py)；[dlcs/dbfox.story/backend/store.py:222](../../dlcs/dbfox.story/backend/store.py)；[dlcs/dbfox.story/backend/store.py:993](../../dlcs/dbfox.story/backend/store.py)；符号：`StoryStateStore._initialize / _migrate_chapter_files / _reconcile_chapter`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 启动恢复/版本历史｜高；**修复优先级：** 高。
- **证据与复现：** 外部编辑合成章节后重新构造Store，当前内容已变化但历史仍只有旧版本；初始化把新hash写回，后续reconcile失去比较依据。 原始证据：`desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_story_order_history.py`。
- **触发条件与根因：** 每次初始化执行的迁移先采用当前文件hash，抹平了reconcile所需的上次已提交内容证据；迁移与日常恢复混在同一路径。
- **影响范围：** 外部编辑或异常重启后的新内容进入当前章节，却没有对应恢复版本，历史记录不再能解释当前内容；没有证明原文本被物理删除。
- **建议修复方案：** 迁移仅处理确需迁移的历史状态，初始化不得无条件采纳当前文件摘要；内容差异通过现有reconcile生成恢复版本并提交。
- **建议回归测试：** 提交v1后关闭Store、外部改文件、重新构造Store再读取；必须生成内容一致的恢复版本且只生成一次；未变化启动不得增版本，旧schema迁移也要保留原始历史。

<a id="fnd-12"></a>

### FND-12：关系批量确认逐条提交，整体报错后仍留下部分确认

- **缺陷标题：** 关系批量确认逐条提交，整体报错后仍留下部分确认。
- **位置：** [dlcs/dbfox.story/backend/store.py:553](../../dlcs/dbfox.story/backend/store.py)；[dlcs/dbfox.story/backend/store.py:571](../../dlcs/dbfox.story/backend/store.py)；符号：`StoryStateStore.decide_edge / decide_batch`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 事务/部分失败｜中；**修复优先级：** 中。
- **证据与复现：** 第一条合法、第二条已不存在的批量请求抛错，第一条却已confirmed；响应不返回部分成功结果。 原始证据：`desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_story_order_history.py`。
- **触发条件与根因：** 批接口循环调用各自提交事务的单条接口；第二条校验失败时第一条已不可回滚，响应却仅表示整体失败。
- **影响范围：** 关系图出现用户未预期的部分修改，重试批请求又可能遇到新状态；调用方没有部分成功清单可恢复。
- **建议修复方案：** 明确批处理合同；现有一次整体响应宜先校验全部并在同一SQLite事务内提交，复用内部SQL而不循环独立事务。
- **建议回归测试：** 一条合法加一条不存在/失效关系，按整体事务合同全部不变；全合法只提交一次；第二条写失败也须回滚首条。

<a id="fnd-13"></a>

### FND-13：同名不同类型实体建立关系时默选第一条

- **缺陷标题：** 同名不同类型实体建立关系时默选第一条。
- **位置：** [dlcs/dbfox.story/backend/store.py:505](../../dlcs/dbfox.story/backend/store.py)；[dlcs/dbfox.story/backend/store.py:509](../../dlcs/dbfox.story/backend/store.py)；符号：`StoryStateStore.propose_relations`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 领域身份/歧义｜中；**修复优先级：** 中。
- **证据与复现：** 实体允许同项目内character和scene同名；关系接口只有name，fetchone未检查歧义，实际选中先创建实体。 原始证据：`desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_story_order_history.py`。
- **触发条件与根因：** 实体唯一性包括kind，关系写入却仅用project/name并fetchone，目标身份在边界上不完整。
- **影响范围：** 同名角色和场景均合法时，关系可能写到错误实体，且没有歧义提示；这是领域身份错误。
- **建议修复方案：** 关系写入使用权威实体ID，名称仅作展示/检索；名称检索发现多项必须要求明确目标，不增加隐式名称映射。
- **建议回归测试：** 创建不同kind的同名实体，名称写入必须拒绝歧义；传入明确ID时只修改指定实体，同时验证跨项目ID拒绝与重命名后的关系稳定性。

<a id="fnd-14"></a>

### FND-14：乐谱历史hash全局唯一，合法反向编辑被当作无变化拒绝

- **缺陷标题：** 乐谱历史hash全局唯一，合法反向编辑被当作无变化拒绝。
- **位置：** [dlcs/dbfox.music/backend/store.py:89](../../dlcs/dbfox.music/backend/store.py)；[dlcs/dbfox.music/backend/store.py:234](../../dlcs/dbfox.music/backend/store.py)；符号：`MusicStore._initialize / commit_revision`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 修订语义/去重约束｜中；**修复优先级：** 中。
- **证据与复现：** 实际transpose +1提交revision2，再-1恢复原文档，commit拒绝且停在revision2；判断比较全部历史而非当前head。 原始证据：`desktop/output/functional-audit-20261106/phase2/music-semantics-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_music_semantics.py`。
- **触发条件与根因：** 把内容去重当成修订是否有效的判断；全历史hash唯一约束阻止合法地回到以前的内容。
- **影响范围：** 移调后反向移调、恢复或其他逆编辑不能提交，用户停留在不想要的head；对当前head确实无变化仍应拒绝。
- **建议修复方案：** 无变化仅与当前head比较；允许新revision引用曾出现的内容hash，迁移删除该历史去重唯一索引，保留revision和父子关系。
- **建议回归测试：** +1再-1应产生v3，v3内容可等于v1而parent为v2；同head无变化仍拒绝；迁移后原修订和父子链保持可读。

<a id="fnd-15"></a>

### FND-15：乐谱峰值复音统计只数相同起点，忽略持续音重叠

- **缺陷标题：** 乐谱峰值复音统计只数相同起点，忽略持续音重叠。
- **位置：** [dlcs/dbfox.music/backend/score_ops.py:225](../../dlcs/dbfox.music/backend/score_ops.py)；[dlcs/dbfox.music/backend/score_ops.py:236](../../dlcs/dbfox.music/backend/score_ops.py)；符号：`score_ops.analyze / peak polyphony`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 统计算法｜中；**修复优先级：** 中。
- **证据与复现：** beat0持续4拍与beat1持续2拍实际同时发声2音，生产分析却输出peak polyphony=1，难度估计也消费该值。 原始证据：`desktop/output/functional-audit-20261106/phase2/music-semantics-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_music_semantics.py`。
- **触发条件与根因：** 仅按note start统计数量，忽略已有持续音；起点同时性不等于发声区间重叠。
- **影响范围：** 峰值复音与使用它的难度估计偏低；不直接影响音符存储，不能扩大为播放丢音。
- **建议修复方案：** 以音符起止时间扫描活动音数量，明确同刻结束与开始的半开区间语义；保留现有ScoreDocument而不引入第二套音符模型。
- **建议回归测试：** 跨起点的持续音应计为2，首尾相接按半开区间计1；覆盖和弦、跨小节、零时长的模型合法性及多声部。

<a id="fnd-16"></a>

### FND-16：Responses到Chat兼容分支原样转发两套不同协议的工具与上下文

- **缺陷标题：** Responses到Chat兼容分支原样转发两套不同协议的工具与上下文。
- **位置：** [engine/agent/providers/openai.py:929](../../engine/agent/providers/openai.py)；[engine/agent/providers/openai.py:936](../../engine/agent/providers/openai.py)；符号：`OpenAI provider Responses→Chat branch`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 供应商协议/集成合同｜中；**修复优先级：** 高。
- **证据与复现：** 端点404后实际Adapter+SDK发出的Chat请求仍使用平铺function定义及function_call/function_call_output Items；缺少Chat的function嵌套与messages结构。复现仅捕获本地MockTransport，无真实供应商请求；正式协议差异有OpenAI Docs支持。分支还移除了store:false。 原始证据：`desktop/output/functional-audit-20261106/phase2/stream-contracts-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_stream_contracts.py`。
- **触发条件与根因：** 把Responses Items与工具定义当成Chat messages与tools原样发送，协议差异没有在真实供应商边界处理；ping式连接测试不能验证工具调用。
- **影响范围：** Responses端点不支持而进入fallback时，带工具/工具历史的运行请求不符合Chat协议。仅有本地请求捕获，未对真实厂商或实际账单行为作结论；移除store字段不是已确认泄漏。
- **建议修复方案：** 依据项目原生Responses合同优先删除不成立的隐式fallback，端点不支持时明确反馈；若产品明确保留Chat支持，需独立、显式的供应商协议边界和官方请求合同验证，禁止伪装成相同消息协议。
- **建议回归测试：** 按产品Responses合同，不支持端点应明确失败；MockTransport捕获真实SDK请求，正常工具调用、工具结果及流式续轮必须是同一官方协议；配置测试同时检查必要能力。

官方说明Responses使用Items、Chat使用messages，function工具配置也不同；本地捕获按此合同判断，不依据模拟服务的400响应断言真实厂商失败。[迁移到Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[Function calling](https://developers.openai.com/api/docs/guides/function-calling)。连接测试`engine/api/agent.py:65/84/93`的ping成功也不证明这些能力可用。

<a id="fnd-17"></a>

### FND-17：SSE历史积压每500条就等待15秒，即使数据库仍有待发事件

- **缺陷标题：** SSE历史积压每500条就等待15秒，即使数据库仍有待发事件。
- **位置：** [engine/api/conversation_stream.py:138](../../engine/api/conversation_stream.py)；[engine/api/conversation_stream.py:155](../../engine/api/conversation_stream.py)；符号：`conversation SSE catch-up loop`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 事件重放/恢复延迟｜中；**修复优先级：** 中。
- **证据与复现：** 实际SQLite预先提交1201事件，消费500后下一帧为keepalive；记录到请求15秒空队列等待，此时仍有701条耐久事件。只加速时钟，未替换EventRepository或流循环。 原始证据：`desktop/output/functional-audit-20261106/phase2/stream-contracts-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_stream_contracts.py`。
- **触发条件与根因：** 每批最多500条后无条件等待通知队列，没有区分批已满与已追到耐久尾部；预提交积压没有新的通知来唤醒。
- **影响范围：** 断线恢复或长会话重放时每500条额外等15秒，界面看似停滞；事件未丢失，但恢复延迟随批次数增长。
- **建议修复方案：** 达到批量上限时立即继续从耐久cursor读取，只有追上当前尾部才等待新提交；保留现有分页、背压和gap恢复，不新建事件传输链。
- **建议回归测试：** 先提交1201条再订阅，消费全部连续cursor时不得触发空队列等待；追到尾部才等待；同时验证新事件、队列溢出和gap恢复。

<a id="fnd-18"></a>

### FND-18：Vega-Lite校验以JSON首键识别转换类型，拒绝语义相同的合法图表

- **缺陷标题：** Vega-Lite校验以JSON首键识别转换类型，拒绝语义相同的合法图表。
- **位置：** [dlcs/dbfox.visualization/backend/validation.py:146](../../dlcs/dbfox.visualization/backend/validation.py)；符号：`validate_visualization_spec transform discrimination`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 图表语法/校验｜中；**修复优先级：** 中。
- **证据与复现：** 只交换aggregate与groupby的JSON键顺序，实际校验一份通过一份报错；项目已安装的官方Vega-Lite6.4.3编译器两份均成功。 原始证据：`desktop/output/functional-audit-20261106/phase2/visualization-order-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_visualization_order.py`；`desktop/output/functional-audit-20261106/phase2/repro_visualization_compiler.mjs`。
- **触发条件与根因：** 用JSON对象首键判别transform，而官方语法用aggregate等判别属性；相同对象因构造顺序不同被赋予不同语义。
- **影响范围：** 合法可视化被偶发拒绝，模型可能反复改写同一图表。项目官方编译器6.4.3已对两种键序都成功编译。
- **建议修复方案：** 按照官方转换定义的判别属性识别类型，与对象插入顺序无关；继续保留本地能力/安全约束，复用已有官方编译器作语义合同验证，不另造完整图表语言解析器。
- **建议回归测试：** 对每种支持transform排列键序，校验结论一致；aggregate/groupby两份同时经官方编译器验证；非法组合和本地安全限制仍拒绝。

官方aggregate定义以`aggregate`/`groupby`属性描述转换；项目已安装编译器对两种对象键序均通过，本地校验应保留能力限制并遵循其语义。[Vega-Lite aggregate](https://vega.github.io/vega-lite/docs/aggregate.html)

<a id="fnd-19"></a>

### FND-19：Dock手工ActionRun不续租，超过30秒后无法完成或失败收尾

- **缺陷标题：** Dock手工ActionRun不续租，超过30秒后无法完成或失败收尾。
- **位置：** [engine/dlc/action_runs.py:158](../../engine/dlc/action_runs.py)；[engine/dlc/action_runs.py:375](../../engine/dlc/action_runs.py)；[engine/dlc/action_runs.py:388](../../engine/dlc/action_runs.py)；[engine/dlc/action_runs.py:419](../../engine/dlc/action_runs.py)；[engine/agent/repositories/session.py:379](../../engine/agent/repositories/session.py)；[engine/agent/repositories/session.py:739](../../engine/agent/repositories/session.py)；符号：`ActionRun claim / complete / __exit__ / lease_lost_probe`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 租约/执行收尾｜高；**修复优先级：** 高。
- **证据与复现：** 实际ActionRun/ToolDispatcher/ToolExecutor及隔离SQLite，唯一受控外部边界为32秒只读操作（工具允许60秒）；invoke成功，complete与__exit__均抛SessionLeaseConflict，Run留在running。生产手工SQL的校验和执行连续走同一ActionRun，多个合法工具的累计时间同样可能超过30秒。 原始证据：`desktop/output/functional-audit-20261106/phase2/action-lease-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_action_lease.py`。
- **触发条件与根因：** 手工ActionRun领取30秒Session lease后没有保持续租，且loss probe未接通；工具允许的执行时间可以大于剩余lease。
- **影响范围：** 真实工具已成功却无法提交完成，退出失败收尾也遭同一冲突，留下running任务；和Agent主RunLoop既有续租是不同调用路径，旧修复不能证明此路径安全。
- **建议修复方案：** 让手工ActionRun复用既有Session lease续期与失租取消机制，完整覆盖start到complete/fail；统一租约所有权，不放宽过期校验，也不能仅把TTL调大。异常收尾必须确保executor关闭且不由旧owner提交终态。
- **建议回归测试：** 手工SQL两工具累计超过30秒仍可完成；另外模拟真正被新owner接管，旧owner必须取消、不能写终态，executor始终关闭；complete失败不能遮蔽原始错误。

<a id="fnd-20"></a>

### FND-20：数据库换源后继续展示旧目录，旧generation刷新仍能覆盖新源目录

- **缺陷标题：** 数据库换源后继续展示旧目录，旧generation刷新仍能覆盖新源目录。
- **位置：** [dlcs/dbfox_data/backend/store.py:458](../../dlcs/dbfox_data/backend/store.py)；[dlcs/dbfox_data/backend/store.py:1284](../../dlcs/dbfox_data/backend/store.py)；[dlcs/dbfox_data/backend/store.py:1353](../../dlcs/dbfox_data/backend/store.py)；[dlcs/dbfox_data/backend/workbench.py:139](../../dlcs/dbfox_data/backend/workbench.py)；[dlcs/dbfox_data/frontend/index.js:60](../../dlcs/dbfox_data/frontend/index.js)；符号：`update_profile / update_database / replace_catalog / workbench.refresh`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 源版本/目录一致性｜高；**修复优先级：** 高。
- **证据与复现：** 两份真实SQLite，A只有only_in_A、B只有only_in_B；生产API对应的update_database将绑定从A改B后scope=1:2，overview仍ready且目录是A；冻结旧handle再次refresh成功，把A写回当前目录。SchemaInventory/replace_catalog没有源版本合同。 原始证据：`desktop/output/functional-audit-20261106/phase2/catalog-generation-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_catalog_generation.py`。
- **触发条件与根因：** 目录缺少源generation戳；换源只增加资源generation，未使已有目录失效；replace_catalog也不校验发起反射的冻结版本。
- **影响范围：** 连接已是B却显示A的表，迟到的A反射还可把目录写回当前资源。当前实现图文档要求的提交前generation验证在该路径缺失。
- **建议修复方案：** 目录的权威提交须绑定并事务内校验精确connection/resource generation；换源时使目录失效，读取时拒绝不同源版本；前端目录key包含该版本。保留反射后一次原子替换，不用新映射层隐藏旧目录。
- **建议回归测试：** A/B各有独有表，换源后旧目录不可ready；延迟A反射至B换源后提交，必须拒绝且不改B目录；同时测试Profile连接generation变化和前端缓存key。

<a id="fnd-21"></a>

### FND-21：运行未结束时增补已完成计划，触发未分类终态异常

- **缺陷标题：** 运行未结束时增补已完成计划，触发未分类终态异常。
- **位置：** [engine/agent/repositories/plan.py:77](../../engine/agent/repositories/plan.py)；[engine/agent/repositories/events.py:223](../../engine/agent/repositories/events.py)；[engine/tools/builtin/control.py:101](../../engine/tools/builtin/control.py)；[engine/agent/tool_dispatcher.py:422](../../engine/agent/tool_dispatcher.py)；符号：`UpdatePlanCommand / PlanRepository.update / EventRepository terminal item`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 状态机/异常分类｜中；**修复优先级：** 高。
- **证据与复现：** 实际UpdatePlanCommand和PlanRepository及SQLite：先完成全部步骤，Run仍running；再增加一项in_progress，两份输入均通过公开schema，第二次却抛ValueError('Terminal RunItem status is immutable')，未转成可修复的ToolInputError。该异常可沿控制命令进入Run级失败路径；复现直接覆盖命令边界，未调用真实模型。 原始证据：`desktop/output/functional-audit-20261106/phase2/plan-transition-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_plan_transition.py`。
- **触发条件与根因：** 全部步骤完成时计划RunItem已completed，活动Run随后扩展计划试图把同一终态项改回in_progress；控制边界只分类部分领域异常。
- **影响范围：** 合法schema输入出现原始ValueError，不能作为可修复的工具错误返回；源调用链可进入Run失败路径，复现未调用模型或完整RunLoop。
- **建议修复方案：** 明确动态计划在活动Run中的生命周期：允许扩展时创建新的计划执行项并保留已完成项；若合同禁止重开，在修改前返回稳定的领域拒绝。不要突破EventRepository的终态不变规则，也不要用宽泛except伪装成功。
- **建议回归测试：** 活动Run先全部完成再加新步骤，应按明确合同创建新执行项或返回稳定领域拒绝；不得改写已完成项；普通进行中更新、重复更新及不可用Artifact也需验证。

<a id="fnd-22"></a>

### FND-22：恢复切换的版本检查与写入不原子，并发换源被覆盖且版本号复用

- **缺陷标题：** 恢复切换的版本检查与写入不原子，并发换源被覆盖且版本号复用。
- **位置：** [dlcs/dbfox_data/backend/store.py:1051](../../dlcs/dbfox_data/backend/store.py)；[dlcs/dbfox_data/backend/store.py:1067](../../dlcs/dbfox_data/backend/store.py)；[dlcs/dbfox_data/backend/store.py:1074](../../dlcs/dbfox_data/backend/store.py)；[dlcs/dbfox_data/backend/store.py:1353](../../dlcs/dbfox_data/backend/store.py)；符号：`DataStateStore.commit_sqlite_restore`。
- **结论状态：** 已确认缺陷。
- **类型与严重程度：** 事务/版本栅栏｜高；**修复优先级：** 高。
- **证据与复现：** 真实DataStateStore和隔离SQLite，在恢复SELECT校验后、UPDATE前控制合法交错：普通update_database从A切换到B并提交scope=1:2，随后旧恢复仍成功切换至restored且scope仍为1:2。同一资源版本实际对应不同数据库。只复现权威提交边界，不涉及用户数据或完整备份文件复制。 原始证据：`desktop/output/functional-audit-20261106/phase2/restore-generation-repro.json`；`desktop/output/functional-audit-20261106/phase2/repro_restore_generation.py`。
- **触发条件与根因：** sqlite3连接上下文在SELECT处尚未开启写事务；版本检查后用WHERE id无条件UPDATE，并从旧快照计算generation，未形成真正CAS。
- **影响范围：** 并发配置已成功指向B，旧恢复覆盖成C且仍标1:2；冻结在1:2上的不同来源失去可区分性，影响后续读、目录和权限版本证明。未操作用户数据库或证明完整restore文件复制链。
- **建议修复方案：** 在同一权威事务中锁定并验证connection与resource generation，提交使用精确版本条件并检查影响行数；冲突必须保持并发更新结果、拒绝旧恢复并清理隔离staging。版本号只能在成功提交时单调推进，不能从失效快照写回。
- **建议回归测试：** 屏障置于版本读取和提交之间，另一路换源先成功；旧恢复必须冲突失败且B保持、无成功restore记录。Profile generation并发变化也拒绝；正常恢复只单调增加一次版本。

## 4. 可读性与构造质量

这些判断由具体行为支持；文件长或使用某种模式本身不构成缺陷。

| 热点 | 代码意图为何难以准确理解 | 克制的改进方向 |
|---|---|---|
| `resolve`同时表示授权目标和操作对象 | FND-05中“经过安全检查”的返回路径已悄悄改变操作身份 | 在现有Workspace边界明确entry与resolved target，避免新增全项目路径包装层 |
| 完整detail归并掩盖异步状态提交 | FND-02把历史补页、接纳响应和实时事件当作相同权威级别 | 分清补页字段和当前实体；显式版本/游标不变量，减少隐式整对象spread |
| 手工ActionRun与Agent执行所有权不对称 | FND-19接口看似同属Run，但一条维护租约、一条未维护 | 复用现有续租机制，检查start→invoke→complete/fail→close的每个出口 |
| Data目录/恢复提交不满足文档版本约束 | FND-20/22中调用者传递了冻结身份，最终Store却未完整消费 | 在Store提交处落实唯一版本事实，删除“上游已检查所以安全”的假设 |
| Story迁移和普通恢复混合 | FND-11重启时先覆盖用于恢复判断的hash | 迁移仅由schema版本驱动，日常读取统一走既有reconcile |
| Music历史去重与无操作判定混合 | FND-14内容相同被当作修订相同 | 分开revision身份与content hash；当前head比较表达无变化意图 |

部分创作Store把持久化、领域变更和回执压在密集函数中，增加审查成本；本轮只建议按真实事务/领域变化轴拆分局部纯函数，不以行数为由创建通用DLC facade。未读完的算法和导出不能定性为设计错误。

## 5. 复用与架构层次决策

调查日期2026-11-06。优先比较项目内实现、锁定依赖和标准库，再查官方合同；本轮没有新增、升级或替换依赖，没有完成全供应链/CVE/许可证审计，不能据此声称全部依赖安全。

| 当前需求 / 方案 | 调查与适配结论 | 采用方向、未选方案及成本 |
|---|---|---|
| ActionRun续租、Engine重启所有权 | 项目已有Session lease、失租取消与Engine epoch，真实生命周期边界缺失 | 最小复用已有机制；不增加通用工作流框架、不以增大TTL解决。无新供应链；需校验异常收尾和取消延迟 |
| 文件并发与安全路径 | 已有hash、tempfile/os.replace、路径containment；缺的是同应用临界区及entry身份 | 局部修权威文件操作；不造多层路径mapper。平台链接差异和外部编辑仍须Windows/Unix验收；不承诺锁住外部编辑器 |
| Data catalog/restore一致性 | SQLite事务、现有generation与update_database条件写可复用 | 精确事务/CAS并使catalog绑定源版本；不加缓存fallback。目录缓存可能需owner schema迁移，旧缓存清空可重建，不产生双事实源 |
| SQLite备份等待 | 标准库Connection.backup具备分页与progress回调，当前调用已复用 | 在同一备份调用加入有界截止/取消。拒绝文件复制fallback以保持一致快照；无新增依赖，额外验证清理与锁竞争 |
| 图表语言语义 | 项目已装官方Vega-Lite6.4.3；本地校验承担能力与安全子集 | 合理最小适配；识别官方判别属性，复用编译器合同用例。无需另造完整语法，官方升级风险由固定版本回归管理 |
| SQL结果序列化 | 当前dict结果合同与唯一列名匹配，但重复列入边界前未拒绝 | 源schema明确唯一列；不静默重命名，不新增双向列名映射。已有消费者保持合同，错误反馈会由成功变为明确拒绝 |
| Responses/Chat隐式fallback | 本地实现和官方协议不等价；Git提交575eac35曾引入此兼容意图 | 按当前原生Responses要求收敛，不能继续扩展不成立路径。删除会让只支持Chat的端点明确不可用，须同步支持范围；若产品另定支持，再建立显式协议能力边界 |
| 项目Coordinator/RunLoop/Tool Runtime | lease、审批、幂等、进度、结果未知状态属于产品特定协议，非普通任务队列 | 合理自研边界，未证明成熟队列库能直接替代该模型。继续修共享不变量，不因本轮竞态替换整个Harness |

### 5.1 应保留和应收敛的层

- **保留真实边界：** Electron→窄IPC、HTTP Pydantic合同→生成API、DLC公开SDK→owner私有Store、模型Provider协议、结果Artifact→Representation。这些层有实际进程/协议/权限变化轴，不能只因名字含adapter就删除。
- **收敛内部不一致：** 完整detail复制归并、catalog无源版本、恢复提交的预检查、Story批处理循环事务。业务事实由源提交一次约束，避免在前端或多处service再加补丁映射。
- **停止扩大已证明不成立的兼容路径：** Responses→Chat fallback不应靠多层字段改名维持。若因明确已发布约束临时保留，责任边界为Provider模块，必须有调用量/错误计数、官方合同回归和删除条件“支持的端点全部具备Responses”。本轮未指定个人负责人，不能把建议写成已安排的迁移。
- **一次性迁移债务：** Music去除历史hash唯一约束、Data目录源版本可能需要DLC私有schema迁移。迁移只执行一次，保留历史身份；不要双写两套修订或目录。回滚发布前须验证旧客户端对新schema的支持范围，不能直接复制旧二进制降级。

### 5.2 与既有文档和修复记录核对

- `docs/architecture/implementation-map.md:268–270`明确要求反射后校验generation再原子替换目录，当前FND-20路径未落实；`:219`恢复版本切换的设计也未使FND-22成为原子CAS。文档设计是验收目标，不能替代代码证据。
- `docs/quality/2026-08-22-agent-core-dlc-workbench-review.md`中的多资源/权威边界修复并未重新算成本轮新问题。
- `docs/quality/2026-08-14-system-review-remediation.md`等记录说明Agent主执行路径已有租约、取消和未知结果处理；FND-19针对另一个手工ActionRun路径，不否定主路径既有修复。

## 6. 验证结果、盲点与测试设计

### 6.1 本轮实际执行

| 检查 | 结果 | 解释 |
|---|---|---|
| 后端7个定向文件，排除外部/迁移等marker | 73 passed / 91.09秒 | coordinator、Story、Music、Workspace、Viz、SSE、Data领域模型的既有断言通过 |
| PlanRepository定向测试 | 3 passed / 3.99秒 | 未覆盖已完成计划在活动Run中再次扩展 |
| conversationStore/workspacePersistence/EngineStartupGate | 3文件18 passed / 18.04秒 | 当前样例通过，未排除旧响应竞争 |
| Electron EngineSupervisor | 1文件9 passed / 567毫秒 | FakeChild.stop立即完成，未复现跨await重叠 |
| 22项独立证据 | 均确认各自反例 | 不作为22个正式回归测试计数；部分共享脚本、仅控制边界或直接调用提交方法 |

Phase1已有工作簿相关37测试通过，另有1544个后端与687个前端仅收集成功；这些不加入本轮执行数、不当成覆盖率。没有跑全量lint、build或Frozen打包验证；产品代码未改，重复广泛测试不会反证已成立的源码反例。

代表性测试盲点：Story已有恢复测试在同一Store实例写后读，未重建Store；Music只测单向移调，未测逆操作；Plan只测进行中到完成；Electron假进程没有挂起stop；前端基础接纳测试没有把旧HTTP响应延迟到新SSE完成之后。这些是已读代表测试的缺口，不声称仓库所有测试都没有相关用例。

### 6.2 白盒保护案例

| 目标 | 安排与执行 | 必须断言 |
|---|---|---|
| 旧投影不回退（FND-02） | 真实Store/Reducer，控制两个HTTP promise；先SSE完成v8/cursor50，再放回v2/cursor10 | run终态、完整文本、实体版本和cursor均单调；旧会话响应无权修改新会话 |
| 文件同路径CAS（FND-06） | 两个Session同hash写入，在校验后精确控制交错 | 一个成功一个明确冲突；真实文件等于成功内容，临时文件/锁释放，不重复副作用 |
| 恢复原子切换（FND-22） | 真实SQLite，恢复读取旧版本后让换源事务先提交 | 旧恢复失败、B绑定不变、无成功restore记录，版本不复用；正常切换递增一次 |
| ActionRun所有权（FND-19） | 工具耗时跨过TTL；另例在中途让新owner接管 | 正常持续续租可完成；真正失租立即取消且不提交终态，complete/fail异常仍关闭executor |
| Story批事务（FND-12） | 第二条领域验证或写入失败 | 第一条回滚，事件/修订与业务状态一致，重试不会看到伪部分成功 |
| SSE追赶（FND-17） | SQLite预提交1201事件后订阅，不制造通知 | 完整有序发出所有cursor再等待；队列等待次数与已追尾状态匹配 |

并发案例控制的是真实允许的交错，不能只sleep碰运气。保护性测试应在修复前失败，修复后验证业务状态和副作用，而非复制实现分支。

### 6.3 黑盒验收矩阵

| 测试目标 | 前置条件 / 输入 / 异常 | 操作步骤 | 预期状态、输出与副作用 | 优先级 |
|---|---|---|---|---|
| 启动失败明确退出等待 | 迁移/Sidecar失败发生在UI订阅前 | 冷启动，再显式重试 | 显示真实错误和可用操作；重试使用新generation，无无限加载 | 高 |
| 多次重启与退出 | 慢关闭子进程 | 连点重试后关闭窗口 | 最新意图生效，进程全收尾，无后台遗留 | 高 |
| 对话完成后翻历史 | 长会话、网络延迟、SSE仍推进 | 发送、翻页、切换会话再返回 | 已完成回答不倒退，消息无重复，无运行中假象 | 高 |
| 等待澄清时继续输入 | 正在等待问题答案 | 发下一条，再答问题/取消 | 等待清楚、无空转；输入不丢失，只恢复一次 | 中 |
| 长手工SQL | 合法只读任务总时长>30秒 | Dock验证并执行 | 有界进度，成功/失败/取消明确终态，无永久running | 高 |
| 文件链接语义 | 工作区内文件symlink和目录junction | 删除、移动链接 | 目标数据保持或操作明确拒绝；反馈的对象与实际一致 | 高 |
| 两处编辑同文件 | Dock与Agent基于同旧版本 | 交错保存 | 仅一次成功，另一次明确版本冲突，不丢更新 | 高 |
| 换库与慢目录刷新 | A/B表不同，A反射慢 | 启动A刷新、切B、释放A结果 | B目录和版本一致，迟到A不覆盖，旧目录不可显示ready | 高 |
| SQL重复字段 | 合法SELECT但同名输出列 | 执行并打开结果Dock | 在丢值前要求唯一别名；唯一列查询准确展示 | 高 |
| 备份被锁 | 排他锁超过操作deadline | 开始备份、取消/等待截止 | 有界失败和清理；原数据库不变，无伪成功记录 | 中 |
| 恢复同时改配置 | 隔离恢复准备完毕 | 并发切换数据库再提交旧恢复 | 明确冲突，保留已成功配置，版本单调 | 高 |
| Story历史与排序 | 外部修改章节后关闭重启、删除中间章节 | 读历史、上下移动、批确认 | 内容对应恢复版本、顺序真实改变、批失败无部分修改 | 高 |
| Music逆操作及分析 | 有持续音重叠的乐谱 | +1/-1移调，再分析 | 新修订允许旧内容、峰值复音准确，历史可读 | 中 |
| Viz对象键序 | 两份语义相同spec | 分别创建并打开 | 校验一致、渲染一致，非法资源/字段仍拒绝 | 中 |
| 模型必要能力 | 端点仅Chat或工具协议不符 | 配置测试后发带工具任务 | 能力缺失明确可见，不能以ping成功承诺工具可用 | 高 |
| 跨DLC和执行器 | 旧版本资源、失效lease、被卸载视图 | 引用/编辑/导出/关闭 | 无旧owner提交、无未知写重放；GPU/音频等仍需实机验收 | 高 |

## 7. 尚未确认为缺陷的风险与未完成范围

- 远程任务风险已在后续真实使用中确认：提交/状态/取消只操作排队 Artifact，没有执行端；生产装配与空壳实现已移除。详见[连续产品使用记录](./continuous-product-use-20261107.md)。
- 扩展激活/停用回调的有界等待、DLC旧schema/降级支持、运行中卸载和未知结果reconcile还有未读分支；不能标记为全部兼容。
- Scene/Animation/Comic/Pixel/Voxel/Shader/Game已读多数Store写入、修订、版本与回执；未全量核验领域算法、导出格式、Phaser/WebGL、音频和UI手工编辑。详见功能清单逐项状态，不能用Store有CAS代替算法正确。
- 未验证真实MySQL/PostgreSQL、SSH/TLS、真实LLM/GitHub权限与限流、全部安装态DLC激活、旧版本升级迁移、生产性能、全局敏感日志及凭据生命周期；未使用用户API Key进行测试。
- 无新增证据支持“工作簿敏感词未脱敏”“文件夹路径一律小写”“手工SQL绕过校验”“Voxel重叠复制读回自己写入”等假设；这些已调查且本轮反例不成立，不列为缺陷。

## 8. 小步修复与清理顺序

每项先加入会失败的最小保护用例，再修源边界；完成后运行对应模块与相邻合同，避免一次重写多条执行链。以下是设计与验收顺序，未实施产品修复。

| 阶段 | 处理项 / 原因 | 行为验收与观测 | 回滚及清理 |
|---|---|---|---|
| A 数据保护 | FND-05/06/22，先限制误操作和覆盖 | 真文件/SQLite交错复现转绿，冲突有稳定分类，无部分提交 | 各自独立提交；不双写；恢复提交与staging清理一起验证，避免回退到不安全写路径 |
| B 完成与等待 | FND-19/01/04/02/03/17 | 长任务有终态、最新生命周期意图生效、UI版本单调、追赶无额外空等；记录失租/旧结果丢弃计数，不记秘密 | 保持公开SDK与耐久事件合同；逐边界切换并删除旧归并分支，无双调度器 |
| C 数据分析 | FND-20/08/09 | 来源版本与目录匹配、唯一列schema、备份截止/清理；真实网络数据库后续验收 | 目录缓存可失效重建；必要schema迁移单向一次，回滚先验证旧客户端可读范围 |
| D 领域语义 | FND-11/10/12/13/14/15/18/21 | 重启历史一致、排序/批事务准确、ID无歧义、合法逆操作、官方图表合同和计划生命周期 | Story/Music历史先备份验证；修订身份不重写，不建立两套新旧版本模型 |
| E 协议与长尾 | FND-16、remote job支持范围、清单未审深分支与真实执行器 | 明确支持能力；逐功能补齐黑盒、恢复和版本兼容证据 | 不保留无条件fallback；临时兼容要责任人、使用观测和可执行删除条件 |

下一轮检查按功能清单继续，只有源码主路径、失败出口及对应实际行为均有证据，才能将单项改为“已验收”。本轮没有任何单项被无条件标为“全部正确”。

## 9. 证据索引与复现命令

以下日志/脚本位于本机忽略目录，非版本库长期质量资产。报告已保留触发条件、调用边界和期望，正式修复应将最小反例转为符合仓库隔离规则的回归用例。Python复现必须用项目`.venv`并从仓库根执行；Node脚本转译当前生产TS，只替换进程/网络等受控边界。

```powershell
# 仓库根：既有后端定向集合，共73项
.venv/Scripts/python.exe -X utf8 -m pytest verification/tests/agent_core/test_session_coordinator.py verification/tests/system/test_story_dlc.py verification/tests/system/test_dbfox_music_dlc_package.py verification/tests/system/test_dbfox_workspace_dlc_package.py verification/tests/system/test_dbfox_visualization_dlc_package.py verification/tests/system/test_conversation_stream_backpressure.py verification/tests/system/test_dbfox_data_domain_model.py -q --tb=short -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"
.venv/Scripts/python.exe -X utf8 -m pytest verification/tests/agent_core/test_plan_repository.py -q --tb=short
# desktop目录：保持串行
npm test -- src/stores/__tests__/conversationStore.test.ts src/stores/__tests__/workspacePersistence.test.ts src/components/__tests__/EngineStartupGate.test.tsx --maxWorkers=1
npm run test:electron -- main/__tests__/engine.test.ts --maxWorkers=1
```

| 缺陷 | 证据文件 | SHA256 |
|---|---|---|
| FND-01 | `desktop/output/functional-audit-20261106/phase2/startup-fatal-repro.json` | `11cf1efa73ce0ff75cacae87563116e41ee5b67ac4f155440dcfa1961f359ec9` |
| FND-02 | `desktop/output/functional-audit-20261106/phase2/projection-stale-repro.json` | `065da526f1e24581c45220cf45a24d78fcaeb5a5afdf1a8338b7b0c9a9179956` |
| FND-03 | `desktop/output/functional-audit-20261106/phase2/coordinator-waiting-repro.json` | `a6d760279c602c7dbec32c5284a1c53de69fd4a11fa2c4d89a0a29b75f2f0848` |
| FND-04 | `desktop/output/functional-audit-20261106/phase2/engine-lifecycle-repro.json` | `240d1cbca599100b7ff69b0619b9e7d00a0c08249d192f1bd692f389ab73d8e3` |
| FND-05 | `desktop/output/functional-audit-20261106/phase2/workspace-link-mutation-repro.json` | `bbbe9f2e8748b4d23ccfd88ce12f021f9767f58f4bde5eace10e775b66347938` |
| FND-06 | `desktop/output/functional-audit-20261106/phase2/workspace-write-scan-repro.json` | `8404f1602408860281165f1bfc8d9dd3de8193eccae65da8202c83915a07fa3f` |
| FND-07 | `desktop/output/functional-audit-20261106/phase2/workspace-write-scan-repro.json` | `8404f1602408860281165f1bfc8d9dd3de8193eccae65da8202c83915a07fa3f` |
| FND-08 | `desktop/output/functional-audit-20261106/phase2/data-result-backup-repro.json` | `c24b6a68b942998ca46cd2c30d17d428d8b7d05e8660d78092f53caf38332baa` |
| FND-09 | `desktop/output/functional-audit-20261106/phase2/data-result-backup-repro.json` | `c24b6a68b942998ca46cd2c30d17d428d8b7d05e8660d78092f53caf38332baa` |
| FND-10 | `desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json` | `e0ef812c8fffa6fc6120d424936a688a2a4827f3ca836088c40d37e44a377ff9` |
| FND-11 | `desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json` | `e0ef812c8fffa6fc6120d424936a688a2a4827f3ca836088c40d37e44a377ff9` |
| FND-12 | `desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json` | `e0ef812c8fffa6fc6120d424936a688a2a4827f3ca836088c40d37e44a377ff9` |
| FND-13 | `desktop/output/functional-audit-20261106/phase2/story-order-history-repro.json` | `e0ef812c8fffa6fc6120d424936a688a2a4827f3ca836088c40d37e44a377ff9` |
| FND-14 | `desktop/output/functional-audit-20261106/phase2/music-semantics-repro.json` | `c2e92ff78f629621ccac01121c932c6899a5ab0d70e08571a2c491144ecfcea3` |
| FND-15 | `desktop/output/functional-audit-20261106/phase2/music-semantics-repro.json` | `c2e92ff78f629621ccac01121c932c6899a5ab0d70e08571a2c491144ecfcea3` |
| FND-16 | `desktop/output/functional-audit-20261106/phase2/stream-contracts-repro.json` | `678f38ada147b34f7fa867e43b858b44bb66162e694e1281ffa2a179af52c1cf` |
| FND-17 | `desktop/output/functional-audit-20261106/phase2/stream-contracts-repro.json` | `678f38ada147b34f7fa867e43b858b44bb66162e694e1281ffa2a179af52c1cf` |
| FND-18 | `desktop/output/functional-audit-20261106/phase2/visualization-order-repro.json` | `5255a058e5f4af4cd9acaf26319e7a5806a1eaa26982943dbd555637e91146fb` |
| FND-19 | `desktop/output/functional-audit-20261106/phase2/action-lease-repro.json` | `1e63c6c68274a3da6ef102c3b5a41a2c69ede9d21ec17a781b00f63952c034f7` |
| FND-20 | `desktop/output/functional-audit-20261106/phase2/catalog-generation-repro.json` | `b187978a7c169f2da0878e9a1507cbb0cbdbea328b9c64bce539955ed51fa559` |
| FND-21 | `desktop/output/functional-audit-20261106/phase2/plan-transition-repro.json` | `8084d8ae6c6f992100251e86398dd0ee50156f0a3944d71ab43ef78712988c31` |
| FND-22 | `desktop/output/functional-audit-20261106/phase2/restore-generation-repro.json` | `a53bc1333634fdeee8d5345c9e49824cd6ee71370851b691b7bcb6b89e0b1ab5` |

既有测试日志：`desktop/output/functional-audit-20261106/phase2/baseline-targeted-pytest.log`；`desktop/output/functional-audit-20261106/phase2/baseline-plan-pytest.log`；`desktop/output/functional-audit-20261106/phase2/baseline-targeted-vitest.log`；`desktop/output/functional-audit-20261106/phase2/baseline-engine-vitest.log`。
