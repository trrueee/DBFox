# DBFox — Local-First AI Database Workbench

DBFox 是本地优先、结果可追溯的 AI 数据分析桌面应用：Tauri/Rust Host 管理
Frozen FastAPI Sidecar 的生命周期，React 工作区通过带短期令牌的 HTTP/SSE 与
Sidecar 通信；Agent 工具调用与 SQL 只读执行都经过正式合同。

本文件只提供修改入口和少量关键不变量。它**不是**版本、命令或依赖的权威来源；
不要按这里的任何具体版本号、命令或路径推断当前状态。

## 修改前先读

- `README.md` — 产品定位、支持范围与快速开始
- `CONTRIBUTING.md` — 开发环境、变更要求、提交与验证流程
- `docs/README.md` — 文档中心与阅读路线
- `docs/architecture/README.md` / `docs/architecture/system-overview.md` — 当前架构
- `docs/architecture/implementation-map.md` — 功能到代码、测试与数据表的索引

## 权威事实源

| 事实 | 权威文件 |
| --- | --- |
| Node 版本 | `desktop/package.json`（`engines`） |
| Rust 版本 | `desktop/src-tauri/rust-toolchain.toml` |
| Frozen Sidecar Python | `.sidecar-python-version` / `.sidecar-python-build` |
| 开发 Python 与依赖 | `CONTRIBUTING.md` + `requirements-dev.lock` |
| 各生态锁文件 | `requirements*.lock`、`desktop/package-lock.json`、`desktop/src-tauri/Cargo.lock` |
| 质量门禁命令 | `docs/quality/engineering-gates.md` + `.github/workflows/ci.yml` |

## 开发入口

优先使用根脚本 `./dev.ps1` / `./dev.sh`（`backend` / `frontend` / `both`）；它们通过
`scripts/dev_environment.py` 生成共享开发 Token，并保持前后端合同一致。开发端口：
后端 `18625`，前端 `5173`。完整桌面开发：`cd desktop && npm run tauri -- dev`。

## 关键架构不变量

1. Rust 是生产 Sidecar 生命周期的唯一权威；不要增加第二套启动器、猜测的 target 映射或 fallback 路径。
2. `scripts/dev_environment.py` 是被忽略的 `desktop/.env.local` 的唯一写入者；`build_sidecar.py` 只负责 Frozen Sidecar 构建，不再承担开发凭据职责。
3. 秘密进入 OS 凭据库；API Key、密码、运行时 Token 或完整 DSN 不得落入业务状态、日志、`.env` 或公开错误。
4. SQLite/Alembic 是耐久事实源；Coordinator 内存只是有界调度状态，不是第二个队列。
5. Agent 上下文区分原始请求、已消费 steers、历史消息、工具观察、结果 Artifact、会话记忆与对话归档。
6. 完成判定 provider-neutral：只有带可展示文本、且无待处理工具/控制/错误的正常回合才能 finalize。
7. 工具错误只暴露注册过的安全公开消息；任意异常文本不进入 UI 或 Provider 输出。
8. 模型 SQL 必须走 `sql_validate` → 不可变校验 Artifact → `sql_execute_readonly`；执行端不接受原始模型 SQL。
9. 大结果留在结果后端；模型只拿有界摘要，并用结果工具检视/分析。
10. 事件先持久化再发布，SSE 用 cursor/snapshot 恢复；没有 UI-only 的真相。

工具只在 `engine/tools/builtin/registry.py` 注册一次；执行策略、审批、幂等、观察上限与
呈现语义属于 provider-neutral 的 Tool Runtime。

## 反模式

- 不要 `python engine/main.py` 直接执行文件；模块入口是 `python -m engine.main`。
- 不要给已退役的带点工具名加别名，也不要在工具层加 provider-name 分支或第二套 SQL 执行链。
- 不要解析 Thought/Action/Observation 文本；Agent 使用原生 Responses Items/function calling。
- 不要在 React/Zustand 里驱动 Agent 循环或耐久状态机。
- 不要为掩盖内部合同错配而加 mapper/wrapper/fallback 层；修权威边界。
- 运行时 generation 变化后，不要自动重放非幂等请求。
- 不要用 force-fix 命令静默改写锁文件等可复现构建合同。
