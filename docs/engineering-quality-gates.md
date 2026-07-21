# 工程质量门禁与依赖策略

`main` 分支和每个 Pull Request 由 `.github/workflows/ci.yml` 执行分层门禁：

1. Python 编译、渐进式 mypy 基线、空数据库 Alembic upgrade/check；
2. 不依赖外部服务或真实 LLM 凭据的核心后端、Agent 运行时、评测回归；
3. 在独立 `.build_venv` 中执行完整 PyInstaller sidecar 构建；
4. 前端的 `npm ci`、ESLint、Vitest、TypeScript/Vite build；
5. Rust 的锁文件验证、fmt、Clippy（警告即失败）和单元测试。

CI 只授予 `contents: read`，每个第三方 GitHub Action 固定到完整提交 SHA，且 checkout 不保留凭据。真实 LLM、外部集成和端到端测试保留给受控环境，不作为普通 PR 的隐式依赖。

## 本地执行

```powershell
python -m pip install --require-hashes -r requirements-dev.lock
python -m compileall -q engine build_sidecar.py
python -m mypy --no-warn-unused-configs --follow-imports=skip build_sidecar.py engine/runtime_paths.py engine/security/credential_vault.py engine/llm/endpoint_policy.py engine/connectivity
python -m alembic upgrade head
python -m alembic check
python -m pytest engine/tests -q --tb=short -m "not e2e and not integration and not real_llm"
python -m pytest engine/agent/tests engine/agent_runtime/tests -q --tb=short -m "not e2e and not integration and not real_llm"

cd desktop
npm ci
npm run lint
npm test -- --maxWorkers=1
npm run build

cd src-tauri
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
```

Windows 打包与 sidecar 的目标 triplet 均为 `*-pc-windows-msvc`。请从 Visual Studio 的 Developer PowerShell（或等价的 MSVC 开发环境）运行 Rust 门禁，并显式选择 MSVC toolchain，例如 `cargo +stable-x86_64-pc-windows-msvc clippy --locked --all-targets -- -D warnings`。项目会明确拒绝 Windows GNU target，避免生成 Rust 壳与 `build_sidecar.py` 侧车命名不一致的安装包；Linux CI 继续使用原生的 Rust 1.95 toolchain。

完整侧车打包在隔离环境执行，避免把构建工具混入运行时依赖：

```powershell
python -m venv .build_venv
.\.build_venv\Scripts\python -m pip install --require-hashes -r requirements-build.lock
.\.build_venv\Scripts\python build_sidecar.py
```

## 锁定策略

`desktop/package-lock.json`、`desktop/src-tauri/Cargo.lock`、`requirements.lock`、`requirements-dev.lock` 与 `requirements-build.lock` 都是提交的解析锁文件。前端使用 `npm ci`，Cargo 使用 `--locked`，Python 使用 `pip --require-hashes`，因此 CI 不会在构建时重新选择依赖版本或接受未固定的分发包。

`requirements*.txt` 是人工维护的输入清单；Python 3.12 的 universal、带 SHA-256 hash 的锁文件必须与它们一起更新。安装 `requirements-dev.lock` 后可使用其中的 `uv` 执行以下命令；生成后必须运行全部 CI 门禁和审查依赖来源、许可证及安全公告：

```powershell
uv pip compile --universal --generate-hashes --python-version 3.12 --output-file requirements.lock requirements.txt
uv pip compile --universal --generate-hashes --python-version 3.12 --output-file requirements-dev.lock requirements-dev.txt
uv pip compile --universal --generate-hashes --python-version 3.12 --output-file requirements-build.lock requirements-build.txt
```

`.github/dependabot.yml` 已覆盖 pip、npm、Cargo 和 GitHub Actions 的每周更新，依赖升级必须通过同一组门禁。

Python 的全仓 mypy 目前仍有既有和并行改造模块的类型债务，因此 CI 先硬性覆盖侧车、运行时路径、凭据库、LLM 端点策略和连接边界。该命令不把未收敛模块静默排除：它是显式的渐进基线；新增模块应先纳入该基线，再逐步扩大至全仓 `mypy engine`。
