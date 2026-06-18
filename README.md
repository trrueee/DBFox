# DBFox

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node.js 20.19+](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![Tauri 2](https://img.shields.io/badge/Tauri-2.x-24C8DB.svg)](https://tauri.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

**DBFox — 本地优先、AI 原生的数据库工作台。**

数据源管理、Schema 浏览、SQL 控制台、对话式问数 Agent 和执行安全策略，集成在同一个桌面应用里。

---

## 核心能力

### 数据源与 Schema

- MySQL、PostgreSQL、SQLite 连接，支持直连 / SSH 隧道 / SSL
- 连接测试、健康检查、Schema 同步、ER 图数据

### SQL 控制台

- Monaco 编辑器，SQL 校验、执行、EXPLAIN、取消
- 查询历史记录，结果集行/列/大小限制

### AI 问数 Agent

- LangGraph / ReAct 本地 Agent Runtime
- 工具链: `db.observe` → `db.search` → `db.inspect` → `db.preview` → `db.query` → `db.remember`
- TrustGate 安全校验 + 审批机制：SELECT-only、危险函数拦截、生产环境二次确认

### 安全模型

- 本地 Token 鉴权，Origin 校验
- Guardrail + TrustGate 双重 SQL 安全门
- 数据库密码加密存储
- 默认只读执行 + 高风险操作需人工确认

---

## 技术架构

```
┌────────────────────────────────────────────────┐
│ Desktop UI                                     │
│ React 19 + TypeScript + Vite + Tauri 2         │
└──────────────────────┬─────────────────────────┘
                       │ HTTP + SSE (X-Local-Token)
┌──────────────────────┴─────────────────────────┐
│ Local Engine (FastAPI @ 127.0.0.1:18625)       │
│ API Router / Policy / SQL Executor / Agent     │
└──────────────────────┬─────────────────────────┘
                       │ DB Driver / SSH / SSL
┌──────────────────────┴─────────────────────────┐
│ Datasources (MySQL / PostgreSQL / SQLite)      │
└────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.12+ ([Anaconda](https://www.anaconda.com/) 推荐)
- Node.js 20.19+
- Rust Toolchain（仅桌面打包需要）

### 开发模式

```bash
# 1. 安装依赖
pip install -r requirements.txt
cd desktop && npm install && cd ..

# 2. 启动开发模式（Tauri 会自动拉起引擎 sidecar）
cd desktop && npm run tauri dev
```

### LLM 配置

1. 前端右上角「设置 → LLM 配置」
2. 填写 API Key、Base URL、Model Name
3. 保存后即可使用 AI 问数

---

## 打包

```bash
# 1. 创建纯净构建环境（一次性）
python -m venv .build_venv
.build_venv\Scripts\pip install -r requirements.txt pyinstaller

# 2. 构建引擎 sidecar
.build_venv\Scripts\python build_sidecar.py

# 3. 构建桌面安装包
cd desktop && npm run tauri -- build
```

产物：`desktop/src-tauri/target/release/bundle/msi/` 和 `nsis/`

安装后若出现白屏，检查 `%TEMP%/dbfox-sidecar.log`。

---

## 项目结构

```
.
├── engine/                    # Python 后端 (FastAPI + LangGraph Agent)
│   ├── main.py                # 入口
│   ├── api/                   # REST API routers
│   ├── agent/                 # ReAct Agent graph + nodes
│   ├── sql/                   # SQL executor + guardrail + TrustGate
│   ├── tools/                 # Agent 工具注册 (db_tools, memory_tools, …)
│   ├── semantic/              # Schema linker + context builder
│   ├── environment/           # Environment / schema tools
│   ├── memory/                # Long-term memory store
│   ├── policy/                # Data redactor
│   ├── models.py              # SQLAlchemy ORM models
│   ├── db.py                  # DB init + Alembic migration
│   └── tests/                 # pytest
├── desktop/                   # 前端 + Tauri 桌面壳
│   ├── src/                   # React + TypeScript
│   │   ├── features/          # agentTask, datasource, workspace
│   │   ├── components/        # UI 组件 (SqlEditor, ChartPanel, …)
│   │   ├── lib/api/           # API client
│   │   └── pages/             # DataSourcesPage, AgentEvalPage
│   └── src-tauri/             # Tauri 2 Rust shell
├── docs/                      # 设计文档
├── build_sidecar.py           # PyInstaller 引擎打包脚本
├── requirements.txt           # Python 依赖
└── README.md
```

---

## Agent 工具链

当前 Agent 使用以下工具（注册于 `engine/tools/dbfox_tools.py`）：

| 工具组 | 工具 | 作用 |
|--------|------|------|
| db | `db.observe` | 观察 catalog：表、列、外键、行数 |
| db | `db.search` | 语义搜索匹配表和字段 |
| db | `db.inspect` | 检查单表结构、索引、外键 |
| db | `db.preview` | 预览样本数据（含敏感字段脱敏） |
| db | `db.query` | 生成 + 校验 + 执行 SQL |
| db | `db.remember` | 记录 schema 别名、业务语义 |
| schema | `schema.list_tables` | 列出活动数据源的所有表 |
| schema | `schema.describe_table` | 描述表结构 |
| memory | `memory.search/write/delete` | 长期记忆 CRUD |
| escalate | `escalate.tool_group` | Agent 自行提升工具权限 |

---

## 常用命令

```bash
# 后端测试
pytest engine/ -q --ignore=engine/agent/tests/test_e2e_qwen.py

# 前端测试
cd desktop && npm test

# 前端 TypeScript 检查
cd desktop && npx tsc --noEmit

# 构建前端（仅 Vite）
cd desktop && npm run build

# 清理 + 完整打包
rm -rf pyinstaller_dist pyinstaller_build
.build_venv\Scripts\python build_sidecar.py
cd desktop && npm run tauri -- build
```

---

## License

MIT
