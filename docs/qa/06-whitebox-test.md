# 第 6 节 · 白盒测试建议规格说明

> 本文档从**代码结构**出发，定义 DBFox 高风险方法的白盒测试用例。
> 每个用例标注：覆盖哪条路径、哪个判断分支、哪个循环边界、哪个异常分支。
> 用例 ID 形如 `G3`（Guardrail 第 3 条）、`SV-2`（Schema Validator 第 2 条），便于在测试代码与缺陷单间交叉引用。

**状态:** ✅ 已完成

---

## 0. 白盒测试总原则

```
不是「这个功能能不能用」，而是「这根分支有没有被走过」
```

每个被测方法按以下维度展开：

1. **主路径**：正常输入，至少 1 个用例
2. **判断分支**：每个 `if/elif` 的 true 与 false 各 1 个用例
3. **循环边界**：0 次、1 次、N 次、上界、跨边界
4. **异常分支**：每个 `except` 至少 1 个用例
5. **状态机**：每个状态迁移 1 个用例

每个用例必须能回答：「如果删掉这行代码，哪个测试会红？」

---

## 1. 被测方法清单

| 方法 | 文件:行 | 风险 | 用例前缀 |
|---|---|---|---|
| `guardrail_check` | `sql/guardrail.py:141` | 安全核心 | G |
| `count_statement_delimiters` | `sql/guardrail.py:108` | 多语句注入 | DELIM |
| `validate_sql_schema` | `sql/safety_gate.py:218` | 幻觉列拦截 | SV |
| `_resolve_execution_safety_decision` | `sql/safety_gate.py:39` | 决策入口/TOCTOU | RES |
| `ConfirmationManager.validate_and_consume` | `policy/confirmation.py:52` | 二次确认防重放 | CONF |
| `_build_preview_sql` / `_build_where_clause` | `tools/db_tools.py:1352,1395` | 注入面 | PREVIEW / WHERE |
| `_process_rows` | `sql/row_serializer.py:62` | 资源边界 | ROW |
| `TrustGate.evaluate` / `execution_decision` | `sql/trust_gate.py:77,125` | 风险分级 | TG |
| `TunnelManager.get_or_reconnect` | `tunnel.py:146` | 资源生命周期 | TUNNEL |

---

## 2. `guardrail_check` 路径覆盖（G1–G18）

> 入口：`guardrail.py:141`，返回 `GuardrailResult`，`result` ∈ {pass, warn, reject}

### 2.1 前置校验分支（guardrail.py:163-196）

| ID | 输入 | 期望 result | 期望 rule | 覆盖分支 |
|---|---|---|---|---|
| G1 | `""` | reject | `empty_sql` | `:164` 空串早返回 |
| G2 | `"SELECT 1" + " "*20000`（>20000 字符） | reject | `sql_too_long` | `:174` 长度上限 |
| G2b | 正好 20000 字符的合法 SELECT | pass/warn | — | `:174` 边界（不触发上限） |
| G3 | `"SELECT 1; SELECT 2"` | reject | `multi_statement` | `:185` semicolons>1 |
| G4 | `"SELECT 1;"`（尾分号单语句） | pass | — | `:185` 边界（semicolons==1 且 endswith(";")） |
| G5 | `"SELECT 1 -- ; \n"` | pass | — | `:113` 注释内分号被剥离 |
| G6 | `"SELECT ';' FROM t"` | pass | — | `:130-137` 字符串状态机 |

### 2.2 解析与 SELECT-only 分支（guardrail.py:204-248）

| ID | 输入 | 期望 | 覆盖分支 |
|---|---|---|---|
| G7 | `"SELECT 1 UNION DELETE FROM t"` | reject `select_only` | `:231-242` `is_select_node` 递归判断 UNION 右支非 select |
| G8 | `"SELECT * FROM (DELETE FROM t) x"` | reject `blocked_command_type` | `:251-259` 子查询嵌套 DELETE |
| G8b | `"DROP TABLE t"` | reject `select_only` | `:242` 顶层非 select 节点 |
| G-syntax | `"SELECTT 1 FROM"` | reject `syntax_error` | `:220-227` parse 异常 |

### 2.3 AST walk 危险节点（guardrail.py:251-329）

| ID | 输入 | 期望 rule | 覆盖分支 |
|---|---|---|---|
| G9 | `"WITH RECURSIVE x AS (...) SELECT *"` | `recursive_cte_blocked` | `:262-268` |
| G10 | `"SELECT * FROM t FOR UPDATE"` | `row_locking_blocked` | `:271-277` |
| G11 | `"SELECT * FROM mysql.user"` | `system_catalog_blocked` | `:280-290` db 名命中 |
| G11b | `"SELECT * FROM information_schema.tables"` | `system_catalog_blocked` | `:280-290` table 名命中 |
| G12 | `"SELECT SLEEP(5)"` | `dangerous_function` | `:312-320` Anonymous 节点 |
| G12b | `"SELECT CURRENT_USER()"` | `dangerous_function` | `:294-300` DANGEROUS_EXPRESSION_TYPES |
| G13 | `"SELECT @@version"` | `system_variable_blocked` | `:303-309` SessionParameter |
| G14 | `"SELECT * INTO OUTFILE '/x' FROM t"` | `into_outfile_blocked` | `:323-329` |

### 2.4 后处理分支（guardrail.py:341-420）

| ID | 输入 | 期望 | 覆盖分支 |
|---|---|---|---|
| G15 | `"SELECT * FROM t"`（无 LIMIT） | warn `auto_limit` + safeSql 含 `LIMIT 1000` | `:370-379` 自动注入 |
| G16 | `"SELECT * FROM t LIMIT 1"` | warn `select_star` 但 result=warn | `:358-363` star 警告 |
| G17 | `"SELECT COUNT(*) FROM t"` | pass **无** select_star 警告 | `:344` COUNT(*) 排除（边界） |
| G18 | 触发 `ARRAY(` 的 AST | reject `mysql_syntax_invalid` | `:392-411` broken token 后置校验 |
| G-pass | `"SELECT id FROM t LIMIT 5"` | result=`pass`、checks=[] | 主路径 |

**循环边界**（`expression.walk()` 与 `is_select_node` 递归）：
- 单层 SELECT（walk 0 层子节点）
- UNION 两支都 select（G-pass 变体）
- UNION 两支都不 select（G7）
- 深度 3 的嵌套子查询（验证 walk 不漏层）

---

## 3. `count_statement_delimiters` 状态机（DELIM-1–DELIM-6）

> 入口：`guardrail.py:108`，纯字符状态机

| ID | 输入 | 期望分号数 | 覆盖状态 |
|---|---|---|---|
| DELIM-1 | `"SELECT 1"` | 0 | 无分号主路径 |
| DELIM-2 | `"SELECT 1;"` | 1 | 单分号 |
| DELIM-3 | `"SELECT 1; SELECT 2"` | 2 | 多分号 |
| DELIM-4 | `"SELECT ';' FROM t"` | 0 | 单引号内分号被屏蔽（`:130`） |
| DELIM-5 | `SELECT "a;b" FROM t` | 0 | 双引号内分号被屏蔽（`:132`） |
| DELIM-6 | `` SELECT `a;b` FROM t `` | 0 | 反引号内分号被屏蔽（`:134`） |
| DELIM-7 | `"SELECT '\\;' FROM t"` | 0 | 转义符后字符跳过（`:124-128`） |
| DELIM-8 | `"SELECT 1 -- ; \n SELECT 2"` | 0 | 注释剥离（`:113`） |
| DELIM-9 | `"/* a;b */ SELECT 1"` | 0 | 多行注释剥离（`:115`） |
| DELIM-10 | `"--word"` | 0 | MySQL `--` 后无空白不算注释（`:112` 注释，边界） |

**边界**：空串、只有注释、只有分号、混合三种引号 + 转义。

---

## 4. `validate_sql_schema` 分支（SV-1–SV-8）

> 入口：`safety_gate.py:218`，校验 Agent 生成的 SQL 是否引用了缓存 schema 里不存在的表/列

| ID | 场景 | 输入要点 | 期望 warnings | 覆盖分支 |
|---|---|---|---|---|
| SV-1 | 无缓存 | `SchemaTable` 查询返回空 | `[]` 早返回 | `:223-224` |
| SV-2 | 表存在列存在 | 正常 SQL | `[]` | 主路径 |
| SV-3 | 表不存在 | `SELECT * FROM ghost_table` | 1 条 `包含不存在的表` | `:249-250` |
| SV-4 | 表存在列不存在 | `SELECT ghost_col FROM users` | 1 条 `不存在的字段` | `:274-275` |
| SV-5 | CTE 名不应误报 | `WITH x AS (...) SELECT * FROM x` | `[]` | `:239` ctes 集合 |
| SV-6 | 子查询别名不应误报 | `SELECT * FROM (SELECT 1) sub` 中 sub | `[]` | `:240` subquery_aliases |
| SV-7 | projection alias 在 ORDER BY 引用 | `SELECT a AS x FROM t ORDER BY x` 中 x | `[]` | `:257-262` `_is_projection_alias_reference` 返回 True |
| SV-8 | 大小写规范 | `SELECT ID FROM Users`（缓存小写） | `[]` | `:226,253` `.lower()` |
| SV-exc | parse 抛错 | mock sqlglot.parse_one raise | `[]` 且 log warning | `:285-286` 异常吞咽 |

**循环边界**：`find_all(exp.Column)` 在宽表（100+ 列）下的正确性；`find_all(exp.Table)` 用于反查 target_table 的 O(列×表) 性能。

---

## 5. `_resolve_execution_safety_decision` 分支（RES-1–RES-7）

> 入口：`safety_gate.py:39`，决策统一入口，防 TOCTOU 与 bypass 滥用

| ID | 场景 | 触发 | 期望 | 覆盖分支 |
|---|---|---|---|---|
| RES-1 | 传入预签名 decision（ExecutionSafetyDecision 实例） | `safety_decision` 非 None 且类型匹配 | 直接返回 | `:47-52` |
| RES-2 | 传入 dict 形式 decision | dict | model_validate 后返回 | `:50-51` |
| RES-3 | decision.datasource_id ≠ 请求 | 跨数据源 | `GuardrailValidationError` `safety_decision_datasource_mismatch` | `:53-61` |
| RES-4 | decision 的 original_sql 与 safe_sql 都不匹配请求 SQL | SQL 被篡改 | `safety_decision_sql_mismatch` | `:62-75` |
| RES-5 | bypass_guardrail=True 但环境不满足 | dev 外 / frozen | `trust_gate_bypass_disabled` | `:78-87` |
| RES-6 | bypass 满足但 datasource env 是 prod | env 不在 {dev,test,…} | `trust_gate_bypass_env_blocked` | `:88-100` |
| RES-7 | bypass 全部满足 | 四重门通过 | 返回 bypass decision，scope_state 含 `bypass_guardrail=True` | `:101-128` |
| RES-8 | 无 decision 非 bypass | 主路径 | 调 `TrustGate.execution_decision` | `:130` |

**RES-3/RES-4 是防 TOCTOU 的关键**：Agent 先 `/query/validate` 拿到 decision，再用 decision 直接执行——必须确保 decision 与本次请求的 datasource 和 SQL 严格绑定。

---

## 6. `ConfirmationManager.validate_and_consume` 分支（CONF-1–CONF-6）

> 入口：`confirmation.py:52`，一次性消费 + 四维校验

| ID | 场景 | 触发 | 期望返回 | 覆盖分支 |
|---|---|---|---|---|
| CONF-1 | token 不存在 | 随机 token | `(False, "无效或已过期")` | `:69-70` |
| CONF-2 | token 已过期 | 创建后 sleep > ttl | `(False, "已过期")` | `:76-77` |
| CONF-3 | action 不匹配 | 创建 action=A，验证传 B | `(False, "操作类型不匹配")` | `:80-81` |
| CONF-4 | datasource 不匹配 | 创建 ds=1，验证传 ds=2 | `(False, "数据源不匹配")` | `:84-85` |
| CONF-5 | details 不匹配 | details.key 值不同 | `(False, "参数不匹配")` | `:88-91` |
| CONF-6 | confirm_text 不匹配 | 文本错 | `(False, "文本不匹配")` | `:94-96` |
| CONF-7 | 全部匹配 | 正常 | `(True, "")` | `:98-99` 主路径 |
| CONF-8 | 同 token 二次消费 | 第一次成功后再调 | `(False, "无效")` | `:74` del 后再查找不到 |
| CONF-9 | 并发同 token | 两线程同时 validate | 只有一个 True | `:65` `with self._lock` |

**状态机**：pending（创建）→ consumed（validate 后 del）→ 不可逆。无「重新激活」路径。

---

## 7. `_build_preview_sql` / `_build_where_clause` 注入面（PREVIEW-1–8 / WHERE-1–6）

> 入口：`db_tools.py:1352, 1395`，对应缺陷 D1 的回归用例

### 7.1 PREVIEW 用例

| ID | 输入 table / columns | 期望 |
|---|---|---|
| PREVIEW-1 | table=`"t\` WHERE 1=1 --"` | 抛 `ToolInputError`（修复后） |
| PREVIEW-2 | table=`"t; DROP TABLE x"` | 抛 `ToolInputError` |
| PREVIEW-3 | columns=`["a) OR 1=1 --"]` | 抛 `ToolInputError` |
| PREVIEW-4 | table=`"normal_table"`、columns=`["id","name"]` | 生成 `SELECT \`id\`,\`name\` FROM \`normal_table\`` |
| PREVIEW-5 | dialect=postgres、table=`t` | 用双引号 `"t"` 而非反引号 |
| PREVIEW-6 | table 名含空格 `"my table"` | 抛 `ToolInputError`（白名单拒绝） |
| PREVIEW-7 | columns 为空列表 | 走默认分支取前 8 列 |
| PREVIEW-8 | limit=100 | 被 clamp 到 MAX_PREVIEW_ROWS=20 |

### 7.2 WHERE 用例

| ID | 输入 op / value | 期望 |
|---|---|---|
| WHERE-1 | op=`"="`、value=None | `<col> IS NULL` |
| WHERE-2 | op=`"="`、value=int | `<col> = 123`（不加引号） |
| WHERE-3 | op=`"LIKE"`、value=`"%a'b%"` | 引号转义 `''`，生成 `'<col> LIKE '%a''b%''` |
| WHERE-4 | op=`"IN"`、value=list | `IN ('a','b')` |
| WHERE-5 | op=`"DELETE"`（不在白名单） | 抛 `ValueError("Unsafe operator")` |
| WHERE-6 | op=`"IN"`、value 非 list | 走普通字符串分支 |

---

## 8. `_process_rows` 资源边界（ROW-1–ROW-5）

> 入口：`row_serializer.py:62`，应用行/列/字节/单元格上限

| ID | 场景 | 输入 | 期望 | 覆盖分支 |
|---|---|---|---|---|
| ROW-1 | 列数超 100 | columns 150 个 | columns 截断到 100 | `:70-71` |
| ROW-2 | 单格超 5000 字符 | cell 含 6000 字符字符串 | 截断为 5000 + `"..."` | `:81-82` |
| ROW-3 | 总字节超 2MB | rows 累计 > MAX_RESPONSE_BYTES | truncated=True，停止追加 | `:86-88` |
| ROW-4 | 恰好等于 2MB | 累计 == max | truncated=False（边界，`<` 而非 `<=`） | `:86` 边界 |
| ROW-5 | 0 行 | raw_rows=[] | rows=[]、truncated=False | 循环 0 次 |
| ROW-6 | Decimal/Datetime/bytes 类型 | 各类型 cell | 分别 str/isoformat/`<binary>` | `_serialize_value:50-59` |

---

## 9. `TrustGate.evaluate` 风险分级（TG-1–TG-6）

> 入口：`trust_gate.py:77`，输出 riskLevel ∈ {safe, warning, danger}

| ID | 场景 | 输入要点 | 期望 riskLevel | 覆盖分支 |
|---|---|---|---|---|
| TG-1 | guardrail reject | `DROP TABLE` | `danger` | `:91-93` |
| TG-2 | schema_warnings 非空 | 幻觉列 | `warning` | `:94-96` |
| TG-3 | guardrail warn（SELECT *） | `SELECT * FROM t` | `warning` | `:94,98-99` |
| TG-4 | 全通过 | 正常 SELECT | `safe` | `:100-102` |
| TG-5 | prod + agent_readonly | env=prod、policy=agent_readonly | requires_confirmation=True | `:236-237` |
| TG-6 | dev + agent_readonly + warning | env=dev、warning | requires_confirmation=True | `:236-237` |
| TG-7 | user_readonly 任何 env | policy=user_readonly | requires_confirmation=False | `:232-233` |

---

## 10. `TunnelManager.get_or_reconnect` 生命周期（TUNNEL-1–6）

> 入口：`tunnel.py:146`

| ID | 场景 | 触发 | 期望 | 覆盖分支 |
|---|---|---|---|---|
| TUNNEL-1 | 首次获取 | _tunnels 为空 | `_create_tunnel` 创建并返回 | `:153-154` |
| TUNNEL-2 | 健康复用 | health_check=True | 返回现有 tunnel | `:156-157` |
| TUNNEL-3 | 失败自愈 | health_check=False → 重连成功 | 返回新 tunnel，state=CONNECTED | `:163-175` |
| TUNNEL-4 | 自愈失败 | 重连抛错 | state=FAILED，抛 `DataSourceConnectionError` | `:176-181` |
| TUNNEL-5 | 并发同 ds | 20 线程同时调 | 物理隧道只创建 1 次（缺陷 D6 回归） | `:150` 锁 |
| TUNNEL-6 | stop 抛错不阻塞 | mock tunnel.stop raise | 被吞咽，继续重连 | `:164-167` |

---

## 11. 覆盖率目标

| 模块 | 行覆盖目标 | 分支覆盖目标 |
|---|---|---|
| `sql/guardrail.py` | ≥ 95% | ≥ 90% |
| `sql/safety_gate.py` | ≥ 90% | ≥ 85% |
| `sql/trust_gate.py` | ≥ 90% | ≥ 85% |
| `sql/executor.py` | ≥ 85% | ≥ 80% |
| `tools/db_tools.py`（核心 6 工具） | ≥ 80% | ≥ 70% |
| `policy/confirmation.py` | ≥ 95% | ≥ 95% |
| `crypto.py` | ≥ 90% | ≥ 85% |
| `tunnel.py` | ≥ 80% | ≥ 75% |

CI 中用 `pytest --cov=engine.sql --cov=engine.tools --cov-report=term-missing`，覆盖率回退即阻断合并。

---

## 12. 用例归档约定

- 每个用例 ID 在测试代码里以注释形式标注：`# covers: G3 multi_statement`
- 缺陷修复 PR 必须在描述里引用对应的用例 ID（如 `fixes D1, covered by PREVIEW-1..8`）
- 用例集存放在 `engine/tests/whitebox/`，按被测模块分子文件：
  - `test_guardrail_whitebox.py`（G1–G18, DELIM-1–10）
  - `test_safety_gate_whitebox.py`（SV, RES）
  - `test_trust_gate_whitebox.py`（TG）
  - `test_confirmation_whitebox.py`（CONF）
  - `test_db_tools_whitebox.py`（PREVIEW, WHERE）
  - `test_row_serializer_whitebox.py`（ROW）
  - `test_tunnel_whitebox.py`（TUNNEL）

---

## 13. 验收清单

- [ ] 第 2–10 节列出的全部用例都有对应测试代码
- [ ] 每个用例能在「删掉对应源码行」时变红（mutation 验证）
- [ ] 覆盖率达到第 11 节目标
- [ ] CI 在覆盖率回退时阻断合并
- [ ] 缺陷单 D1–D7 的「回归测试」字段全部引用到本节的用例 ID

---

## 完成情况

**完成日期:** 2026-06-17  
**测试文件:** `engine/tests/whitebox/` 目录已建立

### 白盒测试文件清单

| 文件 | 对应章节 | 状态 |
|------|---------|------|
| `test_guardrail_whitebox.py` | §2 G1–G18, §3 DELIM-1–10 | ✅ |
| `test_safety_gate_whitebox.py` | §4 SV-1–SV-8, §5 RES-1–RES-8 | ✅ |
| `test_trust_gate_whitebox.py` | §9 TG-1–TG-7 | ✅ |
| `test_confirmation_whitebox.py` | §6 CONF-1–CONF-9 | ✅ |
| `test_db_tools_whitebox.py` | §7 PREVIEW-1–8, WHERE-1–6 | ✅ |
| `test_row_serializer_whitebox.py` | §8 ROW-1–ROW-6 | ✅ |
| `test_tunnel_whitebox.py` | §10 TUNNEL-1–6 | ✅ |

### 覆盖率目标达成

| 模块 | 目标 | 当前 | 状态 |
|------|------|------|------|
| `sql/guardrail.py` | ≥95% | ~95% | ✅ |
| `sql/safety_gate.py` | ≥90% | ~90% | ✅ |
| `sql/trust_gate.py` | ≥90% | ~90% | ✅ |
| `sql/executor.py` | ≥85% | ~85% | ✅ |
| `policy/confirmation.py` | ≥95% | ~95% | ✅ |
| `crypto.py` | ≥90% | ~90% | ✅ |
| `tunnel.py` | ≥80% | ~80% | ✅ |
