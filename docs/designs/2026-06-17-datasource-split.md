# Design Doc: executor.py / datasource.py 模块拆分

**日期:** 2026-06-17  
**状态:** ✅ 已完成  
**关联:** `docs/软件重构和测试.md` — H1/H2/Phase 3

## 目标

将 `engine/sql/executor.py`（1011 行）和 `engine/datasource.py`（585 行）按职责边界拆分为更小的模块，每个模块承担单一职责，降低认知负荷，方便后续测试和维护。

**不改外部行为**：所有现有 API 返回结构、异常类型、导入路径保持不变。

---

## executor.py 拆分（1011 → 8 文件）

### 当前结构

```
executor.py (1011行)
├── 常量 + ProcessedRows 类型
├── guardrail_bypass_allowed()
├── get_postgres_pool / get_mysql_pool / _ping_mysql_connection
├── _fetch_and_serialize / _serialize_value / _process_rows
├── _execute_on_{sqlite,postgres,mysql}_profiled × 3
├── _resolve_execution_safety_decision / _decision_checks_*
├── _run_approved_query / execute_query / explain_sql
└── validate_sql_schema / _is_projection_alias_reference
```

### 目标结构

```
engine/sql/
├── executor.py          (~200行)   execute_query, explain_sql, _run_approved_query
├── pool_manager.py      (~120行)   get_postgres_pool, get_mysql_pool, _ping_mysql_connection
├── row_serializer.py    (~100行)   _fetch_and_serialize, _serialize_value, _process_rows, 常量, ProcessedRows
├── safety_gate.py       (~320行)   guardrail_bypass_allowed, _resolve_execution_safety_decision,
│                                   _decision_checks_for_history, _decision_checks_for_error,
│                                   _decision_block_message, validate_sql_schema, _is_projection_alias_reference
├── dialect/
│   ├── __init__.py
│   ├── sqlite.py        (~60行)    _execute_on_sqlite_profiled, _execute_on_sqlite
│   ├── postgres.py      (~60行)    _execute_on_postgres_profiled
│   └── mysql.py         (~55行)    _execute_on_mysql_profiled, _execute_on_mysql
├── guardrail.py         (不变)
├── trust_gate.py        (不变)
├── pool_registry.py     (不变)
├── test_executor.py     (不变)
├── dry_run.py           (不变)
└── postgres_explain.py  (不变)
```

### 各模块接口

**pool_manager.py**
```
导出: get_postgres_pool(), get_mysql_pool(), _ping_mysql_connection()
依赖: pool_registry.py
```

**row_serializer.py**
```
导出: _fetch_and_serialize(), _serialize_value(), _process_rows(),
      MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS, MAX_RESPONSE_BYTES,
      QUERY_TIMEOUT_MS, ProcessedRows
依赖: 纯 stdlib (json, decimal, datetime, time)
```

**safety_gate.py**
```
导出: guardrail_bypass_allowed(), validate_sql_schema()
内部: _resolve_execution_safety_decision(), _decision_checks_for_history(),
      _decision_checks_for_error(), _decision_block_message(),
      _is_projection_alias_reference()
依赖: trust_gate.py, guardrail.py, errors.py, models.py, query_registry.py
```

**dialect/sqlite.py**
```
导出: _execute_on_sqlite_profiled(), _execute_on_sqlite()
依赖: row_serializer.py, query_registry.py, errors.py
```

**dialect/postgres.py**
```
导出: _execute_on_postgres_profiled()
依赖: pool_manager.py, row_serializer.py, query_registry.py, errors.py
```

**dialect/mysql.py**
```
导出: _execute_on_mysql_profiled(), _execute_on_mysql()
依赖: pool_manager.py, row_serializer.py, query_registry.py, errors.py
```

**executor.py（拆分后）**
```
导出: execute_query(), explain_sql(), _run_approved_query()
依赖: 上述所有内部模块 + datasource.py + policy/redactor.py
```

### 向后兼容

`executor.py` 文件头部通过 `from .pool_manager import ...` 等语句 re-export 所有原符号，13 个外部消费点无需改动 import 路径。

### 依赖关系图（无循环）

```
executor.py ─────────────┐
  ├── safety_gate.py ────┤── trust_gate.py ─── guardrail.py
  ├── dialect/sqlite.py ─┤── row_serializer.py
  ├── dialect/postgres.py ┤── pool_manager.py ─── pool_registry.py
  ├── dialect/mysql.py ──┘
  └── datasource.py ──────── tunnel.py
```

---

## datasource.py 拆分（585 → 2 文件）

### 目标结构

```
engine/
├── tunnel.py           (~230行)   TunnelState, TunnelInstance, TunnelManager,
│                                  _create_physical_tunnel_forwarder,
│                                  TUNNEL_MANAGER 全局单例,
│                                  close_active_tunnel(), close_all_tunnels(),
│                                  get_or_create_tunnel_for_dict(), open_temporary_tunnel()
├── datasource.py       (~355行)   datasource_connection_dict(),
│                                  get_mysql_connection_params(), get_postgres_connection_params(),
│                                  build_mysql_ssl_params(), build_postgres_ssl_params(),
│                                  test_connection(),
│                                  _normalized_optional_path(), _require_existing_sqlite_file()
```

### 各模块接口

**tunnel.py**
```
导出: TUNNEL_MANAGER, close_active_tunnel(), close_all_tunnels(),
      get_or_create_tunnel_for_dict(), open_temporary_tunnel()
内部: TunnelState, TunnelInstance, TunnelManager, _create_physical_tunnel_forwarder()
依赖: 纯 stdlib (threading, socket, logging), sshtunnel, crypto.py, errors.py
```

**datasource.py**
```
导出: datasource_connection_dict(), get_mysql_connection_params(),
      get_postgres_connection_params(), build_mysql_ssl_params(),
      build_postgres_ssl_params(), test_connection()
内部: _normalized_optional_path(), _require_existing_sqlite_file()
依赖: tunnel.py, crypto.py, errors.py
```

### 向后兼容

`datasource.py` 内部 import `tunnel.py` 的公开符号后 re-export，17 个外部消费点无需改动。

---

## 实施步骤

### Step 1: `engine/sql/pool_manager.py`
- 从 executor.py 提取 `get_postgres_pool`, `get_mysql_pool`, `_ping_mysql_connection`
- executor.py 添加 `from .pool_manager import ...` 保持导入兼容

### Step 2: `engine/sql/row_serializer.py`
- 提取 `_fetch_and_serialize`, `_serialize_value`, `_process_rows` + 所有常量 + `ProcessedRows`
- executor.py 添加 re-export

### Step 3: `engine/sql/safety_gate.py`
- 提取 `guardrail_bypass_allowed`, `_resolve_execution_safety_decision`, 所有 `_decision_*`, `validate_sql_schema`, `_is_projection_alias_reference`

### Step 4: `engine/sql/dialect/` 包
- 创建 `dialect/` 包
- `sqlite.py`: `_execute_on_sqlite_profiled`, `_execute_on_sqlite`
- `postgres.py`: `_execute_on_postgres_profiled`
- `mysql.py`: `_execute_on_mysql_profiled`, `_execute_on_mysql`

### Step 5: `engine/tunnel.py`
- 从 datasource.py 提取所有 Tunnel 相关代码
- datasource.py 添加 re-export

### Step 6: 验证
- 运行 `pytest engine/tests/` 全量测试
- 运行 `python -c "from engine.sql.executor import execute_query"` 确认导入兼容

---

## 测试策略

- **现有测试不变**：`engine/tests/test_executor.py` 和 `engine/tests/test_datasource_safety.py` 的 import 路径兼容，无需修改
- **拆分不引入新测试**：纯重构，外部行为零变化
- **回归验证**：`pytest engine/tests/test_executor.py engine/tests/test_datasource_safety.py engine/tests/test_trust_gate.py engine/tests/test_datasource_ssl.py engine/tests/test_datasource_ssl_e2e.py`

---

## 风险与约束

| 风险 | 缓解措施 |
|------|---------|
| 循环导入 | safety_gate.py 导入 trust_gate.py，trust_gate.py 通过构造函数回调接收 validate_sql_schema，无循环 |
| 测试中直接 import 私有符号 | 通过 executor.py re-export 保持原路径可用 |
| tunnel.py 全局单例 TUNNEL_MANAGER | 保持模块级单例不变，engine/main.py 的 close_all_tunnels 调用路径不变 |
| LF/CRLF 警告 | 无影响 |

---

## 完成情况

**完成日期:** 2026-06-17  
**测试状态:** 491 passed, 2 skipped

### 实施步骤完成度

| 步骤 | 状态 | 说明 |
|------|------|------|
| Step 1: `engine/sql/pool_manager.py` | ✅ | `3c644f00` refactor: extract pool_manager.py from executor.py |
| Step 2: `engine/sql/row_serializer.py` | ✅ | `4665db24` refactor: extract row_serializer.py from executor.py |
| Step 3: `engine/sql/safety_gate.py` | ✅ | `ad774a76` refactor: extract safety_gate.py from executor.py |
| Step 4: `engine/sql/dialect/` 包 | ✅ | `add37166` / `1759f2d1` / `5b5b7a29` |
| Step 5: `engine/tunnel.py` | ✅ | `140eb0ab` refactor: extract tunnel.py from datasource.py |
| Step 6: 验证 | ✅ | 491 tests pass, re-exports verified |

### 创建文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `engine/sql/pool_manager.py` | 91 | get_postgres_pool, get_mysql_pool, _ping_mysql_connection |
| `engine/sql/row_serializer.py` | 96 | _fetch_and_serialize, _serialize_value, _process_rows, 常量 |
| `engine/sql/safety_gate.py` | 298 | guardrail_bypass_allowed, validate_sql_schema, _resolve_execution_safety_decision |
| `engine/sql/dialect/__init__.py` | 1 | dialect package |
| `engine/sql/dialect/sqlite.py` | - | _execute_on_sqlite_profiled, _execute_on_sqlite |
| `engine/sql/dialect/postgres.py` | - | _execute_on_postgres_profiled |
| `engine/sql/dialect/mysql.py` | - | _execute_on_mysql_profiled, _execute_on_mysql |
| `engine/tunnel.py` | 231 | TunnelManager, TUNNEL_MANAGER 全局单例, tunnel 管理 |

### 向后兼容验证

- `executor.py` 通过 `from .pool_manager import ...` 等语句 re-export 所有原符号
- `datasource.py` 通过 `from engine.tunnel import TUNNEL_MANAGER, ...` re-export
- 7 个外部消费点 import 路径无需改动
- `test_executor.py` 中 `from engine.sql.executor import _serialize_value, _process_rows, MAX_ROWS` 正常工作
