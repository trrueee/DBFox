# DataBox

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node.js 20.19+](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![Tauri 2](https://img.shields.io/badge/Tauri-2.x-24C8DB.svg)](https://tauri.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

**DataBox 是一个本地优先、AI 原生的数据库工作台。**

它把数据源管理、Schema 浏览、SQL 控制台、结果分析、对话式问数 Agent 和执行安全策略放在同一个桌面应用里。目标不是替代数据库本身，而是为分析师、开发者和数据团队提供一个可信的本地操作台：先理解数据，再生成 SQL，最后在可审计、可回滚、可审批的边界内执行。

---

## 目录

- [核心能力](#核心能力)
- [技术架构](#技术架构)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [LLM 配置](#llm-配置)
- [常用命令](#常用命令)
- [API 概览](#api-概览)
- [Agent 运行时](#agent-运行时)
- [安全模型](#安全模型)
- [开发状态](#开发状态)
- [License](#license)

---

## 核心能力

### 1. 数据源与 Schema 工作台

- 支持 **MySQL、PostgreSQL、SQLite** 数据源连接。
- 支持直连、SSH 隧道、MySQL SSL 证书配置。
- 支持连接测试、健康检查、Schema 同步、表/字段浏览、ER 图数据生成。
- 支持数据源删除的二次确认，降低误操作风险。

### 2. SQL 控制台

- SQL 校验、执行、EXPLAIN、取消执行。
- 查询历史记录，可按数据源、状态、关键字过滤。
- 执行结果做行数、列数、单元格长度和响应体大小限制，避免本地 UI 被超大结果集拖垮。
- 所有 SQL 执行都会进入策略层和 TrustGate，不直接裸奔到数据库。

### 3. AI 问数 Agent

- 基于 LangGraph / ReAct 的本地 Agent Runtime。
- Agent 能读取当前数据源、已选表、Schema、语义上下文和对话历史。
- 支持自然语言问数、SQL 生成、SQL 修复、结果解释、后续追问。
- 支持 SSE 流式事件，把计划、工具调用、产物、审批状态同步到前端时间线。
- 高风险动作进入人工审批，用户确认后才继续。

### 4. 桌面级交互

- React + TypeScript + Vite 前端。
- Tauri 2 桌面壳，支持无浏览器的原生窗口体验。
- Monaco SQL 编辑器、ECharts 图表、Radix UI 组件、工作区 Tabs、命令面板、对话历史、Agent 评测页面。

### 5. Agent 评测与可观测性

- Agent Run、事件、产物、Trace、Checkpoint、审批记录均有 API。
- 内置 Agent Eval 入口，可维护评测任务、导入 benchmark、运行评测并查看 case。
- 适合持续验证 Agent 在真实数据库 Schema 下的可靠性。

---

## 技术架构

DataBox 由三层组成：

```text
┌─────────────────────────────────────────────────────────────┐
│ Desktop UI                                                   │
│ React + TypeScript + Vite + Tauri                            │
│ 工作区 / 数据源管理 / SQL 控制台 / Agent 问数 / 评测页面       │
└───────────────────────────────▲─────────────────────────────┘
                                │ HTTP + SSE + X-Local-Token
┌───────────────────────────────┴─────────────────────────────┐
│ Local Engine                                                  │
│ FastAPI @ 127.0.0.1:18625                                     │
│ API Router / Policy / SQL Executor / Schema Sync / Persistence│
└───────────────────────────────▲─────────────────────────────┘
                                │ DB Driver / SSH Tunnel / SSL
┌───────────────────────────────┴─────────────────────────────┐
│ Datasources                                                   │
│ MySQL / PostgreSQL / SQLite                                   │
└─────────────────────────────────────────────────────────────┘
```

Agent 不是单独的云服务，它运行在本地 Engine 里，只在需要模型推理时访问你配置的 OpenAI-compatible LLM Provider。

---

## 项目结构

```text
.
├── start.py                     # 一键开发启动器：安装依赖、启动 Engine 和前端
├── requirements.txt             # 后端运行依赖
├── requirements-dev.txt         # 后端测试 / 类型检查依赖
├── pyproject.toml               # pytest / mypy 配置
├── engine/                      # FastAPI Local Engine
│   ├── main.py                  # Engine 入口、本地 Token、中间件、路由挂载
│   ├── api/                     # /api/v1 路由：datasources/query/agent/eval/semantic 等
│   ├── agent/                   # LangGraph Agent：节点、图、工具、规划、修复、技能
│   ├── agent_core/              # Agent 通用类型、持久化、事件、运行时门面
│   ├── datasource.py            # DB 连接、SSH 隧道、健康检查
│   ├── environment/             # 环境解析、方言、Schema introspection、工具
│   ├── memory/                  # 会话记忆、长期存储、压缩与检索
│   ├── policy/                  # 查询策略、确认机制、脱敏
│   ├── semantic/                # 语义层：别名、指标、维度、表范围
│   └── sql/                     # SQL 校验、TrustGate、执行、历史记录
└── desktop/                     # React + Tauri 客户端
    ├── package.json             # 前端脚本和依赖
    ├── src/                     # UI、工作区、Agent Bridge、Engine API Client
    └── src-tauri/               # Tauri 2 配置和桌面打包资源
```

---

## 快速开始

### 环境要求

- Python **3.12+**
- Node.js **20.19+**
- npm
- Rust Toolchain（仅 Tauri 桌面开发/打包需要）

### 一键启动开发环境

```bash
python start.py
```

启动器会做三件事：

1. 安装或检查 Python 后端依赖。
2. 安装或检查 `desktop/node_modules`。
3. 启动后端 Engine 和前端 Vite Dev Server。

默认地址：

```text
Backend:  http://127.0.0.1:18625
Frontend: http://localhost:5173
```

### 手动启动

后端：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m engine.main --reload
```

前端：

```bash
cd desktop
npm install
npm run dev
```

浏览器访问：

```text
http://localhost:5173
```

### 启动 Tauri 桌面应用

开发模式下需要先生成 Token（否则 Engine 认证会失败）：

```bash
# 生成开发用 Token
python build_sidecar.py --token-only

cd desktop
npm install
npm run tauri -- dev
```

构建桌面应用（完整打包流程）：

```bash
# 从项目根目录执行

# 1. 安装 Python 依赖及 PyInstaller
pip install -r requirements.txt
pip install pyinstaller

# 2. 构建 Python sidecar + 生成静态 Token
python build_sidecar.py

# 3. 构建 Tauri 桌面安装包
cd desktop
npm install
npm run tauri -- build
```

清理并重新打包：

```bash
# Windows PowerShell
Remove-Item -Recurse -Force desktop/dist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force desktop/src-tauri/target -ErrorAction SilentlyContinue
Remove-Item -Force engine/token_preset.py -ErrorAction SilentlyContinue
Remove-Item -Force desktop/.env.local -ErrorAction SilentlyContinue

# 然后重新执行上述三个步骤
python build_sidecar.py
cd desktop && npm run tauri -- build
```

打包产物位于：

```text
desktop/src-tauri/target/release/bundle/msi/DataBox_1.0.0_x64_en-US.msi
desktop/src-tauri/target/release/bundle/nsis/DataBox_1.0.0_x64-setup.exe
```

若安装后出现白屏，请检查 `%TEMP%/databox-sidecar.log` 确认后端引擎是否启动成功。

### 更新应用图标

```bash
cd desktop

# 从 1024x1024 PNG 源文件生成所有平台图标
npm run tauri -- icon ../assets/fox-icon-source.png
```

图标素材位于 `desktop/public/assets/fox/`，Tauri 图标输出到 `desktop/src-tauri/icons/`。

---

## LLM 配置

DataBox 使用 OpenAI-compatible Chat API。你可以在前端「LLM 配置」里填写 API Key、Base URL 和模型名，也可以通过根目录 `.env` 设置：

```bash
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4o-mini
```

兼容环境变量：

```bash
QWEN_API_KEY=...
DATABOX_LLM_API_KEY=...
```

说明：

- `OPENAI_API_BASE` 可指向 OpenAI、Qwen、DeepSeek 或本地 OpenAI-compatible 服务。
- 推理类模型会自动避免传入不兼容的 `temperature` / `max_tokens` 参数。
- 没有配置 API Key 时，Agent 会拒绝运行并在 UI 中提示用户完成配置。

---

## 常用命令

### 后端

```bash
# 安装运行依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt

# 启动 Engine
python -m engine.main --reload

# 运行测试
python -m pytest

# 跳过 E2E 测试
python -m pytest -m "not e2e"

# 类型检查
python -m mypy engine
```

### 前端

```bash
cd desktop

# 开发服务器
npm run dev

# 单元测试
npm test

# 监听测试
npm run test:watch

# ESLint
npm run lint

# 生产构建
npm run build

# Vite 预览
npm run preview
```

---

## API 概览

所有业务接口都挂载在 `/api/v1` 下。

### Health

```http
GET /api/v1/health
```

### Projects & Datasources

```http
GET    /api/v1/projects
POST   /api/v1/projects
POST   /api/v1/datasources/test
POST   /api/v1/datasources
GET    /api/v1/datasources
POST   /api/v1/datasources/{id}/health
DELETE /api/v1/datasources/{id}
POST   /api/v1/datasources/{id}/sync
```

### Schema

```http
GET /api/v1/schema/tables
GET /api/v1/schema/tables/{table_id}/columns
GET /api/v1/schema/er-diagram
```

### Query

```http
POST   /api/v1/query/validate
POST   /api/v1/query/execute
POST   /api/v1/query/explain
POST   /api/v1/query/cancel
GET    /api/v1/query/history
DELETE /api/v1/query/history/{history_id}
DELETE /api/v1/query/history
```

### Agent

```http
POST /api/v1/agent/llm/test
POST /api/v1/agent/run
POST /api/v1/agent/run/stream
GET  /api/v1/agent/runs/{run_id}
GET  /api/v1/agent/runs/recent
POST /api/v1/agent/runs/{run_id}/resume
POST /api/v1/agent/runs/{run_id}/resume/stream
POST /api/v1/agent/runs/{run_id}/cancel
GET  /api/v1/agent/runs/{run_id}/artifacts
GET  /api/v1/agent/runs/{run_id}/events
GET  /api/v1/agent/runs/{run_id}/trace
GET  /api/v1/agent/runs/{run_id}/approvals
POST /api/v1/agent/runs/{run_id}/approvals/{approval_id}
GET  /api/v1/agent/runs/{run_id}/checkpoints
GET  /api/v1/agent/sessions/{session_id}/runs
```

### Conversations

```http
GET    /api/v1/conversations
PUT    /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
```

### Semantic Layer

```http
GET    /api/v1/semantic/aliases
POST   /api/v1/semantic/aliases
PUT    /api/v1/semantic/aliases/{id}
DELETE /api/v1/semantic/aliases/{id}

GET    /api/v1/semantic/metrics
POST   /api/v1/semantic/metrics
PUT    /api/v1/semantic/metrics/{id}
DELETE /api/v1/semantic/metrics/{id}

GET    /api/v1/semantic/dimensions
POST   /api/v1/semantic/dimensions
PUT    /api/v1/semantic/dimensions/{id}
DELETE /api/v1/semantic/dimensions/{id}

GET    /api/v1/semantic/table-scope
POST   /api/v1/semantic/table-scope
```

### Agent Eval

```http
GET    /api/v1/agent-eval/tasks
POST   /api/v1/agent-eval/tasks
PUT    /api/v1/agent-eval/tasks/{task_id}
DELETE /api/v1/agent-eval/tasks/{task_id}
POST   /api/v1/agent-eval/import-benchmark
POST   /api/v1/agent-eval/run
GET    /api/v1/agent-eval/runs
GET    /api/v1/agent-eval/runs/{eval_run_id}
GET    /api/v1/agent-eval/runs/{eval_run_id}/cases
```

### Backup

```http
GET  /api/v1/projects/{project_id}/backups
POST /api/v1/backups
GET  /api/v1/backups/{backup_id}
POST /api/v1/backups/{backup_id}/restore-precheck
POST /api/v1/backups/{backup_id}/restore
```

---

## Agent 运行时

DataBox Agent 是一个带策略门控的 LangGraph StateGraph。典型流程如下：

```text
START
  ↓
planner
  ↓
model
  ↓
policy ──需要确认──▶ approval
  ↓                    ↓
tools ◀────────────────┘
  ↓
observe
  ↓
progress ──需要修复──▶ repair ──▶ model
  ↓
finalize
  ↓
END
```

关键节点：

- **planner**：理解用户意图，生成任务类型、工具范围、执行模式。
- **model**：基于计划调用 LLM，进行 ReAct 推理与工具调用。
- **policy**：校验工具调用是否符合安全策略。
- **approval**：高风险动作进入人工审批。
- **tools**：执行已批准工具，包括 Schema、SQL、结果画像、图表建议等。
- **observe**：把工具结果绑定回 Agent State，并生成结构化 Artifacts。
- **progress**：判断任务是否完成、继续、重规划、澄清或失败。
- **repair**：针对 SQL / Schema / 执行失败准备修复上下文。
- **finalize**：输出最终回答并持久化运行轨迹。

---

## 安全模型

DataBox 的默认安全边界是：**本地优先、最小权限、先验证再执行、必要时人工确认**。

### 本地访问控制

- Engine 绑定本地端口 `18625`。
- 启动时生成高强度本地 Token。
- 前端调用 Engine 必须携带 `X-Local-Token`。
- Tauri 生产模式下限制请求来源为 `tauri://localhost`。

### 数据库访问安全

- 数据源密码、SSH 密码、私钥口令会加密保存。
- 支持只读账号检测，并对具备写权限的账号给出风险提醒。
- SSH 隧道由本地 TunnelManager 管理，支持健康检查、自愈重连和关闭回收。

### SQL 执行安全

- SQL 执行前经过 PolicyEngine 与 TrustGate。
- TrustGate 会检查 SQL 安全性、Schema 范围、执行策略和人工确认需求。
- 普通运行环境不允许绕过 TrustGate；测试绕过也限制在测试/开发数据源。
- 查询结果做最大行数、最大列数、最大单元格长度和最大响应大小限制。

### 仓库安全

`.gitignore` 已排除以下本地敏感或高噪声文件：

- `.env` / `.env.*`
- `.databox_runtime/`
- 本地 Token、密钥、SQLite 数据库
- Agent checkpoint、eval 输出、报告、日志
- `node_modules/`、前端构建产物、Tauri target

请不要把生产 API Key、数据库密码、私钥、真实业务数据提交到仓库。

---

## 开发状态

DataBox 当前处于快速迭代阶段，核心方向包括：

- 打磨数据库工作台基础体验。
- 提升 Agent 在复杂 Schema 下的 SQL 生成、修复和解释能力。
- 完善 Semantic Layer、Context Pack、Memory、技能系统。
- 强化 Agent Eval，让每次能力升级都有可回归的评测依据。
- 收敛旧接口，统一使用 `/api/v1/agent/*` 作为 AI 能力入口。

---

## License

DataBox is released under the [MIT License](./LICENSE).