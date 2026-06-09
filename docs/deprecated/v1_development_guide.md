下面是整理后的 **DataBox 第一次开发文档 / V1 开发指导文档**。
方向按你最终确认的来：**像 Navicat 一样的桌面客户端，不依赖服务器部署，用户本机直接连接远程 MySQL，再增加 AI 问数能力。**

---

# DataBox V1 开发指导文档

## AI 问数版数据库客户端

## 1. 产品定位

DataBox 是一个面向运营、业务人员、数据分析人员的 **AI 数据库客户端**。

它的基础形态类似 Navicat：

```text
用户安装桌面客户端
↓
配置远程 MySQL 数据库连接
↓
客户端直接连接数据库
↓
浏览表结构、执行 SQL、查看结果
```

在此基础上，DataBox 增加 AI 能力：

```text
自然语言提问
↓
AI 根据数据库 Schema 生成 SQL
↓
系统安全审核 SQL
↓
用户确认执行
↓
返回表格和图表
```

一句话定位：

```text
DataBox = AI 问数版 Navicat
```

V1 目标不是做完整 BI 系统，也不是做云端 SaaS，而是先做一个**安装即用、可远程连接 MySQL、安全可控的 AI 数据库客户端**。

---

# 2. 第一版核心原则

V1 的原则是：

```text
不依赖服务器
不做云端数据库连接
不上传数据库密码
不上传真实查询结果
客户端直接连接远程 MySQL
数据库连接信息本地加密保存
SQL 执行发生在用户电脑
AI 只看 Schema 和用户问题
AI 生成 SQL 后必须人工确认
所有 SQL 执行前必须经过 Guardrail 审核
```

这和 Navicat 的连接逻辑一致：

```text
DataBox Desktop
    ↓ TCP / SSH Tunnel，后续
Remote MySQL
```

---

# 3. 为什么第一版做客户端

因为这个产品涉及：

```text
数据库账号
数据库密码
业务数据
SQL 执行权限
内网数据库
远程数据库
```

如果做成纯 Web SaaS，会遇到：

```text
用户不愿意把数据库密码交给云端
客户数据库可能只允许内网访问
云端服务器未必能访问客户 MySQL
安全合规成本更高
```

所以第一版用客户端更合理：

```text
用户电脑能连数据库，DataBox 就能连
```

DataBox 不需要自己的服务器，也不需要客户部署后端。

---

# 4. 技术路线

## 4.1 桌面端

推荐：

```text
Tauri
React
Vite
TypeScript
Tailwind CSS
shadcn/ui
```

原因：

```text
比 Electron 更轻
适合桌面客户端
可以跨平台打包
UI 开发效率高
可以拉起本地 Python Engine
```

---

## 4.2 本地引擎

使用：

```text
Python Local Engine
FastAPI
SQLite
SQLAlchemy
PyMySQL
sqlglot
Pydantic
cryptography
httpx
```

原因：

```text
Python 更适合 AI 问数
Python 生态适合后续统计分析、报表、洞察
FastAPI 开发快
SQLAlchemy / PyMySQL 连接 MySQL 成熟
sqlglot 可做 SQL AST 安全检查
```

---

## 4.3 前端核心库

```text
Monaco Editor      SQL 编辑器
TanStack Table     查询结果表格
ECharts            简单图表
React Flow         ER 图 / 表关系展示
```

---

## 4.4 本地元数据库

使用：

```text
SQLite
```

SQLite 存：

```text
数据源配置
Schema 缓存
查询历史
Guardrail 结果
LLM 调用日志
本地设置
```

不要让用户本地安装 MySQL。

---

# 5. 总体架构

```text
DataBox Desktop Client
├── Tauri 桌面壳
├── React 前端 UI
│   ├── 数据源页面
│   ├── Schema 页面
│   ├── SQL / AI 问数页面
│   ├── SQL 编辑器
│   ├── 查询结果表格
│   └── 图表展示
│
└── Python Local Engine
    ├── FastAPI 本地接口
    ├── SQLite 本地元数据
    ├── MySQL 远程连接
    ├── Schema 同步
    ├── SQL Guardrail
    ├── SQL Executor
    ├── Text-to-SQL
    ├── 查询历史
    └── LLM 调用
```

运行方式：

```text
用户打开 DataBox
↓
Tauri 启动 Python Local Engine
↓
Python Engine 监听 127.0.0.1 随机端口
↓
Tauri 前端调用本地 API
↓
Python Engine 连接远程 MySQL
```

---

# 6. 版本里程碑

## V1.0：数据库客户端底座，无 AI

先做一个安全可用的小型 Navicat。

必须实现：

```text
桌面客户端启动
Python Local Engine 启动
SQLite 本地元数据
添加 MySQL 数据源
测试远程连接
本地加密保存连接信息
同步 Schema
浏览表和字段
SQL 编辑器
SQL Guardrail
SQL 安全执行
查询结果表格
查询历史
```

V1.0 不做：

```text
自然语言生成 SQL
自动报表
复杂 Dashboard
统计分析
洞察归因
多 Agent
向量库
云端同步
多用户权限
```

---

## V1.1：AI 问数

在 V1.0 稳定后增加 AI。

新增：

```text
自然语言输入
Schema 检索
LLM 生成 SQL
SQL 展示到编辑器
Guardrail 审核
用户确认执行
简单图表展示
Golden SQL 测试集
LLM 调用日志
```

重要规则：

```text
AI 只生成 SQL
AI 不直接执行 SQL
生成后必须人工确认
LLM 不接收真实查询结果
LLM 只接收 Schema 和用户问题
```

---

## V1.2：轻量报表

后续再做：

```text
保存常用查询
保存图表卡片
CSV 导出
手动组装简单看板
```

---

# 7. 第一版目录结构

```text
databox/
├── desktop/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── DataSourcesPage.tsx
│   │   │   ├── SchemaPage.tsx
│   │   │   └── QueryPage.tsx
│   │   ├── components/
│   │   │   ├── SqlEditor.tsx
│   │   │   ├── ResultTable.tsx
│   │   │   ├── GuardrailPanel.tsx
│   │   │   ├── SchemaTree.tsx
│   │   │   └── ChartPanel.tsx
│   │   └── lib/
│   │       └── api.ts
│   │
│   └── src-tauri/
│       ├── tauri.conf.json
│       └── sidecar/
│
└── engine/
    ├── main.py
    ├── api.py
    ├── config.py
    ├── db.py
    ├── models.py
    ├── datasource.py
    ├── schema_sync.py
    ├── guardrail.py
    ├── executor.py
    ├── ai.py
    ├── crypto.py
    └── errors.py
```

原则：

```text
文件不要过多
但也不要把所有逻辑塞进一个文件
每个模块职责清楚
第一版以可维护的小核心为目标
```

---

# 8. Python Engine 模块职责

## 8.1 `main.py`

职责：

```text
启动 FastAPI
初始化配置
初始化 SQLite
注册 API 路由
启动本地服务
```

---

## 8.2 `api.py`

只放本地接口。

接口包括：

```text
POST /api/v1/datasources/test
POST /api/v1/datasources
GET  /api/v1/datasources
DELETE /api/v1/datasources/{id}
POST /api/v1/datasources/{id}/sync

GET /api/v1/schema/tables
GET /api/v1/schema/tables/{table_id}/columns
GET /api/v1/schema/er-diagram

POST /api/v1/query/validate
POST /api/v1/query/execute
GET  /api/v1/query/history
POST /api/v1/query/generate
```

`/query/generate` 属于 V1.1。

---

## 8.3 `datasource.py`

负责：

```text
测试 MySQL 连接
检测只读权限
保存数据源
解密连接信息
创建 MySQL Engine
删除数据源
```

---

## 8.4 `schema_sync.py`

负责：

```text
同步表
同步字段
同步主键
同步外键
读取表列表
读取字段列表
构造 ER 图数据
```

同步流程三阶段：

```text
第一阶段：同步所有表
第二阶段：同步所有字段和主键
第三阶段：同步外键关系
```

---

## 8.5 `guardrail.py`

负责 SQL 安全审核。

原则：

```text
纯代码实现
不依赖 LLM
基于 sqlglot AST
执行前必须再次检查
```

---

## 8.6 `executor.py`

负责：

```text
执行前再次 Guardrail
只执行 safe_sql
设置查询超时
限制返回行数
限制响应大小
序列化结果
写入查询历史
```

---

## 8.7 `ai.py`

V1.1 使用。

负责：

```text
读取 Schema
检索相关表字段
构造 Prompt
调用 LLM
提取 SQL
记录 LLM 调用日志
返回 SQL 和 Guardrail 结果
```

---

## 8.8 `crypto.py`

负责：

```text
AES-256-GCM 加密
AES-256-GCM 解密
nonce 管理
错误脱敏
```

---

## 8.9 `db.py`

负责：

```text
SQLite 初始化
Session 管理
本地表创建
轻量 migration
```

---

# 9. 本地 SQLite 表设计

## 9.1 `data_sources`

```sql
CREATE TABLE data_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    db_type TEXT NOT NULL DEFAULT 'mysql',

    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 3306,
    database_name TEXT NOT NULL,
    username TEXT NOT NULL,

    password_ciphertext TEXT NOT NULL,
    password_nonce TEXT NOT NULL,
    password_key_version TEXT NOT NULL DEFAULT 'v1',

    connection_mode TEXT NOT NULL DEFAULT 'direct',

    status TEXT NOT NULL DEFAULT 'active',

    last_test_at TEXT,
    last_test_status TEXT,
    last_test_error TEXT,

    last_sync_at TEXT,
    last_sync_status TEXT,
    last_sync_error TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

## 9.2 `schema_tables`

```sql
CREATE TABLE schema_tables (
    id TEXT PRIMARY KEY,
    data_source_id TEXT NOT NULL,

    table_schema TEXT NOT NULL,
    table_name TEXT NOT NULL,
    table_comment TEXT,
    table_type TEXT,
    row_count_estimate INTEGER,
    engine_name TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(data_source_id, table_schema, table_name),
    FOREIGN KEY(data_source_id) REFERENCES data_sources(id) ON DELETE CASCADE
);
```

---

## 9.3 `schema_columns`

```sql
CREATE TABLE schema_columns (
    id TEXT PRIMARY KEY,
    table_id TEXT NOT NULL,

    column_name TEXT NOT NULL,
    data_type TEXT,
    column_type TEXT,
    is_nullable INTEGER,
    column_default TEXT,
    column_comment TEXT,

    is_primary_key INTEGER NOT NULL DEFAULT 0,
    is_foreign_key INTEGER NOT NULL DEFAULT 0,

    foreign_table_id TEXT,
    foreign_column_id TEXT,

    ordinal_position INTEGER,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(table_id, column_name),
    FOREIGN KEY(table_id) REFERENCES schema_tables(id) ON DELETE CASCADE
);
```

---

## 9.4 `query_history`

```sql
CREATE TABLE query_history (
    id TEXT PRIMARY KEY,

    data_source_id TEXT NOT NULL,

    question TEXT,

    submitted_sql TEXT,
    generated_sql TEXT,
    safe_sql TEXT,
    executed_sql TEXT,

    guardrail_result TEXT NOT NULL,
    guardrail_checks TEXT,

    execution_status TEXT,
    execution_time_ms INTEGER,
    rows_returned INTEGER,
    columns_returned INTEGER,

    error_message TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY(data_source_id) REFERENCES data_sources(id) ON DELETE CASCADE
);
```

---

## 9.5 `llm_logs`

```sql
CREATE TABLE llm_logs (
    id TEXT PRIMARY KEY,

    request_type TEXT NOT NULL,

    prompt_hash TEXT,
    prompt_text TEXT,
    response_text TEXT,

    model_name TEXT,
    latency_ms INTEGER,
    status TEXT,
    error_message TEXT,

    created_at TEXT NOT NULL
);
```

默认：

```text
不保存 prompt_text
不保存 response_text
只保存 hash、模型、耗时、状态
```

开发模式可以通过配置开启。

---

# 10. 数据源连接设计

## 10.1 支持连接方式

V1 支持：

```text
Direct MySQL
```

即：

```text
DataBox 客户端
    ↓ TCP
远程 MySQL
```

V1.2 后支持：

```text
SSH Tunnel
```

即：

```text
DataBox 客户端
    ↓ SSH
跳板机
    ↓
内网 MySQL
```

---

## 10.2 测试连接

接口：

```text
POST /api/v1/datasources/test
```

请求：

```json
{
  "host": "127.0.0.1",
  "port": 3306,
  "database_name": "shop",
  "username": "readonly_user",
  "password": "******"
}
```

响应：

```json
{
  "ok": true,
  "serverVersion": "8.0.35",
  "readonly": true,
  "tablesCount": 26,
  "warnings": [],
  "message": "连接成功"
}
```

测试内容：

```text
能否连接
数据库是否存在
账号是否可读
账号是否存在高危写权限
是否能读取 information_schema
表数量
MySQL 版本
```

如果账号存在写权限，要提示：

```text
当前账号存在写入权限，建议使用只读账号。
```

V1 可以允许保存，但查询执行必须经过 Guardrail。

---

# 11. Schema 同步设计

同步内容：

```text
表名
表注释
表类型
字段名
字段类型
字段注释
是否可空
默认值
主键
外键
行数估算
```

实现方式：

```text
SQLAlchemy Inspector
+
MySQL information_schema 补充表注释和字段注释
```

同步流程：

```text
用户点击同步
↓
读取所有表
↓
写入 schema_tables
↓
读取所有字段和主键
↓
写入 schema_columns
↓
读取外键
↓
回填 foreign_table_id / foreign_column_id
↓
更新 data_sources.last_sync_at
```

同步失败：

```text
保存 last_sync_status = failed
保存 last_sync_error
前端展示错误信息
```

---

# 12. SQL Guardrail 设计

Guardrail 是安全核心。

## 12.1 原则

```text
只允许 SELECT
不允许多语句
不允许 DDL
不允许 DML
不允许危险函数
不允许系统库访问
不允许文件读写
自动补 LIMIT
SELECT * 给警告
执行前必须二次校验
```

---

## 12.2 必须拦截

```text
DROP
DELETE
UPDATE
INSERT
ALTER
CREATE
TRUNCATE
REPLACE
CALL
LOAD
GRANT
REVOKE
LOCK
UNLOCK
SET
```

危险函数：

```text
SLEEP
BENCHMARK
LOAD_FILE
DATABASE
USER
CURRENT_USER
VERSION
```

系统库：

```text
information_schema
mysql
performance_schema
sys
```

危险语法：

```text
SELECT INTO OUTFILE
SELECT INTO DUMPFILE
多语句 SQL
超长 SQL
```

---

## 12.3 返回结构

```json
{
  "result": "warn",
  "originalSql": "SELECT * FROM orders",
  "safeSql": "SELECT * FROM orders LIMIT 1000",
  "checks": [
    {
      "rule": "select_star",
      "level": "warn",
      "message": "建议不要使用 SELECT *"
    },
    {
      "rule": "no_limit",
      "level": "warn",
      "message": "已自动添加 LIMIT 1000"
    }
  ],
  "message": "需确认后执行"
}
```

---

# 13. SQL 执行设计

执行流程：

```text
前端提交 SQL
↓
后端 guardrail_check
↓
如果 reject，拒绝执行
↓
如果 pass / warn，返回 safe_sql
↓
用户确认
↓
执行接口再次 guardrail_check
↓
只执行 safe_sql
↓
返回结果
↓
写 query_history
```

默认限制：

```text
max_rows = 1000
max_columns = 100
max_cell_chars = 5000
max_response_bytes = 5MB
timeout = 10s
max_sql_length = 20000
```

结果序列化：

```text
Decimal → string
datetime → ISO string
date → ISO string
bytes → "<binary>"
None → null
JSON → 原样
```

---

# 14. AI 问数设计，V1.1

## 14.1 基本流程

```text
用户输入自然语言问题
↓
读取本地 Schema
↓
匹配相关表和字段
↓
构造 Prompt
↓
调用 LLM
↓
提取 SQL
↓
Guardrail 审核
↓
返回 SQL 到编辑器
↓
用户确认执行
```

---

## 14.2 Schema 检索

V1.1 先不用向量库。

检索方式：

```text
匹配表名
匹配字段名
匹配表注释
匹配字段注释
```

后续可升级：

```text
embedding
向量库
语义检索
指标层
```

---

## 14.3 Prompt 模板

```text
你是一个 MySQL SQL 专家。

请根据用户问题和可用表结构，生成一条安全的 SELECT 查询。

规则：
1. 只输出 SQL，不要解释。
2. 只能生成 SELECT 查询。
3. 不允许 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE。
4. 必须使用 LIMIT，默认 LIMIT 100。
5. 如果需要聚合，必须正确使用 GROUP BY。
6. 日期过滤优先使用用户问题中的时间范围。
7. 如果无法确定字段，请选择最相关字段，不要编造不存在的字段。
8. SQL 方言为 MySQL。

可用表结构：
{{schema_context}}

用户问题：
{{question}}

SQL：
```

---

## 14.4 LLM API Key

V1 推荐：

```text
用户配置自己的模型 API Key
```

这样不需要服务器。

支持：

```text
OpenAI
Qwen
DeepSeek
Claude，后续
Ollama，后续
```

如果未来使用你自己的模型 Key，则必须通过云端 AI Proxy，不能把你的 Key 放在客户端。

---

# 15. 前端页面

## 15.1 数据源页

路径：

```text
/datasources
```

功能：

```text
数据源列表
新增数据源
测试连接
同步 Schema
删除数据源
连接状态
同步状态
```

---

## 15.2 Schema 页

路径：

```text
/datasources/:id/schema
```

功能：

```text
表列表
表搜索
字段详情
字段类型
字段注释
主键/外键标识
ER 图只读展示
```

---

## 15.3 问数页

路径：

```text
/query
```

V1.0：

```text
SQL 编辑器
检查 SQL
Guardrail 结果
执行按钮
查询结果表格
简单图表
查询历史
```

V1.1：

```text
自然语言输入框
生成 SQL
SQL 编辑器展示生成结果
用户确认执行
表格和图表展示
```

---

# 16. 前端状态契约

所有核心组件必须支持：

```typescript
type ComponentState =
  | { status: 'idle' }
  | { status: 'loading'; progress?: string }
  | { status: 'success'; data: unknown }
  | { status: 'error'; message: string; code?: string }
  | { status: 'empty'; message: string }
  | { status: 'warning'; message: string; action?: () => void };
```

---

# 17. 本地安全设计

## 17.1 Local Engine 安全

```text
只监听 127.0.0.1
随机端口
启动时生成 local token
前端请求必须带 local token
退出应用时关闭 Engine
```

---

## 17.2 数据安全

```text
数据库密码本地加密
不上传数据库密码
不上传查询结果
不把真实查询结果发给 LLM
LLM 只看 Schema 和用户问题
```

---

## 17.3 SQL 安全

```text
只允许 SELECT
AST Guardrail
执行前二次校验
默认 LIMIT
查询超时
结果大小限制
建议只读数据库账号
```

---

## 17.4 日志安全

```text
不打印数据库密码
不打印完整 DSN
默认不记录完整 Prompt
默认不记录查询结果
错误信息脱敏
```

---

# 18. 测试计划

## 18.1 V1.0 必测

### Guardrail 测试

```text
正常 SELECT
无 LIMIT 自动补 LIMIT
SELECT * 警告
DROP 拦截
DELETE 拦截
UPDATE 拦截
INSERT 拦截
ALTER 拦截
CREATE 拦截
TRUNCATE 拦截
CALL 拦截
多语句拦截
information_schema 拦截
mysql 系统库拦截
SLEEP 拦截
BENCHMARK 拦截
LOAD_FILE 拦截
SELECT INTO OUTFILE 拦截
超长 SQL 拦截
```

---

### Schema 同步测试

```text
同步表
同步字段
同步主键
同步外键
表注释
字段注释
重复同步不重复插入
同步失败状态
删除数据源级联删除 metadata
```

---

### API 测试

```text
测试连接成功
测试连接失败
创建数据源
同步 Schema
查询表列表
查询字段列表
validate SQL
execute SQL
history 查询
```

---

## 18.2 V1.1 必测

```text
LLM 生成 SQL 成功
LLM 返回非 SQL
LLM 超时
LLM 异常
生成 SQL 后 Guardrail 生效
Golden SQL 30 条，结构命中率 ≥ 70%
```

---

# 19. 开发顺序

## 任务 1：初始化桌面客户端

```text
Tauri
React
Vite
TypeScript
Tailwind
基础路由
API client
```

---

## 任务 2：Python Local Engine

```text
FastAPI 启动
随机端口
local token
健康检查
Tauri 拉起 Engine
```

---

## 任务 3：SQLite Metadata

```text
SQLite 连接
SQLAlchemy models
轻量 migration
data_sources
schema_tables
schema_columns
query_history
llm_logs
```

---

## 任务 4：数据源管理

```text
测试连接
创建数据源
AES-GCM 加密
列表
删除
同步状态
```

---

## 任务 5：Schema 同步

```text
SQLAlchemy Inspector
三阶段同步
表
字段
主键
外键
注释
```

---

## 任务 6：SQL Guardrail

```text
sqlglot mysql dialect
AST 检查
safe_sql
完整单元测试
```

---

## 任务 7：SQL 执行器

```text
执行前再次 Guardrail
只执行 safe_sql
超时
序列化
限制结果大小
记录历史
```

---

## 任务 8：前端 V1.0 页面

```text
数据源页面
Schema 页面
SQL 问数页面
ResultTable
ChartPanel
GuardrailPanel
```

---

## 任务 9：Text-to-SQL V1.1

```text
Schema 检索
LLM 调用
Prompt 模板
LLM 日志
Golden SQL 测试
```

---

# 20. V1 验收标准

## V1.0

```text
可以安装并启动桌面客户端
客户端能拉起 Python Local Engine
可以添加远程 MySQL 数据源
可以测试连接
可以同步 20+ 张表
可以浏览 Schema
可以手写 SQL
可以 Guardrail 检查
可以拦截危险 SQL
可以执行安全 SELECT
可以展示查询结果
可以查看查询历史
数据库密码本地加密保存
Local Engine 只能本地访问
```

---

## V1.1

```text
可以自然语言生成 SQL
生成 SQL 后必须人工确认
30 条 Golden SQL 命中率 ≥ 70%
LLM 失败不崩溃
LLM 日志可追溯
可以展示简单图表
```

---

# 21. V1 明确不做

第一版不做：

```text
云端存储客户数据库密码
云端执行客户 SQL
上传真实查询结果给 LLM
自动执行 LLM 生成 SQL
多租户
团队权限
字段权限
行权限
自动报表
定时报表
复杂 Dashboard
LangGraph 多 Agent
向量库
自动归因
```

---

# 22. 后续扩展方向

## V1.2

```text
SSH Tunnel
SSL 连接
保存查询
CSV 导出
图表推荐
轻量报表卡片
```

## V2

```text
统计分析
异常检测
归因分析
指标语义层
本地模板库
PromptOps
```

## V3

```text
可选云端账号
License 授权
云端 AI Proxy
团队协作
模板同步
企业私有化
```

---

# 23. 最终开发原则

DataBox V1 的核心原则：

```text
像 Navicat 一样远程连接数据库
但更适合业务人员问数
数据库连接在客户端
SQL 执行在客户端
真实数据不出本地
AI 只生成 SQL
SQL 必须先审核
执行必须用户确认
所有查询必须审计
```

推荐第一版技术路线：

```text
Tauri + React + Vite
+
Python FastAPI Local Engine
+
SQLite 本地元数据
+
远程 MySQL 数据源
+
SQL Guardrail
+
Text-to-SQL
```

这份文档可以作为 **DataBox 第一次开发指导文档**。
开发时必须按任务逐步实现，不要一次性让 AI 生成完整项目。
