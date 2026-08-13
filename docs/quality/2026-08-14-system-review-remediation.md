# 系统级工程审查整改计划

> 文档类型：质量整改记录
>
> 状态：当前
>
> 最后核验：2026-08-14
>
> 基线：`main@d090fd74abe94eaa0666ffcfaaa22a57edac927d`
> 建立日期：2026-08-14
> 范围：已复核的 P1/P2 缺陷，以及报告所列 P3 候选项的逐项验证
> 原则：修复唯一正式链路；不增加 Provider 特例、兼容 mapper、第二套 SQL 链或巨型状态机。

## 1. 目的与结论边界

本文把系统级审查中已经取得证据的问题转化为可实施、可测试、可回滚的任务。问题分为三类：

- **必须修复**：已由代码调用链和运行实验确认的 P1/P2；
- **部分修复**：问题成立，但建议中的扩大范围或严重等级不成立；
- **只核验**：P3 中尚无运行证据、属于设计取舍或疑似误报的项目。只有核验确认后才允许修改生产代码。

本轮不进行架构重写，不引入新的通用 Adapter/Mapper，不把测试旁路变成生产能力，也不借机修改无关 UI、Updater 或发布配置。

## 2. 实施顺序与提交边界

| 批次 | 范围 | 独立回滚边界 |
| --- | --- | --- |
| A | P1-1 审批后的 SQL 执行权威贯穿执行边界 | SQL approval authority |
| B | P1-2 跨轮答案候选与终态 RunItem 身份一致 | terminal answer identity |
| C | P1-3 备份外部 I/O 移出 SQLite 写事务 | backup short transaction |
| D | P2-2、P2-3 Session/Run 状态竞态 | run state transitions |
| E | P2-4、P2-5 工具大输出与未知工具结算 | tool robustness |
| F | P2-1 PostgreSQL 危险函数只读策略 | readonly SQL policy |
| G | P2-7 中文查询历史检索 | query-history FTS migration |
| H | P2-8 安全错误码目录 | HTTP error contract |
| I | P2-6 committed/live 前端游标归并 | conversation reducer |
| J | P2-9 测试矩阵和 CI 合同 | quality gates |
| K | P3 逐项核验与已确认小修复 | 每项独立决定 |

每一批必须先增加能在旧实现上失败的回归测试，再修改生产代码；相关测试通过后才能进入下一批。最终统一运行 Python、前端、Rust、生产前端构建和差异检查。

## 3. P1 修复设计

### P1-1 已批准 SQL 在执行层再次被阻断

**状态：已确认缺陷；发布优先级：立即。**

根因是 `ExecutionAuthority` 只在 `sql_execute_readonly` 工具叶子中验证，随后原始 `ExecutionSafetyDecision` 被传入 `execute_query`；执行层不知道已经存在与 invocation、输入哈希、Safety 指纹和 datasource generation 绑定的批准权威，因此再次按 `requires_confirmation` 拒绝。

解决方案：

1. `execute_query` 与 SafetyGate 接受可选的、provider-neutral `ExecutionAuthority`；
2. SafetyGate 先完成 datasource、SQL、参数和 generation 的既有指纹校验；
3. 只有 authority 的 tool、Safety 指纹和 generation 全部匹配，才消耗“已确认”条件；
4. 不修改原始 Safety Artifact，不把 `requires_confirmation` 原地清零，不增加 bypass 参数；
5. Console、Result View 和其他非 Agent 调用不携带 authority，行为保持不变。

验收标准：

- 匹配的批准权威可通过真实 `execute_query` 边界；
- 缺失、过期、其他 invocation、其他 datasource generation 或其他 Safety 指纹仍被拒绝；
- 未批准的生产查询仍不能执行；
- 测试不得 mock 掉 SafetyGate。

### P1-2 跨轮答案候选与当前 Turn 错配

**状态：已确认缺陷；发布优先级：高。**

根因是 `ModelTurnResult` 没有保存其耐久 Turn 身份，而 Terminalizer 用候选的 `output_index` 配合当前 `run.current_turn_id` 查找 RunItem。

解决方案：

1. 在 provider-neutral `ModelTurnResult` 中记录可选 `turn_id`；
2. Turn 完成和恢复装配时写入真实 Turn ID；
3. Terminalizer/RunRepository 使用候选所属 Turn ID 定位终态 Message RunItem；
4. 不复制答案到当前 Turn，不伪造新的 Provider 输出；
5. 若候选身份缺失或对应 RunItem 不存在，继续 fail-closed。

验收标准：

- 当前轮正常回答行为不变；
- 早期轮答案在预算或停滞结算时能够引用原 RunItem；
- AgentMessage 和 RunItem 的内容、turn_id、output_index 一致；
- 不产生重复 Message、Evidence 或 RUN_COMPLETED 事件。

### P1-3 备份期间持有 SQLite 写锁

**状态：已确认、降级为 P2 可用性缺陷；发布优先级：高。**

解决方案采用三段式短事务：

1. 短事务创建 `running` 记录并提交；
2. 事务外运行 `mysqldump`、校验文件和计算校验和；
3. 新短事务按 backup ID 回写 success/failed；
4. API 不再负责为整个 dump 保持事务；
5. 失败记录仍保留固定安全错误，不写入子进程原始输出。

验收标准：

- dump 阻塞期间第二个 SQLite writer 可以提交；
- 成功和失败记录均最终结算；
- API 返回合同不变；
- 失败时删除受 DBFox 管理的残缺文件；
- 不在后台线程共享 SQLAlchemy Session。

## 4. P2 修复设计

### P2-1 PostgreSQL 危险函数可从只读 SELECT 调用

在现有 SQLGlot AST 只读判定边界扩充明确的副作用函数策略，至少覆盖 `pg_read_binary_file`、`pg_terminate_backend`、`pg_cancel_backend`、`pg_reload_conf` 和 `dblink_exec`。不另建 SQL 解析器，不用字符串包含判断。

验收标准：大小写、schema-qualified、嵌套调用均拒绝；普通聚合和已允许只读函数不退化；MySQL/SQLite 方言不因名称相同被误伤，除非该函数同样属于对应方言禁用策略。

### P2-2 steer 可复活已终止 Run

`promote_next_input` 在锁内重新读取并校验绑定 Run 仍为可接收输入的非终态；终态 Run 不得被写回 RUNNING。正常完成若发现已接纳的 steer，则原子让出终态结算并进入下一 Turn；若 Run 已因失败或取消成为终态，孤立 steer 明确结算为 cancelled，不把它迁移到新 Run，也不伪造第二份用户请求。

验收标准：COMPLETED/FAILED/CANCELLED 均不可复活；RUNNING steer 行为保持；重复幂等键不产生第二份输入。

### P2-3 取消竞态被结算为 failed

统一 RunRepository 的终态优先规则：已请求取消或处于 CANCELLING 时，正常完成/异常兜底都只能结算 CANCELLED；真实 lease/fencing 冲突仍向上抛出，不能被误当取消。

验收标准：cancel-vs-complete、cancel-vs-runtime-error 两个竞态均为 CANCELLED；非取消异常仍为 FAILED；终态事件只出现一次。

### P2-4 大工具结果丢失 Result Artifact

不能简单提高全局上限，也不能把全量 rows 塞入 Observation。SQL 工具应先持久化可回源 Result Artifact，Provider 只接收有界摘要和 Artifact ID。通用 ToolExecutor 超限处理必须允许“有安全 Artifact 引用的有界输出”保留引用；无引用的普通超限输出继续失败关闭。

验收标准：宽表/大结果不进入模型上下文；Result Artifact 可用 `result_inspect` 分页；同一调用不重复执行；普通工具的超限保护不降低。

### P2-5 未知工具在 PolicyGate 前抛异常

未知工具必须在 Dispatcher 的真实入口结算成固定、安全、可供模型恢复的拒绝 Observation。不得把未知名称物化为临时 Tool，不按 Provider 名称分支。

验收标准：未知工具不令 Run 失败；产生一次 `UNKNOWN_TOOL`（或现有正式目录等价码）Observation；模型可进行下一轮；已物化工具的版本冻结规则不退化。

### P2-6 committed 事件超越 live delta

Durable item revision 与 ephemeral delta revision 是两个不同计数器，不能直接互相赋值。Reducer 接收较新的 committed 完整内容后，若随后到达的下一条连续 live delta 已被该内容完整覆盖，则只推进 live cursor、不重复追加；后续 delta 从权威文本末尾继续。服务端 durable snapshot 仍是事实源。

验收标准：构造 live rev1 → committed 包含 rev1/rev2 内容 → queued live rev2/rev3 的乱序场景，不永久卡死；重复 delta 不重复文本；sequence gap 仍触发既有快照恢复边界。

### P2-7 中文 Query History FTS

旧 `unicode61` 设计适用于词元/完整连续串匹配，不适合 DBFox 中文“输入关键词找历史 SQL”的子串召回语义。SQLite 官方 `trigram` 是当前已使用、无需新增依赖的成熟方案。

解决方案：

1. Alembic 迁移重建 query-history FTS 为 `tokenize='trigram'`；
2. 三个及以上 Unicode 字符使用 FTS trigram；
3. 一至二字符查询采用显式受限策略：默认不执行无界全表 LIKE；若产品需要支持，必须限定 datasource、结果上限并有可用索引/规模门槛；
4. 保留 SQL 字段、错误码、表名等英文/符号查询测试；
5. 启动验证加入 FTS 对象和触发器合同。

验收标准：`数据库`、`订单`、`趋势` 能命中 `分析数据库订单趋势`；不足三字符行为固定且有用户可理解的结果；迁移后新增、更新、删除同步正确；升级和全新建库均通过。

### P2-8 DBFoxError 错误码退化

不信任任意 `DBFoxError.message` 或调用方随意传入的 code。只允许固定类型异常携带类级安全 code，或在构造边界验证 code 属于 `FixedErrorCode`；公开 message 始终从安全目录取得。未注册项继续降为通用错误。

验收标准：已注册业务错误保留稳定 code/status；sentinel 私密 message/code 不泄漏；前端无需新增错误 mapper。

### P2-9 测试矩阵缺口

补充 approval→real SafetyGate→executor、RunLoop→真实 SQL 工具合同、跨轮终态、备份并发和 reducer 超越场景。确认旁路只在明确需要的 fixture 中开启；Windows job 执行 Windows 专属安全合同。真实 PostgreSQL/Provider 场景保持 opt-in，不伪造通过结果。

## 5. P3 核验清单

| 候选项 | 当前判定 | 必须取得的证据 | 处理规则 |
| --- | --- | --- | --- |
| provider retry 三重记账 | 疑似误报 | 单次重试的耐久计数实验 | 无重复计数则不改 |
| lease 丢失被 finally 掩盖 | 高可信风险 | stale lease + stream finally 场景 | 确认异常类型被替换才修 |
| interrupted Turn 不进 transcript | 设计取舍 | 恢复合同与污染风险 | 保持 fail-closed |
| ToolInputError 无长度上限 | 静态成立 | 最大可持久化/展示路径 | 在 ToolRuntime 安全边界统一截断 |
| hostname DSN 脱敏 | 待复现 | `user:pass@db.example` 测试 | 真实泄漏则复用现有 redactor 修复 |
| expire_pending 缺 lease 校验 | 高可信风险 | 所有调用者与并发场景 | 不能伪造/接管 lease |
| Tool leaf Session 跨外部 I/O | 设计风险 | 是否持写锁、连接池影响 | 只在证明资源问题后拆分 |
| row serializer 字符串化 | 合同歧义 | column_types 与客户端解析 | 不为形式类型破坏 Decimal 精度 |
| Result View 派生 SQL 未校验 | 已否定 | 生产调用均调用 `_validate_derived_sql` | 不改 |
| 大 OFFSET | 性能风险 | 查询计划/上限/数据规模 | 需要基准后决定 cursor 方案 |
| query cancel 无归属 | 低风险设计 | loopback token、execution ID 可猜性 | 单用户模型下不夸大 |
| EXPLAIN 不可用仍放行 | 设计取舍 | AST/native readonly 防线 | 保持既有分层策略 |
| Referer 前缀匹配 | 纵深缺口 | frozen HTTP 合同 | 使用 URL 解析，不替代 token |
| 全局请求体限制 | 报告夸大 | 文档真实承诺与大字段端点 | 另立 DoS 需求，不混入本轮 |
| SSE 僵尸流 | 待验证 | 断连后资源释放时间线 | 超过合同才修 |
| 表导出缺安全审计 | 已确认静态不一致 | 与 Artifact 导出对照 | 补同类审计，不记录数据内容 |
| 审计仅启动裁剪 | 已确认部分落实 | 长运行越界实验 | 增加低频有界维护入口 |
| FixedErrorCode 缺项 | 已确认 | 所有 handler 引用与目录比较 | 补固定目录并加完整性测试 |
| SQL 字符/字节上限差异 | 合同歧义 | Unicode 边界测试 | 明确双层上限语义 |
| 清日志原地截断 | 高可信风险 | 活跃 handler 继续写入实验 | 确认 NUL 空洞才修 |
| admit deleted_at | 纵深缺口 | repo 是否有非 API 调用者 | 在领域入口统一保证 |
| event sequence 先增后校验 | 已否定 | 同事务回滚成立 | 不改 |
| 启动不验证 Agent FTS | 已确认 | required objects 对照 | 加入启动合同 |
| committed sequence gap | 文档/纵深缺口 | 服务端 gap 与断流快照 | 补 reducer 测试后决定 |
| ErrorBoundary 原始 message | 已确认静态风险 | 可进入该边界的敏感错误 | 生产固定文案，细节仅脱敏日志 |
| Sidecar try_wait 吞 channel error | 高可信风险 | channel disconnect 单测 | 失败状态必须可观察 |
| 手动 restart 清 crash budget | 设计取舍 | 产品恢复语义 | 默认不改 |
| CSP 任意 loopback 端口 | 低风险权衡 | Tauri 动态端口要求 | 无可行静态收紧前不改 |
| inspect.getsource 测试 | 测试脆弱性 | 替代行为断言 | 触及相应测试时收敛 |
| E2E 绝对路径/静默 skip | 已确认 | CI fixture 可配置性 | 使用显式 opt-in 配置 |
| 真实 LLM 内容硬断言 | 已确认 flaky 风险 | 测试文件断言 | 改合同/结构断言 |
| generated/client 重复树 | 已否定 | 生成 SDK 正常导入 | 不删 |
| main.py 职责多 | 启发式 | 修改扩散/测试困难证据 | 不因行数拆分 |
| 维护扫描缺索引 | 高可信性能风险 | `EXPLAIN QUERY PLAN` 与规模基准 | 确认后加最小复合索引 |

### 5.1 P3 最终核验结论

| 候选项 | 最终状态 | 证据与处理 |
| --- | --- | --- |
| provider retry 三重记账 | 否定 | `test_agentbench_faults` 的一次可重试失败最终耐久计数为 1；内存控制器与数据库计数是同一失败在不同生命周期的镜像，不存在三次累加。 |
| lease 丢失被 finally 掩盖 | 否定 | `RunLeaseLost` 在 loop 顶层独立捕获，`finally` 仅释放瞬态 tool scope/live hub，不执行耐久终态写入。 |
| interrupted Turn 不进 transcript | 保持设计 | 中断文本不能作为可信 assistant message 注入下一轮；恢复只保留失败 Turn 和固定说明，继续 fail-closed。 |
| ToolInputError 无长度上限 | 已修复 | ToolRuntime 在唯一公开边界截断到 1024 字符并不再记录完整 message；普通内部异常合同不变。 |
| hostname DSN 脱敏 | 已有防护 | `test_redactor.py` 已覆盖 `user:pass@db.example`，密码被替换且 host 保留；不另建 redactor。 |
| expire_pending 缺 lease 校验 | 已修复 | Approval/Question 先锁定并验证当前 Session lease；旧 token 实测被拒绝，恢复 worker 仍可接管等待 Run。 |
| Tool leaf Session 跨外部 I/O | 证据不足 | 未发现持有 SQLite 写事务跨模型/数据库外部 I/O 的确认路径；不为理论风险拆第二套执行链。 |
| row serializer 字符串化 | 保持合同 | JSON 无 Decimal 原生类型；字符串保精度并由 `column_types` 描述，不改成有损浮点。 |
| Result View 派生 SQL 未校验 | 否定 | 生产 page/export 均经过 `_validate_derived_sql`；不改。 |
| 大 OFFSET | 性能待测 | 当前有页数/行数上限，但没有规模基准证明需 cursor；不提前改变分页公开合同。 |
| query cancel 无归属 | 风险接受 | loopback token、不可预测 execution ID 和本地单用户模型构成边界；未证明越权，不夸大。 |
| EXPLAIN 不可用仍放行 | 保持设计 | EXPLAIN 是附加预演，AST 与原生只读事务仍是强制防线；不可用不等于跳过只读检查。 |
| Referer 前缀匹配 | 已修复 | 改用 URL 结构解析，拒绝 userinfo 与 `localhost.attacker`，不替代 Token 鉴权。 |
| 全局请求体限制 | 报告夸大 | 当前仅对持久化 Agent 输入和 Console 设置 512 KiB 边界，符合真实承诺；其他端点需独立 DoS 需求。 |
| SSE 僵尸流 | 未复现 | 现有订阅 close/finally 与断连测试未显示泄漏；无时间线证据，不改。 |
| 表导出缺安全审计 | 已修复 | 与 Artifact 导出对齐，记录 datasource/table/format，不记录筛选值或数据内容。 |
| 审计仅启动裁剪 | 已修复 | 保留启动裁剪，并每 256 次安全审计写入摊销执行同一索引化 retention；无第二套清理规则。 |
| FixedErrorCode 缺项 | 已修复 | 补齐跨全局边界的 Vault、Backup mismatch、AI translation；未知 code 固定降为 500/`INTERNAL_ERROR`。 |
| SQL 字符/字节上限差异 | 合同明确 | 输入字符限制与响应 UTF-8 字节预算是不同资源边界；现有 Unicode 测试覆盖，不强行统一单位。 |
| 清日志原地截断 | 已修复 | Python 活动 FileHandler 在锁内关闭、截断并重开；回归测试确认后续写入无 NUL 空洞。 |
| admit deleted_at | 已修复 | SessionRepository 领域入口拒绝软删除 Session，不只依赖 API 列表过滤。 |
| event sequence 先增后校验 | 否定 | sequence 与事件插入处于同一数据库事务，失败会整体回滚。 |
| 启动不验证 Agent FTS | 已修复 | metadata 启动合同加入 agent FTS 表和六个同步触发器；缺失表实测启动验证失败。 |
| committed sequence gap | 已补测试 | committed cursor 去重保持；durable snapshot 超越 live delta 的覆盖/续传场景已加入 reducer 测试。 |
| ErrorBoundary 原始 message | 已修复 | 产品错误页只显示固定文案；原始 Error 只进入开发控制台，不渲染进 UI。 |
| Sidecar try_wait 吞 channel error | 已修复 | channel 错误现在撤销旧端口/Token/Ready，进入 restarting 并触发既有 crash-loop 策略。 |
| 手动 restart 清 crash budget | 保持设计 | 手动恢复是显式用户操作，重新获得完整预算符合产品语义。 |
| CSP 任意 loopback 端口 | 风险接受 | Sidecar 使用动态端口且每次 generation 换 Token；无静态端口可收紧方案时不添加猜测映射。 |
| inspect.getsource 测试 | 测试债 | 本轮未触及相应生产合同；后续修改对应模块时用行为断言替换。 |
| E2E 绝对路径/静默 skip | 已修复 | MySQL SSL E2E 改为显式 opt-in 环境合同，CA/host/port/user/password 均由 fixture 配置，删除本机绝对路径和端口探测。 |
| 真实 LLM 内容硬断言 | 部分否定 | provider 测试主要断言 termination/tool call/arguments；最终值 `7` 是工具闭环的最小语义合同，不是自然语言措辞快照。 |
| generated/client 重复树 | 否定 | 一份是 OpenAPI 生成传输层、一份是产品投影；删除会破坏生成 SDK。 |
| main.py 职责多 | 启发式 | 未提供修改扩散或不可测试证据，不按文件行数拆分。 |
| 维护扫描缺索引 | 未确认 | Security Audit 已有 `created_at` 索引；在缺少规模与查询计划证据时不新增重复复合索引。 |

以上“否定、保持设计、风险接受、证据不足、未确认”均不进入缺陷修复清单；若后续出现运行证据，必须以独立问题和基准重新评估。

## 6. 全局验收门禁

完成所有批次后必须满足：

```text
python -m pytest -q
npm test -- --run
npm run build
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path desktop/src-tauri/Cargo.toml --all -- --check
git diff --check
```

此外必须记录：真实 PostgreSQL、真实 Provider、Windows 安装态和跨平台验证是否执行。没有真实证据的项目必须标记为未验证，不能由确定性测试推断为已通过。

### 6.1 本轮执行结果

| 门禁 | 结果 |
| --- | --- |
| Python 完整测试 | `1076 passed, 4 skipped`；skip 均为显式 opt-in 外部环境场景 |
| Python 编译与静态检查 | `compileall`、`pyflakes`、CI 同参数 mypy：通过（253 个 source files） |
| 前端测试 | 75 个测试文件、314 项测试：通过 |
| 前端 lint/设计合同 | ESLint 与 design-contract 检查：通过 |
| 前端类型与生产构建 | test typecheck、生产构建、Token 扫描、bundle budget：通过 |
| Rust Host | fmt、clippy `-D warnings`、24 项测试：通过 |
| 差异检查 | `git diff --check`：通过；仅有 Windows 工作树换行提示，无 whitespace error |

未执行：真实 PostgreSQL 故障注入、真实 Provider 调用、Windows 安装态和 macOS/Linux 真实运行。本轮不得据此声称这些环境已通过。

### 6.2 方案来源与复用决定

- SQLite 中文子串检索采用 SQLite 官方 FTS5 `trigram` tokenizer，不引入第三方分词器；不足三个 Unicode 字符按官方 tokenizer 能力采用 datasource 限定的绑定参数查询。参考：[SQLite FTS5 Tokenizers](https://www.sqlite.org/fts5.html#tokenizers)。
- PostgreSQL 只读 SELECT 的副作用函数目录依据 PostgreSQL 官方管理函数和 `dblink_exec` 文档，在现有 SQLGlot AST 边界扩展；没有新增字符串 SQL 解析器。参考：[PostgreSQL System Administration Functions](https://www.postgresql.org/docs/17/functions-admin.html)、[dblink_exec](https://www.postgresql.org/docs/17/contrib-dblink-exec.html)。
- 进程启动、退出事件与 external binary 继续由 Tauri Shell plugin 正式路径承载；本轮只修 DBFox Supervisor 对 channel error 的状态结算，不引入第二套进程实现。
- 新增兼容层：否；新 mapper：否；第二套 SQL/Agent/错误链：否；新增第三方依赖：否；迁移债务：仅新增可回滚的 query-history FTS Alembic 迁移。

## 7. 关闭条件

每项只有在以下条件全部满足时才能从“实施中”改为“已完成”：

1. 根因在唯一正式路径修复；
2. 旧实现上可失败的新回归测试通过；
3. 没有新增兼容层、双轨协议、Provider 特例或第二事实源；
4. 相关文档和错误合同同步；
5. 全局门禁通过；
6. 未执行的真实环境验证被明确保留。

本轮上述条件已经满足，整改实施状态为**已完成**；真实外部环境项目保留为独立验证任务，不影响对本轮确定性合同的关闭。
