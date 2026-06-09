# DataBox 可执行开发 Backlog

更新时间：2026-05-25

本文档把 `docs/ROADMAP.md` 拆成可开发、可验收的任务。默认顺序是先稳住本地安全客户端，再加强 AI 问数可信度，最后进入轻量语义层。

## 当前开发基线

仓库已有能力已经覆盖大量 V1 底座：

```text
Tauri + React 桌面端
Python FastAPI Local Engine
SQLite metastore
数据源管理
Schema 同步
SQL Guardrail
SQL Executor
AI 问数基础链路
查询历史
图表与结果表格
Golden SQL / Guardrail 测试
多数据库连接雏形
```

下一阶段不再大幅扩产品边界，优先补齐 AI 问数可信链路和本地客户端稳定性。

## V1.0：安全可用的小型 Navicat

目标：用户能把 DataBox 当作本地数据库客户端安全使用。

| 优先级 | 任务 | 验收标准 | 主要区域 |
|---|---|---|---|
| P0 | 连接健康检查面板 | 每个数据源能显示最近连接状态、延迟、权限风险、最近同步时间 | `engine/datasource.py`、`desktop/src/pages/DataSourcesPage.tsx` |
| P0 | 查询历史治理 | 支持历史搜索、按数据源过滤、清空历史、保留执行状态和耗时 | `engine/api/query.py`、`desktop/src/pages/QueryPage.tsx` |
| P0 | 错误码体系收敛 | 连接、同步、执行、AI 生成错误都有稳定 code 和用户可读 message | `engine/errors.py`、`desktop/src/lib/api.ts` |
| P1 | 诊断包导出 | 用户可导出脱敏诊断包，包含版本、日志摘要、配置摘要，不包含密码和结果集 | `engine/api/backup.py` 或新增 diagnostics 模块 |
| P1 | 本地日志清理策略 | 支持按时间清理 query_history / llm_logs / guardrail_logs | `engine/models.py`、`engine/db.py` |

推荐验证：

```text
pytest -q
python -m compileall -q engine
npm run build
```

## V1.1：可信 AI SQL 生成器

目标：AI 生成 SQL 可信、可解释、可回归测试，但仍必须由用户确认执行。

| 优先级 | 任务 | 验收标准 | 主要区域 |
|---|---|---|---|
| P0 | AI 问题理解结构化 | 生成 SQL 前返回指标、维度、时间、过滤、排序等 query intent | `engine/ai.py`、`desktop/src/components/AiQueryInput.tsx` |
| P0 | Schema RAG 强化 | 检索结果能解释为什么选中这些表字段，并限制上下文 token | `engine/ai.py` |
| P0 | Schema Validation 增强 | 对生成 SQL 的表、字段、别名、聚合字段进行校验，错误进入 warning / reject | `engine/ai.py`、`engine/guardrail.py` |
| P0 | Golden SQL 回归 | 维护不少于 30 条高频问题，记录结构命中率和失败原因 | `engine/tests/test_golden_sql.py` |
| P1 | LLM 日志治理 | 默认只存 prompt hash、模型、耗时、状态，开发模式才保存完整 prompt/response | `engine/ai.py`、`engine/models.py` |
| P1 | 用户修正沉淀 | 用户修改 AI SQL 后可标记为有效样例，进入 Golden SQL 候选 | 新增 query feedback 模型和 API |

推荐验证：

```text
pytest -q engine/tests/test_ai.py engine/tests/test_golden_sql.py
pytest -q engine/tests/test_guardrail.py engine/tests/test_guardrail_bypass.py
npm run build
```

## V1.2：轻量报表与常用查询

目标：把一次性问数沉淀成可复用资产，但不进入复杂 BI。

| 优先级 | 任务 | 验收标准 | 主要区域 |
|---|---|---|---|
| P0 | 常用查询 | 查询历史可收藏、命名、按项目和数据源管理 | `engine/api/query.py`、`desktop/src/pages/QueryPage.tsx` |
| P0 | CSV 导出 | 当前安全查询结果可导出 CSV，遵守响应大小和脱敏规则 | `engine/executor.py`、`desktop/src/components/DataTable.tsx` |
| P1 | 图表保存 | 简单图表配置可保存并从常用查询恢复 | `desktop/src/components/ChartPanel.tsx` |
| P1 | 图表推荐 | 基于字段类型推荐表格、柱状图、折线图、饼图 | `desktop/src/components/ChartPanel.tsx` |
| P2 | 轻量看板 | 手动把常用查询图表组成本地看板，不支持定时云端刷新 | 新增 Dashboard 资产模型 |

推荐验证：

```text
npm run build
pytest -q
```

## V1.3：业务别名与 Golden SQL 沉淀

目标：从纯 Schema RAG 迈向轻量业务语义，但只覆盖高频 20% 场景。

| 优先级 | 任务 | 验收标准 | 主要区域 |
|---|---|---|---|
| P0 | 业务别名候选 | 从表名、字段名、注释、历史问题中推荐业务别名 | 新增 semantic aliases 模型和 API |
| P0 | 用户确认别名 | 用户可确认、编辑、删除别名；AI RAG 优先使用已确认别名 | 前端设置页或 Schema 页 |
| P1 | 高频指标候选 | 从历史 SQL 中发现常见聚合表达式，生成指标候选 | `engine/ai.py` 或新增 semantic 模块 |
| P1 | Golden SQL 资产化 | Golden SQL 不只在测试里存在，可在本地 metastore 中维护 | `engine/models.py`、`engine/tests/test_golden_sql.py` |
| P2 | 默认时间字段 | 用户可为表指定默认时间字段，用于“最近 7 天”等问题 | Schema 语义设置 |

推荐验证：

```text
pytest -q engine/tests/test_ai.py engine/tests/test_golden_sql.py
pytest -q
```

## V2.0：本地优先的语义问数客户端

目标：把高频问题从 NL2SQL 升级为 NL2QueryPlan2SQL。

| 优先级 | 任务 | 验收标准 |
|---|---|---|
| P0 | Query Plan 中间层 | 用户问题先解析为指标、维度、时间、过滤、排序、limit |
| P0 | SQL Compiler | 基于 Query Plan 和已确认语义生成 SQL，而不是完全交给 LLM |
| P1 | 指标语义层 | 支持本地定义指标表达式、默认过滤、时间字段 |
| P1 | 语义回归测试 | 每个指标有固定样例和 SQL snapshot |
| P2 | 企业私有 Data Agent | 在本地语义层上支持更长链路的分析辅助 |

## 不做清单

这些事情在 V1 阶段保持克制：

```text
复杂 Dashboard
定时报表
云端同步查询结果
多租户 RBAC
企业级指标平台
大规模向量库
自动执行 AI SQL
把真实结果集发给 LLM
```

## 每轮开发完成标记模板

每完成一轮开发，在对应路线图或 sprint 文档中追加：

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | 示例任务 | `engine/example.py` | `pytest -q` |

同时记录完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 通过 / 失败原因 |
| `python -m compileall -q engine` | 通过 / 失败原因 |
| `npm run build` | 通过 / 失败原因 |
