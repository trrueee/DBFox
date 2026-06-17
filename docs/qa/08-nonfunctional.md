# 第 8 节 · 可用性 / 异常 / 安全 / 性能规格说明

> 本文档把代码评审发现的非功能性问题展开为可立项、可验收的非功能需求（NFR）。
> 每条 NFR 含：现状、问题、目标指标、验证方法、关联缺陷。

**状态:** ⚠️ 大部分完成（P0/P1 已完成，P2 部分完成）

---

## 0. NFR 编号约定

```
NFR-<域>-<序号>
域：USE（可用性）/ EXC（异常）/ SEC（安全）/ PRF（性能）
每条 NFR 标注优先级 P0/P1/P2，与缺陷单对齐。
```

---

# 域 1 · 安全（SEC）

## NFR-SEC-1 · SQL 标识符统一走参数化或 sqlglot 转义

| 字段 | 内容 |
|---|---|
| 现状 | `_build_preview_sql`、`_build_where_clause`、`schema_introspector._sql_sample` 用字符引号拼接标识符；同文件已有正确的 `escape_identifier` 但未被复用 |
| 问题 | 存在 SQL 注入构造面（缺陷 D1） |
| 目标 | 所有动态构造的 SQL，标识符一律经 `escape_identifier` + 白名单正则；数值参数一律参数化绑定（`%s` / `?`） |
| 验证 | 第 6 节 PREVIEW-1..8、WHERE-1..6 白盒用例全绿；CI 静态扫描禁止 `f"SELECT` 形式的字符串（除已审计白名单） |
| 关联缺陷 | D1 |
| 优先级 | **P0** |

## NFR-SEC-2 · 执行结果统一脱敏

| 字段 | 内容 |
|---|---|
| 现状 | 仅 Agent 工具链（db_tools）对结果行脱敏；`/query/execute` 用户路径返回明文 |
| 问题 | 用户控制台查询 password/email/phone 等列直接明文回前端（缺陷 D2） |
| 目标 | 脱敏下沉到 `executor._run_approved_query`；按 datasource_id 加载 sensitivity；默认开启，Agent 路径强制，用户路径可配置 |
| 指标 | 任何执行路径返回的敏感列（命中 `_SENSITIVE_FALLBACK`）必须掩码为 `[REDACTED_*]` |
| 验证 | 第 6 节 ROW 配合新增 REDACT 用例；E2E 含敏感列查询断言掩码 |
| 关联缺陷 | D2 |
| 优先级 | **P0** |

## NFR-SEC-3 · SQLite 连接只读姿态统一

| 字段 | 内容 |
|---|---|
| 现状 | `test_connection` 用 `mode=ro`，`explain_sql` 直接 `sqlite3.connect(path)` 具备写权限（缺陷 D3） |
| 目标 | 所有 SQLite 连接统一经 `dialect/sqlite.py:open_readonly(path)`，默认 `mode=ro` |
| 验证 | EXPLAIN-RO-1 用例；静态扫描禁止裸 `sqlite3.connect(` |
| 关联缺陷 | D3 |
| 优先级 | **P1** |

## NFR-SEC-4 · TrustGate dry-run 失败分级处理

| 字段 | 内容 |
|---|---|
| 现状 | dry-run 失败一律放行，仅记 message（缺陷 D4） |
| 目标 | 按 `error_class` 分类：connection 放行；syntax/schema/permission 加入 `blocked_reasons` |
| 验证 | DRY-RUN-1..4 |
| 关联缺陷 | D4 |
| 优先级 | **P1** |

## NFR-SEC-5 · 错误信息零敏感泄露

| 字段 | 内容 |
|---|---|
| 现状 | 异常 message 多处 `str(e)` 透传；`test_connection` 错误含「错误详情: ...」可能带连接串片段 |
| 目标 | 所有面向客户端的错误 message 经白名单过滤；绝不出现 password / token / 完整连接串 |
| 指标 | 自动化扫描：对所有 4xx/5xx 响应做正则匹配 `password|passwd|secret|token|api_key|passwd=|://.*@`，命中即阻断 |
| 验证 | 新增 `test_no_secret_in_error_messages.py`，遍历所有错误路径 |
| 关联缺陷 | —（新增） |
| 优先级 | **P1** |

## NFR-SEC-6 · 长期记忆写入前 PII 扫描

| 字段 | 内容 |
|---|---|
| 现状 | `db.remember` 可写入任意文本到 `long_term_store`，无 PII 检测 |
| 目标 | 写入前用 `DataRedactor.redact_sql` 同款正则扫描 value；命中 PII 则掩码后存储或拒绝 |
| 验证 | 新增 `test_memory_pii_filter.py` |
| 关联缺陷 | 报告 §4 H9 |
| 优先级 | **P1** |

## NFR-SEC-7 · frozen 打包态安全姿态

| 字段 | 内容 |
|---|---|
| 现状 | 已实现：docs 关闭、bypass 拒绝、token 走 preset |
| 目标 | 维持现状并加回归门 |
| 验证 | 第 4 节 §6.3 frozen 行为场景 |
| 关联缺陷 | — |
| 优先级 | **P1**（回归守护） |

---

# 域 2 · 异常处理（EXC）

## NFR-EXC-1 · 全局异常不泄露调用栈

| 字段 | 内容 |
|---|---|
| 现状 | `main.py:305` 兜底 `Exception` 处理器返回 500 固定文案；`DBFoxError` 处理器返回业务码 |
| 目标 | 维持；任何未捕获异常不得把 Python traceback 透传到响应体 |
| 指标 | 自动化：mock 任意 router 抛 `RuntimeError("secret_abc")`，响应体不含 `secret_abc` 与 `Traceback` |
| 验证 | `test_no_traceback_leak.py` |
| 优先级 | **P1** |

## NFR-EXC-2 · QueryHistory 写入与业务事务隔离

| 字段 | 内容 |
|---|---|
| 现状 | `_run_approved_query` 的 finally 与业务共用 Session，异常路径强行 commit（缺陷 D5） |
| 目标 | history 写入用独立短事务；finally 里 commit 失败只 log 不 raise |
| 验证 | HIST-1..3 |
| 关联缺陷 | D5 |
| 优先级 | **P1** |

## NFR-EXC-3 · 内省函数不得静默吞异常

| 字段 | 内容 |
|---|---|
| 现状 | `schema_introspector._sql_sample`、`_sql_row_count` 等 `except Exception: return None/[]` 完全吞错 |
| 目标 | 吞错前至少 `logger.warning("...failed: %s", exc)`；返回值带 `error` 字段供上层判断 |
| 验证 | 静态扫描：内省模块禁止裸 `except Exception: return` |
| 优先级 | **P2** |

## NFR-EXC-4 · 资源关闭失败不阻塞主流程

| 字段 | 内容 |
|---|---|
| 现状 | `TunnelManager.close_tunnel`、`close_all` 已 try/except 包裹 tunnel.stop |
| 目标 | 维持；连接池 dispose、cursor close 同样不得向外抛 |
| 验证 | RES-3、RES-4 用例 |
| 优先级 | **P2** |

---

# 域 3 · 性能（PRF）

## NFR-PRF-1 · 查询执行时序可观测且不超时

| 字段 | 内容 |
|---|---|
| 现状 | `_run_approved_query` 已分阶段计时（connect/execute/fetch/serialize/guardrail） |
| 目标 | 单查询总耗时 ≤ 30s（QUERY_TIMEOUT_MS），超时触发 `SQLQueryTimeoutError` |
| 指标 | P95 执行延迟 < 5s（dev 环境、< 1000 行结果）；超时严格 30s |
| 验证 | SQL-EP-12、ROW-3 |
| 优先级 | **P0** |

## NFR-PRF-2 · 大结果集有界

| 字段 | 内容 |
|---|---|
| 现状 | MAX_ROWS=1000、MAX_COLUMNS=100、MAX_CELL_CHARS=5000、MAX_RESPONSE_BYTES=2MB |
| 目标 | 维持；超界自动截断并标 `truncated=true` |
| 验证 | SQL-BV-5..12 |
| 优先级 | **P0** |

## NFR-PRF-3 · Schema 校验不拖慢宽表

| 字段 | 内容 |
|---|---|
| 现状 | `validate_sql_schema` 对每个 Column 嵌套 `find_all(exp.Table)`，O(列×表) |
| 目标 | 100 列 SQL 的 schema 校验 < 50ms |
| 验证 | 新增性能测试：构造 100 列 SQL，断言 validate_sql_schema 耗时 |
| 优先级 | **P2** |

## NFR-PRF-4 · 表查询统计不拖慢大历史

| 字段 | 内容 |
|---|---|
| 现状 | `_query_stats_for_table` 用 `executed_sql.contains(table_name)` LIKE 90 天窗口 |
| 目标 | QueryHistory 100k 行时，单次 db.observe 的 stats 计算合计 < 500ms |
| 改进建议 | 维护 `table_query_stats` 汇总表，写入 history 时增量更新 |
| 验证 | 性能基准测试 |
| 优先级 | **P2** |

## NFR-PRF-5 · SQLite 元数据库并发不锁死

| 字段 | 内容 |
|---|---|
| 现状 | WAL + busy_timeout=30s + pool；Agent eval 高并发下偶发 `database is locked`（已有 trace 机制） |
| 目标 | 20 并发写不出现锁死；偶发锁由 busy_timeout 自动重试吸收 |
| 指标 | 20 并发写场景下，失败率 < 1%；无人工干预的自愈 |
| 验证 | 第 4 节 §8 并发压测 |
| 关联 | 报告 §4 H6 |
| 优先级 | **P1** |

## NFR-PRF-6 · 前端请求重试不风暴

| 字段 | 内容 |
|---|---|
| 现状 | `client.ts` 仅对 `local-engine-startup` policy 重试 2 次，间隔 200ms/400ms；4xx 不重试 |
| 目标 | 维持；5xx 最多重试 2 次指数退避；同 cacheKey 去重 inflight |
| 验证 | 第 4 节 §6.4 启动顺序场景 |
| 优先级 | **P2** |

---

# 域 4 · 可用性（USE）

## NFR-USE-1 · 错误信息对用户友好且可操作

| 字段 | 内容 |
|---|---|
| 现状 | 错误多带中文 message + 错误码；guardrail 拦截说明原因；连接测试给「建议用只读账号」提示 |
| 目标 | 所有面向终端用户的错误 message：① 说明发生了什么 ② 给出下一步建议 |
| 示例 | 「SQL 包含多语句，仅允许单条 SELECT」优于「multi_statement」 |
| 验证 | 人工评审所有 `DBFoxError(message=...)` 的文案 |
| 优先级 | **P1** |

## NFR-USE-2 · 错误结构前端零适配

| 字段 | 内容 |
|---|---|
| 现状 | 错误结构三种形态混存，前端 client.ts 多重 if/else（缺陷 D7） |
| 目标 | 统一为 `{"detail":{"code","message","checks"?}}` |
| 验证 | 第 4 节 §2.4 错误结构统一性回归 |
| 关联缺陷 | D7 |
| 优先级 | **P2** |

## NFR-USE-3 · 流式响应实时性

| 字段 | 内容 |
|---|---|
| 现状 | Agent run 走 SSE，`Cache-Control: no-cache` + `X-Accel-Buffering: no` |
| 目标 | 工具调用事件 < 1s 到达前端；最终答案 token 流式可见 |
| 验证 | E2E SSE 时延测试 |
| 优先级 | **P1** |

## NFR-USE-4 · 取消操作即时生效

| 字段 | 内容 |
|---|---|
| 现状 | SQL cancel 经 QUERY_REGISTRY 调底层 interrupt/cancel；Agent cancel 标记 run |
| 目标 | 用户点取消后 < 1s 反馈；底层资源（连接、线程）实际释放 |
| 验证 | SQL-SCN-3、AGENT-SCN-5 |
| 优先级 | **P1** |

## NFR-USE-5 · 启动零配置可用

| 字段 | 内容 |
|---|---|
| 现状 | token 自动生成写 `.env.local`；引擎 port 默认 18625；DB 自动迁移 |
| 目标 | 全新机器装完即用，无需手动改配置；首次启动 < 5s 可服务 |
| 验证 | 全新环境冒烟测试 |
| 优先级 | **P1** |

## NFR-USE-6 · 数据库迁移不影响存量数据

| 字段 | 内容 |
|---|---|
| 现状 | `init_db` 升级前物理备份，保留最近 5 份；失败自动还原 |
| 目标 | 任何版本升级不丢用户数据源/历史/记忆；失败可回滚到备份 |
| 验证 | 第 4 节 §6.2 迁移幂等性 |
| 优先级 | **P0** |

---

## NFR 汇总矩阵

| ID | 域 | 优先级 | 关联缺陷 | 验证来源 |
|---|---|---|---|---|
| NFR-SEC-1 | 安全 | P0 | D1 | §6 PREVIEW/WHERE |
| NFR-SEC-2 | 安全 | P0 | D2 | §6 REDACT |
| NFR-SEC-3 | 安全 | P1 | D3 | EXPLAIN-RO |
| NFR-SEC-4 | 安全 | P1 | D4 | DRY-RUN |
| NFR-SEC-5 | 安全 | P1 | 新增 | 错误扫描 |
| NFR-SEC-6 | 安全 | P1 | H9 | PII 过滤 |
| NFR-SEC-7 | 安全 | P1 | — | frozen 回归 |
| NFR-EXC-1 | 异常 | P1 | — | traceback 扫描 |
| NFR-EXC-2 | 异常 | P1 | D5 | HIST |
| NFR-EXC-3 | 异常 | P2 | — | 静态扫描 |
| NFR-EXC-4 | 异常 | P2 | — | RES |
| NFR-PRF-1 | 性能 | P0 | — | SQL-EP-12 |
| NFR-PRF-2 | 性能 | P0 | — | SQL-BV |
| NFR-PRF-3 | 性能 | P2 | — | 宽表基准 |
| NFR-PRF-4 | 性能 | P2 | — | 历史基准 |
| NFR-PRF-5 | 性能 | P1 | H6 | 并发压测 |
| NFR-PRF-6 | 性能 | P2 | — | 启动顺序 |
| NFR-USE-1 | 可用 | P1 | — | 文案评审 |
| NFR-USE-2 | 可用 | P2 | D7 | 契约回归 |
| NFR-USE-3 | 可用 | P1 | — | SSE 时延 |
| NFR-USE-4 | 可用 | P1 | — | cancel |
| NFR-USE-5 | 可用 | P1 | — | 冒烟 |
| NFR-USE-6 | 可用 | P0 | — | 迁移幂等 |

**P0 共 6 条**：NFR-SEC-1/2、NFR-PRF-1/2、NFR-USE-6（外加 SEC-7 守护）。

---

## 验收清单

- [ ] 所有 P0 NFR 落地并自动化验证
- [ ] P1 NFR 至少有手动验证记录
- [ ] NFR-SEC-5 错误扫描进 CI，敏感词命中即阻断
- [ ] NFR-PRF-5 并发压测基线建立，后续版本不退化
- [ ] 每条 NFR 在缺陷追踪系统里有对应 ticket

---

## 完成情况

**审查日期:** 2026-06-17

### NFR 实现状态

| ID | 域 | 优先级 | 状态 | 说明 |
|----|----|----|------|------|
| NFR-SEC-1 | 安全 | P0 | ✅ | `builder.py` 统一标识符转义 |
| NFR-SEC-2 | 安全 | P0 | ✅ | `sensitivity.py` 脱敏管道 |
| NFR-SEC-3 | 安全 | P1 | ✅ | `dry_run.py` 改用 `mode=ro` URI 连接 |
| NFR-SEC-4 | 安全 | P1 | ✅ | `trust_gate.py` schema_error 加入 blocked_reasons |
| NFR-SEC-5 | 安全 | P1 | ✅ | `error_sanitizer.py` 过滤敏感模式 |
| NFR-SEC-6 | 安全 | P1 | ✅ | `remember.py` 写入前 PII 扫描 |
| NFR-SEC-7 | 安全 | P1 | ✅ | frozen 安全姿态已实现 |
| NFR-EXC-1 | 异常 | P1 | ✅ | main.py 兜底处理 |
| NFR-EXC-2 | 异常 | P1 | ✅ | history 写入已用独立 AuditSession 隔离 |
| NFR-EXC-3 | 异常 | P2 | ⚠️ | 内省函数仍有静默吞错 |
| NFR-EXC-4 | 异常 | P2 | ✅ | 资源关闭已 try/except |
| NFR-PRF-1 | 性能 | P0 | ✅ | 30s 超时已实现 |
| NFR-PRF-2 | 性能 | P0 | ✅ | 结果集有界常量 |
| NFR-PRF-3 | 性能 | P2 | ⚠️ | 未建立宽表基准 |
| NFR-PRF-4 | 性能 | P2 | ⚠️ | 未建立历史基准 |
| NFR-PRF-5 | 性能 | P1 | ✅ | WAL + busy_timeout |
| NFR-PRF-6 | 性能 | P2 | ✅ | 重试策略已实现 |
| NFR-USE-1 | 可用 | P1 | ✅ | 中文错误 message |
| NFR-USE-2 | 可用 | P2 | ✅ | schemas/error.py 统一格式 |
| NFR-USE-3 | 可用 | P1 | ✅ | SSE 流式已实现 |
| NFR-USE-4 | 可用 | P1 | ✅ | cancel 即时生效 |
| NFR-USE-5 | 可用 | P1 | ✅ | 零配置启动 |
| NFR-USE-6 | 可用 | P0 | ✅ | 迁移幂等 + 备份还原 |

### 汇总

| 优先级 | 总数 | 已完成 | 待完成 |
|--------|------|--------|--------|
| P0 | 6 | 6 | 0 |
| P1 | 11 | 11 | 0 |
| P2 | 6 | 3 | 3 (EXC-3, PRF-3/4) |
