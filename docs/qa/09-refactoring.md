# 第 9 节 · 重构建议规格说明

> 本文档遵循「安全重构」思想：**不重写系统，只做小步、可验证、低风险改进**。
> 每条重构（R1–R8）含：信号、动机、不改后果、小步拆解、需补测试、行为不变验证、回滚策略。
> 严格遵循 Fowler《重构》原则：先有测试再重构，每步保持绿色，行为不变。

**状态:** ✅ 大部分完成（R1-R6 已完成，R7 待实施，R8 部分完成）

---

## 0. 重构总原则

```
1. 先加测试，再动代码   —— 没有测试覆盖的代码不重构
2. 每步小到能单独 review —— 一个 PR 一个语义变更
3. 每步保持绿色         —— 重构与功能改动不混在同一 commit
4. 行为不变是硬约束     —— 用 golden test 守护外部契约
5. 可回滚               —— 每步独立，出问题 revert 单步即可
```

**重构信号清单**（出现即应考虑对应重构）：

| 信号 | 对应重构 |
|---|---|
| 过长文件 / 过长方法 | R1（拆 db_tools）、R7（拆 explain） |
| 重复代码 | R2（标识符工厂）、R3（脱敏下沉）、R5（AST 复用） |
| 过深嵌套 / 参数过多 | R1 拆分时顺手扁平化 |
| 职责混乱的类 | R1、R6 |
| public 数据成员 / 全局可变 | R8（magic number 提常量） |
| 异常处理混乱 | R3 把 redact 从异常路径剥离 |
| 数据类型不一致 | R4（错误结构统一） |
| 多个类因同一变化一起改 | R6（业务标签外置） |

---

# R1 · 拆分 `tools/db_tools.py`（1906 行 → 按工具分文件）

## 信号
- 单文件 1906 行，6 个工具 + 内省 + redact + 记忆 + 搜索混在一起
- AI 改一处易冲突；新加工具不知放哪

## 动机
职责单一、降低合并冲突、提升可读性。当前 `db_tools.py` 同时承担「工具入口」「dialect 内省」「redaction」「记忆写入」「FTS 搜索」5 类职责。

## 不改后果
- 文件继续膨胀；任一新功能都加到这个文件
- 测试文件同步膨胀，难以定位

## 小步拆解

| 步骤 | 动作 | 验证 |
|---|---|---|
| 1 | 新建 `tools/db/` 目录与 `__init__.py` | import 不变 |
| 2 | 提取 `tools/db/_common.py`：常量（MAX_PREVIEW_ROWS 等）、`tool_handler` 装饰器、`_success/_failed`、`_load_sensitivity`、`_redact_row` | 现有测试全绿 |
| 3 | 提取 `tools/db/observe.py`（db_observe + _catalog_* + _schema_sections + _domain_sections + _table_tags） | `test_db_tools.py` observe 相关全绿 |
| 4 | 提取 `tools/db/search.py`（db_search + _fts_search + _fallback_keyword_search） | search 相关全绿 |
| 5 | 提取 `tools/db/inspect.py`（db_inspect + _sqlite/_mysql/_pg_inspect_detail） | inspect 相关全绿 |
| 6 | 提取 `tools/db/preview.py`（db_preview + _build_preview_sql + _build_where_clause + _build_order_clause） | preview 相关全绿；顺带落地 R2 |
| 7 | 提取 `tools/db/query.py`（db_query + _infer_column_types + _limit_was_injected） | query 相关全绿 |
| 8 | 提取 `tools/db/remember.py`（db_remember + _remember_* 各类型） | remember 相关全绿 |
| 9 | `db_tools.py` 改为纯 re-export：`from .tools.db.* import *` + `register_dbfox_tools` 注册逻辑 | 全量测试全绿；外部 import 路径不变 |
| 10 | 删除 `db_tools.py` 中已迁移的旧代码 | 全绿 |

## 需补测试
- 拆分前确保 `test_db_tools.py` 行覆盖 ≥ 70%（当前已有基础）
- 每步迁移前后跑同一份测试集，diff 为空

## 行为不变验证
- `register_dbfox_tools()` 返回的 registry 与拆分前完全一致（用 `assertEqual(registry_before, registry_after)`）
- 6 个工具的 ToolObservation 输出字段逐字对比

## 回滚
- 每步独立 commit；任意步出问题 `git revert <sha>` 即可

---

# R2 · 引入 `sql/builder.py` 统一标识符与参数化

## 信号
- 同文件既有 `escape_identifier`（sqlglot，正确）又有手写引号拼接（错误）
- D1 缺陷根因

## 动机
让「安全构造 SQL」成为默认，而非「记得调用」。

## 不改后果
- 新增的 preview/inspect 路径继续踩同样的注入坑

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | 新建 `engine/sql/builder.py`，定义 `safe_identifier(name, dialect)`、`safe_table(schema, table, dialect)`、`build_select(table, columns, where, order, limit, dialect)` |
| 2 | `safe_identifier` 内部调用 `escape_identifier` + 白名单正则校验，非法抛 `ToolInputError` |
| 3 | 单元测试 builder（PREVIEW/WHERE 用例迁移到此） |
| 4 | `_build_preview_sql` 改为调用 `builder.build_select` |
| 5 | `_build_where_clause` / `_build_order_clause` 同样改为 builder 内部方法 |
| 6 | `schema_introspector._sql_sample` 的 `LIMIT {limit}` 改为 `build_select` 生成 |
| 7 | 静态扫描：禁止 `f"SELECT` 直接拼标识符（白名单已迁移文件） |

## 需补测试
- 第 6 节 PREVIEW-1..8、WHERE-1..6
- builder 自身的单元测试（dialect=mysql/postgres/sqlite 各一组）

## 行为不变验证
- 同一组 (table, columns, where, order, limit) 输入，新旧实现生成的 SQL 字符串完全一致（合法输入下）

## 回滚
- builder 是纯新增；迁移步骤可逐个 revert

---

# R3 · 脱敏下沉到 executor（redaction pipeline）

## 信号
- `_redact_row` 在 db_tools 的 preview 和 query 各调用一次，逻辑重复
- `/query/execute` 路径不脱敏（D2）

## 动机
安全默认：所有执行入口的输出统一经过 redaction。

## 不改后果
- 新增执行入口（导出 API、未来 BI）会再次漏脱敏
- 用户路径持续泄露 PII

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | 在 `executor._run_approved_query` 末尾新增可选 redact 步骤，默认 True |
| 2 | `execute_query` 公开签名新增 `redact: bool = True` 参数 |
| 3 | `_load_sensitivity` 从 db_tools 提取到 `engine/policy/sensitivity.py`，executor 与 db_tools 共用 |
| 4 | db_tools 的 db_preview / db_query 不再自己调 `_redact_row`，依赖 executor 内置 |
| 5 | `/query/execute` 走默认 redact=True |
| 6 | 新增导出类 API 时显式传 redact 参数 |

## 需补测试
- 第 6 节 ROW 配合 REDACT-1..4
- 验证 db_tools 路径行为与之前一致（输出 rows 已掩码）

## 行为不变验证
- 对同一查询，redact=True 时新旧实现输出一致
- Agent 路径（强制 redact）输出不变

## 回滚
- 参数默认 True；如出问题可临时改默认 False（不删代码）

---

# R4 · 统一错误响应 Schema

## 信号
- API 错误三种形态混存（D7）
- 前端 client.ts 多重 if/else 兼容

## 动机
契约统一，前端零适配，降低新增 router 时的踩坑概率。

## 不改后果
- 前端兼容代码持续膨胀；错误处理 bug 概率上升

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | 定义 `engine/schemas/error.py: ErrorResponse {code: str, message: str, checks: list = []}` |
| 2 | `main.py:dbfox_error_handler` 返回 `{"detail": ErrorResponse.model_dump()}` |
| 3 | 新增 `NotFoundError(DBFoxError)`、`ValidationException(DBFoxError)` 等子类，带固定 code |
| 4 | 逐 router 把 `raise HTTPException(detail={...})` 改为 `raise NotFoundError(...)` |
| 5 | 422 校验错保留 FastAPI 默认（前端单独识别 detail 是数组） |
| 6 | 前端 client.ts 简化：只解 `{"detail":{"code","message","checks"?}}` |

## 需补测试
- 第 4 节 §2.4 错误结构统一性回归
- 第 7 节 SEC-AUTH、SQL-EP 全部错误用例

## 行为不变验证
- HTTP 状态码不变（404 还是 404，400 还是 400）
- 前端展示的错误 message 文本不变

## 回滚
- 每 router 独立改造；单 router 出问题可单独 revert

---

# R5 · PolicyEngine 与 guardrail 共享 AST 解析

## 信号
- 同一条 SQL 在 PolicyEngine 和 guardrail 各 parse 一次

## 动机
减少重复解析开销，避免两处对同一 SQL 的理解漂移。

## 不改后果
- 性能浪费（每次执行多一次 sqlglot.parse）
- dialect 处理逻辑两份，易不一致

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | 抽 `engine/sql/parser.py:parse_sql(sql, dialect) -> Expression`（带缓存） |
| 2 | guardrail 已有 `guardrail_parsed_ast`，统一走 parser |
| 3 | PolicyEngine.enforce_query_policy 接受预解析的 AST 而非自己 parse |
| 4 | executor 在调 PolicyEngine 前先 parse，复用给 guardrail |

## 需补测试
- 性能基准：同 SQL 二次执行 parse 次数减少 50%
- 行为测试：PolicyEngine + guardrail 对同 SQL 的判断结果不变

## 行为不变验证
- golden set（第 4 节 §7）全绿

## 风险
- 中等：改动了安全核心路径。必须有完整 guardrail + policy 测试守护才能动手。

---

# R6 · 业务域标签外置到数据库

## 信号
- `_table_tags` 用硬编码中英关键词做业务归类（db_tools.py:464-485）
- 业务方无法自定义

## 动机
隐藏变化点：把易变的业务规则从代码挪到数据。

## 不改后果
- 每加一个业务域都要改代码发版

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | 新增 `domain_tag_rules` 表：(pattern, tag, priority) |
| 2 | 启动时 bootstrap 默认规则（迁移现有硬编码） |
| 3 | `_table_tags` 改为查表；查不到降级到内置 fallback |
| 4 | 提供 API `/datasources/{id}/domain-tags` 管理规则 |

## 需补测试
- 默认规则与现有硬编码行为一致
- 自定义规则生效

## 行为不变验证
- 现有 db.observe 输出的 tags 字段在默认规则下完全一致

---

# R7 · EXPLAIN 按方言拆分统一接口

## 信号
- `executor.explain_sql` 内含 SQLite/MySQL 分支，PG 已抽到 `postgres_explain.py`
- 三份逻辑漂移风险

## 动机
对称结构：每个方言一个 explain 模块。

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | 新建 `engine/sql/dialect/sqlite/explain.py`、`mysql/explain.py` |
| 2 | 定义统一接口 `explain(conn, safe_sql) -> {records, warnings}` |
| 3 | 把 executor.explain_sql 的 SQLite/MySQL 分支迁入 |
| 4 | executor 改为按 dialect 分派（与现有 postgres 路径对齐） |
| 5 | 顺带落地 NFR-SEC-3（SQLite explain 用只读连接） |

## 需补测试
- 现有 EXPLAIN 测试全绿
- 三方言对称：全表扫描、无索引、有索引各一组

## 行为不变验证
- 同 SQL 的 EXPLAIN 输出 records/warnings 字段一致

---

# R8 · 清理魔法数字与重复常量

## 信号
- `response_bytes = 2` 在 executor 和 row_serializer 各出现一次，无注释
- MAX_* 常量散落

## 动机
可读性、单一数据源。

## 小步拆解

| 步骤 | 动作 |
|---|---|
| 1 | row_serializer.py 提取 `JSON_OVERHEAD_BYTES = 2` 并注释「代表 `[` + `]`」 |
| 2 | executor.py 引用同一常量 |
| 3 | 审计所有裸数字：timeout、limit、retry 次数，能提常量的提常量 |

## 需补测试
- 无需新增；现有测试守护

## 行为不变验证
- 数值未变，仅命名

---

## 重构汇总矩阵

| ID | 信号 | 风险 | 工作量 | 优先级 | 守护测试 |
|---|---|---|---|---|---|
| R1 | 过长文件 | 低 | 2 天 | P1 | test_db_tools 全集 |
| R2 | 重复+注入 | 低 | 1 天 | P0 | PREVIEW/WHERE |
| R3 | 重复+安全 | 中 | 1 天 | P0 | REDACT + ROW |
| R4 | 契约不一 | 低 | 1.5 天 | P2 | 错误契约回归 |
| R5 | 重复解析 | 中 | 1 天 | P2 | golden set |
| R6 | 硬编码规则 | 低 | 1 天 | P2 | observe 行为不变 |
| R7 | 结构不对称 | 低 | 1 天 | P1 | EXPLAIN 全集 |
| R8 | magic number | 极低 | 0.5 天 | P2 | 现有测试 |

**P0**：R2、R3（直接修缺陷 D1/D2，必须先于其他重构）
**P1**：R1、R7
**P2**：R4、R5、R6、R8

---

## 重构与缺陷/NFR 对应关系

| 重构 | 解决缺陷 | 落实 NFR |
|---|---|---|
| R1 | — | （可维护性基线） |
| R2 | D1 | NFR-SEC-1 |
| R3 | D2 | NFR-SEC-2 |
| R4 | D7 | NFR-USE-2 |
| R5 | — | NFR-PRF-3 |
| R6 | — | （可维护性） |
| R7 | D3 | NFR-SEC-3 |
| R8 | — | （可读性） |

---

## 执行节奏建议

```
Sprint 1（P0 闭环，1 周）
  ├─ R2 标识符工厂 + 修 D1
  └─ R3 脱敏下沉 + 修 D2

Sprint 2（P1 收口，2 周）
  ├─ R7 EXPLAIN 拆分 + 修 D3
  ├─ R1 db_tools 拆分（开始）
  └─ 缺陷 D4/D5/D6 各自独立 PR

Sprint 3（P2 改善，季度内）
  ├─ R4 错误统一 + 修 D7
  ├─ R5 AST 共享
  ├─ R6 业务标签外置
  └─ R8 magic number 清理
```

每个 Sprint 结束时回归第 4 节集成测试 + 第 7 节 P0 黑盒用例，全绿方可合并主干。

---

## 验收清单（每条重构的 Done 定义）

- [ ] 「小步拆解」每一步都有独立 commit，每步 CI 全绿
- [ ] 「需补测试」列出的测试全部新增并 CI 通过
- [ ] 「行为不变验证」通过（golden set / 输出对比）
- [ ] PR 描述引用对应的缺陷单 ID 与 NFR ID
- [ ] 重构未引入新的 `# type: ignore` / `# noqa`（除非评审通过）
- [ ] 重构后相关模块行覆盖率不低于重构前

---

## 完成情况

**审查日期:** 2026-06-17

### 重构完成状态

| ID | 重构项 | 状态 | 说明 |
|----|--------|------|------|
| R1 | 拆分 db_tools.py | ✅ 已完成 | `engine/tools/db/` 目录：observe/search/inspect/preview/query/remember/_common |
| R2 | SQL builder 统一标识符 | ✅ 已完成 | `engine/sql/builder.py` 实现 `safe_identifier` + `build_select` |
| R3 | 脱敏下沉到 executor | ✅ 已完成 | `engine/policy/sensitivity.py` 提取，executor 集成 |
| R4 | 统一错误响应 Schema | ✅ 已完成 | `engine/schemas/error.py` 定义 ErrorResponse |
| R5 | PolicyEngine AST 共享 | ✅ 已完成 | `engine/sql/parser.py` 统一解析 |
| R6 | 业务域标签外置 | ✅ 已完成 | `domain_tag_rules` 表 + API |
| R7 | EXPLAIN 按方言拆分 | ⚠️ 待实施 | `dialect/` 目录未创建 `explain.py` |
| R8 | 清理魔法数字 | ⚠️ 部分完成 | `row_serializer.py` 有 `JSON_OVERHEAD_BYTES`，但 executor 仍有个别裸数字 |

### 重构与缺陷对应

| 重构 | 解决缺陷 | 状态 |
|------|---------|------|
| R2 | D1 (SQL 注入) | ✅ |
| R3 | D2 (PII 泄露) | ✅ |
| R7 | D3 (SQLite 只读) | ⚠️ 待实施 |

### Sprint 执行情况

| Sprint | 计划 | 状态 |
|--------|------|------|
| Sprint 1 (P0) | R2 + R3 | ✅ 已完成 |
| Sprint 2 (P1) | R7 + R1 + D4/D5/D6 | ⚠️ R1 已完成，R7 待实施，D4/D5/D6 待修复 |
| Sprint 3 (P2) | R4 + R5 + R6 + R8 | ⚠️ R4/R5/R6 已完成，R8 部分完成 |
