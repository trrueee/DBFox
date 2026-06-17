# 第 5 节 · 具体缺陷报告规格说明

> 本文档把代码评审发现的 7 个缺陷（D1–D7）写成可立项、可追踪、可验收的缺陷单。
> 每张缺陷单严格按 IEEE 829 风格组织，让开发、测试、产品三方读完后能直接动手。

**状态:** ✅ 已完成（D1-D7 全部已修复）

---

## 缺陷单通用约定

| 字段 | 含义 |
|---|---|
| **严重程度（Severity）** | 问题对系统的伤害：Critical / High / Medium / Low |
| **优先级（Priority）** | 应该多快修：P0（本周）/ P1（两周）/ P2（季度） |
| **触发条件** | 满足什么前置条件才会出问题 |
| **复现步骤** | 编号步骤，第三方照做能重现 |
| **预期 vs 实际** | 一句话对照 |
| **影响范围** | 哪些用户、哪些数据、哪些模块受波及 |
| **根因** | 不是「哪里写错了」，而是「为什么会这么写」 |
| **修复方案** | 给出可直接落地的伪代码或文件位置 |
| **回归测试** | 修完后必须新增的测试用例编号 |

**严重程度 ≠ 优先级**：D1 是 High/P0（数据可被越权读），D7 是 Low/P2（影响可读性但不影响功能）。

---

# 缺陷 D1 · `db.preview` 表名/列名 SQL 注入面

| 字段 | 内容 |
|---|---|
| 缺陷标题 | `_build_preview_sql` 用字符引号拼接标识符，未走 sqlglot 转义 |
| 文件:位置 | `engine/tools/db_tools.py:1352-1385`（`_build_preview_sql`）<br>`engine/tools/db_tools.py:1395-1414`（`_build_where_clause`） |
| 缺陷类型 | SQL 注入（构造期） |
| 严重程度 | **High** |
| 优先级 | **P0** |
| 触发条件 | Agent 调用 `db.preview` 且传入的 `table` / `columns` / `where.column` 含 SQL 元字符（`` ` ``、`"`、`;`、`--`）；或前端通过结构化参数传入恶意值 |
| 复现步骤 | 1. 启动引擎，`DBFOX_TESTING=1 DBFOX_ALLOW_GUARDRAIL_BYPASS=1`<br>2. 构造工具调用：`db.preview(table="t\` WHERE 1=1 --", columns=["a"], limit=5)`<br>3. 走到 `_build_preview_sql`，生成 `SELECT \`a\` FROM \`t\` WHERE 1=1 --\``<br>4. 该 SQL 经 `execute_query(safety_policy="table_preview")`，而 `PolicyEngine.enforce_query_policy` 对 `table_preview` 直接 `return`（`policy/engine.py:21-22`）跳过 AST 校验 |
| 预期结果 | 非法标识符被拒绝或被 sqlglot 安全转义，SQL 结构不被破坏 |
| 实际结果 | 元字符原样嵌入，SQL 语义被改写；preview 是「信任生成」路径，下游 guardrail 不会重新审校标识符层 |
| 影响范围 | 所有 `db.preview` 调用；Agent 若被 prompt 注入诱导可越权读取任意表/列；`_build_where_clause` 的列名同问题 |
| 可能根因 | ① 为「读起来简单」手写字符引号，未复用同文件已有的 `escape_identifier`（`db_tools.py:804`，用 sqlglot）；② `PolicyEngine` 对 `table_preview` 信任跳过，但生成端没有等价的安全护栏 |
| 修复方案 | 1. `_build_preview_sql` 改用 `escape_identifier(table_name, dialect)` 与 `escape_identifier(c, dialect)`<br>2. 新增白名单校验：`re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)`，不通过抛 `ToolInputError`<br>3. `_build_where_clause` 的 `col` 同样走 `escape_identifier`<br>4. 评估：`PolicyEngine` 对 `table_preview` 不再无脑跳过，至少做一次 AST 解析确认是单条 SELECT |
| 回归测试 | `test_db_tools.py` 新增 PREVIEW-INJ-1..8（见第 6 节白盒用例 P1–P8） |

**修复伪代码：**
```python
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

def _safe_identifier(name: str, dialect: str) -> str:
    if not _IDENT_RE.fullmatch(name):
        raise ToolInputError(f"Invalid SQL identifier: {name!r}")
    return escape_identifier(name, dialect)

def _build_preview_sql(table_name, columns, limit, args, dialect):
    safe_table = _safe_identifier(table_name, dialect)
    safe_cols = ", ".join(_safe_identifier(c, dialect) for c in columns)
    sql = f"SELECT {safe_cols} FROM {safe_table}"
    ...
```

---

# 缺陷 D2 · `/query/execute` 结果行未脱敏

| 字段 | 内容 |
|---|---|
| 缺陷标题 | 用户手写 SQL 执行结果未对 PII 列脱敏，仅 Agent 工具链脱敏 |
| 文件:位置 | `engine/api/query.py:50-70`（`api_execute_sql`，无 redact 调用）<br>对比 `engine/tools/db_tools.py:237, 287`（`db_preview`/`db_query` 调用了 `_redact_row`） |
| 缺陷类型 | 数据泄露 / 隐私 |
| 严重程度 | **High** |
| 优先级 | **P0** |
| 触发条件 | 用户在 SQL 控制台执行 `SELECT password, email, phone FROM users` |
| 复现步骤 | 1. 创建一个含敏感列的 datasource<br>2. `POST /api/v1/query/execute {sql: "SELECT email FROM users LIMIT 5"}`<br>3. 响应 `rows` 字段返回明文 email |
| 预期结果 | 至少对 `_SENSITIVE_FALLBACK` 命中的列（email/phone/password/card…）做掩码，与 Agent 路径行为一致 |
| 实际结果 | 全量明文返回前端 |
| 影响范围 | 所有 SQL 控制台用户；本地单机绝对风险较低，但截图/录屏/共享/远程协助场景下构成泄露；与产品「本地优先 + 安全」定位矛盾 |
| 可能根因 | 脱敏逻辑（`_redact_row` + `_load_sensitivity`）只在工具层实现，未下沉到 executor；新增执行入口（如未来的导出 API）会重复踩坑 |
| 修复方案 | 1. 在 `engine/sql/executor.py:_run_approved_query` 末尾按 `datasource_id` 加载 sensitivity 配置并对 `rows` 做 redact<br>2. 通过 `ExecutionSafetyDecision` 或新参数 `redact=True` 控制开关：Agent 路径强制开、用户路径默认开但可配置<br>3. `execute_query` 公开签名新增 `redact: bool = True`，`db_tools` 调用处显式传 |
| 回归测试 | `test_executor.py` 新增 REDACT-1..4：含 email/phone/card/password 的查询；开关 on/off；混合敏感/非敏感列 |

**修复伪代码：**
```python
def execute_query(db, datasource_id, sql_str, ..., redact: bool = True):
    ...
    result = _run_approved_query(...)
    if redact:
        sensitivity = _load_sensitivity(db, datasource_id)
        result["rows"] = [_redact_row(r, sensitivity) for r in result["rows"]]
    return result
```

---

# 缺陷 D3 · `explain_sql` SQLite 绕过只读模式

| 字段 | 内容 |
|---|---|
| 缺陷标题 | SQLite EXPLAIN 路径用 `sqlite3.connect(path)`，未指定 `mode=ro` URI |
| 文件:位置 | `engine/sql/executor.py:303-335`（`explain_sql` 的 sqlite 分支）<br>对比 `engine/datasource.py:149`（`test_connection` 用 `file:...?mode=ro`） |
| 缺陷类型 | 安全 / 一致性 |
| 严重程度 | **Medium** |
| 优先级 | **P1** |
| 触发条件 | 对 SQLite 数据源调用 `POST /api/v1/query/explain` |
| 复现步骤 | 1. 创建 SQLite datasource（指向一个有写权限的 .db 文件）<br>2. `POST /api/v1/query/explain {sql: "SELECT * FROM users"}`<br>3. 内部 `sqlite3.connect(str(ds.database_name))` 打开的连接具备写权限 |
| 预期结果 | EXPLAIN 用的连接与 `test_connection` 一致为只读（`mode=ro`） |
| 实际结果 | 连接具备写权限；EXPLAIN 本身只读，但连接对象可被复用或误用执行写操作（如 ATTACH 触发副作用） |
| 影响范围 | 所有 SQLite EXPLAIN 调用；与产品「数据源只读姿态统一」承诺不符 |
| 可能根因 | `explain_sql` 与 `dialect/sqlite.py` 各自维护连接工厂，没有共享只读连接 helper |
| 修复方案 | 1. 抽 `engine/sql/dialect/sqlite.py:open_readonly(path)` 返回 `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`<br>2. `test_connection` 与 `explain_sql` 都改用它<br>3. 顺手把 SQLite 的 EXPLAIN 也接入 `dialect/sqlite.py`，与 MySQL/PG 的 explain 模块对齐 |
| 回归测试 | `test_executor.py` 新增 EXPLAIN-RO-1：对只读文件系统上的 SQLite 跑 EXPLAIN 应成功；对有写权限文件跑 EXPLAIN 后文件 mtime 不变 |

---

# 缺陷 D4 · TrustGate dry-run 失败不阻断执行

| 字段 | 内容 |
|---|---|
| 缺陷标题 | EXPLAIN 干跑（dry-run）失败时仅记 message，不再加入 `blocked_reasons` |
| 文件:位置 | `engine/sql/trust_gate.py:173-185`（`execution_decision` 的 dry-run 分支） |
| 缺陷类型 | 安全 / 逻辑回归 |
| 严重程度 | **Medium** |
| 优先级 | **P1** |
| 触发条件 | Agent 路径或用户路径执行 SQL，且该 SQL 在目标库的 EXPLAIN 失败（语法错、权限错、表不存在） |
| 复现步骤 | 1. 准备一个 schema 缓存与实际库不一致的 datasource<br>2. Agent 生成 `SELECT typo_col FROM real_table`<br>3. dry-run EXPLAIN 失败，只追加 message `EXPLAIN dry-run warning (execution allowed): ...`<br>4. `can_execute` 仍为 True，SQL 继续执行，最终在真执行时报 `Unknown column` |
| 预期结果 | dry-run 失败按错误类型分级处理：连接级错误（库离线）放行；语法/权限/schema 级错误应阻断或至少降级 risk_level |
| 实际结果 | 一律放行；Agent 浪费一次工具调用 + 可能执行本应被挡的 SQL |
| 影响范围 | 所有走 TrustGate 的执行路径；Agent 体验下降（多绕一圈才看到错误）；安全门实际「漏」了一类本可提前拦的 SQL |
| 可能根因 | 注释写明「no longer block execution on dry run failures to prevent permission/lock issues from blocking」——为了解决一个症状（锁/权限误杀）而放松了一整类检查。正确做法是分类，而非一刀切 |
| 修复方案 | 1. `dry_run_query` 返回结构化结果：`{ok, error_class: "connection"\|"syntax"\|"permission"\|"schema"\|"unknown", message}`<br>2. trust_gate 按 `error_class` 决策：<br>　• `connection` → 放行（加 `explain_unavailable` 到 messages）<br>　• `syntax`/`schema`/`permission` → 加入 `blocked_reasons`（`schema_error`/`syntax_error`）<br>3. 连接级错误不阻断，但要把 `explain_unavailable` 反映到 `_decision_block_message` 的兜底文案 |
| 回归测试 | `test_trust_gate.py` 新增 DRY-RUN-1..4：四类错误各一；确认 blocked_reasons 正确分类 |

---

# 缺陷 D5 · `execute_query` 双重 commit 与 history 一致性

| 字段 | 内容 |
|---|---|
| 缺陷标题 | 拦截路径（`can_execute=False`）与执行路径（`_run_approved_query` 的 finally）各 commit 一次 QueryHistory，异常路径可能写入不完整记录 |
| 文件:位置 | `engine/sql/executor.py:122-146`（`_run_approved_query` 的 finally commit）<br>`engine/sql/executor.py:226-251`（拦截分支的 commit） |
| 缺陷类型 | 事务 / 一致性 |
| 严重程度 | **Medium** |
| 优先级 | **P1** |
| 触发条件 | 执行 SQL 抛异常（超时、取消、连接断），`_run_approved_query` 的 finally 仍 `db.commit()` 写一条 `execution_status="failed"` 的 history |
| 复现步骤 | 1. 执行一条会超时的 SQL（mock dialect 层抛 `TimeoutError`）<br>2. `executor.py:113-116` 捕获后改 `execution_status="timeout"` 并 `raise SQLQueryTimeoutError`<br>3. finally 块仍执行，`db.add(history); db.commit()` 写入 timeout 记录<br>4. 异常向上抛到 `api/query.py:65`，被兜底转成 500 |
| 预期结果 | history 记录完整且原子：要么写成功（含正确 status），要么完全不写；不与上层事务冲突 |
| 实际结果 | finally 里的 commit 与 API 层的 rollback（`api_execute_sql` 异常时 FastAPI 不显式 rollback）边界不清；SQLite 并发下可能 `database is locked` |
| 影响范围 | 所有失败的 SQL 执行；QueryHistory 可能出现「执行失败但 history 写入也失败」的双失败，日志查不到现场 |
| 可能根因 | history 写入与业务执行共用同一 Session；finally 里强行 commit 把业务事务提前固化 |
| 修复方案 | 1. history 写入用独立短事务：`with SessionLocal() as hdb: hdb.add(history); hdb.commit()`<br>2. 或在 `_run_approved_query` 收集 history 字段，由调用方在 API 层统一持久化<br>3. finally 里若 `db.commit()` 抛错，log warning 但不再 raise（避免掩盖原始业务异常） |
| 回归测试 | `test_executor.py` 新增 HIST-1..3：超时/取消/连接断各一，断言 QueryHistory 写入且 status 正确，原始异常仍向上抛 |

---

# 缺陷 D6 · `TunnelManager.health_check` 状态竞态

| 字段 | 内容 |
|---|---|
| 缺陷标题 | `health_check` 在 `with self._lock` 之外修改 `instance.state`，存在数据竞争 |
| 文件:位置 | `engine/tunnel.py:117-144`（`health_check`）<br>`engine/tunnel.py:159-181`（`get_or_reconnect` 也读了 instance.state） |
| 缺陷类型 | 并发 |
| 严重程度 | **Low** |
| 优先级 | **P2** |
| 触发条件 | 多线程同时通过 `get_or_reconnect` 获取同一 datasource 的隧道 |
| 复现步骤 | 1. 10 个线程并发调用 `get_or_reconnect(same_ds_dict)`<br>2. 线程 A 在 `health_check` 把 `instance.state = TunnelState.STALE`<br>3. 线程 B 在 `get_or_reconnect` 读 `instance.state` 决策是否重连<br>4. 读写无锁保护，可能同时触发多条重连 |
| 预期结果 | 状态变更与读取都在锁内，重连只发生一次 |
| 实际结果 | 状态字段裸写；理论上可能重复创建物理隧道（资源浪费，不直接致错） |
| 影响范围 | 高并发 SSH 隧道场景；当前 DBFox 单用户桌面应用触发概率低 |
| 可能根因 | `health_check` 为了「锁外做 socket 探测不阻塞其他线程」而把状态写也放到了锁外，混淆了「耗时操作」与「状态变更」 |
| 修复方案 | 1. 锁内读 instance，锁外做 socket 探测（保留性能），探测完**再次取锁**写 state<br>2. 或 `TunnelInstance` 自带一个 `threading.Lock`，状态变更走实例锁 |
| 回归测试 | `test_datasource_safety.py` 新增 TUNNEL-RACE-1：20 线程并发 get_or_reconnect，断言物理隧道只创建 1 次（计数 mock `_start_physical_tunnel`） |

**修复伪代码：**
```python
def health_check(self, datasource_id: str) -> bool:
    with self._lock:
        instance = self._tunnels.get(datasource_id)
    if not instance:
        return False
    if not instance.tunnel.is_active:
        with self._lock:
            instance.state = TunnelState.STALE
        return False
    alive = self._probe_socket(instance.tunnel.local_bind_port)  # 锁外耗时
    with self._lock:
        instance.state = TunnelState.CONNECTED if alive else TunnelState.STALE
    return alive
```

---

# 缺陷 D7 · API 错误响应结构不统一

| 字段 | 内容 |
|---|---|
| 缺陷标题 | 不同 router 返回的错误 JSON 结构形态不一，前端需多重 if/else 兼容 |
| 文件:位置 | `engine/main.py:289-302`（`dbfox_error_handler` 返回 `{"detail": {"code","message"}}`）<br>`engine/api/query.py:59`（`HTTPException(detail={"code","message"})` 被 FastAPI 包成 `{"detail": {...}}`）<br>`engine/api/datasources.py:229,280,342`（`HTTPException(detail={"code":"NOT_FOUND","message":...})`）<br>`engine/api/query.py:67-70`（500 错误 `{"code":"EXECUTION_ERROR","message":...}`）<br>前端：`desktop/src/lib/api/client.ts:118-135` 的兼容层 |
| 缺陷类型 | 接口契约 / 可维护性 |
| 严重程度 | **Low** |
| 优先级 | **P2** |
| 触发条件 | 任意 API 报错 |
| 复现步骤 | 1. 触发 `/query/execute` 的 500 → 顶层是 `{"code","message"}` 无 detail 包裹<br>2. 触发 `/datasources/{id}` 404 → `{"detail":{"code","message"}}`<br>3. 触发 guardrail 拦截 → `{"detail":{"code","message","checks"}}`<br>4. 前端 `client.ts` 必须同时处理「顶层有 code」「detail 是对象」「detail 是数组（FastAPI 校验错）」三种 |
| 预期结果 | 所有业务错误统一为 `{"detail": {"code": str, "message": str, "checks"?: list}}` |
| 实际结果 | 三种形态混存，前端兼容代码持续膨胀；新增 router 时容易漏掉某种形态 |
| 影响范围 | 所有 API 错误处理；不影响功能但显著增加维护成本与 bug 概率 |
| 可能根因 | 没有强制的错误响应 Schema；FastAPI 默认 HTTPException 与自定义 exception_handler 各干各的 |
| 修复方案 | 1. 定义 Pydantic `ErrorResponse: {code: str, message: str, checks: list = []}`<br>2. 所有业务错误一律走 `DBFoxError` 体系，由 `main.py:dbfox_error_handler` 统一返回 `{"detail": ErrorResponse}`<br>3. router 内的 `raise HTTPException(...)` 改为 `raise DBFoxError(code=..., message=...)` 或自定义 `NotFoundError(DBFoxError)`<br>4. 校验错（FastAPI 422）保留 FastAPI 默认形态，但 `client.ts` 单独识别 `detail` 是数组的情况 |
| 回归测试 | 集成测试 `test_frontend_contract.py` 的「错误结构统一性回归」（第 4 节 §2.4） |

---

## 缺陷汇总矩阵

| ID | 类型 | 严重 | 优先 | 涉及模块 | 修复工作量预估 |
|---|---|---|---|---|---|
| D1 | SQL 注入 | High | P0 | tools/db_tools | 0.5 天（含测试） |
| D2 | 数据泄露 | High | P0 | sql/executor, tools/db_tools | 1 天 |
| D3 | 安全/一致 | Medium | P1 | sql/executor, dialect/sqlite | 0.5 天 |
| D4 | 安全/逻辑 | Medium | P1 | sql/trust_gate, sql/dry_run | 1 天 |
| D5 | 事务/一致 | Medium | P1 | sql/executor | 1 天 |
| D6 | 并发 | Low | P2 | tunnel | 0.5 天 |
| D7 | 契约/维护 | Low | P2 | api/*, main, schemas | 1.5 天 |

**合计约 6 人天**。建议按 P0 → P1 → P2 顺序排期，P0 两项在同一个 sprint 内闭环。

---

## 验收标准（每张缺陷单的 Done 定义）

- [ ] 根因分析段落被开发确认（不是猜测）
- [ ] 修复方案落地，diff 可 review
- [ ] 「回归测试」一节列出的用例全部新增并 CI 通过
- [ ] 缺陷单状态流转：Open → In Progress → Resolved → Closed（由测试验证后关闭）
- [ ] 若修复引入新风险，在本缺陷单下追加「引入风险」子段，不得静默

---

## 完成情况

**审查日期:** 2026-06-17

### 缺陷修复状态

| ID | 标题 | 状态 | 说明 |
|----|------|------|------|
| D1 | db.preview SQL 注入 | ✅ 已修复 | `engine/sql/builder.py` 引入 `safe_identifier`，白名单正则 + sqlglot 转义 |
| D2 | /query/execute 结果未脱敏 | ✅ 已修复 | `engine/policy/sensitivity.py` 提取，executor 集成脱敏管道 |
| D3 | explain_sql SQLite 绕过只读 | ✅ 已修复 | `dry_run.py` 改用 `mode=ro` URI 连接 |
| D4 | TrustGate dry-run 失败不阻断 | ✅ 已修复 | `trust_gate.py` 现在 `schema_error` 也加入 `blocked_reasons` |
| D5 | execute_query 双重 commit | ✅ 已修复 | `_run_approved_query` finally 块使用独立 `AuditSession` 隔离事务 |
| D6 | TunnelManager.health_check 竞态 | ✅ 已修复 | `health_check` 状态变更在锁内完成 |
| D7 | API 错误结构不统一 | ✅ 已修复 | `engine/schemas/error.py` 定义 ErrorResponse，统一错误格式 |

### 已关联测试

- D1 → PREVIEW-1..8, WHERE-1..6 (test_db_tools_whitebox.py)
- D2 → REDACT-1..4 (test_executor.py)
- D3 → dry_run.py SQLite 连接测试
- D4 → test_trust_gate.py schema_error blocking tests
- D5 → test_executor.py 历史写入隔离测试
- D6 → test_datasource_safety.py TUNNEL-RACE 并发测试
- D7 → test_frontend_contract.py 错误结构回归
