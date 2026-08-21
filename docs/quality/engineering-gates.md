# 工程质量门禁与依赖策略

> 文档类型：质量参考
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 适用范围：本地检查、持续集成、依赖锁定和工程门禁
>
> 权威配置：`.github/workflows/ci.yml`、锁文件和各测试配置

`main` 分支和每个 Pull Request 由 `.github/workflows/ci.yml` 执行分层门禁：

1. Python 编译、生产代码 mypy、全仓 Python pyflakes、空数据库 Alembic upgrade/check；
2. 不依赖外部服务或真实 LLM 凭据的核心后端与 Agent 运行时回归；
3. 使用 `.sidecar-python-version` 指定的生产解释器，重新运行完整确定性后端合同；
4. 在独立 `.build_venv` 中执行完整 PyInstaller sidecar 构建；
5. 前端的 `npm ci`、ESLint、Vitest、Electron Main/真实 Python supervisor smoke、未激活 DLC asset
   protocol 403 证明、TypeScript/Vite build；
6. API client 二次生成稳定、锁文件审计和三平台 Electron packaged release contract。

CI 只授予 `contents: read`，每个第三方 GitHub Action 固定到完整提交 SHA，且 checkout 不保留凭据。真实 LLM、外部集成和端到端测试保留给受控环境，不作为普通 PR 的隐式依赖。

`production-python-compatibility` 使用 `requirements-dev.lock` 提供测试工具，但与生产
Sidecar 的 `.build_venv` 完全分离。这样既能证明生产解释器可运行完整确定性合同，也不会
把 pytest、mypy 等开发依赖带入 Frozen Sidecar。

## 本地执行

```powershell
python -m pip install --require-hashes -r requirements-dev.lock
python -m compileall -q engine build_sidecar.py conftest.py scripts
python -m pyflakes engine build_sidecar.py conftest.py scripts
python -m mypy --no-warn-unused-configs --follow-imports=skip engine build_sidecar.py --no-incremental
python -m alembic upgrade head
python -m alembic check
python -m pytest engine/tests -q --tb=short -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"
python -m pytest engine/tests -q --tb=short -m "migration or engineering_contract or platform_contract"
python -m pytest engine/agent/tests -q --tb=short -m "not e2e and not integration and not real_llm"

cd desktop
npm ci
npm run lint
npm run typecheck:test
npm test -- --maxWorkers=1
npm run test:electron
npm run build
```

后端核心、迁移、工程契约和平台契约的测试集合必须互不重叠；CI 通过
pytest marker 给每个 Node ID 唯一归属。`npm run lint` 同时执行 ESLint 和基于
PostCSS AST 的 DBFox 设计令牌契约，不使用读取组件源码文本的伪单元测试。

Sidecar 目标名称由 `build_sidecar.py` 的显式 OS/arch 映射生成，并由 Electron Main 的 manifest/hash
校验消费；桌面构建不依赖外部编译器推断平台名称。

完整侧车打包在隔离环境执行，避免把构建工具混入运行时依赖：

```powershell
$dbfoxSidecarPython = (Get-Content .sidecar-python-version -Raw).Trim()
$env:UV_PYTHON_CPYTHON_BUILD = (Get-Content .sidecar-python-build -Raw).Trim()
uv python install --managed-python $dbfoxSidecarPython
uv venv --managed-python --python $dbfoxSidecarPython .build_venv
uv pip sync requirements-build.lock --python .\.build_venv\Scripts\python.exe
.\.build_venv\Scripts\python build_sidecar.py
cd desktop
npm run test:sidecar
npm run electron:package
npm run test:electron-packaged
```

## 锁定策略

`desktop/package-lock.json`、`requirements.lock`、`requirements-dev.lock` 与 `requirements-build.lock`
都是提交的解析锁文件。前端和 Electron 使用 `npm ci`，Python 使用 `pip --require-hashes`。

`requirements*.txt` 是人工维护的输入清单；运行时/开发锁使用 Python 3.12，生产 Sidecar 构建锁使用 `.sidecar-python-version` 的精确版本，并由 `.sidecar-python-build` 固定 uv 管理的 `python-build-standalone` 构建批次。所有锁均为 universal、带 SHA-256 hash 的解析结果，并必须与输入清单一起更新。安装 `requirements-dev.lock` 后可使用其中的 `uv` 执行以下命令；生成后必须运行全部 CI 门禁和审查依赖来源、许可证及安全公告：

```powershell
uv pip compile --universal --generate-hashes --python-version 3.12 --output-file requirements.lock requirements.txt
uv pip compile --universal --generate-hashes --python-version 3.12 --output-file requirements-dev.lock requirements-dev.txt
$dbfoxSidecarPython = (Get-Content .sidecar-python-version -Raw).Trim()
uv pip compile --universal --generate-hashes --python-version $dbfoxSidecarPython --output-file requirements-build.lock requirements-build.txt
```

`.github/dependabot.yml` 已覆盖 pip、npm 和 GitHub Actions 的每周更新，依赖升级必须通过同一组门禁。

pyflakes 覆盖 `engine`、`build_sidecar.py`、`conftest.py` 与 `scripts`；
mypy 覆盖整个 `engine` 与 `build_sidecar.py`。Tool、Conversation 和 Catalog
不再使用 `ignore_errors`；新增生产模块必须同时通过对应门禁。
