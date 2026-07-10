# DBFox Foundation Redesign — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge the new foundations into a maintainable, reproducible, observable desktop product: remove obsolete architecture, split oversized modules, harden the Tauri lifecycle and CSP, lock dependencies, enforce clean-environment CI, and add packaged fault-injection/performance gates.

**Architecture:** Phase 3 removes every bypass left after Phases 1 and 2. It organizes code around the CredentialVault, ConnectionFactory, ResultArtifact, AgentRunStateMachine, and Alembic boundaries. It does not preserve old routes, unused adapters, or build assumptions. Delivery validation treats the packaged Windows app as the product, not development mode.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, React/TypeScript/Vite, Rust/Tauri 2, GitHub Actions, PyInstaller, npm, Cargo.

## Global Constraints

- Start only after Phase 1 and Phase 2 acceptance criteria pass.
- Delete obsolete paths instead of retaining deprecation wrappers.
- Every public module has one clear responsibility and explicit dependencies.
- CI must use lock files and run without developer-local `.env`, `%APPDATA%`, live LLM keys, or database services unless a container fixture explicitly provides one.
- Packaged app security controls must be validated in the packaged WebView and sidecar process, not assumed from browser development mode.
- Enforce measurable budgets for bundle size, checkpointer state, cache size, startup failure visibility, logs, and test duration.

---

## File Structure

- Create: `engine/api/agent_runs.py`
  - Run creation, status, approval, cancellation, and SSE replay routes.
- Create: `engine/api/agent_artifacts.py`
  - Result/artifact retrieval and export routes.
- Create: `engine/api/agent_evaluation.py`
  - Development-only evaluation routes, disabled in packaged production.
- Create: `engine/observability/metrics.py`
  - Typed local metrics and budget reporters.
- Create: `engine/observability/redaction.py`
  - Shared semantic redaction for logs, diagnostics, and errors.
- Create: `desktop/src/lib/engineBootstrap.ts`
  - Authenticated engine bootstrap and startup-state contract.
- Create: `desktop/src/lib/externalNavigation.ts`
  - Allowlisted, explicitly confirmed external URL handling.
- Create: `desktop/scripts/check-budgets.mjs`
  - Enforces dist/entry/SVG budgets.
- Create: `scripts/verify-clean-build.ps1`
  - Clean Windows build/install/smoke runner.
- Create: `scripts/test-packaged-app.ps1`
  - Installed sidecar startup, shutdown, crash, and diagnostics tests.
- Modify: `engine/api/agent.py`, `engine/tools/db/inspect.py`, `engine/models.py`, `engine/db.py`
  - Split by responsibility and remove old orchestration/import cycles.
- Modify: `desktop/src-tauri/src/lib.rs`, `desktop/src-tauri/tauri.conf.json`
  - Harden child lifecycle, CSP, resource selection, and diagnostics.
- Modify: `desktop/vite.config.*`, `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`, `desktop/src/index.css`
  - Route-level code split, ECharts core imports, asset cleanup, local fonts.
- Modify: `requirements*.txt`, lock files, `desktop/package-lock.json`, `Cargo.lock`, `.github/workflows/ci.yml`
  - Reproducibility, audit and package gates.
- Modify: `README.md`, `desktop/README.md`, `docs/*`
  - Ensure documentation matches commands and reset behavior.

## Task 1: Delete Legacy Runtime Bypasses and Split API Boundaries

**Files:**

- Create: `engine/api/agent_runs.py`
- Create: `engine/api/agent_artifacts.py`
- Create: `engine/api/agent_evaluation.py`
- Modify: `engine/api/agent.py`
- Modify: `engine/main.py`
- Modify: `engine/agent_runtime/*`
- Test: `engine/tests/test_agent_routes.py`
- Test: `engine/tests/test_agent_eval_production_boundary.py`

**Interfaces:**

- `agent_runs.py` owns `/agent/runs`, `/agent/runs/{run_id}`, approval,
  cancellation, and events routes.
- `agent_artifacts.py` owns artifact/result view/export routes.
- `agent_evaluation.py` is registered only when an explicit development/eval
  mode is enabled.

- [ ] **Step 1: Write route ownership and production-boundary failures**

```python
def test_recent_route_is_not_shadowed_by_dynamic_run_route(client) -> None:
    response = client.get("/api/v1/agent/runs/recent")
    assert response.status_code != 404 or response.json()["detail"]["code"] != "RUN_NOT_FOUND"


def test_eval_import_route_is_absent_in_packaged_mode(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/api/v1/agent/eval/import" not in paths
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_agent_routes.py engine\tests\test_agent_eval_production_boundary.py -q
```

Expected: existing route registration and eval exposure fail the new contract.

- [ ] **Step 3: Split routes and delete legacy API orchestration**

Move runs, artifacts, and evaluation routes into the named modules. Register
static routes before dynamic identifiers. Make frozen/production route
registration exclude arbitrary-path benchmark import. Delete old legacy
runtime/service/coordinator endpoints after all callers use Phase 2 contracts.

- [ ] **Step 4: Run route tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_agent_routes.py engine\tests\test_agent_eval_production_boundary.py engine\tests\test_agent_api.py -q
```

Expected: pass; route ordering and production exposure are explicit.

## Task 2: Eliminate Import Cycles and Large Mixed-Responsibility Modules

**Files:**

- Create: `engine/persistence/metadata_engine.py`
- Create: `engine/persistence/models/*.py`
- Create: `engine/tools/db/inspectors/{sqlite,mysql,postgres,duckdb}.py`
- Modify: `engine/db.py`
- Modify: `engine/models.py`
- Modify: `engine/tools/db/inspect.py`
- Modify: imports in `engine/main.py`, `engine/dev_server.py`, `engine/ai_enrich.py`, `engine/environment/schema_catalog_sync.py`, `engine/sql/safety_gate.py`
- Test: `engine/tests/test_import_boundaries.py`
- Test: existing inspection tests

**Interfaces:**

- `metadata_engine.py` owns engine/session construction only.
- Each model module owns one aggregate; `engine/models.py` becomes an explicit
  re-export module or is removed after imports are updated.
- Each inspector implements `DatabaseInspector.inspect(profile)`.

- [ ] **Step 1: Write dependency-boundary tests**

```python
def test_engine_import_does_not_import_application_routes() -> None:
    module = import_fresh("engine.persistence.metadata_engine")
    assert "engine.api.agent" not in sys.modules
    assert hasattr(module, "build_metadata_engine")


def test_each_dialect_inspector_implements_the_common_protocol() -> None:
    for inspector in (SQLiteInspector(), MySqlInspector(), PostgresInspector(), DuckDbInspector()):
        assert isinstance(inspector, DatabaseInspector)
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_import_boundaries.py -q
```

Expected: current mixed imports and monolithic inspect module violate the
boundary assertions.

- [ ] **Step 3: Extract modules and remove lazy cycle imports**

Move code without retaining compatibility import shims. Replace local imports
used only to break cycles with narrow protocols/dependency injection. Split
the inspector by dialect and make it consume Phase 1 profiles/factory. Move
metadata engine/session setup out of ORM/model declarations.

- [ ] **Step 4: Run import and inspection suites**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_import_boundaries.py engine\tests\test_db_tools.py engine\tests\test_schema_sync.py -q
```

Expected: pass; CodeGraph import-cycle scan reports no production cycles.

## Task 3: Harden Desktop Sidecar Lifecycle, Bootstrap, CSP, and Navigation

**Files:**

- Create: `desktop/src/lib/engineBootstrap.ts`
- Create: `desktop/src/lib/externalNavigation.ts`
- Modify: `desktop/src/main.tsx`
- Modify: `desktop/src/lib/api/client.ts`
- Modify: `desktop/src-tauri/src/lib.rs`
- Modify: `desktop/src-tauri/tauri.conf.json`
- Modify: `desktop/src/components/ImageCell.tsx`
- Test: `desktop/src/lib/__tests__/engineBootstrap.test.ts`
- Test: `desktop/src/lib/__tests__/externalNavigation.test.ts`
- Test: `desktop/src-tauri/src/lib.rs`

**Interfaces:**

- Produces `bootstrapEngine(): Promise<AuthenticatedEngineConfig>`.
- Produces `openExternalUrl(url: string): Promise<void>` that only permits
  confirmed allowlisted `https` URLs.
- Rust supervisor exposes typed status: `starting`, `ready`, `failed`,
  `stopped`.

- [ ] **Step 1: Write startup/security failures**

```typescript
it("does not mount the app when unauthenticated health succeeds but config IPC fails", async () => {
  mockInvoke.mockRejectedValueOnce(new Error("sidecar config unavailable"));
  mockAuthenticatedProbe.mockResolvedValueOnce({ ok: true });

  await expect(bootstrapEngine()).rejects.toThrow("sidecar config unavailable");
});


it.each(["http://example.invalid", "file:///C:/secret", "javascript:alert(1)"])(
  "rejects unsafe external URL %s",
  async (url) => await expect(openExternalUrl(url)).rejects.toThrow(),
);
```

Add Rust tests that a directory or invalid first sidecar candidate falls back
to the next valid, signed/resource-root candidate, and that a child crash
transitions status to failed.

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
npx vitest run src/lib/__tests__/engineBootstrap.test.ts src/lib/__tests__/externalNavigation.test.ts --maxWorkers=1
cargo test --locked
```

Expected: current swallowed bootstrap failure, unsafe options, and candidate
selection do not satisfy the tests.

- [ ] **Step 3: Implement hardened lifecycle**

Require authenticated bootstrap before mounting the application. Show a startup
failure view within eight seconds when the sidecar cannot become ready. Start
the window without a blocking 40-second supervisor wait and update its status
asynchronously. Use graceful shutdown plus bounded forced termination; rotate
and redact stderr logs; watch child exit and publish failure state.

Remove `msSmartScreenProtection` disable and `--no-proxy-server`. Replace
inline scripts/styles and remote font imports so CSP can use `script-src
'self'`, local engine `connect-src`, and explicit restrictive base/object/form
directives. Remote images and links must use the external-navigation policy.

- [ ] **Step 4: Run desktop lifecycle tests**

Run:

```powershell
npx vitest run src/lib/__tests__/engineBootstrap.test.ts src/lib/__tests__/externalNavigation.test.ts --maxWorkers=1
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
```

Expected: pass.

## Task 4: Enforce Reproducible Dependencies, Audits, and Complete CI

**Files:**

- Create: Python lock files and SBOM generation script
- Modify: `requirements.txt`, `requirements-dev.txt`, `requirements-build.txt`
- Modify: `desktop/package-lock.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `build_sidecar.py`
- Create: `scripts/verify-clean-build.ps1`
- Test: `scripts/verify-clean-build.ps1`

- [ ] **Step 1: Write clean-build contract script**

Create `scripts/verify-clean-build.ps1` that:

```powershell
param([Parameter(Mandatory)][string]$Workspace)

$ErrorActionPreference = 'Stop'
Set-Location $Workspace
python -m venv .build_venv
.\.build_venv\Scripts\python.exe -m pip install --require-hashes -r requirements-build.lock
.\.build_venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
Push-Location desktop
npm ci
npm run build
Pop-Location
```

The script must then build the Tauri package and invoke the packaged smoke
script. Add Pester assertions that missing lock files or a local `.env` do not
silently bypass the intended install.

- [ ] **Step 2: Run against the current project and verify red**

Run:

```powershell
pwsh -File scripts\verify-clean-build.ps1 -Workspace (Get-Location)
```

Expected: current requirements and build dependency declarations cannot satisfy
the clean build contract.

- [ ] **Step 3: Generate locks and rewrite CI**

Generate separate hash-locked Python runtime, development, and build inputs.
Pin a tested SSH implementation/Paramiko combination. Update npm packages to
the fixed advisory ranges and remove unused dependencies such as unreferenced
Monaco modules where applicable. Generate SBOMs from locked manifests.

In CI, pin actions to commit SHA and set top-level `permissions: contents:
read`. Add independent jobs for backend, frontend, Rust, dependency audit, and
Windows package smoke. Full test commands are:

```yaml
- run: python -m pytest engine/tests engine/agent/tests engine/evaluation/tests
- run: python -m mypy engine
- run: python -m alembic check
- run: npm ci && npm test && npm run lint && npm run build
  working-directory: desktop
- run: cargo fmt --check && cargo clippy --locked -- -D warnings && cargo test --locked
  working-directory: desktop/src-tauri
- run: pwsh -File scripts/verify-clean-build.ps1 -Workspace $env:GITHUB_WORKSPACE
```

- [ ] **Step 4: Verify clean build and audits**

Run:

```powershell
npm audit --registry=https://registry.npmjs.org
.\.build_venv\Scripts\python.exe -m pip check
pwsh -File scripts\verify-clean-build.ps1 -Workspace (Get-Location)
```

Expected: current locked dependency graph passes audits according to the
project's configured severity policy and produces a runnable package.

## Task 5: Add Packaged Fault Injection, Observability, and Performance Budgets

**Files:**

- Create: `engine/observability/metrics.py`
- Create: `engine/observability/redaction.py`
- Create: `desktop/scripts/check-budgets.mjs`
- Create: `scripts/test-packaged-app.ps1`
- Modify: `engine/diagnostics/*`, `desktop/src/lib/diagnostics/clientLog.ts`, `desktop/src/pages/DiagnosticsPage.tsx`
- Modify: `desktop/vite.config.*`, `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`, `desktop/src/index.css`
- Test: `engine/tests/test_observability_redaction.py`
- Test: `desktop/src/lib/diagnostics/__tests__/clientLog.test.ts`
- Test: `desktop/scripts/check-budgets.mjs`

- [ ] **Step 1: Write redaction, budget, and package-fault tests**

```python
def test_semantic_redaction_removes_nested_authorization_and_query_values() -> None:
    value = {
        "headers": {"Authorization": "Bearer super-secret"},
        "query": {"api_key": "super-secret"},
    }

    assert "super-secret" not in repr(redact_for_diagnostics(value))
```

```javascript
assertBudget({
  entryGzipBytes: readGzipSize("dist/assets/index-*.js"),
  maxEntryGzipBytes: 350 * 1024,
  maxDistBytes: 4 * 1024 * 1024,
  maxSvgBytes: 200 * 1024,
});
```

`test-packaged-app.ps1` must install the produced package in a temporary user
profile and exercise: start, authenticated health, forced sidecar crash,
visible failure state, restart, graceful exit during SQLite write, and bounded
sidecar log rotation.

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_observability_redaction.py -q
npx vitest run src/lib/diagnostics/__tests__/clientLog.test.ts --maxWorkers=1
node desktop/scripts/check-budgets.mjs
```

Expected: current diagnostics redaction and bundle size violate the stated
contract.

- [ ] **Step 3: Implement metrics, redaction, and budgets**

Use one semantic redactor for backend errors, events, logs, artifacts, and
diagnostics. Bound individual and total logs, clear local/backend records
together, and rotate sidecar logs. Emit metrics for run transitions,
cancellation latency, checkpoint bytes, connection creation, catalog outcomes,
export duration, SSE replay, and bundle sizes.

Code-split heavy workspace/graph/chart modules. Import ECharts from
`echarts/core` with only required chart/render components. Remove unused SVG
variants and self-host or replace remote fonts. Enforce the stated budgets in
CI.

- [ ] **Step 4: Run performance/package verification**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_observability_redaction.py -q
npx vitest run src/lib/diagnostics/__tests__/clientLog.test.ts --maxWorkers=1
npm run build
node scripts/check-budgets.mjs
$installer = Get-ChildItem desktop\src-tauri\target\release\bundle\nsis\*.exe | Select-Object -First 1 -ExpandProperty FullName
pwsh -File scripts/test-packaged-app.ps1 -PackagePath $installer
```

Expected: all metrics/redaction tests pass; the package meets budgets and
fault-injection checks.

## Task 6: Align Documentation and Remove Obsolete Code

**Files:**

- Modify: `README.md`
- Modify: `desktop/README.md`
- Modify: `docs/README.md`
- Modify: affected source/test files after orphan scan
- Create: `scripts/check-documentation.ps1`
- Test: `scripts/check-documentation.ps1`

- [ ] **Step 1: Write documentation contract checks**

The script must parse documented commands and assert they exist in
`package.json`, CI, or scripts. It must fail when README names nonexistent
`npm run test:e2e`, `start.py`, or `run_desktop.py` commands.

- [ ] **Step 2: Run and verify red**

Run:

```powershell
pwsh -File scripts\check-documentation.ps1
```

Expected: current desktop README claims unsupported commands.

- [ ] **Step 3: Update docs and delete dead code**

Document the v2 reset, required credential re-entry, safe backup limitation,
supported package commands, CI gates, and security model. Remove modules found
by CodeGraph/orphan analysis that are only test-referenced and not part of the
new product path; do not retain unused dependencies simply to preserve them.

- [ ] **Step 4: Run docs/orphan checks**

Run:

```powershell
pwsh -File scripts\check-documentation.ps1
codegraph sync
```

Expected: documented commands resolve and no removed module remains referenced.

## Task 7: Final Whole-System Verification and Commit

- [ ] **Step 1: Run every enforced quality gate**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests engine\agent\tests engine\evaluation\tests -q -m "not real_llm and not e2e"
.\.build_venv\Scripts\python.exe -m mypy engine
.\.build_venv\Scripts\python.exe -m alembic check
npm test
npm run lint
npm run build
node scripts/check-budgets.mjs
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
npm audit --registry=https://registry.npmjs.org
pwsh -File scripts/verify-clean-build.ps1 -Workspace (Get-Location)
```

Expected: every command exits 0; external-service-only tests remain explicitly
separated rather than silently skipped.

- [ ] **Step 2: Review architecture boundaries**

Use CodeGraph to verify there is no production import or call path that bypasses
`CredentialVault`, `ConnectionFactory`, `AgentRunStateMachine`,
`ResultArtifact`, or Alembic initialization. Inspect runtime/package output for
the sentinel secret and assert it is absent.

- [ ] **Step 3: Commit Phase 3**

```powershell
git add engine desktop scripts requirements*.txt .github README.md docs
git commit -m "refactor: converge secure desktop architecture"
```
