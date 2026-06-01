# 📦 DataBox — 本地优先的可信 Text-to-SQL 数据探索客户端 (Local-First Trusted Text-to-SQL Data Exploration Client)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node.js 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Security: Guardrails Built-in](https://img.shields.io/badge/security-guardrails%20active-red.svg)]()

> **DataBox** 是一款面向运营、业务和数据分析人员的 **本地优先可信 Text-to-SQL 数据探索桌面客户端**。系统基于本地 Schema 语义层、SQL 安全校验和注解式 SQL Action Engine，实现了自然语言智能问数、SQL 生成、执行编排、结果可视化，并通过 Spider / BIRD / Golden SQL 标准测试集对 SQL 生成效果进行量化评估与诊断。

[English Summary](#english-documentation) | [中文系统架构说明](#chinese-documentation)

---

<a name="chinese-documentation"></a>

## 🌟 核心设计定位

DataBox 并不是简单的“大模型生成 SQL 演示工具”，而是一个将**本地优先安全理念**与**严谨的编译执行编排管线**深度结合的数据探索平台。其核心能力围绕以下四大维度展开：
1. **轻量 Schema 语义层**：基于 Workspace 工作区限定 RAG 检索范围，结合 Schema Linking 实现业务别名、同义词和库值检索，彻底解决 NL（自然语言）歧义和幻觉。
2. **三道门可信校验锁 (Trust Gate)**：提供 Schema Validation 字段校验、AST 安全围栏拦截，并结合 Revise Agent 机制实现 SQL 报错的自动提示与自愈建议。
3. **注解式编排执行管线 (SQL Action Engine)**：提供基于 `@` DSL 注解的插件化编排框架，支持对查询结果执行限流、超时挂起、自动下载、图表可视化的全阶段声明式控制。
4. **量化评测体系 (Evaluation Harness)**：深度集成 Spider、BIRD Mini-Dev 等全球顶级 Text-to-SQL 指标评测集，提供 EX、Valid SQL、Rerank Recall 等多重维度量化指标报告。

---

## 🏗️ 十层系统整体架构设计

DataBox 采用高内聚、分层解耦的架构设计，整体数据流与编排逻辑如下所示：

```text
       自然语言问题 (NL) / 原始 SQL 输入 + @快捷指令
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [1] Workspace Scope Layer                        │   ◄── 限定业务域，限定表范围，缩减 Context Token
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [2] Lightweight Semantic Layer                   │   ◄── 业务别名、同义词语义关联、高频计算指标定义
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [3] Schema Linking / Schema RAG                  │   ◄── 基于 TF-IDF/Embedding 与库值检索，召回表/字段
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [4] Query Plan Layer (结构化查询计划)             │   ◄── CoT 推理链，拆解指标、维度、过滤、排序，降低幻觉
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [5] Text-to-SQL Generator Layer                  │   ◄── 智能生成 SQL / 离线 Heuristic 模板规则 Fallback
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [6] Trust Gate Layer (安全可信校验)               │   ◄── Schema 验证 + AST 安全围栏 + Revise Agent 自愈
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [7] SQL Action Engine                            │   ◄── @limit/@timeout/@export/@chart 编排生命周期管线
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [8] Local Engine Layer                           │   ◄── FastAPI / SQLAlchemy / AES-256-GCM 远程直连
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [9] Interactive Presentation Layer               │   ◄── Monaco 编辑器 + ECharts 图表渲染 + CSV/JSON 自动下载
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ [10] Evaluation Harness                          │   ◄── Spider / BIRD Mini-Dev 量化评测 Execution Accuracy
└──────────────────────────────────────────────────┘
```

---

## ⚡ 核心子系统解析

### 1. 工作区 (Workspace) 与轻量语义层 (Semantic Layer)
为了解决大型数据库表关系极其复杂、字段冗余导致的“上下文窗口爆炸”与“模型幻觉”问题，DataBox 设计了：
*   **Workspace 工作区隔离**：允许用户按业务模块（例如“财务工作区”、“运营工作区”）限定问数的表范围，极大地缩减了 Prompt 的 Token 消耗。
*   **Schema Linking 机制**：将自然语言中的实体名词与表注释、字段注释、高频别名及数据库特定列值进行精准关联，甚至解决错别字与同义词歧义，确保召回表结构的 Recall 指标维持在极高水准。

### 2. 三道可信校验门锁 (Trust Gate) 与 Revise Agent
为确保 AI 生成 SQL 的“绝对可信性”与“系统安全性”，执行流必须经过严密的漏斗校验：
*   **第一道门：Schema Validation**。在前端解析 SQL AST，校验 AI 是否引用了虚构的表名或字段名，从根源拦截幻觉报错。
*   **第二道门：SQL Guardrail (AST 拦截)**。运行基于 `sqlglot` 的纯本地语法分析引擎，强力拦截 DDL、危险 DML、无条件更新或隐式全表扫描行为。
*   **第三道门：Human Confirmation 与 Revise Agent 自愈**。危险写操作或重构操作需经过用户双阶段显式确认。若数据库执行报错，系统会抓取 Error 信息，通过 `Revise Agent` 闭环自动给出修复建议，引导用户确认并一键重新执行。

### 3. 注解式快捷操作引擎 (SQL Action Engine)
Action Engine 是前端控制台交互的编译中枢，采用 Registry + Processor 插件化架构，将指令解析执行抽象为 compile、beforeExecute、aroundExecute、afterExecute 四个阶段：
*   **`@limit [rows]`**：自动重写并限制返回行数，防范海量数据吞吐。
*   **`@timeout [seconds]`**：设置客户端等待上限，并在超时时请求后端取消执行。
*   **`@explain`**：自动改写为执行计划评估模式，方便开发排查慢查询与索引命中的性能瓶颈。
*   **`@export [csv/json]`**：查询成功后自动进行本地数据序列化，即时触发浏览器下载保存，实现指令级自动归档。
*   **`@chart [bar/line/pie] x=列名 y=列名`**：查询成功后自动解析坐标列，将数据转换为 ECharts 图表，同数据表格并列渲染，可视化体验极佳。

---

## 🧪 Evaluation Harness (量化评测体系)

DataBox 自带完备的基准评测中心，用于解决 Text-to-SQL 落地过程中的“准确度无法量化评估”问题：

| 评测数据集 (Dataset) | 包含规模 (Scale) | 评测核心用途 (Purpose) |
| :--- | :--- | :--- |
| **Spider (跨域经典集)** | 10,181 组问题 / 200 个复杂多表 Schema | 评测系统在陌生领域及复杂多表关联 SQL 上的泛化生成能力 |
| **BIRD Mini-Dev (专业级实战集)** | 500 个高质量样例 / 支持多方言 | 评测真实复杂业务数据库、大数据量以及多方言下的实际执行准确率 |
| **自建 Golden SQL (业务预设集)** | 业务定制的高频问数指标和标准解答 | 评测系统在自身电商 / 订单 / 运营业务下的特定表现与准确度 |

### 量化评测指标 (Core Metrics)
在 DataBox 评测中心运行 Benchmark，会自动生成包含以下指标的结构化诊断报告：
1.  **Execution Accuracy (EX)**: 生成 SQL 的实际执行结果与标准 SQL 的数据比对一致性。
2.  **Valid SQL Rate**: 生成 SQL 的可解析性及成功运行率。
3.  **Schema Linking Recall**: 标准表和字段被语义层成功召回的比例。
4.  **Hallucination Rate**: 生成 SQL 引用不存在的表或字段的比例。
5.  **Guardrail Pass Rate**: 生成 SQL 成功通过本地 AST 安全围栏校验的比例。
6.  **Prompt Compression Ratio**: 召回后 Schema token 占用与数据库完整 Schema 相比的压缩比率。
7.  **P95 Latency**: SQL 智能生成与编译计划生成的 P95 响应延迟。
8.  **Revise Success Rate**: 报错 SQL 经 `Revise Agent` 修正提示后成功运行的比例。

---

## 📂 项目模块与目录结构

```text
DataBox/
├── desktop/                    # 前端及 Tauri 桌面壳代码
│   ├── src/                    # React 开发源码
│   │   ├── components/         # 核心可重用组件 (Monaco SQL编辑器、ER图、AI面板、数据表等)
│   │   │   ├── QueryActionPlanPreview.tsx # 【新增】注解执行计划预览卡 (SQL Diff 对比)
│   │   │   └── ChartPanel.tsx  # 支持 @chart 默认预设的 ECharts 可视化图表面板
│   │   ├── pages/              # 系统主页面 (工作台、数据源、备份管理、Dashboard等)
│   │   ├── hooks/              # 封装的数据请求与查询执行 hooks
│   │   └── lib/                
│   │       └── query-actions/  # 【重构】DSL 注解式编排执行引擎核心包
│   │           ├── types.ts    # 管线运行时类型、诊断 Issue 与 Extended Meta Autocomplete
│   │           ├── registry.ts # 统一微插件指令注册表
│   │           ├── index.ts    # 模块暴露总入口
│   │           └── processors/ # 独立的单职责 Processor 插件 (limit, timeout, chart 等)
│   └── src-tauri/              # Rust Tauri 桌面分发配置及安全策略
├── engine/                     # Python 本地安全及 AI 问数引擎
│   ├── semantic/               # 【新增规划】轻量级 Schema 语义层 (工作区、Linker、QueryPlan)
│   ├── evaluation/             # 【新增规划】Evaluation Harness (BIRD/Spider/Golden 加载与评测)
│   ├── api/                    # FastAPI 路由端点 (数据源、表结构设计、备份、AI问数等)
│   ├── policy/                 # 安全策略定义 (双阶段确认引擎、敏感字段脱敏、脱敏管理器)
│   ├── tests/                  # 包含 190+ 测试用例的完整自动化测试套件
│   ├── ai.py                   # 大语言模型接口对接与 Schema 精准检索
│   ├── crypto.py               # AES-256-GCM 编解码与秘钥本地管理
│   ├── db.py                   # 本地 SQLite 元数据库初始化及 Session 管理
│   └── guardrail.py            # 基于 AST 语法分析的本地 SQL 安全围栏
├── docs/                       # 系统核心设计、PRD、路线图及开发指南
│   ├── v1_development_guide.md # V1 核心开发指导文档
│   └── walkthrough_22nd_round.md # 第22轮迭代：生产稳定性确认绕过设计归档
├── start.py                    # 【快速启动】本地一键启动助手 (拉起前后端服务并在浏览器中打开)
├── run_desktop.py              # 【快速启动】本地 Native 独立窗口渲染启动器 (pywebview 驱动)
├── pyproject.toml              # Python 项目 mypy 类型检查及环境配置
└── requirements.txt            # Python 后端运行核心依赖列表
```

---

## ⚡ 快速启动指南

### 1. 环境依赖准备
确保您的计算机上已安装以下环境：
*   **Python**: 3.12 或更高版本 (推荐使用 Conda 或 venv 管理虚拟环境)
*   **Node.js**: 18.x 或更高版本 (前端构建及包管理工具)

### 2. 一键启动 (Web 开发版)
在项目根目录下执行以下命令，启动助手会自动为您校验并安装 Python 和 Node 依赖，并自动拉起 Local Engine 后端和 Vite 前端，最后在您的系统默认浏览器中打开页面：
```bash
python start.py
```
*   **安全后端监听**: `http://127.0.0.1:18625`
*   **前端开发页面**: `http://localhost:5173`
*   *提示：进入页面后，可直接点击“一键秒连演示库”秒级加载包含 20 张表的示例库进行 AI 问数安全测试。*

### 3. 一键启动 (原生桌面窗口版)
如果您希望像使用 Navicat 桌面软件一样，在一个独立且具备硬件加速的 Native App 窗口中操作 DataBox，可执行：
```bash
python run_desktop.py
```
这会调用系统的 `pywebview` 引擎，拉起精美的无边框独立窗口，加载完整的桌面极客体验。

---

## 🧪 自动化测试验证

DataBox 拥有极高测试覆盖率的高标准自动化测试集（共 **194 个核心测试**），覆盖密码加密、AST安全过滤、敏感数据模糊脱敏、SSL双向握手、备份还原以及多阶段确认策略。

在根目录下运行以下命令，即可执行完整的测试套件：
```bash
python -m pytest engine/tests
```

---

<br/>
<hr/>

<a name="english-documentation"></a>

## 🌟 Core Philosophy & Security Principles

DataBox is a **local-first trusted Text-to-SQL database exploration client** built ground-up on the philosophy of **"No DB Passwords to Cloud, All Actions Executed Locally"**:

*   **Workspace-Isolation**: Limit AI schema retrieval domain scope based on business categories, compressing prompt token sizes and eliminating hallucination from unrelated fields.
*   **Schema Linking Layer**: Precision-maps natural language nouns to schema comments, aliases, and specific database column values. Resolves dictionary ambiguity and typos.
*   **Trust Gate Funnel**: Passes compiled SQL queries through a rigorous verification funnel, including Schema Validation (checks for fake table/column names), AST-based local Guardrails (`sqlglot`), and error self-healing options guided by a `Revise Agent`.
*   **Plugin-Based Action Engine**: Extensible Registry orchestrating directive lifecycles: `@limit` (compiles SELECT limits), `@timeout` (prevents physics connections hanging), `@explain` (reveals execution plan), `@export` (triggers automated download), and `@chart` (renders visual charts using ECharts).
*   **Text-to-SQL Evaluation Harness**: Benchmark generation metrics using Spider and BIRD Mini-Dev (500 cases), calculating EX (Execution Accuracy), Valid SQL rate, Rerank Recall, and average generation latency.
