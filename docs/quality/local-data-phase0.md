# 本地模型与 Data 能力 Phase 0

> 文档类型：质量记录
>
> 状态：当前
>
> 最后核验：2026-11-22

本轮是 Phase 0 的可靠性与真实模型基线增量，不表示 Phase 0 全部关闭，也没有实施业务
语义层、Recipe、定时任务或新增 DLC。基线 HEAD 为
`45f83a6a6352ea0c73d03c315df8429dcc040087`，改动在独立分支
`codex/local-model-phase0`。用户 Word 文件保持原样。本文保留各轮合并前的验证记录；
文中提交状态指当次验证结束时，最终提交与合并状态以 Git 历史为准。

首次基线与随后增量均保留在本文；最新代码与跨任务验证见“工具纠正反馈与文档编辑边界”。
这轮未下载模型或更改用户 profile，仍不能将 Phase 0 标记为全部通过。

## A. 已由当前源码和实机证明的事实

### 生产模型路径

`ManagedLocalModel` → `build_product_run_loop` → 原生 Responses Adapter → 唯一 RunLoop /
Tool Runtime → Data DLC 的 SQL 校验、执行、Result Artifact → Completion / Terminalizer。
没有新增模型控制循环、结果数据库、前端事实源或业务专用 Core 分支。

本机配置及 Ollama 实际登记均为 `qwen3.5:4b-q4_K_M`，摘要
`d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`，
权重约 3.32 GB，Ollama 0.40.16。运行时与权重在 E 盘；本轮只将私有验证 profile 的状态、
日志和临时文件置于 D 盘。用户 profile、模型参数和云端配置没有改动，没有下载模型。

实机为 Windows 11 x64 / RTX 4060 Laptop（8188 MiB VRAM）/ 约 16 GB RAM。
加载元数据报告模型占用和 GPU 占用均为 4,109,379,828 bytes，context_length=32768。
GGUF 标称上下文 262144 不是这台机器的部署配置。温度 1、top_k 20、top_p 0.95、
presence_penalty 1.5、think=false；输出上限 2048，单并行请求。

生产装配已经正确收敛输入预算：32768 − 2048 输出 − 1024 余量 = **29696 tokens**。
真实 Turn 记录也使用此上限，而非通用 RunLimits 的 65536。本次每轮物化 18 个
相关工具，工具 Schema 估计 9578 tokens；历史和观察也计入预算；本轮没有通过加大上下文、轮次或停止预算制造成功。

### 已有 Data 能力与覆盖范围

- Catalog Workbench 为工具和 UI 提供同一套目录、字段、关系与版本信息。
- `ResultProfileTool` / `profile_rows` 已对有界 Result / 显式 Snapshot 统计空值、去重值、
  数值/日期范围与频次，并返回 sample_size / sample_truncated。它不是整个数据库的
  持久画像，也不能把样本统计冒充全表结论。
- `workbook_inspect` 按范围读取结构与样本；`workbook_prepare` 保留附件 hash、工作表、
  明细区域、排除行和原始行来源，准备后的数据仍经过现有 SQL 验证执行链。
- 普通 Result 只持有来源和元数据；模型通过有界观察读取数据。没有复制整表到 Core。
- 60-case Data Agent 集合分为 basic_sql 12、multi_stage 8、tool_recovery 8、
  context_memory 8、security 8、large_result 6、fault_interrupt 5、uncertainty 5。
  本轮只真实运行其中三题，各三次，不能称为 60 题真实模型通过。
- Data + Workspace Composition 只有一个脚本模型组合题：读取目标文件并检查 orders
  Schema。它不是 Excel 对账、指标治理、月度报告或 Recipe 的端到端证明。

## B. 已复现的问题

| 问题 | 当前证据与处理 |
| --- | --- |
| 草稿会话并发创建 | 附件、电脑和发送同时进入可创建多份 Session。新回归修改前 2 fail / 1 pass；现在三个入口共享同一 workbench 的在途创建 Promise，迟到结果只绑定原 scope，失败可重试。 |
| 有效共享被历史分页隐藏 | 一个有效窗口后加入 20 个已撤销浏览器共享，旧查询会遗漏窗口。现在有效/暂停且未过期的当前代次共享与最近 16 条历史共同查询，执行授权仍独立检查。 |
| 坐标审批不完整 | 后端已有 position，但 UI 未显示。现在展示精确相对 X/Y、对应观察 Artifact、观察尺寸与完整时间；不将旧截图冒充当前画面，审批仍绑定精确 Invocation 输入。 |
| 只剩引用仍可完成 | 真实模型先给数值，引用修复轮却只返回 cite，旧 Completion 仍可 completed / partial。现在纯引用及其常见 Markdown 包装请求完整回答修复，到预算时拒绝；合法 Artifact 展示仍可独立交付。 |
| Linux mypy 错检 Windows 实现 | 在本地用 --platform linux 重现 14 个 ctypes/msvcrt/os.O_BINARY 类型错误。显式平台守卫保留真实实现；CI 同时保留全量 Linux 检查和 Windows 目标检查。 |
| 浏览器等待占用写事务 | 原真实 Edge 延迟 1.5 秒时，写事务 **1.530 秒**，另一 Session 停止 **1.527 秒**。后续保留授权围栏，拆分异步派发与等待；同法复测分别降至 **2.05 毫秒 / 2.55 毫秒**，仍只发送一次导航。详见后续增量。 |
| CLI 验证装配与生产脱节 | Bench catalog 提前导入不相关 runtime，污染隔离 DB 绑定；Data/Music 手工构建 Loop 遗漏生产配置；Authority 只有 resolver 没有 discovery。现改为标准库 EntryPoint 延迟载入选中 runner、复用生产工厂或明确登记合成资源发现。 |
| 评测证据选择不正确 | 旧数据集使用退役的非命名空间 Artifact 类型；旧 oracle 可选到从未成功执行的 SQL。现在按真实 Result→sourceSqlArtifactId 血缘取查询，未知工具按实际拒绝记录，不导致整批评分崩溃。 |
| 分组排序误判 | 用户没有指定顺序，两个 300 条分组顺序不同不应失败。只修正该用例 ordered=false，数据集 1.2.1；错误数值仍失败，原始基线保留并按同一合同重评。 |
| 过期漏洞例外 | 当前 Data 连接明确不支持 SSH，生产源码无 sshtunnel/paramiko 调用，但清单和 Frozen hidden import 仍保留。移除这两包及多余传递依赖，声明 DLC 实际使用的 cryptography，删除过期忽略。三份 uv 哈希锁未升级其他包。 |

## C. 尚待验证的风险与未完成事项

1. **当前配置的完整交付仍不可靠**：首轮两个矩阵各为 1/9；后续 Prompt 4.7 原三题为
   **5/9**，查询结果 9/9 正确，但四次引用失败。新增两题为 **5/6**，另一次只有检查计划
   就提前完成，没有计算结果。本轮新增计划合同矩阵为 6/9，任务集不同，不作直接成功率
   对比。不能把局部数字正确或测试通过当作任务完成；尚未证明稳定。
2. 浏览器长等待的写锁问题已修复并验证停止、提交失败和不重放。Native UIA/COM 仍同步
   派发；未声明所有原生操作均可立即中断，也没有替代 OS 沙箱或撤销已发送的界面副作用。
3. 只核验了当前实际安装的 4B。历史 9B 视觉记录不代表当前已安装；本轮未下载或评价 9B。
4. 未进行完整 Electron 用户路径、安装包、Linux/macOS 进程实机验收，不能将 Windows
   测试或交叉类型检查描述为这些平台的产品级通过。
5. 公开 CI 元数据表明旧提交存在类型、依赖、生产解释器、Windows release contract 和
   deterministic bench 失败。最新 main 的 skip-ci 提交没有等价远端 CI 证据。
   认证日志下载因尚未授权读取 Git 登录凭据被自动审批拒绝；只使用公开元数据和本地复现。
6. 外部数据变化时普通 Result 可能重新查询；只有显式 Snapshot 才是冻结数据。Phase 1
   不能把“引用可打开”直接表述为历史数值已冻结。

### 公开 CI 基线

| 运行 | 对应提交与公开失败步骤 |
| --- | --- |
| [CI 44772093517](https://github.com/trrueee/DBFox/actions/runs/44772093517) | PR 8797f952，与本轮 HEAD 不同；完整 Python 类型检查、Python OSV 审计失败。 |
| [Scheduled CI 43856077225](https://github.com/trrueee/DBFox/actions/runs/43856077225) | 旧 d7f45a8b；Windows EngineSupervisor release contract、类型检查、生产解释器回归与依赖审计失败。 |
| [Agent evaluation 44716922604](https://github.com/trrueee/DBFox/actions/runs/44716922604) | 旧 d7f45a8b；确定性 Core/Capability/Composition 执行步骤失败。 |

公开 annotations 只给出退出码 1。没有认证日志，不能把本地复现原因直接当成远端
每个失败的确切根因。本轮将本地可复现的类型、依赖和 Bench 问题修复并保留回归证据，
未触发远端 workflow，也不宣称这些历史运行已变绿。

## D. 最小改动、所有权与复用决策

| 文件/范围 | 职责与变化 |
| --- | --- |
| ConversationCenter / workspaceStore / 并发测试 | 合并在途创建请求，仍由现有 Session Store 与 workbench scope 保存身份；不建第二份 Session 缓存。 |
| computer/store.py | 共享可见性查询，不改变授权状态机和资源版本。 |
| computer/tools.py / ComputerApprovalDetails | 准入 review 补充实际观察身份与尺寸；UI 只投影精确审批信息。 |
| agent/completion.py / prompt.py / model/system_prompt.py | 通用正文完成条件和完整修复指引，Prompt 4.4；不包含 SQL/业务指标判断，不伪造或程序拼接模型结论。 |
| computer/native.py / local_execution/windows.py / ci.yml | 用 Python/mypy 官方平台守卫表达真实 OS 边界，分别检查 Linux 与 Windows。 |
| verification/bench | 验证系统使用生产装配、规范身份和真实结果血缘；新增本地 profile 入口、首条公开文本延迟、每 trial 检查点和运行环境证据。 |
| requirements / constraints / build_sidecar / osv-scanner | 移除已退役依赖，cryptography 作为 DLC 签名直接依赖；无新增兼容层、无漏洞忽略。 |

采用项目已有 Store、生产工厂、标准库 importlib.metadata.EntryPoint、既有 citation parser、
SQLite/Alembic 和实际 SQL/Representation 合同。未引入新依赖、Registry、Mapper、
Agent Scheduler 或长期双协议。新增代码位于真实并发入口、完成边界和验证激活边界。
没有 API Schema 变更，不需手改或重新生成 API 客户端。

不采用额外 Agent SDK、新模型控制层或模糊工具别名。未选择升级整套 SSH：现行产品
没有该执行路径；不以装一个包冒充支持 SSH。恢复 SSH 必须另行设计与实机验收。

## E. 测试和真实证据

### 配对本地模型矩阵

三个问题：orders 精确计数、payments.amount 为 NULL 的计数、按客户 segment 分组计数；
每题三次，均走生产 RunLoop 和本地模型，未使用脚本模型生成回答。独立 oracle 对
实际执行过的 Result 所指 SQL 在固定只读合成源中复算；它证明查询数值，不代替 Dock
加载成功或用户任务完成。

| 指标 | 基线 Prompt 4.3 | 修复后 Prompt 4.4 |
| --- | --- | --- |
| 独立任务检查通过 | 1/9 | 1/9 |
| 实际执行查询结果等价 | 9/9 | 9/9 |
| 任务耗时中位数 | 11.135 s | 16.952 s |
| 最慢任务 | 26.003 s | 31.466 s |
| 输入 tokens（九次合计） | 588584 | 630234 |
| 输出 tokens（九次合计） | 3934 | 4419 |
| 工具失败/拒绝 | 1/34 | 1/37 |
| Provider 重试 | 0 | 0 |

这不是成功率提升证据，也没有性能提升结论。基线中唯一通过的分组回答正文仍偏弱；
当前通过样例明确给出 36 条 NULL 记录及真实证据引用。安全和来源检查通过不能抵消
其他任务未向用户交付回答的失败。

修复中间轮另有 0/9 记录，包含一次 Provider 500 后受控重试；同样保留，不挑选删除。
最早 CLI 配置错误、隔离 DB 检查和 oracle 失败属于验证基础设施故障，不混入模型成绩。

原始合成数据和运行时均在本地忽略目录（不是 clean checkout 的链接要求）：

- `.tmp/phase0-local-model/baseline-4b-final/`、`candidate-4b/`、`candidate-4b-final/`
- 同名 `-rescored/` 保留统一数据集 1.2.1 评分；`paired-summary.json` 记录重评来源。
- 隐藏 `.*-work/runtime/metadata.sqlite` 保存 Run / Turn / Invocation / Artifact 事实。
- `probe/attestation.json`、各报告 `environment.json` 为实际模型和设备配置证据。
- `browser-lock-measurement.json`、`browser-lock-measurement-timed.json` 为两次真实浏览器测量；后者记录 BEGIN IMMEDIATE 成功到 commit 事件的实际时间。

首条公开文本延迟由既有 LiveStreamHub 订阅测量，是执行开始到公开 delta 的延迟，
不是 Provider TTFT。温度未固定随机种子，九次样本量有限，冷启动和前缀缓存也会影响
耗时，因此不以单次速度或 token 数作性能承诺。

### 已执行验证与待完成门禁

| 验证 | 最终结果与证据 |
| --- | --- |
| CPython 3.14.6 系统确定性集合 | **1348 passed / 143 deselected**，`production314.log`；排除 e2e、integration、real_llm、migration、engineering_contract、platform_contract，不能冒充 Linux 上 CI 全 marker 集合。 |
| Core + Bench 确定性集合 | **495 passed / 2 deselected**，`core-bench-final.log`；生产进程路径、无外部模型。 |
| 真实 Edge + 工程合同 + Music 组合回归 | **52 passed**，`phase0-real-browser.log`；包括审批观察来源、停止、外 Session 拒绝。 |
| 最终工程与文档合同 | **45 passed**，`engineering-docs-final.log`。 |
| 五个公开 deterministic Bench | Core Loop 3/3、Context 2/2、Authority 3/3、Data Direct 3/3、Data+Workspace Composition 1/1；Authority 修复前 1/3 的失败报告保留。 |
| Data grader 与 manifest | `verification.bench validate` 和 `calibrate capability.dbfox_data.agent` 通过；不是 60 题 LLM 通过。 |
| 前端受影响回归 | **44 passed**，`frontend-final-reviewed.log`；六个文件，包含源码复核后的最终重跑。 |
| Electron Host | **40 passed**，`electron-tests.log`；不代表安装包验收。 |
| Lint / 类型 / 构建 | Python pyflakes、Linux 和 Windows 目标 mypy（各 269 个源文件）、前端 lint（0 error / 20 既有 warning）、测试类型和生产构建通过（最终构建 `frontend-build-reviewed.log`）。 |
| 新哈希锁环境一致性 | CPython 3.14.6 的 67 个已安装包，`uv pip check` 通过。 |

主要复现命令（均从仓库根执行；前端命令在 desktop 下）：

```powershell
# 实际 4B 三题各三次；profile 是私有状态目录的验证副本
$env:DBFOX_RUN_REAL_LLM = "1"
python -m verification.bench run capability.dbfox_data.agent `
  --local-model-profile .tmp/phase0-local-model/probe/local-model.json `
  --case sql-count-orders --case sql-null-payments --case sql-segment-count `
  --repetitions 3 --keep-runtime --output .tmp/phase0-local-model/candidate-4b-final

python -m pytest verification/tests/agent_core verification/tests/bench -q --tb=short `
  -m "not e2e and not integration and not real_llm"
.\.tmp\phase0-local-model\python314-venv\Scripts\python.exe -m pytest verification/tests/system -q --tb=short `
  -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"
python -m pytest verification/tests/system/test_computer_browser.py verification/tests/system/test_engineering_contracts.py verification/tests/bench/test_music_bench.py -q --tb=short
```

实际运行另给每组 pytest 指定唯一 D 盘 basetemp / cache_dir，并设置 TEMP/TMP，避免 C 盘
空间不足和历史临时目录权限影响。首次发现的失败记录保留；当前源码修复后的结果才列为通过。
本机模型程序缺失的私有 profile 负向检查明确退出 2：`LOCAL_MODEL_FILES_MISSING`，
没有进入远端凭据路径。这是启动失败验证，**没有**冒充推理中断故障注入；后者仍待验收。

OSV 官方批量 API 核验三份哈希锁的 76 个包版本，覆盖 Windows/Linux/macOS 与
Python 3.12/3.14 条件，返回 0 个公告，不使用忽略项。这是包版本公开元数据核验，
不冒充 GitHub 上 checksum-verified OSV Scanner 作业已通过。

已用固定 CPython 3.14.6 单独建立 D 盘验证环境，依赖按哈希锁安装；没有把测试依赖
装入 Frozen 构建环境。上述选定系统回归已经通过；没有运行的 marker、Linux/macOS 实机与安装包仍未验证。

## F. 下一阶段最小切片与验收

后续增量已完成浏览器 effect fence / 等待边界和查询后的模型停止故障注入；仍需解决引用
交付可靠性、只给检查计划就过早完成，并验收真实 Electron 历史成果、取消与流式半途
断连。模型继续使用用户配置，不切换云端。未通过上述质量门禁前不扩展完整语义层和 Recipe。

Phase 1 的最小切片是**一份已授权数据库 / 工作簿的有界质量概览**，先复用
`result_profile`、Catalog、Workbook 和现有 Representation，而非新增业务语义平台：

1. Data DLC 持有来源版本、检查参数、样本范围和质量结论。Core 只持有通用 Artifact /
   Evidence / Run 状态；React Query 和 Dock 是展示投影。
2. 正式查询继续经过不可变 SQL Validation Artifact 和只读执行。UI 批量动作复用现有
   Action Run 的正式调用与结算，不从组件直接绕过 SQL/Policy，也不由工具另开循环。
3. 有界样本给出 NULL、候选重复、数值/日期范围；准确全表计数仅在明确预算内运行。
   不可计算的全表结果标 unknown，不从样本外推成精确事实。
4. 本地模型只对已计算的有界事实组织摘要。模型不可用时确定性概览仍可用，摘要失败
   显示失败并保留已确认成果；不要求 4B 自主完成十几轮分析。
5. 每项结论引用成功观察的真实 Artifact；点击走现有 Dock。重开时区分实时重查与冻结
   Snapshot；数据版本变化必须可见。

验收数据按可复现生成器构建：订单、客户、支付三表及一份 Excel 目标表，明确植入
NULL 金额、重复业务键、缺失维度键、不同货币/日期格式、缺月和一对多放大风险；所有
数据均为合成数据。最初只验收画像与质量，不把未批准的净收入定义当成事实。
现有 SQLite seed 的 1000 条订单、36 条 NULL 支付可作为第一组已有精确 oracle。

验收分层：L0 无模型计算/权限/版本测试；L1 生产 RunLoop + 脚本模型验证顺序与失败；
L2 同配置本地模型每题三次、保留失败与耗时；L3 真实 Electron 打开、点击证据、关闭
Dock 重开、切换会话、取消和历史重载。全链通过后再讨论指标版本、Recipe 和月度报告，
本轮没有将这些后续能力描述为已实现。

## Phase 0 后续增量（2026-11-21）

### A / B. 实际调用链与根因

1. `ContextSnapshot.model_message_plan` 原先把 `run_focus` 放在当前请求与原生历史之前。
   最末条却是刚被拒绝的 Assistant 回答，真实 4B 经常只补引用或返回空输出。反馈本身
   原本已是 Runtime 内容，不能误称为“不可信数据”。现在只在 Prompt 尾部表达一次，
   位于完整响应 batch 之后、用户 steer 之前，单独预留和记录其预算；不提升 system 权限。
2. `evaluate_bounded_partial` 对有成果但引用错误的回答直接返回 FAIL；反而无回答、有成果
   可以进入最终整理。现在前者返回 REPAIR，只允许在现有预算内进入一次已有 synthesize
   阶段，不授权发布不合法文字。最终整理后仍不合法则失败，不增加重试或轮次。
3. 最终整理中的普通反馈会覆盖 synthesize 标记。现在保留同一 `Run.focus` 的单向阶段，
   防止恢复 worker 重新开放能力工具；缺失项和原因仍正常更新，没有新增状态表。
4. 同步 Playwright 将 goto 等网络等待包含在 `effect_lease` 中。复用官方异步 API、
   标准库 Runner / eager task factory 和现有电脑 worker：事务内检查并派发一次，事务外
   等待同一个 Future。提交失败仍收集原动作结果并报告 unknown，不能回滚后重发动作。
5. 真实模型故障注入发现，Bench 最后调用具有启动语义的 `endpoint()` 获取遥测，模型已
   关闭时会遮住原始 Trial 结果。新增 Host 内部只读 `running_endpoint()`，Bench 只读取
   活动实例；状态不可用就记录 unavailable，不重启模型、不隐藏任务失败。

### C. 本轮仍存在的问题

- 原三题的四次失败均产生正确查询结果和正文，但最终引用未满足合同，例如模型使用
  `[[cite:artifact_...]]`。系统仍拒绝发布；没有自动改写标记、拼接证据或降低完成校验。
- 未参与修复的 `sql-completed-revenue` 第三次在 Schema 发现后只说“让我检查该表结构”，
  Provider 正常结束被接纳为最终回答；没有执行 SQL，也没有可独立比较的计算结果。
  这是实际任务失败，不能仅归因于引用或说六次查询全部正确。后续应明确目标与完成证据
  的合同，不能在 Core 增加“收入/SQL”关键词分支或根据测试 case_id 指挥模型。
- 新逻辑没有使 4B 稳定达到业务可用标准，不能以 5/9 宣称成功；也没有以增加预算、
  选择最佳一轮、切换 9B/云端或放宽 scorer 换取通过。

### D. 复用决策与代码边界

复用既有 Run.focus、CompletionSupport、REPAIR、最终整理工具物化限制、Tool Settlement
与 Artifact；不改 SQL 安全链、资源授权、SDK/API v2、数据库 schema、Run 身份或预算。
浏览器复用已经锁定的 Playwright 和 Python 标准库，不增加依赖、目标锁注册表或第二套
调度。read-only 模型端点是同一生命周期 owner 的内部观测，不是新的推理/适配层。

新增运行数据仍由现有 SQLite / Trial 文件保留，Future 只是一次已授权动作的等待句柄，
不承担耐久事实。无兼容 mapper、镜像状态、自动重放或迁移债务。主要后续风险是
Playwright 升级时异步派发先后需要继续做真实 Edge 回归，以及模型无法遵循完成合同。

### E. 真实模型与独立验证

模型、摘要、采样参数、输出/上下文、单并行设置均与首轮相同；每道题各三次。
旧基线、过渡版本和失败原始记录全部保留。

| 同题矩阵 | 原 Prompt 4.3 | 原增量 4.4 | 顺序/预算 4.5 | 加强文字 4.6 | 当前 4.7 |
| --- | --- | --- | --- | --- | --- |
| 完整任务通过 | 1/9 | 1/9 | 5/9 | 4/9 | 5/9 |
| 实际执行结果等价 | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 |
| 耗时中位数 | 11.135 s | 16.952 s | 15.621 s | 14.446 s | 17.714 s |
| 最慢任务 | 26.003 s | 31.466 s | 23.067 s | 28.383 s | 38.445 s |
| 输入 tokens | 588584 | 630234 | 596060 | 608561 | 655347 |
| 输出 tokens | 3934 | 4419 | 5069 | 5101 | 5645 |

额外文字的 4.6 没有证明收益，已移除。4.7 保留顺序修复和最终整理资格修复，但不能声称
后者将同题总体成功率提高到了 4.5 以上。4.7 的订单计数 3/3、NULL 计数 2/3、segment
分组 0/3，任务分布仍不稳定；全部九次只有最终引用不合格或任务通过，没有基础设施失败。

额外两题共 **5/6**：金额范围 3/3、已完成订单收入 2/3。五次有正确执行结果，另一次
过早完成、没有计算结果；不是错误数值被放行，也不能记为 6/6 数值正确。两题耗时中位数
14.811 s，合计输入 368184 / 输出 2714 tokens，零 Provider 重试。无配对旧基线，不作
泛化成功率提升或性能提升结论。

浏览器相同 1.5 秒延迟复测：写事务最大 **0.002050 s**，另一 Session 停止 **0.002549 s**，
导航请求 1 次；原分别为 1.530384 / 1.526556 s。计时范围为 BEGIN IMMEDIATE 成功到
SQLAlchemy commit 事件。真实竞态覆盖：等待期间停止、提交失败后结果未知、恰好一次
导航；不是仅检查 mock 或把等待缩短为零。

真实模型停止注入通过：在只读查询成功后关闭本测试独占的 ManagedLocalModel，Run
返回 `LOCAL_MODEL_START_FAILED`，Result 的 1000 条计数仍可独立复算；完整源库 dump
与种子重建相同，仅执行一次查询，远端配置解析从未进入，结束遥测标记 unavailable。
正常业务 Bench 将该故障 Trial 标为 unscored；本次负向验收另核验中断语义，不把它计入
业务通过率。首次遥测异常和验证脚本字段/评分读取错误均保留，最终独立验证才列为通过。
本次是两次模型调用之间的停止，不冒充流式 token 半途中断、自动恢复或 Electron 验收。

| 代码验证 | 结果 |
| --- | --- |
| Core + Bench + 电脑/构建/工程合同 | 554 passed / 43 deselected；随后阶段标记修复另跑完整 Core，393 passed / 2 deselected。 |
| CPython 3.14.6 真实 Edge、Native/Store/取消/派发 | 18 passed；包括真实浏览器阻塞、停止与提交失败。 |
| CPython 3.14.6 Prompt / Completion / RunLoop / Budget / Frozen 构建合同 | 107 passed；包含后续阶段标记修复。 |
| CPython 3.14.6 本地状态、Conversation、Data grader/report | 54 passed；模型状态查询禁止启动，现有会话准入和评分合同保留。 |
| 最终工程 / 类型 / Lint | 工程文档合同 45 passed；Linux、Windows 目标 mypy 各 269 个源文件通过；pyflakes 和 git diff --check 通过。 |
| 改前反例 | 反馈顺序/预算 2 fail；慢导航反例 fail；最终整理 2 fail；阶段标记 1 fail / 1 pass；修复后对应测试通过。 |

源码与原始证据位于忽略的 `.tmp/phase0-followup/`：`feedback-4b/`、
`feedback-syntax-4b/`、`finalization-4b/`、`holdout-4b/`、隐藏同名 work/runtime SQLite、
`comparison.json`、`source-4.6/`、`source-4.7/`、最终源码与哈希 `source-final/`、`browser-lock-measurement-timed.json`、
`local-model-outage-attested/fault-evidence.json` 与各 pytest 日志。4.7 同题矩阵后又修复了
最终整理标记覆盖，额外两题使用修复后的代码；没有将中断恢复未经实测的部分混称通过。
保留原始模型证据、日志与用户文件，仅清理已完成的 pytest 临时夹具以控制 D 盘空间。

### F. 下一步验收条件

仍停留在 Phase 0。下一步围绕“最终回答是否完成目标”的通用合同、真实引用交付和
Electron 的历史成果/取消路径设计可复现反例；不按单个指标硬编码、不更换用户模型。
确定性质量概览仍是随后 Phase 1 的候选切片，本文没有把该功能或完整月度报告描述为已实现。

## 计划合同校验与已撤回的模型验收实验

### 调查与取舍

本轮首先尝试在同一 RunLoop 内增加受限模型验收 Turn，沿用原生 function calling、
Invocation、Observation、预算和持久化；没有把它作为第二个 Agent。实验记录了三种
建议：目标满足、仍需工作、受限。随后用固定的八类合成候选、每类三次检验，包括普通
解释、计算/开发计划、与证据矛盾的结论、正确结果、真实访问限制、范围错配和候选注入。

真实本地 4B 的三分类结果为 **14/24 符合预期**：6 次完整回答均判为满足；15 次应该继续
的候选中 6 次判为继续、9 次判为受限；3 次实际受限中 2 次判为受限、1 次判为继续。
未出现把未完成候选判为完全满足，但不能因此宣称验收通过：该实验可能把未来工作承诺
交付成 bounded partial，且输入没有充分表达执行者的完整能力边界。数字不是模型能力
上限，也不是完整 Agent 用户任务成功率；只有验收使用了真实模型，作者和来源为合成夹具。

早期两题六次完整任务实验为 3/6，另发现验收只能看到“返回一行”等元数据，无法检查
作者当轮拿到的真实数值。实验中补过同一有界 transient output 的来源摘要绑定，但这
仍不能把目标语义变成确定性事实。所有中间源代码、真实模型输出和失败记录均保留。

**取舍：撤回这条未达标的产品路径。** 当前产品没有 `review_completion` 工具、额外验收
模型调用、可选审核框架或其运行状态；代码没有保留为待清理的兼容/实验中间层。生产
回到同一原有 RunLoop，接着修复能够从当前权威事实确定的问题，不针对 4B 或某个题目
增加提示词、关键词判断、分支、别名与自动引用修补。

### 当前落地的源头修复

| 已复现缺口 | 当前实现 |
| --- | --- |
| 当前计划仅在可淘汰的原生工具历史中 | 从同一 PlanRepository 读取带版本 TaskPlan，放入 ContextSnapshot；Prompt 在历史之后呈现当前版本。 |
| 有 pending / in_progress / blocked 计划仍能提交完整回答 | CompletionPolicy 根据明确状态拒绝完整交付，不读取答案里的业务关键词。 |
| 结算自动将未执行步骤改为 skipped，再把计划标为 completed | Terminalizer 最终事务拒绝不合格计划；Plan owner 自身也拒绝该状态转换，删除自动制造完成的分支。 |
| 靠上下文裁剪省掉完成要求 | 当前计划单独保留必需预算，预算不足明确失败；历史淘汰不会抹掉它。 |

同一 `agent_task_plans` 仍是权威。新 Snapshot 是冻结投影，不是另一套计划库；无新依赖、
公共工具/SDK/HTTP 合同或迁移。Agent 定义 **4.3**、Prompt **5.0** 标识这轮策略；之前
临时实验版本的记录保留但不描述为当前产品。

保留显式重规划和有理由不再需要的步骤处理，不要求每个简单回答强制建计划。`is_settled`
只表示计划显式结清，不能证明用户目标理解正确、所有必要步骤都已声明，或结果语义正确。

### 验证与实际局限

- 改前 **9 个反例失败**，包含不完整计划在常规/预算边界被接纳、当前计划缺失、最终事务
  自动跳过步骤及 owner 直接制造完成；对应修复后通过。另补顺序/预算保护和中英文、不同
  任务目标的真实 RunLoop 脚本回归，保持实际成果只执行一次。
- Core / Bench / 注册与工程合同集合 **564 passed / 2 deselected**；随后补充的三条跨任务
  回归和计划顺序用例也在生产解释器集合复验。
- CPython **3.14.6** 的完整 Core 与 Action Run、Conversation、Scene、模型状态、Frozen
  构建合同相关系统集合 **478 passed / 43 deselected**；不是安装包或 Electron 用户路径验收。
- 实验撤回、当前代码与文档收敛后，完整 Bench、注册和工程合同再验为 **161 passed**；
  未保留实验期间为额外审核调用调整的组合评分或脚本行为。
- Windows 和 Linux 目标 mypy 各 **269 个源文件**通过；pyflakes 与 diff 格式检查通过。

最终真实模型选取已有 `multi-catalog-pivot`、`sql-min-max`、`sql-completed-revenue`，各三次，
数据集与 scorer 未修改、预期未注入生产请求、模型参数和停止预算未改变：

| 任务 | 完整业务验收 |
| --- | --- |
| 显式要求维护计划、检查关联字段后查询 | 1/3 |
| 金额范围 | 2/3 |
| 已完成订单收入 | 3/3 |
| 合计 | **6/9** |

九次实际 SQL 结果均与独立 oracle 等价，零安全 veto、零未评分基础设施任务；观察到两次
本地服务 500 后的有界 Provider 重试。两个计划题失败分别是只有一次事后计划、没有维护
计划；另一次金额题因回答/引用收尾停滞而失败。不能把引擎 completed 当作业务成功。

这仍未达到可靠可用门禁：自然语言要求并不等于已正式声明的验收合同。当前修复阻止
Runtime 擦掉已声明但未完成的计划，不会假装能从任意自然语言推导所有成功条件；无计划
的过早结束、遗漏明确步骤和引用问题仍保留。普通两题为 5/6，没有高于此前 5/6；新增计划
题无配对基线，不宣称总体成功率或性能提升。

证据在忽略目录 `.tmp/goal-review/`：`experiment-source/`、`holdout-4b/`、
`reviewer-4b-evidence/`、`reviewer-real.log`、`plan-before.log`、`plan-after.log`、
`plan-loop.log`、`plan-core.log`、`production314-final.log`、`plan-production-4b/` 及其
隐藏 work/runtime SQLite。仅清理已经完成的确定性 pytest 临时夹具；模型证据、权重、
原 profile 和用户文件保留。

后续应通过现有 CompletionConstraint、Tool 语义、Artifact/Representation 表达可客观
验证的交付条件，由相应 owner 校验；不另建万能验收 Agent，也不把每个业务题目写进 Kernel。
引用表达应继续评估通用的类型合同，不能靠识别某种错误括号来冒充来源可信。

## 结构化答案交付与跨任务复核

### 本轮落地与边界

在相同 HEAD、同一未提交分支继续开发，Agent **4.4**、Prompt **5.1**。新增唯一 Core 控制
入口 `submit_answer@1`，输入为有界 Markdown 片段及各片段的来源 ID。复用现有严格输入、
Registry、Policy、Invocation、Observation、Completion、TaskPlan、Terminalizer、Evidence 和
Dock；没有新答案表、第二套 RunLoop、模型自评、业务关键词判断或参数猜测/自动转换。
详细合同和七项 Kernel 变更依据见[连续执行上下文](../architecture/agent-context-continuity.md#结构化答案提交agent-44--prompt-51)。

模型不能提交可信 Evidence、观察位置、授权、完成状态或限制代码。来源先在现有调度
边界解析，未授权、跨 Session、缺失与内部工件不能成为引用。候选必须来自已成功结算、
owner 为 Core 的独立 Invocation；原生 function_call 和参数不改写为假造的模型消息。
Terminalizer 再次检查来源，按明确片段生成原有引用/Evidence；不再静默删掉无效来源。
最终 UI / SSE / 历史 snapshot 合同不变，不需要 HTTP 客户端或 API v2 迁移。

普通无来源回答仍可用 assistant 文本。结构化提交成功仅表示候选接收，不能跳过计划
与领域完成约束，也不能证明某条引用确实支持该业务结论。已有正文引用仍是正式呈现
合同，不增加两份 UI 或 Evidence 权威。

另外，一条取消竞态反例暴露了原有最终事务问题：提交之后、落库之前到达的取消会在
底层抛异常。最终事务现在复用 `begin_agent_write`，先检查当前取消与 steer，再检查计划
和写入；取消由已有 checkpoint 结算，不先完成计划、不发布假成功。改前反例和修复后
记录分别保存在 `edge.log` / `edge-fixed.log`。

### 确定性与产品呈现检查

- CPython **3.14.6**：完整 Core、注册、工程合同、Action Run 生命周期与 Conversation
  集合 **520 passed / 2 deselected**，只有既有第三方 Starlette 弃用警告。
- 完整 Bench 与注册合同 **116 passed**，未调整业务 scorer、黄金 SQL、组合工具顺序、
  模型参数或停止预算。首次集合的 4 处失败涉及新入口注册快照和原反馈文本断言；注册
  指纹按新增合同显式更新，原正文引用反馈保留，后续集合通过。
- 新回归覆盖结构化输入边界、真实 Invocation 结算、原生记录保留、精确片段 Evidence、
  反复引用同一工件、混合批次拒绝、非法来源、跨 Session、计划门禁、进程中断后的候选
  读取，以及最终事务取消。中断测试证明候选来自持久参数，不等于无人介入业务恢复验收。
- 前端 Markdown / Evidence / Dock **17 passed**，包括加粗、表格、emoji 与各处独立引用
  的点击身份；`typecheck:test`、lint 通过，lint 仍有 **20 条既有 warning**。无前端产品
  样式或 API 变更；未将组件渲染测试描述为 Electron 实机验收。
- Windows / Linux 目标 mypy 各 **270 个源文件通过**，pyflakes 与 diff 检查通过。未打包、
  安装、发布或推送，也没有声称 Linux / macOS 原生进程或安装包已通过。

### 同一本地模型的实际结果

仍使用既有 `qwen3.5:4b-q4_K_M`、相同 digest、Ollama 0.40.16、32K context / 2048 output、
相同采样参数，没有模型下载、用户 profile 修改或云端调用。评测输入是合成资源，所有
动作通过正式生产 RunLoop；期望值只在外部 oracle，未注入工具或生产提示。

| 固定 Data 任务（各三次） | 完整业务验收 |
| --- | --- |
| 已完成订单收入 | 3/3 |
| 金额最小/最大值 | 3/3 |
| 显式计划与关联字段检查后查询 | 0/3 |
| 合计 | **6/9** |

六次基础任务实际使用结构化提交并生成可解析引用。总体仍为 6/9，没有超过上一轮；
只有八次产生可与独立 oracle 比较的执行结果，均等价。另一次在计划证据更新时停滞，
没有执行查询，不能算正确。多步失败还包括将 citations 放错层级并重复参数、引用内部
工件，以及整理前已耗费过多调用。现有校验层已给字段位置反馈，未再增加该题专用规则。
本组 70 Turn，实际 input/output 847599 / 9397 token，median 26.179 秒，零安全 veto、零
未评分基础设施任务；这是本组测量，不能归因为单一改动的速度/可靠性提升。

跨任务还通过正式 Workspace 和 Windows Broker 检查：

- **文件摘要三次**：内容数值均正确、源文件未变，但只有 **1/3** 产生真正可点击的正文
  Evidence 引用；另两次只是写出 Artifact ID 或错误标记。普通文本完成资格尚不能从
  自然语言自动得到所有交付要求，新入口不等于所有模型都会正确使用它。
- **代码修复三次（正确 Worker 环境）**：一轮真正经过失败测试 → 文件修改 → 成功测试，
  并由独立 `unittest` 再验通过，测试文件未改；但该轮没有有效引用。因此代码行为闭环
  为 **1/3**，包含证据交付的完整验收仍为 **0/3**。另两轮分别停在 CRLF 精确编辑锚点和
  未使用规范函数名。保留现有冲突保护、权限和错误反馈，没有为 clamp 增加专用工具。
- **普通解释三次**：自动初筛曾报 2/3，但人工查看原文发现其宽松的“非空/包含术语”规则
  会把 XML 伪工具文本或只解释进程、遗漏 Agent Run 的回答判为通过。**撤销该组产品通过
  结论**，保留初筛与原文。Runtime 没有解析或执行这些伪工具文本；交付质量仍不合格。

代码任务的第一次验收环境还有独立问题：脚本只给父进程注入显式 System DLC bundle，
没有设置子 Worker 需要继承的 `DBFOX_SYSTEM_DLC_DIR` / `DBFOX_SYSTEM_DLC_MANIFEST`，
导致签名发布者在子进程未被认可。原生子进程对照确认：原环境没有 file_edit，带正式
bundle 配置后可用；**未关闭信任校验或更改产品权限**。这三轮不作为模型能力失败，
修正验收配置后在新夹具上重验上述三轮。采集器还修正了对未知工具的处理和 Job 字段
`root_exit_code`；第二组已结算记录从同一 SQLite 恢复，没有重跑或覆盖它们。

以上说明通用类型边界已实现，但完整产品可靠性仍未达标。下一层需要由可信任务入口
或能力 owner 提供可以验证的交付要求，而不是模型批准自己完成；还需要改进/评估统一
工具可发现性、编辑反馈的可用性与最终输出合同。不能靠宽松 scorer、识别某种错括号、
追加引用、给出测试题专用提示或扩大预算来宣布完成。

### 本轮证据

忽略目录 `.tmp/answer-delivery/` 保留：`before.patch`、`unit.log`、`core.log`、取消竞态前后
日志、`production314.log`、`bench-final.log`、Windows/Linux mypy、前端日志、`data-4b/`
及隐藏 work/runtime SQLite、`workspace-4b/`、`workspace-4b-collected/`、修正环境后的
`workspace-code-4b/`。真实模型原文、代码文件、命令 Job、审批和独立测试输出均保留。
只清理已经结束的确定性 pytest 临时夹具来释放 D 盘空间，不删除模型、真实 Run 或用户文件。

## 可信输入的答案要求与最终结算

### 源头问题与架构选择

Agent **4.5**、Prompt **5.2** 延续同一 HEAD 和工作分支。上一轮证明：有结构化提交入口，
不等于模型会使用它；仅把“请引用”放在自然语言中，也不能成为最终写入的强约束。
本轮将这项可客观检查的交付要求放在已鉴权的 Input 准入边界，沿用 `Run.request_json`
冻结，不从模型计划、答案正文、工具输出或关键词推断要求。详细合同、状态所有权及
Kernel/API 变更理由见[连续执行上下文](../architecture/agent-context-continuity.md#输入准入时冻结的答案要求agent-45--prompt-52)。

HTTP Input 增加可选 `answer_requirements.evidence`：`when_observed` 在实际观察过公共
Artifact 后要求结构化引用，`required` 则要求至少一项真实来源。新桌面任务默认前者；
普通无来源解释可以直接回答。steer/respond 不重置当前 Run 的要求；显式试图通过 steer
改变要求会被拒绝。旧客户端及历史 Run 未声明此字段时保留原行为。

复用已有 Pydantic 合同、Input 指纹、Run 请求、Artifact 访问证明、Context、Completion
与最终写事务，不引入新依赖、状态表、执行循环、审核模型、自然语言规则或兼容转换层。
这是可选 HTTP 合同扩展，已通过正式生成器更新客户端；没有改变 SDK API v2 导出。

当前可引用身份与“曾观察到公共来源”的历史事实分别从现有记录读取。撤销来源不能
抹掉交付要求，也不能带来读取权限；内部工件不会强迫用户引用。Prompt 的八项示例和
历史裁剪都不充当访问/完成权威。最终事务重新核对成功提交、实际 Evidence、来源身份
以及准确正文，不能靠纯文本标记、空引用或服务器自动生成的部分总结绕过。

这项合同只校验来源交付，不证明引用支持每条结论，也不证明自然语言目标、SQL 结果
形状或计划维护全部正确。未增加万能验收器，不让模型批准自己完成。

### 确定性验证与构建

- CPython **3.14.6** 完整 Core、注册、工程合同、Action Run 与 Conversation 集合为
  **543 passed / 2 deselected**。随后补入无答案部分结算反例，答案要求文件复验
  **16 passed**；这些数目有重叠，不累加成独立测试数。
- 生产 RunLoop 回归覆盖中英文及不同任务目标的提前纯文本、纠正后原生提交、内部来源、
  无来源预算耗尽和最终正文被替换；实际能力动作只执行一次。API 回归检查可选字段的
  持久准入，普通 steer 保留初始要求，显式降级被拒绝。
- 完整 Bench / 注册集合 **116 passed**。未修改本轮的数据集、黄金 SQL、scorer、模型
  参数或停止预算。真实 Data Bench 的新 Run 与桌面一样声明默认交付要求，未额外注入
  测试题特有要求或期望答案。
- 最终测试类型检查发现新测试误将内部 `respond` 模式传给仅支持三种发送模式的前端
  `sendMessage`。改为实际的 steer 与 cancel-and-replace 路径后复验；提问回复仍走既有
  专用接口，没有扩宽产品类型或增加运行时兼容分支。失败日志单独保留。
- 前端 Conversation Store、Markdown 和 Evidence Dock **31 passed**，包含新任务
  声明、steer 继承及替换任务重新声明；`typecheck:test` 通过。lint 通过，保留 **20 条既有
  warning**。API 由隔离运行目录中的正式生成命令产出，未手改生成代码。
- Windows / Linux 目标 mypy 各 **271 个源文件通过**；pyflakes 与差异格式检查通过。
- 首次前端构建与模型及 Bench 并行时在 Rolldown 分块阶段发生内存分配失败。保留失败
  日志；待模型与测试退出后，不改变源码、依赖、构建参数或预算，单独重跑 `npm run build`
  **通过**，包含 Main/Preload、生产 Token 和 bundle 预算检查。未把重跑成功描述成
  已修复并行构建的资源问题，也未进行本轮 Electron 安装包或实机交互验收。

### 同一 4B 模型的实际表现

仍使用本文登记的同一 Ollama / Qwen digest、32K context、2048 output 与采样参数。
无云端回退、模型下载、用户 profile 改动或预算放宽。正式 RunLoop、已签名 DLC 与
实际 Workspace/Broker 用于合成资源；测试 fixture 审批不代表用户实机审批验收。

| 固定 Data 任务（各三次） | 完整既定验收 |
| --- | --- |
| 已完成订单收入 | 2/3 |
| 金额最小/最大值 | 3/3 |
| 关联字段检查、显式计划及客户订单查询 | 1/3 |
| 合计 | **6/9** |

总体与前两轮一样是 6/9，**没有证明成功率提升**。八次实际完成的 Run 均通过结构化
提交生成可解析引用。八次有执行结果，其中七次满足既有严格结果等价检查；收入第三次
额外返回 `COUNT(*)` 列，触发结果形状不等价。独立只读重算确认该次金额 54980.0 与
订单数 400 均正确；保留严格 scorer 的失败，不将这一项误报为金额算错，也不为抬高
通过率放宽结果合同。

另外两次多步任务失败分别是只有事后计划、未按要求持续维护，以及反复计划参数错误
和非规范工具名后 `AGENT_NO_PROGRESS`，后者未执行结果查询。本轮 64 Turn，真实
input/output **782072 / 9648 tokens**，median **24.204 秒**，零安全 veto、零未评分
基础设施任务、零 Provider 重试；这些只是样本测量，不归因为单一改动的性能收益。

同一文件摘要请求、同一 Workspace 配置另验三次，**2/3** 同时满足实际内容、正文引用
与源文件不变。第三次两次提交相同正文，`citations` 都为空，仅把 Artifact ID 写成普通
Markdown 链接，最终明确失败，没有发布已完成。上一轮该任务为 1/3，这个样本太小，
不能宣称总体可靠性或因果提升；也没有自动追加引用、解析错误链接或增大重复预算。

本轮没有重验代码修复和普通概念解释，上一节这两类的失败与撤销结论继续有效。没有
完成全部 60 题、数据库加 Excel 月报、完整语义层、Recipe 或 Electron 产品验收。
下一步仍应调查规范工具可发现性、原生调用参数反馈及编辑冲突反馈的共同原因，而不是
把某一题的 SQL、字段、文件名或模型错误写进 Core。

### 证据与可复核范围

忽略目录 `.tmp/delivery-requirements/` 保留 `before.patch`、中间失败及修复日志、
`production314.log`、`requirements-final.log`、`bench.log`、API 生成及类型/lint 日志、
首轮失败和串行成功的构建日志、Windows/Linux mypy、`files-4b/`、`data-4b/` 及隐藏
work/runtime SQLite。`independent-review.json` 记录严格验收失败项和独立只读数值重算；
真实模型原文、成功/失败提交及来源未覆盖。最终源码快照与 hash 单独保存于该忽略目录。
不提交模型、临时运行目录、数据库或用户文件；本轮没有提交、推送或发布。

## 工具纠正反馈与文档编辑边界

### 调查事实与设计

继续使用相同 HEAD、独立分支及用户现有本地模型。Agent 定义为 **4.6**，Prompt 保持
**5.2**。本轮从原始参数、Observation 和实际源码核验，而非仅阅读上轮 scorer：

- 旧 Python 编辑失败的参数在 JSON 解码后确实包含 LF，目标是 CRLF。详细错误已进入
  `error_message` 和模型输出，不是反馈在结算时丢失；模型仍未成功纠正。
- UNKNOWN_TOOL 原反馈没有给出本轮准确名称，DLC 的 local name 和模型调用名容易混淆。
- 仅关闭 Pydantic 的 input 输出仍会反射动态字段名；错误 location 和自定义错误类型
  都可携带输入字符串。已用合成哨兵和超长键复现，不代表发现真实凭据泄漏事故。
- 编辑唯一性用 `str.count` 只数非重叠匹配，漏掉 `ababa` 中两个 `aba` 位置；Unicode
  与多行锚点也可复现。

复用当前 Registry / ToolMaterialization、Pydantic 错误模型、Invocation/Observation 和
WorkspaceService；参考官方 Pydantic、VS Code、Codex patch 及 Anthropic 工具设计。
实际规则、取舍、权限边界及 Kernel 七问见
[工具纠正与文件编辑合同](../architecture/agent-tool-context-memory-contract.md#工具输入纠正与文件编辑agent-46)。

| 边界 | 落地职责 |
| --- | --- |
| ToolDispatcher | 拒绝未知名称时展示本 Turn 至多 24 个准确函数名；空集合明确说明，隐藏或未物化函数不出现。提示不执行别名，也不自动重发调用。 |
| PolicyGate | 保留声明 schema 的字段、判别联合的声明标签、有界索引及标准错误类型；未知键、自定义类型、参数值与错误 ctx 不进入公开诊断。最多八条，文本有界。 |
| Workspace DLC | `file_edit@3` 对统一 LF/CRLF 文档使用文档换行约定；读和 raw hash 不变，周围字节保持。混合或仅 CR 文档保留字面编辑。 |
| Workspace 编辑保护 | 两次 find 检查全部起始位置，默认拒绝重叠歧义；显式 replace_all 按标准非重叠替换。统一后相同的文本拒绝作为修改。 |

没有新增工具、状态表、Schema validator、发现服务、错误码映射、模型参数自动修复、
第二套 Loop 或依赖安装。文件编辑仍由 DLC owner 拥有；Core 不解释代码、语言或换行。
`file_write`、raw sha256、绑定代次、审批、写事务及原子发布沿用原合同。`file_edit` 声明
版本升为 3，既有冻结合同和 package digest 核验阻止升级后重放旧调用；API v2、HTTP、
Artifact schema 与前端 API 无变更。

### 确定性证据

- 第一组改前反例 **11 failed / 5 passed**：动态诊断键/类型、可用名称反馈、跨换行编辑、
  唯一性与 no-op。修复后的 Policy / Recovery / Workspace 集合 **49 passed**。
- 独立增加重叠锚点反例，改前两条失败；修复后 Workspace owner 与包 conformance
  **32 passed**，包含 Unicode、保留原始字节、混合换行、外部写冲突和跨进程写保护。
- 最终 CPython **3.14.6** 完整 Core、Workspace、Action Run、注册与工程合同集合
  **553 passed / 2 deselected**。先前 551 的记录保留，不累加重叠测试数。
- 完整 Bench / 注册集合 **116 passed**；最后追加的唯一性修复又通过上述 owner 与最终
  Core 集合。业务 scorer、黄金 SQL、数据集、工具/Turn/修复预算均未为本轮更改。
- Windows / Linux 目标 mypy 各 **271 个源文件通过**，pyflakes 覆盖 Engine、构建脚本、
  scripts 和 Workspace backend。不是 Linux/macOS 原生进程验收。
- 本轮未改变前端代码，没有重复前端构建/截图、原生 Electron、安装包或远程 CI 验收；
  上一节的前端证据保持其实际版本与范围。

主要可复核命令（pytest 从仓库根运行，Core 记录使用上述生产解释器；临时目录和缓存
均放在 D 盘）：

```powershell
python -m pytest verification/tests/agent_core verification/tests/system/test_dbfox_workspace_dlc_package.py verification/tests/system/test_workspace_mutation_safety.py verification/tests/system/test_action_run_lifecycle.py verification/tests/system/test_engineering_contracts.py verification/tests/system/test_builtin_registry_contract.py -q --tb=short -m "not e2e and not integration and not real_llm"
python -m pytest verification/tests/bench verification/tests/system/test_builtin_registry_contract.py -q --tb=short
python -m pyflakes engine build_sidecar.py scripts dlcs/dbfox.workspace/backend
python -m mypy --no-warn-unused-configs --follow-imports=skip engine build_sidecar.py --no-incremental
python -m mypy --platform linux --no-warn-unused-configs --follow-imports=skip engine build_sidecar.py --no-incremental
```

真实 RunLoop 回归使用两个不同 owner、相同 local name，检查错误调用没有执行、参数
没有进入拒绝 Invocation/Observation，纠正后只执行一次准确函数；原始模型历史仍按
现行合同持久化，不把这项检查解释成对所有原生模型数据的秘密清洗。

### 本地模型与陌生项目实际验收

相同 4B digest、Ollama、32K context / 2048 output、采样及停止预算。Node 为本机
**v24.13.0**，只使用已有标准库，无 npm 安装。未下载或切换模型、未修改用户 profile、
未调用云服务。夹具、测试代码、初始字节 hash 由外部验收准备；修复由 DBFox 的正式
RunLoop、签名 Workspace DLC 和 Windows Broker 完成，独立测试在结束后复查。

第一组九次覆盖三个任务，每项三次；保持原 Python/文件请求，新增一个此前未适配的
Node ESM 区间判断项目。测试及 package 初始字节不得修改，不将预期修复注入生产代码。

| 第一组任务 | 严格完整验收 |
| --- | --- |
| 文件摘要与有效正文引用 | 2/3 |
| Python 定位、修改、实际失败/成功测试及引用 | 0/3 |
| 陌生 Node 项目同类闭环 | 1/3 |

Node 成功样本真实执行原测试并观察退出码 **1 → 0**，源码修改、正文引用和独立复验均
成立，测试与 package 字节未改。Python 有一次源码修正并被外部测试确认正确，但它
提交的是 `python`，偏离已声明的绝对解释器许可，执行被夹具拒绝；Agent 没有实际
测试闭环，因此不计通过。其他失败包括错误规范名称、跳过操作后直接回答，以及命令
参数偏离许可范围。文件摘要仍为上一轮的 2/3，没有证明提升。

第一组运行时保持已装配包不变；在追加重叠唯一性修复后，再以最终源码和新隔离目录
复验 Node 三次，完整验收 **0/3**。其中两次源码修改经独立测试正确，但 Agent 自身
未完成获准命令下的验证；另一次看到了初始失败，随后因错误工具名停滞。两组记录和
初始源码都保留，不能挑选第一次成功样本代表最终三次均通过。

夹具审批事先严格限制为给定绝对解释器、测试参数、项目工作目录和目标源码。它会拒绝
bare `python`/`node`、附加文件参数及其他变体；第一组有一次额外指定实际测试文件也被
此夹具拒绝。**这些拒绝不等于 OS 执行器故障，也不能证明所有被拒绝命令本来不可用**。
本轮没有事后扩大许可或重分类为通过。更宽的真实用户许可与人工交互需要单独、预先
声明的验收；当前不能由这组严格夹具估计所有通用 CLI 行为的成功率。

上述运行不是全绿，未证明总体任务可靠性提升。准确名字反馈能让错误可纠正，不保证
模型一定纠正；结构化来源交付也不能检测完全未执行的自然语言步骤。尚无同题更强模型
对照，不能把剩余差距全部归因于模型或宣称 Harness 已经解决。未重验 Data 三题、全部
60-case、Excel 报告及普通解释，上一轮 6/9 不能转写成本轮 Agent 4.6 的成绩。

### 证据与下一步

忽略目录 `.tmp/tool-feedback/` 保存改前 patch、改前/改后及重叠反例日志、最终 Core、
owner/包测试、Bench、Windows/Linux mypy、pyflakes、两组真实模型报告及其完整 SQLite、
源码、Job、审批、独立测试与初始文件 hash。`initial-real-summary.json` 和
`final-real-review.json` 分别记录两组结果，`service-before-overlap.py` 保留第一组包对应
源码。启动脚本首次缺少仓库模块路径而未开始 Run，失败日志单独保存；显式设置
PYTHONPATH 后运行，不将该启动问题计为产品/模型失败。最终源码快照另保留于同目录。

下一步应围绕规范工具暴露、可纠正反馈的真实使用和用户目标/执行证据之间的差距建立
可配对验收；明确区分输入/许可、执行器、模型决策和成果交付。保留统一合同，继续由
领域 owner 处理文件或计算语义，不增加业务题目规则或放宽结束条件。

本轮未提交、推送、发布或重装；用户 Word 文件、模型权重及原配置保持。

## 调研依据

- [Ollama 上下文配置](https://docs.ollama.com/context-length)：部署上下文与标称上限分开核验。
- [Ollama API 兼容范围](https://docs.ollama.com/api/openai-compatibility)：不能从基础兼容推断所有 Responses 功能可用。
- [SQLite 事务](https://www.sqlite.org/lang_transaction.html)：长等待占用写事务会影响其他 writer。
- [Playwright 异步 API](https://playwright.dev/python/docs/library#usage) 与 [标准库 eager task factory](https://docs.python.org/3.12/library/asyncio-task.html#eager-task-factory)：在现有 worker 中分离派发和等待，不另造协议或浏览器调度。
- [mypy 平台守卫](https://mypy.readthedocs.io/en/stable/common_issues.html#python-version-and-system-platform-checks)：表达实际操作系统边界。
- [标准库 EntryPoint](https://docs.python.org/3.12/library/importlib.metadata.html#entry-points)：只激活选中验证 runner，避免重复装配层。
- [OSV 官方 API](https://google.github.io/osv.dev/api/)：仅查询公开依赖元数据，不读取 Git 凭据。
