# DBFox — Agent 指南

本地优先的 AI 数据分析桌面应用：Electron Host 管理 Frozen FastAPI Sidecar 的生命周期，
React 工作区通过带短期令牌的 HTTP/SSE 访问 Sidecar。修改前先读
[`CONTRIBUTING.md`](CONTRIBUTING.md)；功能→代码→测试索引见
[`docs/architecture/implementation-map.md`](docs/architecture/implementation-map.md)。

## 命令

- 开发启动（仓库根）：`./dev.ps1 [backend|frontend|both]`（Unix 为 `./dev.sh`）。后端
  `127.0.0.1:18625`，前端 Vite `localhost:5173`；脚本会先运行 `scripts/dev_environment.py`
  生成共享开发 Token 并注入 `DBFOX_ENGINE_TOKEN`。
- 完整桌面开发：`cd desktop && npm run electron:dev`。
- 后端入口是模块：`python -m engine.main`；不要 `python engine/main.py` 直接执行文件。
- 依赖安装：Python 用 `.venv` + `pip install --require-hashes -r requirements-dev.lock`；
  前端 `cd desktop && npm ci`。不要绕过哈希校验或手改锁文件。

### 验证（按改动范围选最小充分集合）

Python（仓库根运行）：

```powershell
# 单个测试
python -m pytest verification/tests/system/test_sql_safety_service.py -q --tb=short

# 后端核心回归（CI 同款 marker 排除）
python -m pytest verification/tests/system -q --tb=short -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"

# Agent 运行时（独立目录）
python -m pytest verification/tests/agent_core -q --tb=short -m "not e2e and not integration and not real_llm"

# 工程合同（锁文件、依赖治理）
python -m pytest verification/tests/system/test_engineering_contracts.py -q

# Lint 与类型检查
python -m pyflakes engine build_sidecar.py scripts
python -m mypy --no-warn-unused-configs --follow-imports=skip engine build_sidecar.py --no-incremental
```

前端（`desktop/` 下运行）：

```powershell
npm run lint            # ESLint + 基于 PostCSS AST 的设计令牌契约检查
npm run typecheck:test  # 测试代码类型检查（tsc tsconfig.test.json）
npm test -- --maxWorkers=1   # 必须串行，保证内存确定性
npm run test:electron   # Electron Main/Preload 单测（EngineSupervisor 合同等）
npm run build           # tsc -b + 构建脚本 + 生产 Token 与 bundle 预算检查
```

注意：`CONTRIBUTING.md` 列出的 `npm run test:rust` 已不存在于 `desktop/package.json`
（当前仓库无 Rust 代码），以 `package.json` 脚本为准。

## 结构

| 路径 | 内容 |
| --- | --- |
| `engine/api/` | FastAPI 路由、请求合同、HTTP 边界 |
| `engine/agent/` | SessionCoordinator、Run Loop、上下文、Provider、持久化仓库（测试在 `verification/tests/agent_core/`） |
| `engine/tools/` | 工具注册、输入合同、策略、审批、执行运行时 |
| `dlcs/dbfox_data/` | Data System DLC：连接、数据库资源、Catalog、SQL 与结果视图 |
| `dlcs/dbfox.workspace/` | Workspace System DLC：目录绑定与文件能力 |
| `engine/migrations/` | DBFox 本地元数据库的 Alembic 迁移 |
| `desktop/src/` | React 工作区（TanStack Query/Table/Virtual、Zustand、Radix UI） |
| `desktop/main/`、`desktop/preload/` | Electron Host 与窄化 IPC；Sidecar 生命周期由 `desktop/main/engine.ts` 的 `EngineSupervisor` 管理（TypeScript，非 Rust） |
| `verification/bench/framework/` | Bench manifest、统计、报告与比较；不含领域 scorer |
| `verification/bench/core/` | Data-free Agent Kernel/Harness 测评，走生产 RunLoop |
| `verification/bench/capabilities/` | 单 DLC 的 direct/agent 能力测评与 suite-owned scorer |
| `verification/tests/` | 与产品物理分离的 Core、System、Integration 与 Bench 测试 |
| `verification/testkit/` | 只供验证系统使用的 fixture 构建与外部边界控制 |

## 关键不变量（违反即架构错误）

1. 模型 SQL 必须走 `sql_validate` → 不可变校验 Artifact → `sql_execute_readonly`；
   执行端不接受原始模型 SQL，不建第二套执行链。
2. 工具只在 `engine/tools/builtin/registry.py` 注册一次；执行策略、审批、幂等、观察上限
   属于 provider-neutral Tool Runtime；工具层不得加 provider-name 分支。
3. 秘密只进 OS 凭据库；API Key、密码、运行时 Token、完整 DSN 不得落入业务状态、日志、
   `.env`、前端 localStorage 或公开错误消息。
4. SQLite/Alembic 是耐久事实源；事件先持久化再发布，SSE 用 cursor/snapshot 恢复；
   UI/Zustand 内存只是投影，不得驱动 Agent 循环或耐久状态机。
5. 大结果留在结果后端；模型只拿有界摘要，用结果工具检视。
6. 不加 mapper/wrapper/fallback/兼容层掩盖内部合同错配；修权威边界。
7. 取消、断线、generation 变化后不自动重放非幂等请求。
8. Agent 使用原生 Responses function calling；不要解析 Thought/Action/Observation 文本。

## 环境与测试怪癖

- 根 `conftest.py` 在任何 DBFox 模块导入前设置 `DBFOX_RUNTIME_DIR`（进程独占临时目录）、
  `DBFOX_TESTING=1` 等隔离变量；pytest 必须从仓库根运行才能生效。
- pytest markers：`e2e`、`integration`、`real_llm`、`migration`、`engineering_contract`、
  `platform_contract`、`slow`。默认本地验证跑确定性集合（排除外部服务标记）；CI 要求
  各 marker 集合互不重叠、每个测试唯一归属。
- 前端 API client 是生成的：FastAPI 合同变化后运行 `cd desktop && npm run generate:api`
  （需要本机 Python 环境已装 `requirements.lock`），输出到 `desktop/src/lib/api/generated`，
  与合同变更一起提交；不要手改生成文件（CI 用 `git diff --exit-code` 校验）。
- 安全相关环境变量（`DBFOX_DATABASE_URL`、`DBFOX_RUNTIME_DIR`、`DBFOX_ENGINE_TOKEN`、
  `DBFOX_TESTING`、`DBFOX_ALLOW_GUARDRAIL_BYPASS`）不从 `.env` 加载，只能由父进程注入；
  `.env` 白名单仅限非敏感调优参数（见 `.env.example`）。
- 生产 Sidecar 解释器由 `.sidecar-python-version` / `.sidecar-python-build` 固定；
  Frozen Sidecar 构建使用隔离的 `.build_venv`（`build_sidecar.py` 只负责构建，
  开发脚本不使用它）。
- 锁文件合同：`requirements*.txt` 是人工维护的输入清单，`requirements*.lock` 由
  `uv pip compile --universal --generate-hashes` 生成，两者必须同步更新；
  不要用 force-fix 命令静默改写锁文件。
- 不要提交：`.env*`、API Key/Token/DSN、本地 SQLite 数据库、日志、MSI/NSIS 安装包、
  Sidecar 二进制、临时测试脚本或 Agent 私有工作目录。

## 文档维护

- 当前设计写 `docs/architecture/`，跨模块合同写 `docs/specs/`，质量与发布证据写
  `docs/quality/`；完成后旧方案移入 `docs/archive/` 并标明替代关系。
- 行为、命令、配置或支持范围变化时，同步更新对应的"当前"文档；文档状态只用
  "当前/已接受/草案/历史"。
