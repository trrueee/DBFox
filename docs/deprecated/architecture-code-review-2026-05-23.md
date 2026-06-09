# DataBox 架构与代码审查报告

审查日期：2026-05-23

审查范围：当前仓库真实代码、项目结构、Python Engine、React/Tauri 前端、SQL Guardrail、数据源连接、查询执行、AI 问数、凭证安全、测试覆盖。

审查原则：本报告只基于已看到的代码证据；没有看到实现的能力标记为“未实现”或“未确认”。

## 1. 项目结构理解

### 1.1 前端

| 项 | 结论 | 证据 |
|---|---|---|
| Tauri | 已使用 | `desktop/src-tauri/tauri.conf.json` |
| React / Vite / TypeScript | 已使用 | `desktop/package.json` |
| 页面目录 | 已存在 | `desktop/src/pages` |
| 页面 | `QueryPage`、`DataSourcesPage`、`SchemaPage`、`DashboardPage` 均存在 | `desktop/src/pages/*.tsx` |
| 核心组件 | `SqlEditor`、`DataTable`、`ChartPanel`、`ExplainVisualizer`、`ErrorBoundary`、`AiQueryInput` 存在 | `desktop/src/components` |
| GuardrailPanel | 未独立拆分 | Guardrail 面板逻辑内嵌在 `desktop/src/pages/QueryPage.tsx` |
| SchemaTree / AiQuerySidebar | 未看到独立组件 | `rg` 未检索到 |
| ResultTable | 存在但未看到被实际引用 | `desktop/src/components/ResultTable.tsx` |

### 1.2 Python Local Engine

| 项 | 结论 | 证据 |
|---|---|---|
| FastAPI | 已使用 | `engine/main.py` |
| 启动入口 | `engine/main.py` | `uvicorn.run("engine.main:app", host="127.0.0.1", port=18625, reload=True)` |
| API 路由 | 已集中在 `engine/api.py` | `router = APIRouter(prefix="/api/v1")` |
| SQLite / Metastore | 已使用 SQLite | `engine/db.py` |
| datasource | 已有模块 | `engine/datasource.py` |
| schema_sync | 已有模块 | `engine/schema_sync.py` |
| guardrail | 已有模块 | `engine/guardrail.py` |
| executor | 已有模块 | `engine/executor.py` |
| ai / rag | 已有模块 | `engine/ai.py` |
| crypto | 已有模块 | `engine/crypto.py` |

### 1.3 打包与运行

| 项 | 结论 | 证据 |
|---|---|---|
| Tauri 拉起 Python Engine | 有，但不是标准 sidecar | `desktop/src-tauri/src/lib.rs` 使用 `Command::new("python")` |
| 随机端口 | 未实现 | Engine 固定端口 `18625` |
| local token | 已实现 | `engine/main.py` 的 `.local_token` |
| 前端 token header | 已实现 | `desktop/src/lib/api.ts` 设置 `X-Local-Token` |
| 监听地址 | 仅监听 `127.0.0.1` | `engine/main.py` |
| 健康检查 | 已实现 | `/api/v1/health` |
| Engine 崩溃恢复 | 未确认 | 未看到进程健康轮询或自动重启 |

## 2. 综合评分

综合分：5.7 / 10

判断：当前项目已经具备 DataBox V1 主链路原型能力，但还不适合作为可连接生产 MySQL 的稳定桌面客户端。主要短板集中在 SQL Guardrail 绕过、服务端长查询控制、凭证密钥保护、Tauri sidecar 打包、前端构建质量。

## 3. 分维度评分表

| 维度 | 分数 | 理由 |
|---|---:|---|
| 产品定位清晰度 | 7.0 | 页面和模块围绕数据源、Schema、SQL、AI 问数、Guardrail 展开，方向清楚 |
| 架构合理性 | 6.0 | Desktop + Local Engine 分层合理，但 sidecar、端口、token、API 边界不成熟 |
| 代码可维护性 | 5.5 | 模块已拆，但 `QueryPage.tsx`、`api.py`、`datasource.py` 偏大 |
| 前端工程质量 | 5.5 | 有组件和 ErrorBoundary，但 TypeScript 编译失败，无前端测试 |
| Python Engine 质量 | 6.2 | pytest 通过，业务模块清晰；mypy strict 失败，API 层偏重 |
| SQL Guardrail 安全性 | 6.0 | 使用 sqlglot AST，但存在危险函数绕过和 UNION 不补 LIMIT |
| 数据源连接与 SSH Tunnel 稳定性 | 5.5 | 有连接测试、SSH keepalive/health，但无 SSL、无池、无后台清理 |
| 本地 Metastore 设计 | 6.5 | 有 schema_migrations 和备份恢复，但仍是启动时手写 ALTER |
| 密码与凭证安全 | 4.5 | AES-GCM 有，但密钥文件与数据库同侧存放，未使用系统安全存储 |
| AI 问数链路 | 6.2 | 默认只发 Schema + 问题，不执行 SQL；缺 prompt version 和字段幻觉校验 |
| 查询执行稳定性 | 5.5 | 二次 Guardrail + safe_sql 执行；缺服务端取消、分页、响应大小限制 |
| 错误处理与容灾 | 5.0 | 有部分异常封装和 ErrorBoundary；日志脱敏、同步事务、Engine 重启不足 |
| 测试覆盖 | 6.0 | Engine 测试较多；前端、真实 MySQL、SSH、SSL、绕过测试缺失 |
| 打包部署可维护性 | 3.5 | 依赖系统 Python，固定端口，CSP 为 null，前端构建当前失败 |

## 4. 产品定位判断

当前代码已能支撑“AI 问数版数据库客户端”的基础形态：

| 能力 | 证据 | 结论 |
|---|---|---|
| 添加远程 MySQL 数据源 | `engine/api.py`、`desktop/src/pages/DataSourcesPage.tsx` | 已实现基础流程 |
| 测试连接 | `engine/datasource.py` | 已实现 |
| 本地加密保存连接信息 | `engine/crypto.py`、`engine/models.py` | 已实现基础加密 |
| 同步 Schema 到 SQLite | `engine/schema_sync.py` | 已实现 |
| 浏览表和字段 | `desktop/src/pages/SchemaPage.tsx` | 已实现 |
| 手写 SQL / AI 生成 SQL | `desktop/src/pages/QueryPage.tsx`、`engine/ai.py` | 已实现 |
| Guardrail 审核 SQL | `engine/guardrail.py` | 已实现但有缺口 |
| 用户确认执行 | 前端手动执行，PROD 二次确认 | 已实现部分 |
| 返回表格和图表 | `DataTable`、`ChartPanel` | 已实现 |
| 保存查询历史 | `engine/models.py`、`engine/executor.py` | 已实现 |

不适合现在直接上生产连接的原因：

| 风险 | 说明 |
|---|---|
| Guardrail 仍有绕过 | `CURRENT_USER()`、`DATABASE()`、`VERSION()`、`@@version` 实测未拦截 |
| 长查询不可控 | 前端 abort 不等于服务端 kill query |
| 凭证密钥保护不足 | `.secret_key` 与本地 DB 同侧存储 |
| 远程连接缺 SSL | 未看到 MySQL SSL 配置与证书校验 |
| 打包依赖系统 Python | 桌面端分发不可控 |

## 5. 架构总体评价

较好的架构点：

| 证据 | 说明 |
|---|---|
| `desktop/src/lib/api.ts` + `engine/main.py` | 前后端通过本地 HTTP + token 通信 |
| `engine/executor.py` | SQL 执行前会二次 Guardrail |
| `engine/executor.py` | 执行的是 Guardrail 返回的 `safeSql` |
| `engine/models.py` | 查询历史不保存真实结果集 |
| `engine/ai.py` | LLM 默认只接收 Schema 和用户问题 |

主要结构问题：

| 优先级 | 阶段 | 文件 | 问题 | 建议 |
|---|---|---|---|---|
| P0 | V1.0 | `engine/guardrail.py` | 危险函数绕过 | 补 sqlglot 具体表达式类型拦截 |
| P0 | V1.0 | `engine/executor.py` | 无服务端 timeout / cancel / response bytes | 增加 execution_id、statement timeout、kill query、响应大小限制 |
| P0 | V1.0 | `engine/crypto.py` | 密钥与密文同侧保存 | 短期移到用户数据目录并限制权限，长期接系统密钥链 |
| P1 | V1.0 | `desktop/src-tauri/src/lib.rs` | 非标准 sidecar，依赖系统 Python | 打包 Python Engine 或独立 sidecar |
| P1 | V1.0 | `engine/api.py` | API 层过重 | 拆 `benchmark.py`、`history.py`、`datasource_service.py` |
| P1 | V1.0 | `engine/schema_sync.py` | 同步失败可能丢旧 Schema | 临时表或事务原子替换 |

## 6. 前端审查

### 6.1 做得好的地方

| 证据 | 说明 |
|---|---|
| `QueryPage.tsx` | DataTable、ChartPanel、ExplainVisualizer 有局部 ErrorBoundary |
| `useQueryExecution.ts` | 生产环境执行 SQL 有二次确认 |
| `App.tsx` | 顶部显示 PROD / TEST / DEV 与只读标识 |
| `SqlEditor.tsx` | 使用 Monaco Editor，具备基础 SQL 编辑体验 |
| `DataSourcesPage.tsx` | 数据源创建、测试连接、同步 Schema 流程闭环 |

### 6.2 主要问题

| 优先级 | 阶段 | 文件 | 问题 | 风险 | 建议修复 | 测试方式 |
|---|---|---|---|---|---|---|
| P1 | V1.0 | `desktop/src/pages/QueryPage.tsx` | 803 行 Mega Component | 后续功能叠加会快速失控 | 拆 `QueryTabs`、`QueryToolbar`、`QueryResultPanel`、`GuardrailPanel`、`QueryHistoryPanel` | 组件测试与交互测试 |
| P1 | V1.0 | `desktop/src/lib/api.ts`、`DashboardPage.tsx` | 类型不一致，`guardrail_reason` 不存在 | `tsc` 当前失败 | 对齐 API 类型或移除字段 | `tsc --noEmit` |
| P1 | V1.0 | `SchemaPage.tsx` | ER/Data Preview 无局部 ErrorBoundary | 坏数据可能影响整页 | 给 `ErDiagram`、Schema DataTable 包 ErrorBoundary | 构造坏数据测试 |
| P1 | V1.0 | `DataTable.tsx` | 无虚拟滚动/分页 | 1000 行 x 100 列可能卡顿 | 加分页或虚拟滚动 | 大表渲染性能测试 |
| P1 | V1.0 | `SqlEditor.tsx` | 补全包含 INSERT/UPDATE/DELETE/DROP | 与只读定位冲突 | 默认只展示 SELECT 相关补全 | 编辑器补全测试 |
| P2 | V1.1 | `ChartPanel.tsx` | 数值列检测依赖 `typeof number` | 后端多转 string，图表可能选错列 | 支持数字字符串识别 | 字符串数字图表测试 |

### 6.3 建议拆分文件

| 新文件 | 目标 |
|---|---|
| `desktop/src/components/query/QueryTabs.tsx` | Tab 新增、关闭、重命名 |
| `desktop/src/components/query/QueryToolbar.tsx` | 校验、执行、取消、复制、导出 |
| `desktop/src/components/query/GuardrailPanel.tsx` | 右侧安全审核展示 |
| `desktop/src/components/query/QueryResultPanel.tsx` | table/chart/explain 切换 |
| `desktop/src/components/query/QueryHistoryPanel.tsx` | 查询历史列表 |
| `desktop/src/hooks/useAiQuery.ts` | AI 生成状态、配置、错误 |
| `desktop/src/hooks/useChartState.ts` | 图表类型和字段选择 |
| `desktop/src/hooks/useQueryTabs.ts` | 从 `useQueryExecution` 拆出 Tab 状态 |

## 7. Python Engine 审查

### 7.1 做得好的地方

| 证据 | 说明 |
|---|---|
| `engine/main.py` | 有本地 token 中间件 |
| `engine/main.py` | 有 `/api/v1/health` |
| `engine/executor.py` | Decimal、datetime、date、bytes、None 做了序列化 |
| `engine/models.py` | 查询历史字段较完整 |
| `engine/db.py` | 有 `schema_migrations` 表 |

### 7.2 主要问题

| 优先级 | 阶段 | 文件 | 问题 | 建议修复 | 测试方式 |
|---|---|---|---|---|---|
| P1 | V1.0 | `engine/main.py` | 启动时打印 Access Token | 不打印 token，只打印 token 文件路径 | 日志断言无 token |
| P1 | V1.0 | `engine/main.py` | 固定端口 18625 | 随机端口写入握手文件，前端读取 | 多实例启动测试 |
| P1 | V1.0 | `engine/api.py` | 创建数据源不强制先测试连接 | 服务端 create 前做 test 或保存 test snapshot | 未测试连接创建测试 |
| P1 | V1.0 | `engine/db.py` | 迁移逻辑写在启动函数中 | 抽正式 migration 模块 | 迁移幂等和失败恢复测试 |
| P1 | V1.0 | `engine/api.py` | Guardrail 统计用 `"blocked"`，实际状态是 `"reject"` | 统一为 `reject` | Dashboard stats 测试 |
| P1 | V1.0 | `engine/executor.py` | `guardrail_checks` 用 `str(...)` 存 | 改 `json.dumps(..., ensure_ascii=False)` | 历史 JSON 解析测试 |

## 8. SQL Guardrail 审查

Guardrail 安全评分：6.0 / 10

### 8.1 已覆盖规则

| 规则 | 证据 |
|---|---|
| 使用 sqlglot AST | `engine/guardrail.py` |
| 指定 MySQL dialect | `sqlglot.parse(sql_str, read="mysql")` |
| 禁止多语句 | `len(expressions) > 1` |
| 只允许 SELECT | `is_select_node` |
| 禁止 DDL/DML/Command | `BLOCKED_COMMAND_TYPES` |
| 禁止系统库 | `BLOCKED_SCHEMAS` |
| 禁止部分危险函数 | `DANGEROUS_FUNCTIONS` |
| 禁止 SELECT INTO | `exp.Into` |
| 限制 SQL 长度 | `len(sql_str) > 20000` |
| 自动补 LIMIT | `expression.limit(1000)` |
| 执行前二次 Guardrail | `engine/executor.py` |

### 8.2 缺失规则与绕过示例

| 优先级 | 阶段 | 问题 | 实测示例 | 当前结果 | 建议 |
|---|---|---|---|---|---|
| P0 | V1.0 | `CURRENT_USER()` 未拦截 | `SELECT CURRENT_USER()` | warn | 补 sqlglot 专用表达式拦截 |
| P0 | V1.0 | `DATABASE()` 未拦截 | `SELECT DATABASE()` | warn，且转为 `SCHEMA()` | 同时拦截 `DATABASE` / `SCHEMA` |
| P0 | V1.0 | `VERSION()` 未拦截 | `SELECT VERSION()` | warn | 拦截对应 AST 类型 |
| P0 | V1.0 | 系统变量未拦截 | `SELECT @@version` | warn | 禁止系统变量 |
| P0 | V1.0 | UNION 不自动补 LIMIT | `SELECT name FROM products UNION SELECT name FROM suppliers` | pass 且无 LIMIT | 对 Union/With 外层补 LIMIT |
| P1 | V1.0 | `COUNT(*)` 被误报为 `select_star` | `SELECT COUNT(*) FROM users LIMIT 10` | warn | 排除 `COUNT(*)` |
| P1 | V1.0 | DUMPFILE 依赖 syntax_error 拦截 | `SELECT * FROM users INTO DUMPFILE '/tmp/a'` | reject by syntax_error | 增加显式规则测试 |

### 8.3 必须补的测试用例

| 测试文件 | 用例 |
|---|---|
| `engine/tests/test_guardrail_bypass.py` | `test_current_user_blocked` |
| `engine/tests/test_guardrail_bypass.py` | `test_database_schema_blocked` |
| `engine/tests/test_guardrail_bypass.py` | `test_version_blocked` |
| `engine/tests/test_guardrail_bypass.py` | `test_system_variable_blocked` |
| `engine/tests/test_guardrail_bypass.py` | `test_union_auto_limit` |
| `engine/tests/test_guardrail_bypass.py` | `test_count_star_no_warning` |
| `engine/tests/test_guardrail_bypass.py` | `test_table_star_warning` |

## 9. 数据源连接 / SSH Tunnel 审查

连接能力评分：5.5 / 10

### 9.1 已实现

| 能力 | 证据 |
|---|---|
| Direct MySQL 测试连接 | `engine/datasource.py` |
| MySQL 版本检测 | `SELECT VERSION()` |
| 表数量检测 | `information_schema.tables` |
| 写权限 warning | `SHOW GRANTS FOR CURRENT_USER()` |
| 连接超时 | `connect_timeout=5` |
| SSH 密码 / 私钥 / passphrase | `SSHTunnelForwarder` 参数 |
| SSH keepalive | `keepalive=30` |
| tunnel health probe | `TunnelManager.health_check` |
| tunnel 自动重连 | `TunnelManager.get_or_reconnect` |

### 9.2 风险与修复

| 优先级 | 阶段 | 文件 | 问题 | 建议 | 测试 |
|---|---|---|---|---|---|
| P1 | V1.0 | `engine/datasource.py` | 无 MySQL SSL 配置 | 支持 CA/client cert、verify_identity | TLS MySQL 集成测试 |
| P1 | V1.0 | `engine/datasource.py` | 每次查询新建连接，无 pool/recycle 策略 | 明确 per-query 模式或加连接管理 | 并发查询测试 |
| P1 | V1.0 | `engine/datasource.py` | `cleanup_stale()` 存在但未调度 | lifespan 启动后台清理任务 | stale tunnel 测试 |
| P1 | V1.0 | `engine/datasource.py` | 高危权限检测不完整 | 增加 `FILE`、`SUPER`、`PROCESS`、`GRANT OPTION` 等 | grant 字符串测试 |
| P2 | V1.1 | `engine/datasource.py` | 测试连接临时 tunnel 与正式 tunnel 逻辑重复 | 复用 TunnelManager 临时模式 | SSH mock 测试 |

## 10. 查询执行与长查询保护审查

查询执行稳定性评分：5.5 / 10

### 10.1 已实现

| 能力 | 证据 |
|---|---|
| 执行前二次 Guardrail | `engine/executor.py` |
| 只执行 `safeSql` | `engine/executor.py` |
| max_rows | `MAX_ROWS = 1000` |
| max_columns | `MAX_COLUMNS = 100` |
| max_cell_chars | `MAX_CELL_CHARS = 5000` |
| MySQL read/write timeout | `engine/datasource.py` |
| 前端 AbortController | `desktop/src/hooks/useQueryExecution.ts` |
| 前端 running/success/error/timeout/cancelled 状态 | `QueryStatus` |
| JSON 序列化 | `_serialize_value` |

### 10.2 缺口

| 优先级 | 阶段 | 文件 | 问题 | 风险 | 建议 | 测试 |
|---|---|---|---|---|---|---|
| P0 | V1.0 | `engine/executor.py` | 无服务端 query cancel | 前端取消不等于 MySQL 取消 | execution_id + KILL QUERY + 状态表 | 取消长查询测试 |
| P0 | V1.0 | `engine/executor.py` | 无 max_response_bytes | 宽表/大字段可能撑爆响应 | 估算 JSON bytes，超限截断 | 超大响应测试 |
| P1 | V1.0 | `engine/executor.py` | 无分页/流式 | 1000 行保护不等于分页 | V1 先加 bytes，V1.1 加分页 | 分页测试 |
| P1 | V1.0 | `engine/api.py` | Benchmark 同步执行多条 SQL | 可能阻塞请求、污染历史 | 后台任务化，prod 默认禁止 | Benchmark 超时测试 |
| P1 | V1.0 | `engine/models.py` | 后端历史只有 success/failed | timeout/cancelled 不可审计 | 补状态枚举 | 历史状态测试 |

## 11. AI 问数链路审查

AI 问数评分：6.2 / 10

### 11.1 做得好的地方

| 证据 | 说明 |
|---|---|
| `desktop/src/pages/QueryPage.tsx` | AI 只生成 SQL，不自动执行 |
| `engine/ai.py` | LLM user prompt 只包含 Schema 和用户问题 |
| `engine/ai.py` | LLM 输出会过 Guardrail |
| `engine/ai.py` | 有基于问题的 Schema Context / RAG 选择 |
| `engine/tests/test_golden_sql.py` | 有 30 条离线 Golden SQL 结构测试 |
| `engine/models.py` | LLMLog 有 prompt_hash，不默认保存完整 prompt |

### 11.2 主要风险

| 优先级 | 阶段 | 文件 | 问题 | 建议 | 测试 |
|---|---|---|---|---|---|
| P1 | V1.1 | `engine/ai.py` | 无 prompt version | 记录 `prompt_version`、模板 hash、model 参数 | prompt 回归测试 |
| P1 | V1.1 | `engine/ai.py` | 只做 SQL 安全，不校验表字段存在 | 生成后做 schema reference validation | 幻觉字段测试 |
| P1 | V1.1 | `engine/api.py` | Benchmark 会真实执行 SQL | 增加 dry-run / explain-only 模式 | benchmark 安全测试 |
| P1 | V1.1 | `engine/ai.py` | LLM 错误文本直接入库 | 错误信息脱敏和长度限制 | LLM error 脱敏测试 |
| P2 | V1.1 | `engine/ai.py` | RAG 是简单词面匹配 | 后续加业务词典、向量召回 | 大 schema 召回测试 |

## 12. 凭证安全审查

凭证安全评分：4.5 / 10

### 12.1 当前方案

| 项 | 证据 | 判断 |
|---|---|---|
| AES-256-GCM | `engine/crypto.py` | 已实现 |
| nonce 独立保存 | `engine/models.py` | 已实现 |
| key_version | `engine/models.py` | 有字段，但未看到轮换逻辑 |
| 密钥保存 | `engine/crypto.py` | `.secret_key` 文件 |
| SSH 密码加密 | `engine/api.py` | 已实现 |
| SSH passphrase 加密 | `engine/api.py` | 已实现 |
| LLM API Key | `engine/api.py` | 请求态使用，未持久化 |
| 系统安全存储 | 未看到实现 | 未实现 |

### 12.2 风险与建议

| 优先级 | 阶段 | 文件 | 问题 | 建议 | 测试 |
|---|---|---|---|---|---|
| P0 | V1.0 | `engine/crypto.py` | 密钥与 SQLite 元数据同侧保存 | 短期移到用户数据目录并限制 ACL，长期使用系统密钥链 | 文件权限测试 |
| P1 | V1.0 | `engine/main.py` | local token 打印到控制台 | 不打印 token | 日志扫描测试 |
| P1 | V1.0 | 项目根目录 | 无 root `.gitignore` | 忽略 `.db`、`.secret_key`、`.local_token`、备份 | `git check-ignore` |
| P1 | V1.1 | `engine/models.py` | 有 key_version 但无轮换策略 | 实现 key rotation 和恢复流程 | 密钥轮换测试 |

## 13. 本地 Metastore / Migration 审查

Metastore 评分：6.5 / 10

### 13.1 已实现

| 能力 | 证据 |
|---|---|
| Metastore SQLite | `engine/db.py` |
| 数据源表 | `engine/models.py` |
| Schema 表/列 | `engine/models.py` |
| 查询历史 | `engine/models.py` |
| LLM 日志 | `engine/models.py` |
| schema_migrations | `engine/db.py` |
| 启动前备份 | `engine/db.py` |
| 失败恢复 | `engine/db.py` |

### 13.2 问题

| 优先级 | 阶段 | 文件 | 问题 | 建议 | 测试 |
|---|---|---|---|---|---|
| P1 | V1.0 | `engine/db.py` | `PRAGMA table_info({table})` 使用 f-string | 使用白名单 | migration 单测 |
| P1 | V1.0 | `engine/db.py` | 迁移代码与启动代码耦合 | 抽 `engine/migrations` | 迁移顺序测试 |
| P1 | V1.0 | `engine/schema_sync.py` | 同步失败会清空旧 Schema | 临时表/事务替换 | 失败保留旧 schema 测试 |
| P2 | V1.1 | `engine/models.py` | LLMLog 有 prompt_text/response_text 字段但当前不用 | 明确隐私策略，默认不写 | 日志字段测试 |

## 14. 测试覆盖审查

验证结果：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 114 passed |
| `python -m compileall -q engine` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 失败，11 个类型错误 |
| `tsc -p tsconfig.app.json --noEmit --pretty false` | 失败，6 个错误 |
| `tsc -p tsconfig.node.json --noEmit --pretty false` | 通过 |

已有测试：

| 文件 | 覆盖 |
|---|---|
| `engine/tests/test_guardrail.py` | SELECT、DDL/DML、多语句、系统库、危险函数、OUTFILE、长度 |
| `engine/tests/test_schema_sync.py` | Demo schema 表/列/主键/外键/幂等/级联删除 |
| `engine/tests/test_executor.py` | 序列化、行列限制、SQLite demo 查询 |
| `engine/tests/test_api.py` | API 基础流程、token header、执行与历史 |
| `engine/tests/test_ai.py` | 离线 SQL、mock 在线 LLM、HTTP error、Guardrail reject |
| `engine/tests/test_crypto.py` | AES-GCM 加解密、nonce、异常 |
| `engine/tests/test_golden_sql.py` | 30 条离线 Golden SQL 结构测试 |

明显缺失：

| 缺失项 | 建议文件 |
|---|---|
| Guardrail 绕过测试 | `engine/tests/test_guardrail_bypass.py` |
| 真实或模拟 MySQL 超时、断连、SSL | `engine/tests/test_mysql_connection.py` |
| SSH Tunnel stale/reconnect | `engine/tests/test_ssh_tunnel.py` |
| 服务端取消、timeout、max_response_bytes | `engine/tests/test_query_limits.py` |
| migration 失败恢复 | `engine/tests/test_migrations.py` |
| 日志脱敏 | `engine/tests/test_log_redaction.py` |
| 前端组件测试 | `desktop/src/**/*.test.tsx` |
| ErrorBoundary 测试 | `desktop/src/components/ErrorBoundary.test.tsx` |
| QueryPage hook 测试 | `desktop/src/hooks/useQueryExecution.test.ts` |

## 15. P0 问题清单

| 阶段 | 文件 | 问题 | 风险 | 修复 | 测试 |
|---|---|---|---|---|---|
| V1.0 | `engine/guardrail.py` | 危险函数存在绕过 | 泄露当前用户、库名、版本等环境信息 | 补 sqlglot 特定表达式拦截 | Guardrail bypass tests |
| V1.0 | `engine/guardrail.py` | UNION 不补 LIMIT | 大查询绕开默认保护 | 对 Union/With 外层 AST 补 LIMIT | `test_union_auto_limit` |
| V1.0 | `engine/executor.py` | 无服务端取消与 statement timeout | 长查询不可控 | execution_id + timeout + kill query | 长查询取消测试 |
| V1.0 | `engine/executor.py` | 无响应大小上限 | 大结果/大字段可能拖垮 Engine | max_response_bytes + 截断 warning | 超大响应测试 |
| V1.0 | `engine/crypto.py` | 密钥与密文同侧保存 | 本机文件泄露即可解密 | 迁移密钥位置、权限、root `.gitignore` | 权限与误提交测试 |

## 16. P1 问题清单

| 阶段 | 文件 | 问题 | 修复 | 测试 |
|---|---|---|---|---|
| V1.0 | `desktop/src/pages/QueryPage.tsx` | 803 行 Mega Component | 拆组件和 hooks | 前端交互测试 |
| V1.0 | `engine/schema_sync.py` | 同步失败丢旧 schema | 事务/临时表原子替换 | 失败回滚测试 |
| V1.0 | `engine/datasource.py` | MySQL SSL 未实现 | 增加 SSL 配置和证书校验 | TLS 集成测试 |
| V1.0 | `engine/main.py` | 固定端口和持久 token | 随机端口 + session token | 多实例测试 |
| V1.0 | `desktop/src-tauri/src/lib.rs` | Tauri 依赖系统 Python | 标准 sidecar/独立二进制 | 安装包测试 |
| V1.0 | `desktop/src-tauri/tauri.conf.json` | CSP 为 null | 设置最小 CSP | WebView 安全测试 |
| V1.0 | `engine/api.py` | Guardrail 统计字段错误 | `blocked` 改 `reject` | stats 单测 |
| V1.0 | `desktop/src/pages/DashboardPage.tsx` | 访问不存在字段 | 对齐 API 类型 | `tsc --noEmit` |
| V1.0 | `engine/main.py` | token 打印 | 移除 token 输出 | 日志测试 |
| V1.0 | `engine/datasource.py` | stale tunnel cleanup 未调度 | 后台清理任务 | SSH stale 测试 |

## 17. P2 问题清单

| 阶段 | 文件 | 问题 | 修复 | 测试 |
|---|---|---|---|---|
| V1.1 | `engine/ai.py` | 无 prompt version | 加 prompt_version | prompt 回归测试 |
| V1.1 | `engine/ai.py` | RAG 简单词面匹配 | 引入业务词典/向量召回 | 大 schema 测试 |
| V1.1 | `desktop/src/components/ChartPanel.tsx` | 图表字段推荐弱 | 类型推断 + 推荐图表 | 图表选择测试 |
| V1.1 | `desktop/src/components/DataTable.tsx` | 无虚拟滚动 | 分页/虚拟列表 | 性能测试 |
| V2 | `engine/crypto.py` | 未接 OS Keychain | DPAPI / Keychain / Secret Service | 跨设备恢复测试 |

## 18. 推荐整改路线图

| 优先级 | 目标 | 涉及文件 | 预计影响 | 测试方式 | 适合 AI Coding Agent |
|---|---|---|---|---|---|
| P0 | 补 Guardrail 绕过 | `engine/guardrail.py`、`engine/tests/test_guardrail.py` | 提升 SQL 安全底线 | pytest | 适合 |
| P0 | 服务端 query timeout/cancel/response bytes | `engine/executor.py`、`engine/api.py`、`engine/models.py` | 降低长查询风险 | 长查询集成测试 | 适合，但需人工确认策略 |
| P0 | 凭证与 token 最小硬化 | `engine/crypto.py`、`engine/main.py`、root `.gitignore` | 降低本地泄露风险 | 权限/日志测试 | 适合 |
| P1 | 前端构建修复 | `ErrorBoundary.tsx`、`DashboardPage.tsx`、`QueryPage.tsx` | 恢复 CI 构建 | `tsc --noEmit` | 适合 |
| P1 | Schema sync 原子化 | `engine/schema_sync.py` | 防同步失败损坏本地缓存 | 故障注入测试 | 适合 |
| P1 | Tauri sidecar 化 | `desktop/src-tauri`、打包脚本 | 提升桌面分发能力 | 安装包冷启动 | 适合部分，需人工验收 |
| P1 | SSL 配置 | `engine/datasource.py`、API/前端表单 | 远程 MySQL 安全传输 | TLS MySQL 测试 | 适合 |
| P2 | QueryPage 架构拆分 | `desktop/src/pages/QueryPage.tsx`、新组件/hooks | 提升维护性 | 组件测试 | 适合 |
| P2 | AI prompt version + schema validation | `engine/ai.py` | 提升 AI 可靠性 | Golden SQL 回归 | 适合 |

## 19. 不建议现在做的事情

| 不建议 | 原因 |
|---|---|
| 不建议现在做复杂 BI 仪表盘 | 安全和查询稳定性还没补齐 |
| 不建议上云端同步查询结果 | 当前产品定位默认本地，应避免扩大隐私面 |
| 不建议先做复杂多租户/RBAC | 当前是本地桌面客户端，应优先补本地安全闭环 |
| 不建议先引入大型向量库 RAG | V1.1 前先做 schema validation、prompt version、Golden SQL |
| 不建议大量美化 QueryPage | 应先拆分结构和修构建，再做 UI 体验 |

## 20. 下一轮最小整改任务

1. [x] 修 Guardrail：拦截 `CURRENT_USER()`、`DATABASE()/SCHEMA()`、`VERSION()`、`@@version`，修 UNION 自动 LIMIT，修 `COUNT(*)` 误报。
2. [x] 补 P0 测试：新增 `test_guardrail_bypass.py`，覆盖本报告列出的绕过样例。
3. [x] 修前端构建：解决 `tsc --noEmit` 当前 6 个错误。
4. [x] 硬化本地 token/secret：不打印 token，补 root `.gitignore`，密钥文件迁移到用户数据目录或至少限制权限。
5. [x] 给执行层加 `max_response_bytes` 和服务端 timeout 设计，先不做复杂流式分页。

## 21. 开发完成标记

更新时间：2026-05-23

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | Guardrail 绕过修复：拦截 `CURRENT_USER()`、`DATABASE()/SCHEMA()`、`VERSION()`、`@@version`，`UNION` 自动补 `LIMIT`，`COUNT(*)` 不误报 | `engine/guardrail.py`、`engine/tests/test_guardrail_bypass.py`、`engine/tests/test_guardrail.py` | `pytest engine\tests\test_guardrail.py engine\tests\test_guardrail_bypass.py -q` |
| 已完成 | P0 | 响应大小保护：结果序列化时按 `MAX_RESPONSE_BYTES` 截断并返回 `truncated/responseBytes/maxResponseBytes` | `engine/executor.py`、`desktop/src/lib/api.ts`、`engine/tests/test_executor.py` | `pytest engine\tests\test_executor.py -q` |
| 已完成 | P0 | 长查询保护与服务端取消：SQLite 使用进度回调和 `interrupt()`，MySQL 尝试设置 `MAX_EXECUTION_TIME` 并通过 `execution_id + KILL QUERY` 主动取消 | `engine/executor.py`、`engine/errors.py`、`engine/query_registry.py`、`engine/api.py`、`engine/tests/test_executor.py`、`engine/tests/test_api.py` | `pytest engine\tests\test_executor.py engine\tests\test_api.py -q` |
| 已完成 | P0 | 凭证与 token 最小硬化：新 token/key 写入私有运行目录，保留 legacy 文件读取兼容，不再打印 token，补 root `.gitignore` | `engine/runtime_paths.py`、`engine/crypto.py`、`engine/main.py`、`.gitignore`、`engine/tests/test_crypto.py` | `pytest engine\tests\test_crypto.py -q` |
| 已完成 | P1 | 前端 TypeScript 构建修复：修复 type-only import、未使用导入、历史字段类型不一致 | `desktop/src/components/ErrorBoundary.tsx`、`desktop/src/components/ExplainVisualizer.tsx`、`desktop/src/pages/DashboardPage.tsx`、`desktop/src/pages/QueryPage.tsx`、`desktop/src/lib/api.ts` | `tsc -p tsconfig.app.json --noEmit --pretty false` |
| 已完成 | P1 | Guardrail 统计与历史审计小修：`blocked` 统计改为 `reject`，历史返回 `guardrail_checks` | `engine/api.py`、`desktop/src/lib/api.ts` | `pytest -q` |

本轮完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 126 passed |
| `python -m compileall -q engine` | 通过 |
| `tsc -p tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余旧问题集中在 `datasource.py`、`db.py`、`api.py` 的类型标注；本轮未新增 executor/guardrail 类型错误 |

仍未完成：

| 优先级 | 任务 | 说明 |
|---|---|---|
| P1 | Tauri sidecar 化 | 仍依赖系统 Python |

## 22. 第二轮开发完成标记

更新时间：2026-05-23

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | 真正的服务端查询取消：执行请求携带 `execution_id`，Engine 注册运行中查询，取消接口可打断 SQLite / MySQL 后端执行 | `engine/query_registry.py`、`engine/executor.py`、`engine/api.py`、`engine/errors.py` | `pytest engine\tests\test_executor.py engine\tests\test_api.py -q` |
| 已完成 | P0 | 前端取消链路接入 Engine：取消按钮和客户端超时都会先请求 `/query/cancel`，再 abort 当前 fetch | `desktop/src/hooks/useQueryExecution.ts`、`desktop/src/lib/api.ts` | `tsc -p tsconfig.app.json --noEmit --pretty false` |
| 已完成 | P0 | 查询取消测试：覆盖未知 execution_id、指定 execution_id 执行返回、SQLite 长查询被后台 cancel | `engine/tests/test_api.py`、`engine/tests/test_executor.py` | `pytest -q` |

第二轮完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 126 passed |
| `python -m compileall -q engine` | 通过 |
| `tsc -p tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余旧问题为 `datasource.py`、`db.py`、`api.py` 类型标注 |

## 23. 第三轮开发完成标记

更新时间：2026-05-23

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P1 | Schema sync 原子化：先采集完整新 Schema snapshot，再在单个事务中替换旧缓存 | `engine/schema_sync.py` | `pytest engine\tests\test_schema_sync.py -q` |
| 已完成 | P1 | 同步失败保留旧缓存：采集或写入失败时 `rollback`，只更新 `last_sync_status=failed`，不删除旧 `schema_tables/schema_columns` | `engine/schema_sync.py`、`engine/tests/test_schema_sync.py` | `test_sync_failure_preserves_existing_schema` |
| 已完成 | P1 | Demo schema 同步去除全局数据污染：不再向 `MOCK_TABLES_INFO` 写入 `temp_id` | `engine/schema_sync.py` | `pytest engine\tests\test_schema_sync.py -q` |

第三轮完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 127 passed |
| `python -m compileall -q engine` | 通过 |
| `tsc -p tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余旧问题为 `datasource.py`、`db.py`、`api.py` 类型标注；本轮未新增 `schema_sync.py` 类型错误 |

## 24. 第四轮开发完成标记
更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P1 | MySQL SSL/TLS 配置闭环：数据源支持 `ssl_enabled`、CA 证书、client cert、client key、`ssl_verify_identity` | `engine/models.py`、`engine/db.py`、`engine/api.py`、`desktop/src/lib/api.ts`、`desktop/src/pages/DataSourcesPage.tsx` | `pytest -q`、`tsc -p desktop/tsconfig.app.json --noEmit --pretty false` |
| 已完成 | P1 | 真实连接调用链接入 TLS 参数：测试连接、查询执行、Schema sync 均使用统一 SSL 参数构造 | `engine/datasource.py`、`engine/executor.py`、`engine/schema_sync.py` | `engine/tests/test_datasource_ssl.py`、`engine/tests/test_api.py` |
| 已完成 | P1 | SSL 配置校验：默认启用证书校验；开启主机名校验时要求 CA 证书路径，避免“只加密不验身份”误配置 | `engine/datasource.py`、`engine/api.py` | `test_build_mysql_ssl_params_requires_ca_for_identity_verification` |

第四轮完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 133 passed |
| `python -m compileall -q engine` | 通过 |
| `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p desktop/tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余旧问题为 `datasource.py`、`api.py` 类型债；本轮顺手清理了 `engine/db.py` 的 migration 类型标注错误 |

## 25. 第五轮开发完成标记
更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P2 | AI 问数 PromptTelemetry 追踪：元数据库新增 v5 增量迁移，记录 `prompt_version`、`prompt_template_hash`、`model_temperature` 和 `max_tokens` | `engine/models.py`、`engine/db.py`、`engine/ai.py` | `pytest -q` (134 passed) |
| 已完成 | P2 | AST 语法树 Schema 幻觉校验：利用 `sqlglot` 遍历生成 SQL 抽象语法树（包含表别名与多表 Join），校验表与字段是否存在于本地 Schema 缓存中 | `engine/ai.py` | `test_validate_sql_schema_hallucinations` |
| 已完成 | P2 | 前端幻觉字段警告渲染：扩展 React 标签页 `QueryTabState`，在右侧 Guardrail 审核侧边栏渲染极富质感的「AI 字段存在性校验警告」列表 | `desktop/src/hooks/useQueryExecution.ts`、`desktop/src/pages/QueryPage.tsx` | `tsc -p desktop/tsconfig.app.json --noEmit` |

第五轮完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 134 passed (新增幻觉与 schema reference 单元测试覆盖) |
| `python -m compileall -q engine` | 通过 |
| `npx tsc --noEmit (desktop)` | 100% 编译通过，0 警告，0 错误 |

## 26. 第六轮开发完成标记 (Tauri Sidecar 打包发布与操作系统安全 Keychain 集成)
更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P1 | **Tauri Python Sidecar 化**：编译 FastAPI Local Engine 为完全独立的单文件 sidecar 二进制程序，不再依赖宿主系统预安装 Python | `desktop/src-tauri/tauri.conf.json`、`desktop/src-tauri/src/lib.rs` | 编译出 `databox-engine-x86_64-pc-windows-msvc.exe` |
| 已完成 | P1 | **自动化 Sidecar 构建体系**：编写 `build_sidecar.py` 实现“编译期安全 Token 预置”+“前端 JS 注入”+“PyInstaller 自动集成编译”的一键自动化链路 | `build_sidecar.py`、`engine/token_preset.py` (动态)、`desktop/.env.local` (动态) | `python build_sidecar.py` 成功执行 |
| 已完成 | P1 | **操作系统 Keychain 集成 (Credential Manager)**：升级对称加密密钥存储，将 `.secret_key` 从明文文件迁移至操作系统原生安全存储（如 Windows Credential Manager / macOS Keychain / Linux Secret Service），并包含无感平滑迁移与优雅文件兜底逻辑 | `engine/crypto.py` | `test_keyring_lifecycle_and_migration` 单元测试通过 |
| 已完成 | P1 | **真实 TLS MySQL 集成验收**：接入配置自签名证书的 MySQL 实例进行真实端到端集成验证，打通安全传输校验与服务器身份校验 | `engine/datasource.py`、`engine/tests/test_datasource_ssl_e2e.py` | 新增 `test_mysql_ssl_connection_e2e` 真实 Docker 容器端到端集成测试，136 个测试全部通过 |

第六轮完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 136 passed (新增真实 MySQL SSL 容器端到端集成测试且全部通过) |
| `python -m compileall -q engine` | 通过 |
| `python build_sidecar.py` | 100% 成功生成 143MB 完全自包含 Sidecar 并清理全部 PyInstaller 临时文件 |

仍未完成：

无。本项目第一至第十一阶段所有高价值商业功能、安全底座与交互体验打磨已 100% 顺利实现，测试套件 100% 通过。
## 27. 产品定位校正标记
更新时间：2026-05-24

本审查报告最初以“AI 问数版数据库客户端”为前提展开。后续产品定位已校正为：

> 从数据库设计、创建环境、建库建表，到查询管理和备份恢复的一站式数据库客户端。

关键结论：

| 状态 | 调整项 | 说明 |
|---|---|---|
| 已确认 | ER 图定位 | ER 图只是数据库设计/数据建模模块的一部分，不应作为产品主线 |
| 已确认 | V1 主线 | 第一版优先抓环境管理、连接管理、SQL 编辑器、表结构/结果表格、AI ER 图 + 建表、备份恢复 |
| 已沉淀 | 新路线图 | 详见 `docs/product-module-roadmap.md` |

后续开发应优先围绕“数据库生命周期工作台”闭环推进，而不是继续单点扩展 ER 图能力。
