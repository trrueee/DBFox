# DBFox

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node.js 20.19+](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![Tauri 2](https://img.shields.io/badge/Tauri-2.x-24C8DB.svg)](https://tauri.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

**DBFox — 本地优先、AI 原生的数据库工作台。**

在同一个桌面应用里集成了数据源管理、Schema 浏览、SQL 控制台、对话式问数 Agent 和执行安全策略。

---

## 核心能力

### 数据源管理
- MySQL、PostgreSQL、SQLite，支持直连 / SSH 隧道 / SSL
- 连接测试、健康检查、Schema 自动同步（FTS5 全文搜索 + AI 语义索引）
- ER 图数据导出，表作用域筛选（Workspace Table Scope）

### SQL 控制台
- Monaco 编辑器，多标签页，SQL 校验、执行、EXPLAIN 可视化
- 查询历史，结果集行/列/大小限制，图表呈现（ECharts）
- TRUSTED / UNTRUSTED 风险分级，高风险操作人工确认

### AI 问数 Agent
- LangGraph ReAct 本地 Agent Runtime，SSE 流式响应
- 完整工具链：schema 探索 → 语义搜索 → 表结构检查 → 数据预览 → SQL 生成执行 → 图表建议 → 答案合成
- TrustGate 安全门 + 审批节点：SELECT-only、危险函数拦截、生产环境二次确认
- 长期记忆：表别名、业务语义、会话摘要持久化

### 安全模型
- 本地 Token 鉴权（64 位随机 hex），Origin 校验
- Guardrail（语法检查）+ TrustGate（风险评分）双重 SQL 安全门
- 数据库密码加密存储（cryptography）
- 默认只读执行，高风险操作需人工确认
- 错误消息脱敏，敏感字段自动检测

---

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│  Desktop Shell (Tauri 2)                                │
│  ┌───────────────────────────────────────────────────┐  │
│  │  React 19 + TypeScript 6 + Vite 8 + Tailwind 3   │  │
│  │  Zustand 5 (datasource / workspace / agent /      │  │
│  │             conversation)                          │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │ HTTP + SSE (X-Local-Token)     │
│  ┌──────────────────────┴────────────────────────────┐  │
│  │  Engine Sidecar (Python 3.12, FastAPI + Uvicorn)  │  │
│  │  127.0.0.1:18625 (dev) / random port (prod)       │  │
│  │                                                    │  │
│  │  ┌──────────┐ ┌────────┐ ┌──────┐ ┌───────────┐  │  │
│  │  │ API      │ │ Agent  │ │ SQL  │ │ Semantic  │  │  │
│  │  │ Routers  │ │ Runtime│ │Exec. │ │ Layer     │  │  │
│  │  └──────────┘ └────────┘ └──────┘ └───────────┘  │  │
│  │  ┌──────────┐ ┌────────┐ ┌────────────────────┐  │  │
│  │  │ Policy   │ │ Memory │ │ Migration (Alembic) │  │  │
│  │  │ Engine   │ │ Store  │ │ SQLite metadata DB  │  │  │
│  │  └──────────┘ └────────┘ └────────────────────┘  │  │
│  └──────────────────────┬────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────┘
                          │ DB Driver / SSH / SSL
                 ┌────────┴────────┐
                 │  MySQL · PG ·   │
                 │  SQLite         │
                 └─────────────────┘
```

---

## 快速开始

### 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 推荐使用虚拟环境 `.build_venv` |
| Node.js | 20.19+ | 前端构建和 Tauri 桌面打包 |
| Rust | latest stable | 仅 Tauri 桌面打包需要 |

### 开发模式

最简单的方式 —— 用项目自带的启动脚本：

```bash
# Windows PowerShell
./dev.ps1              # 同时启动后端 + 前端
./dev.ps1 backend      # 仅后端 (http://127.0.0.1:18625)
./dev.ps1 frontend     # 仅前端 (http://localhost:5173)
./dev.ps1 -NoReload    # 禁用后端自动重载

# Unix / macOS / Git Bash
./dev.sh               # 同时启动后端 + 前端
./dev.sh backend       # 仅后端
./dev.sh frontend      # 仅前端
```

手动启动：

```bash
# 终端 1 — 后端（必须用模块模式）
python -m engine.main

# 终端 2 — 前端
cd desktop && npm run dev
```

> **注意**：必须用 `python -m engine.main`（模块模式），不能用 `python engine/main.py`（会报 `ModuleNotFoundError`）。后端启动时自动将 Token 写入 `desktop/.env.local`，前端通过 `X-Local-Token` 头鉴权。

首次运行前安装依赖：

```bash
# Python 依赖
pip install -r requirements.txt

# 前端依赖
cd desktop && npm install
```

### Tauri 桌面开发模式

```bash
cd desktop && npm run tauri -- dev
```

Tauri 自动拉起后端 sidecar 和 Vite 开发服务器，在原生窗口中运行。

### LLM 配置

1. 启动后端和前端后，点击界面右上角「设置 → LLM 配置」
2. 填写 API Key、Base URL、Model Name（兼容 OpenAI / Qwen / DeepSeek 等接口）
3. 也可以设置环境变量：
   ```bash
   cp .env.example .env
   # 编辑 .env，设置 OPENAI_API_KEY 和可选的 OPENAI_BASE_URL
   ```

---

## Agent 工具链

Agent 可调用 19 个工具（注册于 `engine/tools/dbfox_tools.py`）：

| 分组 | 工具 | 功能 |
|------|------|------|
| **schema** | `schema.list_tables` | 列出数据源所有表 |
| | `schema.list_tables_page` | 分页列出表 |
| | `schema.describe_table` | 查看单表结构、索引、外键 |
| | `schema.refresh_catalog` | 刷新 Schema 缓存 |
| | `schema.expand_related_tables` | 展开关联表 |
| **environment** | `environment.get_profile` | 获取数据源环境概览 |
| **db** | `db.observe` | 观察 catalog：表、列、行数 |
| | `db.search` | FTS5 语义搜索匹配表和字段 |
| | `db.inspect` | 检查单表详细结构 |
| | `db.preview` | 预览样本数据（含敏感字段脱敏） |
| | `db.query` | 生成 + 校验 + 执行 SQL |
| | `db.remember` | 记录 schema 别名、业务语义 |
| **sql** | `sql.validate` | SQL 语法校验和 Guardrail 检查 |
| | `sql.execute_readonly` | 只读执行 SQL（SELECT-only） |
| **chart** | `chart.suggest` | 自动建议合适的图表类型和维度 |
| **answer** | `answer.synthesize` | 综合所有证据生成结构化最终答案 |
| **escalate** | `escalate.tool_group` | Agent 自行提升工具权限 |
| **memory** | `memory.search` | 搜索长期记忆 |
| | `memory.write` | 写入长期记忆 |
| | `memory.delete` | 删除长期记忆 |
| | `memory.summarize_session` | 会话摘要持久化 |

Agent 技能（YAML 定义）：`engine/agent/skills/builtin/` — `schema_exploration`、`result_analysis`。

---

## 项目结构

```
.
├── engine/                         # Python 后端 (FastAPI + LangGraph Agent)
│   ├── main.py                     # FastAPI 入口，CORS、Token 鉴权、生命周期
│   ├── db.py                       # SQLAlchemy 引擎 + Alembic 自动迁移
│   ├── models.py                   # ORM 模型
│   ├── runtime_env.py              # 环境变量加载（.env 优先级链）
│   ├── runtime_paths.py            # 跨平台运行时路径
│   ├── errors.py                   # 自定义异常类
│   ├── dev_server.py               # 开发服务器启动工具
│   ├── api/                        # REST API 路由组（10 个模块）
│   ├── agent/                      # ReAct Agent（graph / nodes / tools / skills / progress）
│   ├── agent_core/                 # Agent 核心原语（state / events / artifacts / answer / checkpointer）
│   ├── sql/                        # SQL 执行器 + Guardrail + TrustGate + 方言适配
│   ├── tools/                      # 工具注册（19 个工具）+ Runtime V2 层
│   ├── semantic/                   # Schema Linker + Alias Resolver + Context Builder
│   ├── environment/                # 数据源环境、Schema 内省、目录同步
│   ├── llm/                        # LLM Provider 抽象（OpenAI 兼容）
│   ├── memory/                     # 长期记忆（CRUD + 压缩 + 检索 + 策略）
│   ├── policy/                     # 策略引擎 + 确认管理 + 数据脱敏
│   ├── evaluation/                 # Agent 评估框架（benchmarks + evaluators）
│   ├── migrations/                 # Alembic 迁移（9 个版本）
│   ├── schemas/                    # Pydantic 请求/响应模型
│   ├── projects/                   # 项目管理服务
│   ├── diagnostics/                # 诊断日志
│   └── tests/                      # pytest 测试（55+ 文件）
├── desktop/                        # 前端 + Tauri 桌面壳
│   ├── src/
│   │   ├── features/               # 功能模块
│   │   │   ├── appShell/           # 应用壳（路由、侧边栏、命令面板）
│   │   │   ├── conversation/       # 对话工作区（MessageList / MessageBubble / Artifact Panel）
│   │   │   ├── datasource/         # 数据源树 + 右键菜单
│   │   │   ├── workspace/          # 主工作区（SQL 控制台 / 表浏览 / Agent 时间线 / 图表 / 查询结果）
│   │   │   └── engine/             # 引擎通信层
│   │   ├── components/             # 共享 UI（SqlEditor / DataTable / ChartPanel / ER Diagram / Toast）
│   │   ├── stores/                 # Zustand 状态管理（4 个 store）
│   │   ├── lib/api/                # API 客户端（fetch 封装 + 各模块 API）
│   │   ├── pages/                  # 页面（DataSources / AgentEval / Diagnostics）
│   │   ├── types/                  # TypeScript 类型定义
│   │   └── styles/                 # 设计令牌（tokens.css）
│   ├── src-tauri/                  # Tauri 2 Rust 壳
│   │   ├── src/lib.rs              # Engine sidecar 生命周期管理
│   │   └── tauri.conf.json         # Tauri 配置（窗口、CSP、打包）
│   └── package.json                # Node 项目配置
├── docs/                           # 设计文档（designs / plans / reviews / qa / reference）
├── .build_venv/                    # Python 虚拟环境（构建 sidecar 用）
├── build_sidecar.py                # PyInstaller 引擎打包脚本
├── dev.ps1 / dev.sh                # 开发启动脚本（Windows / Unix）
├── requirements.txt                # Python 运行时依赖
├── requirements-dev.txt            # Python 开发依赖（pytest / mypy）
├── pyproject.toml                  # mypy + pytest 配置
└── CLAUDE.md                       # AI 编码助手项目上下文
```

---

## 常用命令

```bash
# === 开发启动 ===
./dev.ps1                          # Windows：同时启动前后端
./dev.sh                           # Unix：同时启动前后端
python -m engine.main              # 仅后端（http://127.0.0.1:18625）
cd desktop && npm run dev          # 仅前端（http://localhost:5173）

# === 测试 ===
pytest engine/ -q --tb=short \
  --ignore=engine/agent/tests/test_e2e_qwen.py   # 后端测试（~650 个用例）
cd desktop && npm test                            # 前端测试（Vitest）

# === 代码质量 ===
mypy engine                                      # Python 类型检查
cd desktop && npm run lint                       # ESLint
cd desktop && npx tsc --noEmit                   # TypeScript 类型检查

# === 打包 ===
# 1. 构建引擎 sidecar
.build_venv/Scripts/python build_sidecar.py
# 2. 构建桌面安装包（自动执行构建 sidecar + Vite build）
cd desktop && npm run tauri -- build
```

---

## 设计原则

- **本地优先**：所有数据和处理在本地完成，不上传云端
- **安全默认**：默认只读、高风险需确认、密码加密存储
- **渐进式 AI**：Agent 从 schema 探索到 SQL 执行逐步获取权限，可人工介入
- **模块化边界**：API → Service → Core 分层，工具层独立可测试
- **SSE 流式**：Agent 推理过程实时可见，非黑盒体验
---

## License

MIT
