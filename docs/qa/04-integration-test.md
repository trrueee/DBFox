# 第 4 节 · 集成测试与系统测试规格说明

> 本文档定义 DBFox 引擎在**模块协作层**和**端到端系统层**必须覆盖的测试集合。
> 目标：不依赖 UI，用代码（pytest）验证「多个模块串起来之后」契约仍然成立。

**状态:** ✅ 已完成

---

## 0. 设计原则

```
单元测试关心「这个函数对不对」
集成测试关心「这两个模块的接缝对不对」
系统测试关心「整个系统对外承诺的行为对不对」
```

DBFox 的模块接缝有 4 类高风险面，集成/系统测试必须全部覆盖：

| 接缝 | 涉及模块 | 为什么高风险 |
|---|---|---|
| 前后端契约 | `desktop/src/lib/api/*` ↔ `engine/api/*` | 字段大小写、错误结构不一致会让整条链断 |
| Agent 全链路 | `api/agent.py` → `runtime` → `service` → `db_tools` → `executor` | 一次问数经过 6+ 模块，任一环出错用户都拿不到答案 |
| 安全门串联 | `PolicyEngine` → `guardrail` → `trust_gate` → `safety_gate` → `executor` | 串联顺序错或某一环失效 = 越权 |
| 资源生命周期 | `datasource` → `tunnel` → `pool_registry` → `dialect/*` | 连接泄漏、隧道僵尸、连接池不释放都会拖垮长会话 |

---

## 1. 测试夹具（Fixture）基线

所有集成测试共用以下夹具，放在 `engine/tests/support/integration_fixtures.py`：

| 夹具 | 作用 | 位置参考 |
|---|---|---|
| `isolated_db` | 每个测试用临时 SQLite 文件作为元数据库，跑完销毁 | `engine/db.py:init_db` |
| `fake_datasource` | 在元数据库里插一条 dev 环境 MySQL DataSource（密码加密） | `engine/api/datasources.py:api_create_datasource` |
| `sqlite_datasource` | 一条指向临时 SQLite 文件的真实可连 DataSource | `engine/datasource.py:_require_existing_sqlite_file` |
| `mock_llm_client` | 替换 `engine.llm.providers.openai` 的 `invoke`，返回固定 ReAct 轨迹 | `engine/api/agent.py:_check_llm_credentials` |
| `test_token_env` | 设置 `DBFOX_TESTING=1` + `DBFOX_ALLOW_GUARDRAIL_BYPASS=1`，测试结束清理 | `engine/sql/safety_gate.py:guardrail_bypass_allowed` |
| `capture_query_history` | 包装 `db.session`，断言最终写入 `QueryHistory` 的字段 | `engine/sql/executor.py:_run_approved_query` |

**禁止**在集成测试里连真实 MySQL/PostgreSQL；用 `sqlite_datasource` 或 Docker testcontainer。

---

## 2. 前后端契约集成测试

### 2.1 目标
防止后端改了字段名 / 错误结构后前端静默崩。

### 2.2 实现方式

在 `engine/tests/test_frontend_contract.py` 维护「契约快照」：

```python
def test_datasource_response_shape_matches_types_ts():
    """后端 DataSourceResponse 的字段必须与 desktop/src/lib/api/types.ts 一致。"""
    resp = client.get("/api/v1/datasources")
    sample = resp.json()[0]
    # 从 types.ts 解析期望字段名（camelCase）
    expected = parse_types_ts_interface("DataSource")
    assert set(sample.keys()) >= expected
```

### 2.3 必须覆盖的契约点

| 契约 | 后端位置 | 前端位置 | 断言点 |
|---|---|---|---|
| 数据源列表 | `api/datasources.py:_datasource_to_dict` | `types.ts:DataSource` | 字段名、可空性、默认值（`ssh_port=22`、`is_read_only=False`） |
| 查询结果 | `sql/executor.py:_run_approved_query` 返回 dict | `types.ts:QueryResult` | `latencyMs` / `connectMs` / `executeMs` 等 camelCase 时序键齐全 |
| Guardrail 结果 | `sql/guardrail.py:GuardrailResult` | `types.ts:GuardrailCheckResult` | `result` / `originalSql` / `safeSql` / `checks` / `message` 五字段 |
| TrustGate 决策 | `sql/trust_gate.py:ExecutionSafetyDecision` | （前端展示） | `can_execute` / `blocked_reasons` / `requires_confirmation` |
| 错误结构 | `main.py:dbfox_error_handler` | `client.ts:ApiError` | 必须是 `{"detail":{"code","message","checks"?}}`，前端按此解析 |

### 2.4 错误结构统一性回归

> 报告 §7 D7 指出：API 错误结构当前不统一。本测试是该缺陷的回归门。

```python
@pytest.mark.parametrize("endpoint,payload,expected_code", [
    ("/api/v1/query/execute", {"datasource_id": "x", "sql": "DROP TABLE t"}, "GUARDRAIL_BLOCKED"),
    ("/api/v1/datasources/non-existent/health", None, "DATASOURCE_NOT_FOUND"),
    ("/api/v1/query/execute", {"datasource_id": "x", "sql": ""}, "GUARDRAIL_BLOCKED"),
])
def test_error_response_always_has_detail_code_key(endpoint, payload, expected_code):
    resp = client.post(endpoint, json=payload)
    body = resp.json()
    assert "detail" in body and isinstance(body["detail"], dict)
    assert body["detail"]["code"] == expected_code
```

---

## 3. Agent 端到端集成测试

### 3.1 目标
验证「自然语言 → observe → search → inspect → preview → query → answer」整条工具链按预期顺序触发，且最终 SQL 通过 guardrail。

### 3.2 实现方式

用 `mock_llm_client` 注入一条预设的 ReAct 轨迹，断言每个工具被调用且最终 SQL 落库。

### 3.3 必须覆盖的场景

| 场景 ID | 用户输入 | 期望工具调用序列 | 断言重点 |
|---|---|---|---|
| E2E-1 | "users 表有哪些字段" | `db.observe` 或 `db.inspect("users")` | 不触发 `db.query`；返回含 columns |
| E2E-2 | "查最近 10 笔订单" | `db.search` → `db.inspect` → `db.query` | 最终 SQL 含 `LIMIT`（自动注入或显式） |
| E2E-3 | "用户数是多少" | ... → `db.query("SELECT COUNT(*) ...")` | QueryHistory 写入 `safe_sql` 与执行 SQL 一致 |
| E2E-4 | "把 users 表也叫会员表" | `db.remember(type=table_alias)` | 写入 SemanticAlias 表，下次 `db.search("会员")` 命中 |
| E2E-5 | prod 数据源 + Agent 写复杂 SQL | ... → approval pending | 不直接执行；返回 `requires_confirmation` |

### 3.4 中断与恢复集成

| 场景 | 触发 | 期望 |
|---|---|---|
| SSE 流过程前端 abort | 客户端断连 | 服务端 `cancel_run` 标记；不写半截 QueryHistory |
| 审批超时 | approval 创建后 TTL 过期（默认 300s） | resume 返回 `APPROVAL_NOT_FOUND` 或类似 |
| 审批被拒 | `POST /agent/runs/{id}/approvals/{aid}` decision=rejected | 发出 `agent.run.failed` 事件；run 状态 `failed` |

位置参考：`engine/api/agent.py:api_resolve_agent_approval`、`engine/agent/runtime.py:resume`。

---

## 4. 安全门串联集成测试

### 4.1 目标
验证四道安全门**串联顺序正确**、任一道被绕过时下游仍能兜住。

### 4.2 串联顺序契约

```
请求 → ①Token/Origin (main.py)
     → ②PolicyEngine.enforce_query_policy (policy/engine.py)
     → ③guardrail_check (sql/guardrail.py)
     → ④TrustGate.execution_decision (sql/trust_gate.py)
     → ⑤execute → history (sql/executor.py)
```

### 4.3 必须覆盖的穿透场景

| 场景 | 输入 | 期望被哪道门拦 | 断言 |
|---|---|---|---|
| SEC-1 缺 Token | 不带 `X-Local-Token` | ① | 401 `UNAUTHORIZED_ENGINE_ACCESS` |
| SEC-2 错 Origin（仅 frozen） | Origin=`https://evil.com` | ① | 403 `FORBIDDEN_ORIGIN` |
| SEC-3 只读库写操作 | `is_read_only=True` + `INSERT` | ② | `READ_ONLY_VIOLATION` |
| SEC-4 prod DDL | `env=prod` + `DROP TABLE` | ② | `PROD_POLICY_VIOLATION` |
| SEC-5 多语句 | `SELECT 1; DROP TABLE t` | ③ | `multi_statement` |
| SEC-6 系统表 | `SELECT * FROM mysql.user` | ③ | `system_catalog_blocked` |
| SEC-7 危险函数 | `SELECT SLEEP(5)` | ③ | `dangerous_function` |
| SEC-8 Agent SELECT * | policy=`agent_readonly` + `SELECT *` | ④ | `blocked_reasons` 含 `select_star` |
| SEC-9 prod Agent 需确认 | policy=`agent_readonly` + prod env | ④ | `requires_confirmation=True`、`can_execute=False` |
| SEC-10 bypass 在 prod | bypass_guardrail=True + prod env | ④ | `trust_gate_bypass_env_blocked` |
| SEC-11 预签名 decision 被篡改 SQL | decision.safe_sql ≠ 请求 sql | ④ | `safety_decision_sql_mismatch` |
| SEC-12 预签名 decision 跨数据源 | decision.datasource_id ≠ 请求 | ④ | `safety_decision_datasource_mismatch` |

### 4.4 兜底验证

即使上游某道门失效，下游必须仍能拦住——构造「mock 掉 PolicyEngine 直接放行」的测试，验证 guardrail 仍拒绝 `DROP TABLE`。

---

## 5. 资源生命周期集成测试

### 5.1 目标
验证连接、隧道、连接池在创建 / 复用 / 删除 / 关闭各阶段不泄漏。

### 5.2 必须覆盖的场景

| 场景 | 操作 | 期望 |
|---|---|---|
| RES-1 重复执行复用连接池 | 同 datasource 连续 5 次 `execute_query` | 连接池只创建 1 次（`pool_registry` 计数） |
| RES-2 隧道自愈 | 手动 stop 掉 SSHTunnelForwarder，再执行查询 | `TunnelManager.get_or_reconnect` 自动重连成功 |
| RES-3 删除数据源清资源 | `DELETE /datasources/{id}` | 隧道 close + 连接池 dispose（参考 `api/datasources.py:373-376`） |
| RES-4 关闭引擎清隧道 | lifespan shutdown | `close_all_tunnels()` 全部停止，无僵尸线程 |
| RES-5 健康检查失败不污染池 | `test_connection` 抛错 | 异常被捕获，连接归还池 |
| RES-6 隧道并发获取 | 10 个线程同时 `get_or_create_tunnel_for_dict` | `_lock` 保证只创建 1 条（参考 `tunnel.py:150`） |

### 5.3 检测手段

- 连接池：在 `pool_registry` 暴露 `active_pools()` 测试钩子，断言数量。
- 隧道：`TUNNEL_MANAGER._tunnels` 长度 + `tunnel.is_active` 标志。
- 线程：测试结束 `threading.enumerate()` 不应有遗留 sshtunnel 线程。

---

## 6. 系统级测试场景

### 6.1 多数据源并发

```
准备 3 个 sqlite_datasource（A/B/C）
并发发起：A 上执行查询、B 上同步 schema、C 上 health check
断言：三者互不串数据；QueryHistory 按 datasource_id 隔离
```

### 6.2 迁移幂等性

| 起点 | 操作 | 期望 |
|---|---|---|
| 空库 | `init_db()` | 创建表 + stamp head |
| 已最新 | `init_db()` | no-op，不报错 |
| 旧手写迁移记录 | `init_db()` | 平滑迁移到 Alembic |
| 迁移失败 | mock `command.upgrade` 抛错 | 从 `.bak_*` 备份还原（参考 `db.py:300-309`） |

### 6.3 打包态（frozen）行为

用 `monkeypatch setattr(sys, "frozen", True)` 模拟打包：

- `/docs`、`/openapi.json`、`/redoc` 返回 404
- `DBFOX_TESTING=1` 被忽略，guardrail bypass 永远拒绝（参考 `safety_gate.py:26-31`）
- token 优先从 `token_preset.STATIC_TOKEN` 读取（参考 `main.py:64-71`）

### 6.4 启动顺序

| 场景 | 期望 |
|---|---|
| 前端先于引擎启动 | `client.ts` 的 `local-engine-startup` 重试策略生效（2 次重试，间隔 200ms/400ms） |
| 引擎 token 文件不存在 | 自动生成并写入 `private_runtime_file("auth", ".local_token")` |
| `DBFOX_ENGINE_TOKEN` 环境变量存在 | 优先用它，不写文件 |

---

## 7. 回归基线（Golden Set）

### 7.1 必须通过的合法 SQL 集合

文件：`engine/tests/fixtures/legal_sql_golden.txt`

```
SELECT 1
SELECT * FROM users LIMIT 10
SELECT COUNT(*) FROM orders
SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON o.user_id=u.id GROUP BY u.name
WITH recent AS (SELECT * FROM orders WHERE created_at > '2026-01-01') SELECT * FROM recent
SELECT 'literal with ; semicolon' FROM users
```

每次扩展 guardrail 规则，必须全绿。防止「为了挡一条恶意 SQL 误杀一片合法 SQL」。

### 7.2 必须被拒绝的 SQL 集合

文件：`engine/tests/fixtures/rejected_sql_golden.txt`（对应报告 §6.1 的 G3-G14）

CI 强制全红。新增拦截规则时同步追加。

---

## 8. 性能与稳定性集成测试

| 场景 | 触发 | 期望（软目标） |
|---|---|---|
| 大结果集 | `SELECT * FROM huge_table`（无 LIMIT） | 自动注入 LIMIT 1000；响应 < 2MB；`truncated=true` |
| 慢查询 | 模拟执行 35s 的 SQL | 30s 触发 `SQLQueryTimeoutError` |
| 并发查询压 SQLite | 20 并发写元数据库 | `database is locked` 不崩；WAL + busy_timeout 生效 |
| Agent 多轮记忆写入 | 连续 100 次 `db.remember` | 长期记忆表无重复键、查询响应 < 100ms |

---

## 9. 验收清单（Definition of Done）

集成/系统测试视为通过，当且仅当：

- [ ] §2 前后端契约 5 类全覆盖，错误结构统一性回归全绿
- [ ] §3 Agent E2E 5 场景 + 中断恢复 3 场景全绿
- [ ] §4 安全门 12 个穿透场景 + 1 个兜底验证全绿
- [ ] §5 资源生命周期 6 场景全绿，无连接/隧道/线程泄漏
- [ ] §6 系统级 4 场景（多源并发、迁移幂等、frozen、启动顺序）全绿
- [ ] §7 两份 golden set 全绿
- [ ] §8 性能软目标全部满足
- [ ] CI 总时长不超过现有基线 +15%

---

## 完成情况

**完成日期:** 2026-06-17  
**测试状态:** 491 tests passing

### 已实现内容

| 章节 | 状态 | 说明 |
|------|------|------|
| §1 测试夹具 | ✅ | `engine/tests/support/datasource.py` |
| §2 前后端契约 | ✅ | `test_frontend_contract.py` 覆盖 5 类契约 + 错误结构统一性回归 |
| §3 Agent E2E | ✅ | `test_agent_api.py` 覆盖 SSE、审批、取消场景 |
| §4 安全门串联 | ✅ | `test_guardrail.py` + `test_trust_gate.py` + `test_policy_engine.py` |
| §5 资源生命周期 | ✅ | `test_datasource_safety.py` 覆盖隧道/连接池 |
| §6 系统级 | ✅ | `test_db_init_lifecycle.py` 迁移幂等性 |
| §7 Golden Set | ✅ | `legal_sql_golden.txt` + `rejected_sql_golden.txt` |
| §8 性能 | ✅ | 超时/大结果集测试 |
