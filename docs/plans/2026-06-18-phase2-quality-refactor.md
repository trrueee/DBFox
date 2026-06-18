# Phase 2 Quality Refactor — Architecture Optimization

> 基于第二轮深度质量审查。不做迁移兼容，追求模块最优解。

## Refactor 1: Backup Failure Audit Fix

**问题**: `create_backup()` 失败后更新 `status="failed"` 但 re-raise，API 层 `db.rollback()` 回滚整条审计记录。

**方案**: `create_backup()` 独立 `db.commit()` 失败状态，API 层不再 rollback。

---

## Refactor 2: context_pack.py — Extract Section Builders

**问题**: `build_context_pack()` 210 行单函数组装 13 个 section，圈复杂度 ~92。

**方案**: 每个 section 提取为独立 `_build_*_section(state) -> Section` 函数。
保持 `build_context_pack()` 为编排层（约 30 行），每个 builder 可独立测试。

```
Before:
  build_context_pack(state)           # 210 lines, 13 sections inline

After:
  build_context_pack(state)           # ~30 lines, orchestrates 13 builders
  _build_workspace_section(state)     # ~50 lines
  _build_environment_section(state)   # ~25 lines
  _build_schema_section(state)        # ~25 lines
  _build_semantic_section(state)      # ~20 lines
  _build_sql_section(state)           # ~10 lines
  _build_safety_section(state)        # ~10 lines
  _build_execution_section(state)     # ~15 lines
  _build_result_section(state)        # ~15 lines
  _build_memory_section(state)        # ~5 lines
  _build_runstate_section(state)      # ~20 lines
  _build_skill_section(state)         # ~10 lines
  _build_intent_section(state)        # ~20 lines
  _build_recent_activity_section(state) # ~30 lines
  _build_constraints_section(state)   # ~15 lines
```

外部行为不变。验证：现有 context pack 集成测试通过。

---

## Refactor 3: response_builder.py — Strategy Dispatch

**问题**: `build_response()` ~250 行，混合状态解析、消息组装、artifact 打包、错误处理。

**方案**: 提取 `_build_answer()`, `_build_artifacts()`, `_build_canvas()`, `_build_events()` 为独立函数，
`build_response()` 变为纯编排。

---

## Refactor 4: test_data.py — Decompose generate_smart_test_data

**问题**: ~280 行单函数：FK 解析 + 行生成 + SQL 构造 + 插入。

**方案**: 拆为三段独立函数：
```
_resolve_foreign_keys(db, datasource_id, table) → fk_mappings
_generate_mock_rows(table, row_count, language, fk_mappings) → List[dict]
_insert_test_data_rows(db, datasource_id, table_name, rows) → inserted_count
```

---

## Refactor 5: policy/gate.py — Rule Chain Dispatch

**问题**: `check()` 方法 160 行，顺序检查 8 个条件，if-elif 堆叠。

**方案**: 提取 `_check_tool_exists`, `_check_side_effects`, `_check_tool_group`, `_check_execution_mode`, `_check_validated_sql`, `_check_approval` 为 `_RuleFunc` 类型，`check()` 变为链式调用。

```python
_RuleFunc = Callable[..., PolicyDecision | None]

_RULES: list[_RuleFunc] = [
    _check_tool_exists,
    _check_side_effects,
    _check_escalate_tool,
    _check_tool_group,
    _check_execution_mode,
    _check_validated_sql,
    _check_agent_autonomous,
    _check_requires_approval,
]

def check(self, ...) -> PolicyDecision:
    for rule in _RULES:
        decision = rule(self, ...)
        if decision is not None:
            return decision
    return PolicyDecision(status="allowed", ...)
```

---

## Refactor 6: datasource.py — Connection Strategy Pattern

**问题**: `test_connection()` 377 行，MySQL/PostgreSQL/SQLite 三套逻辑混在一个 if-else 链。

**方案**: 提取 `ConnectionTester` 协议 + `MySQLTester` / `PgTester` / `SQLiteTester`。
`test_connection()` 变为 `_get_tester(dialect).test(ds)`.
