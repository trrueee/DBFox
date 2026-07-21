# DBFox

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![Node.js 20.19+](https://img.shields.io/badge/Node.js-20.19%2B-green)](https://nodejs.org/)
[![Tauri 2](https://img.shields.io/badge/Tauri-2.x-24C8DB)](https://tauri.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

DBFox 是一个本地优先的 AI 数据库桌面客户端，面向数据库浏览、SQL 分析、自然语言问数和结果可视化等工作流。它将 Tauri 桌面壳、React 前端和 Python FastAPI 引擎组合在一起，帮助用户在同一个应用中完成数据源管理、Schema 探索、SQL 执行和 AI 辅助分析。

![DBFox 演示图](docs/images/dbfox-demo.png)

## 功能特性

- 数据源管理：支持 MySQL、PostgreSQL、SQLite，提供连接测试、Schema 同步、SSH/SSL 配置和只读模式。
- 智能问数：通过对话式 AI Agent 理解数据库结构、生成 SQL、执行分析并汇总结果。
- SQL 工作台：提供 SQL 编辑、语法校验、查询执行、结果查看和历史记录。
- 可视化建议：根据查询结果推荐折线图、柱状图等图表形式，并支持结果导出。
- 安全控制：包含本地鉴权、SQL 安全检查、只读执行、高风险操作确认和敏感信息脱敏。
- 本地优先：核心服务运行在本机，默认使用本地运行时目录和本地元数据库保存配置与状态。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 桌面端 | Tauri 2, Rust |
| 前端 | React 19, TypeScript, Vite, Zustand, Tailwind CSS, Radix UI |
| 编辑器与图表 | Monaco Editor, ECharts |
| 后端引擎 | Python 3.12, FastAPI, Uvicorn, SQLAlchemy, Alembic |
| AI 能力 | 自有 ReAct Runtime、OpenAI-compatible API、持久化事件流 |
| 数据库驱动 | PyMySQL, psycopg2, SQLite |
| 测试与质量 | pytest, mypy, Vitest, ESLint |

## 环境要求

- Python 3.12+
- Node.js 20.19+
- npm
- Rust stable（仅在运行或打包 Tauri 桌面应用时需要）

## 安装

克隆项目后进入仓库根目录：

```bash
git clone <your-repo-url>
cd DBFox
```

安装 Python 依赖：

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

python -m pip install --require-hashes -r requirements-dev.lock
python -m pip check
```

安装前端依赖：

```bash
cd desktop
npm ci
```

生产 sidecar 构建使用独立环境和运行时锁文件：

```bash
python -m pip install --require-hashes -r requirements.lock
```

## 环境变量

项目提供了 `.env.example` 作为安全的非敏感调优模板：

```bash
cp .env.example .env  # 仅端口、连接池和导出上限等白名单参数
```

常用配置如下：

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| LLM 凭据 | 否 | 通过设置页写入 OS credential vault；不要放入 `.env`、环境变量或源码文件 |
| LLM endpoint/model | 否 | 以不透明 credential ID 配置；远程 endpoint 仅允许 HTTPS，loopback HTTP 必须显式启用 |
| `DBFOX_ENGINE_PORT` | 否 | 本地后端端口，默认 `18625` |
| `DBFOX_RUNTIME_DIR` | 否 | 仅由受控的父进程环境注入；不能从 `.env` 读取 |
| `DBFOX_DATABASE_URL` | 否 | 仅由受控的父进程环境注入；可能携带凭据，绝不能写入 `.env` |
| `DBFOX_MYSQL_CLIENT_DIR` | 仅原生 MySQL 备份需要 | 由受控父进程注入的绝对目录；其中必须存在非链接、普通文件形式的 `mysqldump`（Windows 为 `mysqldump.exe`），不能从 `.env` 读取 |

`.env` 采用严格白名单，未知变量、Provider 设置、凭据、token、数据库 URL、运行时路径和安全绕过开关都会被忽略。部署或 CI 如需设置受限配置，应由受控的服务管理器/CI 直接注入进程环境。

> 数据库原地恢复已被禁用：逻辑 SQL dump 无法对既有目标提供原子恢复保证。`POST /backups/{id}/restore` 会固定返回 `409 RESTORE_REQUIRES_ISOLATED_TARGET`，直到实现“隔离目标恢复 + 可审计切换”的持久化恢复设计。

桌面打包运行时由 Tauri IPC 将每次启动生成的引擎端口和令牌交给前端；后端绝不会向源码工作区写入 `.env.local`。浏览器式源码调试必须在启动前显式为后端和 Vite 注入同一个一次性 `DBFOX_ENGINE_TOKEN` / `VITE_LOCAL_ENGINE_TOKEN`，不要把令牌写入仓库文件。

## 启动

Windows PowerShell：

```powershell
./dev.ps1
./dev.ps1 backend
./dev.ps1 frontend
./dev.ps1 -NoReload
```

macOS / Linux / Git Bash：

```bash
./dev.sh
./dev.sh backend
./dev.sh frontend
```

也可以手动分别启动后端和前端：

```bash
# 终端 1：后端引擎
python -m engine.main

# 终端 2：前端开发服务
cd desktop
npm run dev
```

运行 Tauri 桌面应用：

```bash
cd desktop
npm run tauri -- dev
```

构建桌面安装包：

```bash
cd desktop
npm run tauri -- build
```

## 使用示例

1. 启动 DBFox。
2. 在左侧数据源面板中添加 MySQL、PostgreSQL 或 SQLite 数据源。
3. 点击连接测试，确认配置可用。
4. 同步数据库结构，可按需启用 AI 语义增强。
5. 在智能问数面板输入自然语言问题，例如：

```text
统计最近 7 天 AI 工具调用量，并生成趋势图。
```

也可以在 SQL 工作台直接执行查询：

```sql
SELECT
  DATE(created_at) AS date,
  COUNT(*) AS daily_invocations
FROM ai_tool_invocations
GROUP BY DATE(created_at)
ORDER BY date;
```

查询结果可在结果视图中查看，并可根据字段类型生成图表建议。

## 项目结构

```text
DBFox/
|-- engine/                 # Python 后端引擎，包含 API、Agent、SQL、安全和评估模块
|-- desktop/                # React 前端与 Tauri 桌面壳
|   |-- src/                # 前端页面、组件、状态和 API 客户端
|   `-- src-tauri/          # Tauri/Rust 配置、入口和打包资源
|-- docs/                   # 项目文档与演示资源
|-- build_sidecar.py        # 后端 sidecar 构建脚本
|-- dev.ps1                 # Windows 开发启动脚本
|-- dev.sh                  # Unix/macOS/Git Bash 开发启动脚本
|-- requirements.txt        # Python 运行依赖
|-- requirements-dev.txt    # Python 开发依赖
|-- pyproject.toml          # pytest 与 mypy 配置
`-- LICENSE
```

## 常用命令

```bash
# 后端测试
pytest engine -q

# Python 类型检查
mypy engine

# 前端测试
cd desktop
npm test

# 前端 lint
cd desktop
npm run lint

# 前端构建
cd desktop
npm run build
```

## 贡献

欢迎提交 Issue 和 Pull Request。建议在提交前先运行相关测试与 lint，并尽量让改动保持聚焦、可 review。

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。
