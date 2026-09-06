# Shader independent verification testkit

This directory owns independent stimuli, controlled external boundaries and sanitized public evidence. It imports no product verification logic into production. The verifier did not author Shader product changes. The current report is `docs/quality/shader-independent-verification.md`.

Run ordinary independent tests from the repository root:

```powershell
python -m pytest verification/tests/system/test_shader_independent_production_factory.py verification/tests/system/test_shader_independent_commit_fence.py verification/tests/system/test_shader_independent_recovery.py -q --tb=short
python -m pyflakes verification/testkit/shader_independent verification/tests/system/test_shader_independent_production_factory.py verification/tests/system/test_shader_independent_commit_fence.py verification/tests/system/test_shader_independent_recovery.py
```

From `desktop`:

```powershell
npx vitest run src/features/dlc/__tests__/dbfoxShaderFixture.test.ts src/features/dlc/__tests__/dbfoxShaderIndependent.test.ts --maxWorkers=1
npm run typecheck:test
npm run lint
```

The first frontend file is author regression, not part of the independent count. Negative compute fixtures never claim successful GPU compilation or rendering. Recovery uses actual ToolExecutor timeout/cancel and child `os._exit` at the real transaction boundary; reconciliation cannot replay mutation.

Electron evidence was produced on Windows with the actual Main/Preload/EngineSupervisor and source Python Sidecar. `browser-launch.mjs` serves the existing production `desktop/dist` using Vite preview and imports the exact Host CSP. It requires the existing pinned dependencies; do not install into a shared node_modules junction. `prepare.py` signs the complete package and uses normal trust/install/enable lifecycle. `--upgrade` requires this task's previous Electron to be closed and preserves owner data through normal disable/uninstall/install/enable. Keys, profiles, databases, signed archives and raw logs belong in an external task directory, never this repository.

The model server is loopback only and emits official-SDK-validated native Responses SSE. It has no DBFox imports, database access or invented tool results. Workload plans reuse the Director's complete stimuli, while actual GPU, native UI, immutable files and interruption assertions are independently verified. No real-LLM intelligence claim is made.

Browser scripts are recorded acceptance phases, not a bulk replay suite. Several contain the immutable IDs of the original public evidence dataset. Mutation phases have version/state guards and must not be rerun after their writes committed. A script failure after publication must be recovered through public reads, not retried. `browser-final-cold.cjs` records the final native phase; `browser-final-audit.cjs` recovers its specific already completed ActionRun without another compute request. This dependence on the retained task dataset is explicit; the ordinary pytest/Vitest suites create their own isolated data.

Original external runtime: `D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime`. Renderer port 5182, CDP port 19228, model-boundary port 19328. Typical launch/attachment and one phase:

```powershell
node verification/testkit/shader_independent/browser-launch.mjs D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime --reuse
npx --no-install --package @playwright/cli playwright-cli -s=shader-independent attach --cdp http://127.0.0.1:19228
npx --no-install --package @playwright/cli playwright-cli -s=shader-independent run-code --filename verification/testkit/shader_independent/browser-final-audit.cjs --raw
python -m verification.testkit.shader_independent.audit_final D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime
```

`audit_native_agent.py`, `audit_png.py`, `audit_snapshots.py` and `audit_final.py` independently check public RunItems or actual native files. Original evidence must remain paired with its package/version: the final canonical byte loader can change JSON key order without changing the immutable canonical revision fingerprint. `audit_final.py` checks canonical bytes before parsed-object equality, original texture bytes, native DownloadItem completion, public PNG stream bytes and every final pixel. The testkit controls only the native download destination; it does not prove a human Save-dialog path choice. The unavailable native file picker service is reported as an acceptance limitation.
