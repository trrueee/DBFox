# DBFox

[![Python dev 3.12](https://img.shields.io/badge/Python%20dev-3.12-blue)](https://www.python.org/)
[![Frozen sidecar 3.14.6](https://img.shields.io/badge/Frozen%20sidecar-3.14.6-blue)](./.sidecar-python-version)
[![Node.js 20.19+](https://img.shields.io/badge/Node.js-20.19%2B-green)](https://nodejs.org/)
[![Tauri 2](https://img.shields.io/badge/Tauri-2.x-24C8DB)](https://tauri.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

DBFox 是一个本地优先的 AI 数据库桌面工作台，用于数据源管理、Schema 探索、SQL 分析、自然语言问数和结果可视化。Tauri/Rust 是桌面宿主和 Sidecar 生命周期权威，React 提供工作区界面，FastAPI 引擎承载 Agent、工具、安全策略和持久化。

![DBFox 演示图](docs/images/dbfox-demo.png)

## 当前能力

- 数据源：MySQL、PostgreSQL、SQLite、DuckDB，支持连接测试、SSH/TLS、只读策略和 Catalog 同步。
- SQL 工作台：编辑、校验、只读执行、分页结果、分析、图表和导出。
- AI Agent：provider-neutral 的显式 ReAct 循环、原生 function calling、计划/审批/取消、耐久事件和证据型回答。
- 上下文与记忆：区分当前请求、已消费 steer、历史消息、工具观察、结果 Artifact、会话记忆和可检索对话归档。
- 安全边界：每次启动生成的 loopback Token、OS credential vault、SQL guardrail、参数绑定、结果血缘脱敏和 RFC 9457 Problem Details。
- 故障恢复：Rust Runtime Supervisor、运行时 generation、数据库耐久队列、会话串行化、租约恢复和 SSE cursor/snapshot。

## 系统边界

```text
Tauri 2 / Rust Runtime Supervisor
  ├─ 启动并监管 Frozen Python Sidecar
  ├─ 生成随机端口、Token 和 generation
  └─ 通过 IPC 向 React 暴露当前运行时配置
                    │
                    ▼
React 19 / TypeScript ── authenticated HTTP + SSE ── FastAPI Engine
                                                        ├─ Agent Harness
                                                        ├─ Tool Runtime / SQL Safety
                                                        ├─ Session Coordinator
                                                        └─ SQLite metadata + external datasources
```

生产模式没有固定端口或开发 Token；桌面端只使用 Rust 提供的当前 generation 配置。开发脚本使用固定的 `18625` 后端端口，并为本次启动生成共享的本地 Token。

更完整的当前事实见[文档索引](./docs/README.md)和[系统架构](./docs/architecture/system-overview.md)。

## 技术栈

| 层 | 当前实现 |
| --- | --- |
| 桌面宿主 | Tauri 2、Rust 1.95、`tauri-plugin-shell`、`tauri-plugin-log` |
| 前端 | React 19、TypeScript、Vite、Zustand、TanStack Query/Table/Virtual、Radix UI |
| 数据与图形 | ECharts、XYFlow、项目内 SQL 编辑器 |
| 引擎 | Python 3.12（开发/测试）、FastAPI、Uvicorn、SQLAlchemy、Alembic |
| 正式 Sidecar | `.sidecar-python-version` 固定 Python 3.14.6，PyInstaller 冻结 |
| Agent | provider-neutral ReAct Harness、OpenAI-compatible Responses API、原生工具调用 |
| 数据源 | PyMySQL、psycopg、SQLite、DuckDB |
| 质量 | pytest、pyflakes、mypy、Vitest、ESLint、Cargo test/clippy、OSV/npm/RustSec 审计 |

## 平台支持

- Windows x64 是当前经过真实 Sidecar、MSI/NSIS 和安装态验收的发布目标。
- macOS/Linux 保留静态构建合同；没有对应 Runner、产物和运行证据时，不视为已验证发布平台。
- macOS 签名/公证、Gatekeeper，以及 Linux 安装、桌面启动和动态依赖必须在真实平台单独验收。

## 开发环境

需要 Python 3.12、Node.js 20.19+、npm。构建桌面应用还需要仓库固定的 Rust 1.95 工具链和对应平台的 Tauri 系统依赖。

```powershell
git clone <your-repo-url>
Set-Location DBFox

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip check

Set-Location desktop
npm ci
```

macOS/Linux 激活虚拟环境时使用 `source .venv/bin/activate`。

## 启动

推荐使用根目录脚本，它们会生成开发 Token，并保持前后端配置一致：

```powershell
./dev.ps1                 # backend + frontend
./dev.ps1 backend
./dev.ps1 frontend
./dev.ps1 -NoReload
```

```bash
./dev.sh                  # backend + frontend
./dev.sh backend
./dev.sh frontend
```

运行完整 Tauri 桌面开发模式：

```bash
cd desktop
npm run tauri -- dev
```

只调试前端时可运行 `npm run dev`，但仍需先启动引擎。不要手工编写 `desktop/.env.local`；`scripts/dev_environment.py` 是该文件的唯一写入者。

## 配置与凭据

- LLM API Key、数据库密码和 SSH 秘密写入操作系统 credential vault，不写入 `.env`、日志或业务数据库。
- `.env.example` 只包含允许从 dotenv 读取的非敏感调优项。未知项、Provider 配置、Token、数据库 URL、运行时目录和安全绕过开关会被忽略。
- `DBFOX_RUNTIME_DIR`、`DBFOX_DATABASE_URL`、运行时 Token 等受限值只能由受控父进程直接注入。
- 远程 LLM endpoint 只允许 HTTPS；loopback HTTP 必须显式启用。

```powershell
Copy-Item .env.example .env
```

## 测试与质量门禁

```powershell
# Python
python -m pytest -q --tb=short
python -m pyflakes engine build_sidecar.py
python -m mypy engine build_sidecar.py

# Frontend
Set-Location desktop
npm run lint
npm run typecheck:test
npm test -- --maxWorkers=1
npm run build

# Rust
npm run test:rust
```

供应链与锁文件合同：

```powershell
python -m pytest engine/tests/test_engineering_contracts.py -q
```

完整发布门禁、真实 Provider 合同测试和平台验收均为显式 opt-in；不要用单元测试结果替代正式产物验证。详见[工程质量与发布门禁](./docs/quality/engineering-gates.md)。

## 构建正式产物

Tauri 构建会按官方 `externalBin` 合同准备 Frozen Sidecar：

```powershell
Set-Location desktop
npm run tauri -- build
```

只构建或验证 Sidecar 时：

```powershell
python build_sidecar.py
Set-Location desktop
npm run test:sidecar
```

Sidecar 构建使用 `.sidecar-python-version`、`requirements.lock` 和独立构建环境；不要把开发虚拟环境当作正式产物来源。

## 仓库结构

```text
DBFox/
├─ engine/                 # FastAPI、Agent、工具、SQL、安全、持久化和迁移
├─ desktop/
│  ├─ src/                 # React 工作区、功能模块、状态和生成的 API 类型
│  └─ src-tauri/           # Rust Runtime Supervisor、Tauri 配置和打包资源
├─ docs/                   # 当前事实、规格、质量记录、设计、计划与审查证据
├─ scripts/                # 开发环境与验证脚本
├─ build_sidecar.py        # Frozen Sidecar 构建入口
├─ dev.ps1 / dev.sh        # 统一开发启动入口
└─ requirements*.lock      # 已哈希的 Python 依赖事实源
```

## 已知边界

数据库原地恢复被明确禁用：逻辑 SQL dump 不能为既有目标提供原子恢复保证。恢复接口在隔离目标恢复与可审计切换完成前保持 fail closed。

## 贡献与文档

提交前请运行与改动范围匹配的门禁。架构事实、实施计划和历史审查不能混作同一种文档；新增或更新文档前先阅读[文档体系](./docs/README.md)。

## 许可证

DBFox 基于 [MIT License](./LICENSE) 开源。
