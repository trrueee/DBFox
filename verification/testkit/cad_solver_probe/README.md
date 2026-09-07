# CAD solver deployment probe

> 文档类型：验证指南
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：CAD 实现前的上游求解器选型，不是产品验收

Run from the CAD worktree root. This probe uses the unmodified published
`@salusoft89/planegcs@1.2.0`; it does not install a DBFox dependency or run npm
lifecycle scripts. Node 24.13.0 and HeadlessChrome 152 were used.

## Prepare the pinned package

```powershell
New-Item -ItemType Directory -Force output/cad-solver-probe | Out-Null
npm pack @salusoft89/planegcs@1.2.0 --ignore-scripts --registry=https://registry.npmjs.org --pack-destination output/cad-solver-probe
```

Before extracting with Python `tarfile.extractall(..., filter="data")`, verify
the tarball's SHA-512 base64 equals
`NcdWJnJRCnIDvM9yJD98Jm8qaK//wRqMEbJ0WtibKnhbzI484TjIEbYD6EVUZejndXGC9yBkuKgqXg+9buzi6Q==`.
Extract into `output/cad-solver-probe`; the archive has a `package/` prefix.
The WASM must be 508,141 bytes with SHA-256
`039601df53b11cd06d0f8626cd2e9422b07aca31b18db9ba437b7d26cf5594c5`.

The matching upstream tag `1.2.0` resolves to
`ee9b156da9827a91a56a888a53520f63d5cffaa6`. Preserve this source identity for any
subsequent rebuild; do not run `update-freecad.sh` against mutable upstream HEAD.

## Execute

```powershell
node verification/testkit/cad_solver_probe/planegcs.mjs output/cad-solver-probe/package output/cad-solver-probe/node-result.json
python verification/testkit/cad_solver_probe/serve.py
```

In a separate terminal, use the Playwright CLI skill and a dedicated session:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=cad-solver-policy open http://127.0.0.1:18846/strict
npx --yes --package @playwright/cli playwright-cli -s=cad-solver-policy --raw eval '() => window.probeResult'
npx --yes --package @playwright/cli playwright-cli -s=cad-solver-policy goto http://127.0.0.1:18846/wasm-only
npx --yes --package @playwright/cli playwright-cli -s=cad-solver-policy --raw eval '() => window.probeResult'
npx --yes --package @playwright/cli playwright-cli -s=cad-solver-policy close
```

Wait until `probeResult` is present. Stop the probe server with Ctrl+C afterwards.
The strict route uses the checked-out Host policy. The second route adds only
`wasm-unsafe-eval` on this local server; no production file is changed.

## Expected evidence for the published package

- Node: five cases pass, including 200 repeated width changes on the same sketch.
- Strict browser: instantiation rejected by CSP; the upstream ArrayBuffer retry
  is rejected too.
- WASM-only browser: still rejected with `EvalError` in the generated bindings.
  Both pages reject the explicit JavaScript dynamic-evaluation control.

Browser failure is a measured deployment incompatibility, not a passing CAD
gate. A rebuilt module must be remeasured with the same tests and separately
prove real signed DLC installation, lifecycle, authority, cancellation, bounded
memory, solids, topology, constraints, exports, and the original user task.
