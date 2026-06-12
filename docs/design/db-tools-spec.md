# DataBox Agent 数据库工具设计说明

## 从零开始。不是对现有工具的修改，是新工具面的完整定义。

---

## 核心原则

```
Agent 可以主动，工具必须保守
```

- Agent 决定用什么工具、什么顺序、探索到什么程度
- 工具内部强制安全边界（只读、超时、脱敏、行数截断）
- 工具返回结构化信息，Agent 自己判断下一步

---

## 工具分层

```
┌──────────────┐
│ 离线（毫秒）  │  数据来源：本地 Database Index
│              │  连接数据库时一次性构建，AI 辅助整理
├──────────────┤
│ db.observe   │  ← 全局数据库地图
│ db.search    │  ← 关键词搜索表/字段/别名
│ db.remember  │  ← 写入业务记忆（写操作，需确认）
└──────────────┘

┌──────────────┐
│ 在线（秒级）  │  数据来源：真实数据库连接
├──────────────┤
│ db.inspect   │  ← 实时查看表结构、列信息、外键、索引
│ db.preview   │  ← 安全预览真实数据行
│ db.query     │  ← 执行 Agent 写的只读 SQL
└──────────────┘
```

---

## 离线 vs 在线

| | 离线（observe / search） | 在线（inspect / preview / query） |
|---|---|---|
| 数据源 | 本地索引 | 真实数据库 |
| 速度 | 毫秒 | 秒 |
| 准确性 | 可能有延迟 | 始终最新 |
| Agent 何时用 | 找方向、搜候选 | 确认结构、验证数据、执行查询 |

---

# 工具 1：db.observe

## 是什么

给 Agent 的"数据库可视化视角"。返回当前连接数据库的全局地图。

类比：
- 文件系统的 `tree` 命令
- IDE 的侧边栏文件树
- DBeaver 连上数据库后看到的表列表

## 输入

```json
{
  "mode": "overview"
}
```

也可以缩小范围：

```json
{
  "mode": "schema",
  "schema_name": "public"
}
```

```json
{
  "mode": "tables",
  "table_names": ["users", "orders", "channels"]
}
```

`mode` 取值：
- `"overview"` — 默认，返回整个数据库的地图（表列表 + 分组 + 统计）
- `"schema"` — 返回指定 schema 下的表
- `"tables"` — 返回指定几张表的摘要

## 输出 (mode = "overview")

```json
{
  "dialect": "mysql",
  "version": "8.0.35",
  "environment": "prod",
  "table_count": 47,
  "view_count": 5,
  "total_estimated_rows": 45000000,
  "schemas": [
    {
      "name": "public",
      "table_count": 42,
      "tables": [
        {
          "name": "users",
          "type": "table",
          "columns": 23,
          "comment": "用户主表",
          "tags": ["core", "user"],
          "row_estimate": 1200000,
          "query_hit_count": 42,
          "last_queried_at": "2026-06-10"
        },
        {
          "name": "orders",
          "type": "table",
          "columns": 18,
          "comment": "订单表",
          "tags": ["core", "transaction"],
          "row_estimate": 8500000,
          "query_hit_count": 67,
          "last_queried_at": "2026-06-12"
        }
      ]
    }
  ],
  "domains": [
    {
      "label": "用户",
      "tables": ["users", "user_profiles", "user_logs", "user_tags"],
      "confidence": 0.9
    },
    {
      "label": "交易",
      "tables": ["orders", "order_items", "payments", "refunds"],
      "confidence": 0.85
    }
  ]
}
```

每个 table 包含：
- `name` — 表名
- `type` — table / view
- `columns` — 列数
- `comment` — 表注释（来自数据库 + AI 整理）
- `tags` — 业务标签（AI 整理阶段打的）
- `row_estimate` — 估算行数
- `query_hit_count` — 历史查询命中次数
- `last_queried_at` — 最近被查询的时间

`domains` 是 AI 整理阶段推断的业务域分组：
- `label` — 域名
- `tables` — 该域包含的表
- `confidence` — AI 对分组的置信度

## 输出 (mode = "tables")

```json
{
  "tables": [
    {
      "name": "users",
      "primary_key": "id",
      "columns": 23,
      "comment": "用户主表",
      "tags": ["core", "user"],
      "row_estimate": 1200000,
      "connected_tables": ["orders", "payments", "user_logs", "user_tags"]
    }
  ]
}
```

`connected_tables` 是通过外键关联的表列表。

## 什么时候用

- Agent 第一次处理用户问题，不知道有哪些表 → `db.observe("overview")`
- 已经定位到几张表，想快速了解它们 → `db.observe("tables", ["users", "orders"])`

---

# 工具 2：db.search

## 是什么

在离线 Database Index 中搜索表和字段。搜索范围包括：表名、字段名、表注释、字段注释、AI 整理的别名、业务标签、历史查询记录。

类比：代码库的 `grep` / symbol search。

## 输入

```json
{
  "query": "退款 渠道",
  "limit": 10
}
```

- `query` — 自然语言关键词，支持中文和英文
- `limit` — 返回的候选数量上限，默认 10

可选过滤：

```json
{
  "query": "退款",
  "limit": 10,
  "search_scope": "columns",
  "preferred_domain": "交易"
}
```

- `search_scope` — `"all"` | `"tables"` | `"columns"`
- `preferred_domain` — 优先返回某个业务域的结果

## 输出

```json
{
  "query": "退款 渠道",
  "results": [
    {
      "type": "table",
      "table_name": "refunds",
      "score": 0.92,
      "reasons": [
        "table_name_match: refund (exact)",
        "table_comment_match: 退款记录表",
        "tag_match: 交易"
      ],
      "columns": ["id", "order_id", "amount", "channel_id", "status", "created_at"],
      "short_comment": "退款记录表"
    },
    {
      "type": "table",
      "table_name": "payments",
      "score": 0.78,
      "reasons": [
        "column_match: status='refunded'",
        "column_comment_match: payment_status 包含 '退款'",
        "alias_match: payments ≈ 支付/退款"
      ],
      "columns": ["id", "order_id", "amount", "channel_id", "status"],
      "short_comment": "支付流水表"
    },
    {
      "type": "column",
      "table_name": "orders",
      "column_name": "refund_status",
      "score": 0.65,
      "reasons": [
        "column_name_match: refund_status",
        "column_comment_match: '退款状态'"
      ]
    },
    {
      "type": "table",
      "table_name": "channels",
      "score": 0.81,
      "reasons": [
        "table_name_match: channel (exact)",
        "table_comment_match: '渠道主表'",
        "alias_match: channel ≈ 渠道/来源"
      ],
      "columns": ["id", "name", "type", "status"],
      "short_comment": "渠道主表"
    }
  ],
  "total_matches": 8
}
```

每个结果包含：
- `type` — table 或 column
- `score` — 综合匹配分数 (0-1)
- `reasons` — 命中的具体原因列表，Agent 据此判断可信度
- 如果是表：返回列名列表（前 8 列）和简短注释
- 如果是字段：返回所在表名

## 搜索策略（后端实现）

执行顺序（取并集，按 score 排序）：
1. 表名精确匹配 — score +0.9
2. 表名部分匹配 — score +0.7
3. 字段名精确匹配 — score +0.8
4. 字段名部分匹配 — score +0.6
5. 表/字段注释匹配 — score +0.5
6. AI 别名匹配 — score +0.7
7. 业务标签匹配 — score +0.4
8. 历史查询记录匹配 — score +0.3（被频繁查过的表提升）
9. 外键扩散 — 高 score 表关联的表 +0.2

## 什么时候用

- Agent 拿到用户问题，需要找相关表和字段
- `db.observe` 返回 47 张表太多，Agent 用 search 缩小范围
- 某个表结构不够清楚，search 确认字段含义

---

# 工具 3：db.inspect

## 是什么

**连接真实数据库**，实时查看某张表或某个字段的完整结构信息。

类比：
- coding agent 的 `cat file` 读文件内容
- DBeaver 里点开一张表看到的 DDL / Columns / Foreign Keys / Indexes 标签页

## 输入

```json
{
  "target": "users"
}
```

```json
{
  "target": "users.channel_id"
}
```

- `target` — 表名 或 `表名.字段名`

## 输出（查表）

```json
{
  "object_type": "table",
  "name": "users",
  "type": "table",
  "comment": "用户主表",
  "row_estimate": 1200000,
  "columns": [
    {
      "name": "id",
      "type": "bigint",
      "nullable": false,
      "default": null,
      "primary_key": true,
      "foreign_key": null,
      "comment": "用户唯一ID"
    },
    {
      "name": "channel_id",
      "type": "int",
      "nullable": false,
      "default": null,
      "primary_key": false,
      "foreign_key": {
        "table": "channels",
        "column": "id"
      },
      "comment": "用户注册渠道ID"
    },
    {
      "name": "created_at",
      "type": "datetime",
      "nullable": false,
      "default": null,
      "primary_key": false,
      "foreign_key": null,
      "comment": "注册时间"
    }
  ],
  "foreign_keys_out": [
    {
      "column": "channel_id",
      "references": {
        "table": "channels",
        "column": "id"
      }
    }
  ],
  "foreign_keys_in": [
    {
      "table": "orders",
      "column": "user_id",
      "references": {
        "column": "id"
      }
    },
    {
      "table": "payments",
      "column": "user_id",
      "references": {
        "column": "id"
      }
    },
    {
      "table": "user_logs",
      "column": "user_id",
      "references": {
        "column": "id"
      }
    }
  ],
  "indexes": [
    {
      "name": "PRIMARY",
      "columns": ["id"],
      "unique": true
    },
    {
      "name": "idx_users_channel",
      "columns": ["channel_id"],
      "unique": false
    },
    {
      "name": "idx_users_created_at",
      "columns": ["created_at"],
      "unique": false
    }
  ]
}
```

## 输出（查字段）

```json
{
  "object_type": "column",
  "table": "users",
  "name": "channel_id",
  "type": "int",
  "nullable": false,
  "default": null,
  "primary_key": false,
  "foreign_key": {
    "table": "channels",
    "column": "id"
  },
  "comment": "用户注册渠道ID"
}
```

字段模式下不返回 `foreign_keys_in` 和 `indexes`（那是表级信息）。

## 实现要点

- 直连真实数据库，执行系统内省查询，不能查离线索引
- 后端根据 dialect（MySQL / PostgreSQL / SQLite / DuckDB）选择对应的内省 SQL 模板
- 内省 SQL 是硬编码的系统模板，不是 AI 生成的，不经过 guardrail
- 表名使用参数化绑定，防注入
- 超时 10 秒
- 表不存在返回明确的 `{"status": "failed", "error": "Table 'xxx' not found"}`

## Dialect 内省 SQL 模板（各写一套）

### MySQL

#### 列信息
```sql
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    c.COLUMN_COMMENT,
    c.COLUMN_KEY = 'PRI' AS is_primary_key,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM information_schema.COLUMNS c
LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu
    ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA
    AND c.TABLE_NAME = kcu.TABLE_NAME
    AND c.COLUMN_NAME = kcu.COLUMN_NAME
    AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
WHERE c.TABLE_SCHEMA = DATABASE()
  AND c.TABLE_NAME = ?
ORDER BY c.ORDINAL_POSITION
```

#### 反向外键（谁引用了我）
```sql
SELECT
    kcu.TABLE_NAME,
    kcu.COLUMN_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE kcu
WHERE kcu.TABLE_SCHEMA = DATABASE()
  AND kcu.REFERENCED_TABLE_NAME = ?
```

#### 索引
```sql
SHOW INDEX FROM `{table_name}`
```

#### 行估算
```sql
SELECT TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = ?
```

### PostgreSQL

#### 列信息
```sql
SELECT
    c.column_name,
    c.data_type,
    c.is_nullable,
    c.column_default,
    pg_catalog.col_description(
        (c.table_schema||'.'||c.table_name)::regclass::oid,
        c.ordinal_position
    ) AS column_comment,
    CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_primary_key
FROM information_schema.columns c
LEFT JOIN (
    SELECT ku.table_schema, ku.table_name, ku.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage ku
        ON tc.constraint_name = ku.constraint_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
) pk
    ON c.table_schema = pk.table_schema
    AND c.table_name = pk.table_name
    AND c.column_name = pk.column_name
WHERE c.table_schema = ?
  AND c.table_name = ?
ORDER BY c.ordinal_position
```

#### 外键（含反向）
```sql
-- 正向
SELECT
    kcu.column_name,
    ccu.table_name AS ref_table,
    ccu.column_name AS ref_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = ?
  AND tc.table_name = ?

-- 反向
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.column_name AS ref_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = ?
  AND ccu.table_name = ?
```

#### 索引
```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = ?
  AND tablename = ?
```

#### 行估算
```sql
SELECT n_live_tup
FROM pg_stat_user_tables
WHERE schemaname = ?
  AND relname = ?
```

### SQLite

#### 列信息
```sql
PRAGMA table_info('{table_name}')
```
返回：cid, name, type, notnull, dflt_value, pk

#### 外键
```sql
PRAGMA foreign_key_list('{table_name}')
```
返回：id, seq, table, from, to, on_update, on_delete, match

#### 索引
```sql
PRAGMA index_list('{table_name}')
```
然后对每个索引执行：
```sql
PRAGMA index_info('{index_name}')
```

#### 行估算
```sql
SELECT COUNT(*) FROM "{table_name}"
```

#### 反向外键（SQLite 没有系统表直接支持）
遍历 sqlite_master 中所有表的建表语句，或遍历所有表执行 `PRAGMA foreign_key_list`，筛选 `table = 目标表名` 的。

## 什么时候用

- `db.search` 返回了 3 个候选表，Agent 调 inspect 确认每个的结构
- 看到 `users` 有 `channel_id` 外键，想知道 channels 长什么样 → `db.inspect("channels")`
- 某个字段不确定含义 → `db.inspect("users.channel_id")`

---

# 工具 4：db.preview

## 是什么

**连接真实数据库**，安全地预览指定表的少量真实数据行。

类比：
- coding agent 看日志文件的前几行
- DBeaver 打开表后看到的 Data 标签页的前 10 行

## 输入

```json
{
  "table": "users",
  "columns": ["id", "name", "channel_id", "created_at"],
  "limit": 10,
  "where": "created_at >= '2026-06-01'",
  "order_by": "created_at DESC"
}
```

- `table` — 必填，表名
- `columns` — 可选，要看的列。不填则返回全部列
- `limit` — 可选，返回行数。默认 5，最大 20
- `where` — 可选，筛选条件。后端必须绑参数，不接受原始字符串拼接
- `order_by` — 可选，排序

## 输出

```json
{
  "table": "users",
  "columns": ["id", "name", "channel_id", "created_at"],
  "total_columns": 23,
  "returned_rows": 5,
  "total_rows": 5,
  "rows": [
    {
      "id": 1001,
      "name": "张三",
      "channel_id": 3,
      "created_at": "2026-06-10 14:22:00"
    },
    {
      "id": 1002,
      "name": "李四",
      "channel_id": 1,
      "created_at": "2026-06-09 08:15:00"
    }
  ],
  "truncated": false,
  "column_summaries": {
    "id": {
      "distinct_in_sample": 5,
      "null_count": 0
    },
    "channel_id": {
      "distinct_in_sample": 3,
      "null_count": 0,
      "sample_values": [3, 1, 2, 3, 1]
    }
  }
}
```

- `total_columns` — 表的全部列数
- `returned_rows` — 实际返回的行数
- `truncated` — 如果表没有其他列了则为 false
- `column_summaries` — 采样列的简单统计

## 安全约束（后端强制执行）

- **只读** — 始终 SELECT，不可写
- **limit 上限** — 最大 20 行，超过截断
- **敏感列脱敏** — 如果离线索引标记了敏感列（身份证、手机号、密码），自动打码
- **超时** — 10 秒
- **表名参数化绑定** — 防注入
- **列名白名单校验** — 请求的列名必须真实存在
- **WHERE 子句参数化** — 不接受原始 SQL 拼接
- **审计记录** — 每次 preview 记录到 QueryHistory

## 实现要点

- 后端根据 dialect + table + columns + where + order_by 构造 `SELECT ... FROM t WHERE ... ORDER BY ... LIMIT N`
- `columns` 和 `table` 参数化绑定
- `where` 和 `order_by` 需要用 sqlglot 解析后重写为参数化形式，或要求 Agent 传结构化条件而非原始 SQL 片段

**关于 where：** 推荐第一期支持简单的结构化条件：

```json
{
  "where": {
    "column": "created_at",
    "op": ">=",
    "value": "2026-06-01"
  }
}
```

不支持复杂 AND/OR 组合。Agent 真正需要复杂筛选时应该直接写 SQL 走 `db.query`。

## 什么时候用

- `inspect` 看完了结构，不确定 status 字段实际存什么值 → `db.preview` 看几行
- 想确认两个表之间 JOIN 的关联字段值是否匹配 → preview 两张表各几行
- 不确定 `created_at` 的日期格式 → preview 看真实数据

---

# 工具 5：db.query

## 是什么

**连接真实数据库**，执行 Agent 自己写的只读 SQL，返回结构化的查询结果。

类比：
- coding agent 的 `node script.js` / `python -c "..."` —— 执行自己写的代码
- DBeaver 的 SQL 编辑器中执行 SELECT

## 输入

```json
{
  "sql": "SELECT c.name, COUNT(*) as cnt FROM users u JOIN channels c ON c.id = u.channel_id WHERE u.created_at >= '2026-05-01' GROUP BY c.name ORDER BY cnt DESC LIMIT 20"
}
```

唯一的参数：`sql` — 一条完整的 SELECT 语句。

## 输出

```json
{
  "columns": ["name", "cnt"],
  "column_types": ["varchar", "bigint"],
  "returned_rows": 3,
  "truncated": false,
  "rows": [
    ["Google", 12450],
    ["Apple", 9800],
    ["官网", 7200]
  ],
  "execution_time_ms": 234,
  "explain_plan": "..."  // 可选，EXPLAIN 输出
}
```

- `columns` — 列名列表
- `column_types` — 列类型
- `returned_rows` — 实际返回行数
- `truncated` — 是否因超过上限被截断
- `rows` — 数据行（二维数组）
- `execution_time_ms` — 执行耗时
- `explain_plan` — 可选，执行计划文本

## 安全约束（后端强制，不可绕过）

### 第一层：SQL 解析校验

解析 SQL，拒绝：
- 多语句（`;` 分割）
- 非 SELECT 语句（INSERT / UPDATE / DELETE / DROP / CREATE / ALTER / TRUNCATE / MERGE）
- 系统库访问（information_schema / pg_catalog / sys / performance_schema）
- 写文件（INTO OUTFILE / DUMPFILE）
- 锁表（FOR UPDATE / FOR SHARE）
- 递归 CTE（WITH RECURSIVE）
- 危险函数（sleep / benchmark / load_file / pg_read_file / ...）
- 系统变量（@@version / @@hostname / ...）

### 第二层：强制限制
- 无 LIMIT 时自动追加 `LIMIT 1000`
- 超时 30 秒
- 结果最大 1000 行、100 列
- 单格最大 5000 字符
- 响应总大小最大 2MB

### 第三层：执行环境
- 只读事务（`SET TRANSACTION READ ONLY`）
- 敏感列脱敏（查询结果中的身份证、手机号自动打码）
- 审计记录（SQL + 耗时 + 结果行数写入 QueryHistory）

### 第四层：必要时确认
- prod 环境 + 大表扫描（EXPLAIN 显示全表扫描）→ 弹确认
- 危险函数虽然被拦截，但会记录告警

## 实现要点

- 后端拿到 SQL → sqlglot 解析 AST → guardrail 逐条检查 → TrustGate 评估风险等级
- prod 环境 + warning 风险 → 插入 approval 节点等用户确认
- 通过后 → 连接池取连接 → 执行 → 序列化结果 → 审计记录
- 执行失败 → 返回明确的错误信息（截断、脱敏过的），Agent 自己决定修 SQL 还是换方法

## 什么时候用

- 探索完成，Agent 确信知道怎么写 SQL → `db.query(sql)`
- 结果不对 → Agent 修改 SQL → 再 `db.query`（不是自动 repair，是 Agent 自己改）

---

# 工具 6：db.remember

## 是什么

Agent 在探索过程中发现值得记住的语义信息，提议写入离线 Database Index。

写入的内容举例：
- "users.channel_id 的 FK 指向 channels.id，含义是用户注册渠道"
- "payments 表的 status 列包含 'pending', 'paid', 'refunded', 'cancelled'"
- "orders 和 payments 通过 orders.id = payments.order_id 关联"
- "用户问 'GMV' 通常指 orders 表 pricing_type='paid' 的 total_amount 之和"

类比：
- coding agent 在代码库里加注释 / README
- CI 的 cache 机制

## 输入

```json
{
  "type": "table_alias",
  "target": "users",
  "key": "aliases",
  "value": ["用户表", "会员表"],
  "evidence": "表名 users，表注释 '用户主表'，包含 name/email/phone 等个人信息字段"
}
```

```json
{
  "type": "column_alias",
  "target": "payments.status",
  "key": "aliases",
  "value": ["支付状态", "交易状态"],
  "evidence": "字段注释 'payment_status'，实际数据包含 pending/paid/refunded/cancelled"
}
```

```json
{
  "type": "column_values",
  "target": "payments.status",
  "key": "observed_values",
  "value": ["pending", "paid", "refunded", "cancelled"],
  "evidence": "db.preview 返回的 20 行中 status 列的全部去重值"
}
```

```json
{
  "type": "join_path",
  "target": "orders ↔ payments",
  "key": "join_condition",
  "value": {
    "left_table": "orders",
    "left_column": "id",
    "right_table": "payments",
    "right_column": "order_id",
    "join_type": "LEFT JOIN",
    "description": "订单的支付记录，一个订单可能有多笔支付"
  },
  "evidence": "db.inspect 显示 payments.order_id 是 FK → orders.id"
}
```

```json
{
  "type": "business_definition",
  "target": "GMV",
  "key": "definition",
  "value": {
    "sql": "SELECT SUM(total_amount) FROM orders WHERE status IN ('paid', 'shipped', 'delivered') AND pricing_type = 'paid'",
    "description": "已支付订单的 total_amount 总和，不含已取消和已退款"
  },
  "evidence": "用户询问'本月GMV'时，Agent 探索后确认了这个定义"
}
```

参数：
- `type` — 记忆类型：`table_alias` | `column_alias` | `column_values` | `join_path` | `business_definition`
- `target` — 记忆绑定的对象（表名 / 字段名 / 表对 / 业务术语）
- `key` — 记忆的键（aliases / observed_values / join_condition / definition）
- `value` — 记忆的值
- `evidence` — 推断依据。Agent 必须说明它为什么认为这是对的

## 输出

```json
{
  "status": "remembered",
  "id": "mem_abc123",
  "stored_at": "2026-06-12T10:30:00Z",
  "type": "column_values",
  "target": "payments.status",
  "will_affect_future_search": true
}
```

或需要确认：

```json
{
  "status": "pending_confirmation",
  "id": "mem_abc123",
  "reason": "prod 环境，修改业务定义需要用户确认",
  "message": "Agent 提议将 'GMV' 定义为已支付订单金额之和，是否接受？"
}
```

## 何时需要用户确认

| 环境 | 类型 | 需要确认 |
|---|---|---|
| dev | table_alias, column_alias, column_values | 否 |
| dev | join_path, business_definition | 是 |
| staging | 全部类型 | 否 |
| prod | table_alias, column_alias, column_values | 否 |
| prod | join_path, business_definition | 是 |

## 实现要点

- 写入本地 Database Index（SQLite / JSON 文件）
- 写入后立即对 `db.search` 可见（下次搜索命中）
- 与 AI 整理阶段（连接时）写的记忆合并，人工 > Agent > AI 推断
- 提供 `db.remember_delete` 或 `db.remember_list` 用于管理

## 什么时候用

- Agent 发现 `inspect` 的注释和实际数据对不上，更新别名
- Agent 在 `preview` 里看到了字段的全部去重值，记下来以后 search 能命中
- 用户用了一个业务术语（"GMV"、"次日留存"），Agent 探索后确认了 SQL 定义，记下来

---

# 工具总览

| 工具 | 数据源 | 速度 | 做什么 | 类比 |
|---|---|---|---|---|
| `db.observe` | 离线索引 | 毫秒 | 看数据库全局地图 | `tree` / 文件树 |
| `db.search` | 离线索引 | 毫秒 | 关键词搜表/字段/别名 | `grep` / symbol search |
| `db.inspect` | **真实库** | 秒 | 看表结构/列/外键/索引 | `cat file` / DDL 预览 |
| `db.preview` | **真实库** | 秒 | 看少量真实数据行 | `head file` / Data 标签页 |
| `db.query` | **真实库** | 秒 | 执行 Agent 写的 SELECT | `python script.py` |
| `db.remember` | 离线索引 | 毫秒 | 记住发现的语义 | 写注释 / cache |

---

# Agent 典型工作流

```text
用户："上个季度各渠道的退款金额和退款率"

1. db.search("退款 渠道 金额")
   → refunds (0.92), payments (0.78), channels (0.81)
   → Agent 注意到 refunds 和 channels 都高分

2. db.inspect("refunds")
   → columns: id, order_id, amount, channel_id, status, created_at
   → FK_OUT: channel_id → channels.id
   → FK_IN: (none)
   → Agent 确认：refunds 有金额、渠道外键、创建时间

3. db.inspect("channels")
   → columns: id, name, type
   → FK_IN: users.channel_id, refunds.channel_id, orders.channel_id
   → Agent 确认：channels.name 是渠道名

4. db.preview("refunds", columns=["status", "amount"], limit=10)
   → 数据确认 status 列有 'refunded', 'partial_refund'
   → Agent 确认退款状态的含义

5. db.query("
     SELECT c.name AS channel,
            SUM(r.amount) AS refund_amount,
            COUNT(DISTINCT r.order_id) AS refund_order_count
     FROM refunds r
     JOIN channels c ON c.id = r.channel_id
     WHERE r.created_at >= '2026-01-01'
       AND r.created_at < '2026-04-01'
       AND r.status IN ('refunded', 'partial_refund')
     GROUP BY c.name
     ORDER BY refund_amount DESC
   ")
   → 返回 5 行结果

6. db.query("
     SELECT c.name AS channel,
            COUNT(DISTINCT o.id) AS total_orders
     FROM orders o
     JOIN channels c ON c.id = o.channel_id
     WHERE o.created_at >= '2026-01-01'
       AND o.created_at < '2026-04-01'
     GROUP BY c.name
   ")
   → 拿到各渠道总订单数，Agent 自己算退款率

7. db.remember("join_path", "refunds ↔ channels",
     evidence="db.inspect 确认 refunds.channel_id → channels.id")

8. 组织最终回答给用户
```

**Agent 始终保持主动权**——它决定搜什么、看什么、查什么、记住什么。工具只提供能力和安全边界。
