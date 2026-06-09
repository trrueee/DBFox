# DataBox 当前产品路线图

更新时间：2026-05-25

本文档是 DataBox 后续产品开发的当前主线。产品需求见 `docs/PRD.md`，历史过程记录保留在 `docs/product-module-roadmap.md`，后续排期和取舍优先以本文档为准。

## 1. 产品定位

DataBox 的阶段性定位收敛为：

```text
DataBox = AI 问数版 Navicat
```

第一阶段不做完整 BI，也不做云端 SaaS，而是先做一个安装即用、本地运行、可连接远程数据库、安全可控的 AI 数据库客户端。

产品演进分三层：

```text
V1：AI 数据库客户端
V2：可信 AI 问数工具
V3：本地优先的轻量 ChatBI / Data Agent
```

核心原则：

```text
数据库密码不上传云端
真实查询结果不发给 LLM
SQL 执行发生在用户电脑
AI 只基于 Schema 和用户问题生成 SQL
所有 SQL 必须经过 Guardrail
生成 SQL 必须由用户确认后执行
```

## 2. 目标用户与第一阶段场景

优先服务三类用户：

| 用户 | 核心需求 |
|---|---|
| 运营人员 | 用自然语言查业务数据，不需要先学 SQL |
| 数据分析人员 | 更快探索数据，并能接管和修改生成 SQL |
| 开发 / 技术负责人 | 需要轻量、安全、可本地运行的数据库客户端 |

第一阶段重点场景：

```text
连接远程 MySQL / PostgreSQL / SQLite
浏览表结构和字段
执行安全 SELECT SQL
自然语言生成 SQL
查看表格结果
生成简单图表
保存查询历史
沉淀常用问法
```

暂时不优先做：

```text
复杂 Dashboard
自动归因分析
多 Agent
云端协作
多租户权限
企业级指标平台
```

## 3. 核心工作流

### SQL 工作流

```text
用户输入 SQL
↓
Guardrail 检查
↓
reject 禁止执行
↓
pass / warn 返回 safe_sql
↓
用户确认
↓
执行前二次 Guardrail
↓
执行 safe_sql
↓
返回表格结果
↓
写入 query_history
```

### AI 问数工作流

```text
用户自然语言提问
↓
Schema RAG 检索相关表和字段
↓
构造 Prompt
↓
LLM 生成 SQL
↓
Schema Validation 检查表字段是否幻觉
↓
Guardrail 审核
↓
SQL 展示到编辑器
↓
用户确认执行
↓
返回表格 / 图表
↓
沉淀到查询历史 / Golden SQL
```

RAG 演进路线：

```text
Schema RAG
↓
业务别名 RAG
↓
指标语义 RAG
↓
NL2QueryPlan2SQL
```

## 4. 性能边界

V1 按中小型业务数据库客户端设计，不承担数仓或 OLAP 平台能力。

默认边界：

```text
max_rows = 1000
max_columns = 100
max_cell_chars = 5000
max_response_bytes = 5MB
timeout = 10s
max_sql_length = 20000
```

优化顺序：

1. 限制返回行数、超时、响应大小
2. 分页查询、结果懒加载
3. 大结果导出 CSV
4. 查询计划提示 / 慢查询提示
5. 缓存常用 Schema 和查询历史

## 5. SQL 安全底线

V1 必须坚持：

```text
只允许 SELECT
不允许多语句
不允许 DDL
不允许 DML
不允许危险函数
不允许系统库访问
不允许文件读写
自动补 LIMIT
SELECT * 给 warning
执行前必须二次校验
```

后续安全增强：

```text
支持只读账号检测
连接测试时提示写权限风险
不同环境标识：dev / test / prod
生产环境执行更严格限制
敏感字段识别：password、token、secret、phone、email
高风险查询二次确认
查询结果脱敏展示
```

安全原则：

```text
AI 可以生成 SQL，但绝不能绕过 Guardrail。
```

## 6. AI 可靠性路线

AI 可靠性依赖工程体系，不只依赖模型能力。

当前体系：

```text
Schema RAG
Prompt 约束
SQL 提取
Guardrail
Schema Validation
Golden SQL 测试集
LLM 调用日志
```

后续路线：

| 阶段 | 能力 |
|---|---|
| 阶段 1 | Text-to-SQL：用户问题 -> Schema RAG -> SQL |
| 阶段 2 | Text-to-SQL + 校验：生成 SQL -> 表字段校验 -> Guardrail -> 用户确认 |
| 阶段 3 | Text-to-QueryPlan-to-SQL：问题 -> 指标/维度/时间/过滤 -> 确定性 SQL Compiler |
| 阶段 4 | 语义层增强：高频指标、业务别名、默认时间字段、Golden SQL 自动沉淀 |

采用 20/80 策略：

```text
20% 高频核心指标 -> 强语义层
80% 长尾探索问题 -> Schema RAG + Guardrail + 用户确认
```

## 7. 连接生命周期

完整闭环：

```text
新增数据源
↓
测试连接
↓
检测权限
↓
保存本地加密配置
↓
同步 Schema
↓
查询 / 问数
↓
连接状态监控
↓
重新同步
↓
删除数据源
```

阶段安排：

```text
V1.0：Direct MySQL / PostgreSQL / SQLite
V1.2：SSH Tunnel 稳定化
V1.3：SSL 连接完善
V1.4：连接健康检查
V1.5：多环境管理：dev / test / prod
```

## 8. 桌面体验

核心页面：

```text
数据源页
Schema 页
SQL / AI 问数页
查询历史页
轻量图表页
设置页
```

体验重点：

```text
启动快
连接配置简单
SQL 编辑器好用
错误提示清楚
Guardrail 结果可理解
AI 生成 SQL 可编辑
结果表格不卡顿
图表一键生成
查询历史可复用
```

AI 交互应展示“系统理解的问题结构”，而不仅仅展示 SQL：

```text
指标：销售额
维度：商品类目
时间：上个月
过滤：已支付订单
排序：销售额降序
```

## 9. 工程架构

保持本地优先的小核心：

```text
DataBox Desktop Client
├── Tauri 桌面壳
├── React 前端
└── Python Local Engine
    ├── FastAPI 本地接口
    ├── SQLite 本地元数据
    ├── 数据库连接
    ├── Schema 同步
    ├── SQL Guardrail
    ├── SQL Executor
    ├── Text-to-SQL
    ├── 查询历史
    └── LLM 调用
```

工程优先级：

1. 模块边界清晰
2. 本地 Engine 稳定启动和退出
3. API 契约稳定
4. 错误码体系
5. 测试覆盖 Guardrail / Schema Sync / Executor / AI

## 10. 数据与日志治理

默认原则：

```text
不上传数据库密码
不上传真实查询结果
LLM 不接收真实查询结果
默认不保存完整 Prompt
默认不保存完整 Response
错误信息脱敏
查询历史本地保存
```

本地日志分类：

| 日志 | 内容 |
|---|---|
| query_history | 用户问题、SQL、执行状态、耗时、行列数 |
| llm_logs | 模型、耗时、状态、prompt hash、schema warnings |
| guardrail_logs | 检查结果、警告、拒绝原因 |

后续补强：

```text
日志清理策略
敏感信息脱敏
本地导出诊断包
用户可一键清空历史
开发模式才保存完整 prompt / response
```

## 11. 发布路线

```text
V0.1 内测版：开发者可用，验证连接、SQL 执行、Schema 同步
V0.2 Alpha：加入 AI 问数、Guardrail、查询历史
V0.3 Beta：加入 SSH Tunnel、图表、Golden SQL
V1.0 正式版：稳定安装包、自动更新、错误诊断、基础文档
```

发布重点：

```text
跨平台打包
本地 Engine 启动稳定性
版本升级 migration
SQLite schema migration
崩溃日志本地收集
用户手动导出诊断信息
模型 API Key 配置检查
```

## 12. 商业护城河

短期护城河：

```text
AI 问数版 Navicat
本地运行
不上传数据库密码
不上传查询结果
SQL 安全可控
```

中期护城河：

```text
Schema RAG + Golden SQL
业务别名自动推荐
高频指标沉淀
用户修正反哺系统
```

长期护城河：

```text
本地语义层
可信 Query Plan
企业私有数据 Agent
跨数据库连接
轻量 BI 能力
```

最终目标：

```text
DataBox 不只是帮用户写 SQL，而是逐步成为理解用户数据库语义的本地 AI 数据助手。
```

## 13. 总体开发顺序

```text
1. 稳定数据库客户端底座
2. 做扎实 SQL Guardrail 和 Executor
3. 完成 Schema 同步和 Schema RAG
4. 接入 AI 问数，但必须人工确认 SQL
5. 加 Golden SQL 测试集和 LLM 日志
6. 加查询历史复用和常用查询
7. 加轻量图表和 CSV 导出
8. 加业务别名候选
9. 加高频指标沉淀
10. 从 NL2SQL 升级到 NL2QueryPlan2SQL
```

阶段目标：

```text
V1.0：安全可用的小型 Navicat
V1.1：可信的 AI SQL 生成器
V1.2：轻量报表和常用查询
V1.3：业务别名与 Golden SQL 沉淀
V2.0：本地优先的语义问数客户端
```
