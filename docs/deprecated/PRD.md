# DataBox 产品需求文档

更新时间：2026-05-25

## 1. 背景

DataBox 面向需要安全访问业务数据库的人群，提供一个本地运行的数据库客户端，并在客户端内加入可信 AI 问数能力。

产品的关键判断是：

```text
先把本地安全数据库客户端做扎实
再把 AI 问数做可信
最后从 Schema RAG 逐步升级到轻量语义层
```

## 2. 产品目标

阶段性目标：

```text
DataBox = AI 问数版 Navicat
```

V1 不是 BI 平台，不是云端 SaaS，不要求客户部署服务器。用户安装桌面客户端后，本机直接连接数据库，SQL 在本机执行，AI 只参与生成和辅助理解。

## 3. 用户画像

| 用户 | 需求 | 成功标准 |
|---|---|---|
| 运营人员 | 不会 SQL，也能问业务数据 | 能用自然语言得到可确认的 SQL 和表格结果 |
| 数据分析人员 | 会 SQL，但希望探索更快 | AI 生成 SQL 后可编辑、可复用、可沉淀 |
| 开发 / 技术负责人 | 需要轻量安全的数据库客户端 | 密码、结果集、执行链路都在本地可控 |

## 4. 核心范围

V1 必须支持：

```text
数据源连接
连接测试
本地加密保存连接信息
Schema 同步
表结构浏览
SQL 编辑
Guardrail 审核
安全 SELECT 执行
查询结果表格
查询历史
AI 生成 SQL
Schema Validation
Golden SQL 回归
LLM 调用日志
轻量图表
CSV 导出
```

V1 暂不支持：

```text
复杂 BI Dashboard
自动报表调度
云端保存查询结果
自动执行 AI SQL
多租户权限
企业级指标平台
大规模向量库
多 Agent 自动分析
```

## 5. 关键用户流程

### 5.1 新增数据源

```text
填写连接信息
↓
测试连接
↓
检测只读权限和高危权限
↓
本地加密保存
↓
同步 Schema
↓
进入查询工作台
```

验收标准：

```text
连接失败时错误可读
存在写权限时给风险提示
密码不出现在日志和诊断信息中
Schema 同步失败时保留旧缓存
```

### 5.2 手写 SQL 查询

```text
用户输入 SQL
↓
Guardrail 检查
↓
展示 pass / warn / reject
↓
用户确认
↓
执行前二次校验
↓
执行 safe_sql
↓
展示结果并写入历史
```

验收标准：

```text
危险 SQL 被拒绝
无 LIMIT 查询被自动补 LIMIT
SELECT * 给 warning
结果大小、行数、耗时受限制
查询历史不保存真实结果集
```

### 5.3 AI 问数

```text
用户自然语言提问
↓
Schema RAG 找相关表字段
↓
返回问题理解结构
↓
LLM 生成 SQL
↓
Schema Validation
↓
Guardrail
↓
SQL 放入编辑器
↓
用户确认执行
```

验收标准：

```text
LLM 不接收真实查询结果
生成 SQL 不会自动执行
表字段幻觉会被提示或拒绝
用户能编辑 AI SQL
失败时不影响手写 SQL 工作流
```

## 6. 安全要求

SQL Guardrail 必须阻止：

```text
多语句
DDL
DML
危险函数
系统库访问
文件读写
超长 SQL
```

数据安全要求：

```text
数据库密码本地加密保存
不上传真实查询结果
默认不保存完整 Prompt
默认不保存完整 Response
错误信息脱敏
本地日志可清理
可导出脱敏诊断包
```

## 7. 性能要求

默认限制：

```text
max_rows = 1000
max_columns = 100
max_cell_chars = 5000
max_response_bytes = 5MB
timeout = 10s
max_sql_length = 20000
```

体验要求：

```text
结果表格在默认限制内不卡顿
长查询可取消
失败查询有明确错误提示
大结果优先导出，不在 UI 中强行渲染
```

## 8. 日志与审计

本地日志分三类：

| 日志 | 记录内容 |
|---|---|
| query_history | 用户问题、SQL、执行状态、耗时、行列数 |
| llm_logs | 模型、耗时、状态、prompt hash、schema warnings |
| guardrail_logs | 检查结果、警告、拒绝原因 |

默认不记录：

```text
数据库密码
完整 DSN
真实查询结果
完整 Prompt
完整 LLM Response
```

## 9. 版本验收

### V1.0

```text
可以作为本地数据库客户端安全使用
可以连接数据源、同步 Schema、手写 SQL、执行安全 SELECT
Guardrail 和 Executor 形成闭环
查询历史可追踪
本地 Engine 稳定启动和退出
```

### V1.1

```text
可以自然语言生成 SQL
生成 SQL 经过 Schema Validation 和 Guardrail
用户确认后才能执行
Golden SQL 不少于 30 条
LLM 失败不影响基础 SQL 工作流
```

### V1.2

```text
常用查询可保存复用
查询结果可 CSV 导出
简单图表可生成和恢复
不进入复杂 BI 或定时报表
```

### V1.3

```text
支持业务别名候选和确认
支持高频指标候选沉淀
Golden SQL 可资产化维护
```

## 10. 成功指标

产品成功指标：

```text
首次连接成功率
Schema 同步成功率
危险 SQL 拦截率
AI 生成 SQL 可执行率
Golden SQL 结构命中率
查询历史复用率
用户手动修正 SQL 的沉淀率
```

质量成功指标：

```text
核心后端测试稳定通过
前端构建稳定通过
Guardrail 绕过用例持续回归
LLM 日志默认不泄露敏感信息
诊断包默认脱敏
```
