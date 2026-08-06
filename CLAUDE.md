# DBFox — Local-First AI Database Workbench

本文件是仓库开发入口，不替代当前架构文档。开始跨模块修改前先读 `docs/README.md` 和 `docs/architecture/README.md`；源码、迁移、锁文件和当前 commit 的测试证据优先级最高。

## Runtime Baseline

- Backend development/test: Python 3.12 + FastAPI + Uvicorn (`engine/`)
- Frozen production Sidecar: Python 3.14.6，版本由 `.sidecar-python-version` 固定
- Frontend: React 19 + TypeScript + Vite (`desktop/src/`)
- Desktop host: Tauri 2 + Rust 1.95 (`desktop/src-tauri/`)
- Node.js: 20.19+
- Development virtualenv: `.venv/`; production build environment is isolated and must not be inferred from it

## Run

Prefer the root scripts; they generate a shared development Token and keep the frontend/backend contract aligned.

```powershell
./dev.ps1
./dev.ps1 backend
./dev.ps1 frontend
./dev.ps1 -NoReload
```

```bash
./dev.sh
./dev.sh backend
./dev.sh frontend
```

Manual backend development entry:

```bash
python engine/dev_server.py
```

Never run `python engine/main.py`; direct-file execution breaks package imports. Full desktop development:

```bash
cd desktop
npm run tauri -- dev
```

Development uses backend port `18625` and frontend port `5173`. Production Sidecar port, Token and generation are selected by Rust at runtime and delivered through Tauri IPC.

## Quality Gates

```bash
python -m pytest -q --tb=short
python -m pyflakes engine build_sidecar.py
python -m mypy engine build_sidecar.py

cd desktop
npm run lint
npm run typecheck:test
npm test -- --maxWorkers=1
npm run build
npm run test:rust
```

Run the platform/Frozen Sidecar/release gates when the change affects Runtime, auth, ACL, bundling or dependencies. Windows evidence does not validate macOS/Linux.

## Architecture

```text
Tauri Runtime Supervisor
  └─ Frozen FastAPI Sidecar
       ├─ Agent Harness + SessionCoordinator
       ├─ Tool Runtime + Approval/Idempotency
       ├─ SQL validation/execution/artifacts
       ├─ SQLite metadata/event durability
       └─ MySQL / PostgreSQL / SQLite / DuckDB datasources

React Workspace ── authenticated HTTP + recoverable SSE ── FastAPI
```

## Core Contracts

- Rust is the only production Sidecar lifecycle authority; do not add a second launcher, guessed target mapping or fallback path.
- `scripts/dev_environment.py` is the only writer of ignored `desktop/.env.local`.
- Secrets live in the OS credential vault. Never persist API keys, passwords, runtime Tokens or complete DSNs in business state, logs or `.env`.
- SQLite/Alembic is the durable source of truth. Coordinator memory is bounded scheduling state, not a second queue.
- Agent context distinguishes the raw current request, consumed steers, historical messages, tool observations, result Artifacts, session memory and conversation archive.
- Completion is provider-neutral: only a normally completed turn with displayable assistant text and no pending tools/control/error may finalize.
- Tool errors expose only registered safe public messages. Arbitrary exception text is not trusted UI/provider output.
- Model-authored SQL follows `sql_validate` → immutable validation Artifact → `sql_execute_readonly`; execution does not accept raw model SQL.
- Large query results remain in the result backend. The model receives bounded summaries and uses result tools to inspect/profile them.
- Events are persisted before publish and recovered with SSE cursor/snapshot; no UI-only truth.

## Agent Tool Chain

Tools are registered once in `engine/tools/builtin/registry.py`:

- Runtime: `request_clarification`, `update_plan`
- Conversation recall: `conversation_search`, `conversation_read`
- Catalog: `catalog_overview`, `catalog_refresh`, `schema_list`, `schema_search`, `schema_inspect`
- Query: `data_preview`, `sql_validate`, `sql_execute_readonly`
- Results: `result_inspect`, `result_profile`, `chart_create`

Tool schemas, execution policy, approval, idempotency, observation limits and presentation semantics belong to the provider-neutral Tool Runtime. Do not add provider-name branches or a second SQL execution chain.

## Dependency Sources

- Python runtime/dev/build locks: `requirements.lock`, `requirements-dev.lock`, `requirements-build.lock`
- Frontend: `desktop/package-lock.json`
- Rust: `desktop/src-tauri/Cargo.lock` and `desktop/src-tauri/rust-toolchain.toml`
- Frozen Python: `.sidecar-python-version`

Do not replace locked installs with floating dependencies or use force-fix commands that silently rewrite contracts.

## Anti-patterns

- Do not run `python engine/main.py`.
- Do not add aliases for retired dotted tool names.
- Do not parse textual Thought/Action/Observation; the Agent uses native Responses Items/function calling.
- Do not drive the Agent loop or durable state machine from React/Zustand.
- Do not expose arbitrary `DBFoxError.message`, Provider text, SQL/DSN fragments or tool exception strings.
- Do not auto-replay non-idempotent requests after Runtime generation changes.
- Do not add mapper/wrapper/fallback layers to hide an internal contract mismatch; fix the canonical boundary.
