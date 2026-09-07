# CAD solver deployment probe

> 文档类型：验证指南
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：CAD 实现前的上游求解器选型，不是产品验收

Run from the CAD worktree root. This probe supports the published
`@salusoft89/planegcs@1.2.0` and a source rebuild; it does not install a DBFox
dependency. The published-package preparation does not run lifecycle scripts.
The isolated rebuild runs the pinned upstream binding tools' install steps.
Node 24.13.0 and HeadlessChrome 152 were used for execution.

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

## Fixed source rebuild: measured success

[rebuild-evidence.json](rebuild-evidence.json) records the actual 2026-09-07
Windows build and browser results. [cases.mjs](cases.mjs) runs the same five
numeric checks in Node and Chrome. The rebuilt solver passes all five in both
Node and the `wasm-only` page; `new Function` remains rejected with `EvalError`.
The strict page still fails at WASM compilation. This qualifies the solver for
further deployment evaluation, not for the current unmodified Host policy.

| Rebuilt asset | Raw bytes | gzip bytes (Python gzip, level 9, mtime 0) |
| --- | ---: | ---: |
| planegcs.js | 27,602 | 10,739 |
| planegcs.wasm | 508,141 | 173,175 |

Use only a task directory such as ignored `output/cad-solver-probe`. No Docker,
global tool install, product lock change, or permanent environment activation is
needed. The actual build used local VS 2022 BuildTools 17.14.37314.3, its CMake
3.31.6-msvc6 and Ninja 1.12.1, and Python 3.12.7. Paths below assume the worktree
root and a fresh task directory; retain the already prepared npm package.

1. Obtain the PlaneGCS source from its fixed `1.2.0` tag into `upstream` and verify
   commit `ee9b156da9827a91a56a888a53520f63d5cffaa6`. The existing probe used an
   integrity-checked archive of that source. Preserve LF source bytes; for Git
   use `git -c core.autocrlf=false clone --branch 1.2.0 --depth 1 https://github.com/Salusoft89/planegcs.git upstream`.
   Never execute `update-freecad.sh`:
   it downloads mutable FreeCAD HEAD and applies patches. This build uses the
   patched files already in the PlaneGCS tag, whose `planegcs/commit.txt` names
   `5f8eac49f31626354ee69bf40616bac801ca5560`.
2. Clone [official emsdk](https://github.com/emscripten-core/emsdk) tag `3.1.45`
   into `emsdk`; verify commit `c8dcb45665fec5e743336703f1d22a191810f2a8`.
   From that directory run `python emsdk.py install 3.1.45`, then
   `python emsdk.py activate 3.1.45` **without `--permanent`**. This writes its
   local `.emscripten` configuration. The tag resolves to official build
   `2b7c5fb8ffeac3315deb1f82ab7bf8da544f84a1`; emcc reports source
   `ef3e4e3b044de98e1811546e0bc605c65d3412f4`. Downloads use the official
   `storage.googleapis.com/webassembly/emscripten-releases-builds` URLs recorded
   in that fixed SDK manifest. This old SDK does not independently verify a
   publisher checksum for those archives; observed executable hashes are in
   the evidence, not claimed as a signed toolchain attestation.
3. Clone [Eigen](https://gitlab.com/libeigen/eigen) tag `3.4.0` into `eigen`;
   verify commit `3147391d946bb4b6c68edd901f2add6ac1f31f8c`.
   Download [Boost 1.74.0](https://archives.boost.io/release/1.74.0/source/boost_1_74_0.tar.gz)
   to `boost_1_74_0.tar.gz`; compare SHA-256 with the
   [official checksum](https://archives.boost.io/release/1.74.0/source/boost_1_74_0.tar.gz.json):
   `afff36d392885120bcac079148c177d1f6f7730ec3d47233aa51b0afa4db94a5`.
   Extract with Python `tarfile`'s `filter="data"`; only `boost_1_74_0/boost/`
   headers and `LICENSE_1_0.txt` are needed. Both dependencies are compile-time
   headers. The original Docker image did not pin their apt versions, so this
   is a documented input pin, not a claim to reproduce its binary byte for byte.
4. In `upstream`, run `npm ci --ignore-scripts --no-audit --no-fund` using its
   unchanged lockfile. Set the current process PATH to put
   `../emsdk/node/16.20.0_64bit/bin` first and point `npm_config_cache` and
   `npm_config_devdir` to task-local `npm-cache` and `node-gyp` absolute paths.
   Run that SDK's `npm.cmd rebuild tree-sitter tree-sitter-cpp --foreground-scripts`.
   The native generator is Tree-sitter 0.20.6 / C++ grammar 0.20.5. Node 24's
   first attempt failed because this old addon forces C++17 while Node 24
   requires C++20; Node 16.20.0 completed the original install steps successfully.
5. From `upstream/build-bindings`, create `../planegcs_dist` and run the same
   template arguments as upstream `process_all.sh`:

```powershell
& ../../emsdk/node/16.20.0_64bit/bin/node.exe ../node_modules/tsx/dist/cli.mjs ./render_templates.ts gcs_system.cpp.njk ../planegcs/bindings.cpp enums.ts.njk ../planegcs_dist/enums.ts id.ts.njk ../planegcs_dist/id.ts gcs_system.ts.njk ../planegcs_dist/gcs_system.ts gcs_system_mock.ts.njk ../planegcs_dist/gcs_system_mock.ts constraints.ts.njk ../planegcs_dist/constraints.ts constraint_param_index.ts.njk ../planegcs_dist/constraint_param_index.ts
```

6. Return to the worktree root and run:

```powershell
python verification/testkit/cad_solver_probe/rebuild.py --task output/cad-solver-probe --cmake 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe' --ninja 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
node verification/testkit/cad_solver_probe/planegcs.mjs output/cad-solver-probe/rebuilt-package output/cad-solver-probe/node-rebuilt-result.json
python verification/testkit/cad_solver_probe/serve.py --package output/cad-solver-probe/rebuilt-package
```

The rebuild checks [source-hashes.json](source-hashes.json), including the
generated bindings. It copies native sources to `portable-source`, adapts only
the Linux Boost/Eigen include paths, and adds the official
[`DYNAMIC_EXECUTION=0`](https://emscripten.org/docs/tools_reference/settings_reference.html#dynamic-execution)
setting to upstream CMake's release link flags. The remaining release flags,
including exceptions policy, Closure, 5 MB stack, fixed memory and undefined
symbol policy, are inherited unchanged. No generated/minified JS is edited.
The published TypeScript wrapper's compiled files are copied unchanged into an
isolated package, replacing only the freshly compiled JS and WASM. This is an
investigative assembly, not a published npm package or a product dependency.

Use the earlier browser commands with session `cad-independent`, capture
`window.probeResult` on each route, and close only that session and the local
server. A successful `wasm-only` page has `passed: 5`, `ok: true`, empty
diagnostics, and `javascript_eval: "EvalError"`. Browser times are a single
sample, not a benchmark. The impossible triangle still returns failure with
an empty conflict list, so both solve status and conflicts remain necessary.

## Remaining deployment and provenance decisions

The chosen reuse is the existing FreeCAD solver, the upstream binding generator
and Emscripten's official setting. No solver, compatibility layer, alternate
backend, or host permission change was added. Raw asset sizes fit the existing
20 MiB bound. Execution placement still requires an explicit Host/platform
decision because strict CSP rejects all WASM; this probe cannot authorize it.

Package metadata, wrapper source headers and vendored FreeCAD headers carry
different LGPL version wording. Eigen's `COPYING.README` states primarily MPL2
with some BSD/LGPL files; this build did not add `EIGEN_MPL2_ONLY`. Boost has its
own Boost Software License. Complete transitive notices, source correspondence,
relink/rebuild distribution requirements, patched-FreeCAD provenance and release
toolchain attestation remain to be resolved before shipping. This investigation
does not establish license clearance, full API safety, memory/cancellation
bounds, arbitrary constraint robustness, or signed Electron/DLC installation.
