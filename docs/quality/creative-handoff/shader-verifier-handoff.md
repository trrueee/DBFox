# Shader verifier closeout copy

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Creative DLC AI handoff

Source: creative/shader a293e46f, verification/testkit/shader_independent/HANDOFF.md. This copy preserves instructions; scripts and runtime data stay in their original worktree.

# Shader independent verification handoff

Status: paused by explicit user instruction on 2026-09-06 to preserve remaining usage and hand work to another AI. Do not resume implementation, verification or another DLC without new authorization.

## Current ownership and commits

This verifier is `/root/pixel_workbench`, formally Shader independent Verification Engineer, not a Shader author or its separate Adversarial reviewer. Director `/root` owns product fixes. Separate reviewer `/root/voxel_lead/domain_architect` owns `shader_adversarial*`. Do not modify their files or count their tests as ours.

Worktree: `D:/Project/DBFox-worktrees/creative-shader`, branch `creative/shader`. Independent completed evidence commit: `5fce70bc` (91 exact owner files). Full report: `docs/quality/shader-independent-verification.md`. Complete original manifest: `D:/Project/DBFox-worktrees/creative-program/shader-independent-files.txt`. Preserve all unrelated dirty baseline and the shared desktop node_modules junction.

Last completed product cold verification: `8a412cdb`, signed digest `8a14196f82c580313a08ee98d763a1d37f1cd3f9df00c8e279307201275fb361`. Final canonical reads preserve Native v1, Coral v12 and large v24 hashes/texture bytes. Real native JSON downloads are full-object equivalent. Current large v24 has 62 stages and 128 actually used uniforms; loading took 30 requests / 840 ms. Original cold ActionRun `run_15203363d6854c3e8b26844c40b4beb7` completed one GPU attempt / 609 ms; downloaded 853-byte PNG matches public stream and all 65,536 independently decoded pixels. Do not replay that publication.

Earlier completed evidence includes actual same-Sidecar native Agent error→driver diagnostics→local repair→compile→preview with Dock closed, full Coral human/Agent stress, dirty native drafts/CAS/explicit resolution, uniform editing, historical deletion and read-only diagnostic navigation, real compute cancellation and rejected late handoff, project/session delayed response isolation, native context loss/reconnect/resource disposal, Host disable/restart/enable/restart, and actual executor/process-death reconciliation without replay. Original fixture mistakes remain documented.

Final focused results on `8a412cdb`: 9 independent Python tests / 25.53 s; 13 author + 9 independent frontend tests / 29.01 s; typecheck and Python pyflakes pass; lint zero errors / five old Host warnings. Do not rerun long backend/GPU suites solely for the CSS change below.

## Unfinished item and latest installed package

Final screenshot `docs/quality/evidence/shader-independent/final-cold-gpu.png` revealed a long pixel hash expanding the narrow Artifact grid. Director confirmed and committed CSS-only `cd8c94a7` (artifact minmax column, child min-width zero, long-text wrapping). This is not an unfixed product implementation item; **independent layout closure remains unverified**.

The complete new package was signed/trusted/installed/enabled with digest `7e6f64e5c84e6f190e0a12c59ffe414e65890024d518afff39b4b9239dde683c`; all 13 frontend archive files match. Provenance: `evidence/package-provenance-cd8c94a7.json`. An Electron launch and initial CDP attach succeeded, but the endpoint was no longer available when the layout driver was invoked (browser-not-open / ECONNREFUSED). No new narrow/wide measurements or screenshots were produced. Do not describe that attempted run as a CSS pass or claim a cause for the endpoint stopping.

Prepared, unexecuted phase: `browser-artifact-layout.cjs`. Once reauthorized, run only existing preview v24 at narrow and fullscreen widths, one existing compile card and fixed historical v1 document card. It checks actual child/scroll bounds and records zero owner mutations/GPU requests. Save its JSON output as `evidence/electron-artifact-layout.json`, inspect the four screenshots, update the report, and commit only the small independent supplement. The driver may need selector adjustment after observing the actual native UI; preserve any failures honestly.

## Retained runtime and recovery

External profile/owner data/downloads: `D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime`. It contains metadata.sqlite, electron-profile, signed-package provenance, native `downloads`, and `download-events.jsonl`. Keys, archives, logs and SQLite stay external and must not be committed. The model boundary was already stopped; it is unnecessary for the layout check. No task Electron PID or CDP listener remains at handoff. Do not kill other owners' Electron processes.

Python: `D:/Project/DBFox/.venv/Scripts/python.exe`. Node/npm are installed under `D:/tools/node.js`. Production renderer dist already exists. No rebuild, dependency install, new signing or GPU execution is needed to verify the currently installed CSS package.

After renewed authorization, from the Shader worktree:

```powershell
node verification/testkit/shader_independent/browser-launch.mjs D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime --reuse
npx.cmd --no-install --package @playwright/cli playwright-cli -s=shader-independent attach --cdp http://127.0.0.1:19228
npx.cmd --no-install --package @playwright/cli playwright-cli -s=shader-independent run-code --filename verification/testkit/shader_independent/browser-artifact-layout.cjs --raw
```

The launcher uses actual Main/Preload/EngineSupervisor, source Python Sidecar and production dist served on `127.0.0.1:5182` with the exact Host CSP. It is not a packaged-installer/frozen-Sidecar or dbfox-app protocol proof. Close only this task's Electron through the native Host close button afterward.

Other retained limitations: Windows computer-use pipe unavailable prevented native PNG picker completion; native DownloadItem destination was fixture-controlled; no long-run GC/heap bound and no real-LLM intelligence claim. Separate Adversarial status belongs to that reviewer's report. The Director decides integration and release.
