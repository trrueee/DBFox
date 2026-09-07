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

> 文档类型：验证交接
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：Shader 独立验证与保留的外部运行环境

The user reauthorized development and verification after the 2026-09-06 pause. Focused Shader Artifact layout verification is complete. Current authoritative results are in `docs/quality/shader-independent-verification.md`; program integration remains the Director's responsibility.

## Current ownership and commits

This verifier is `/root/pixel_workbench`, formally Shader independent Verification Engineer, not a Shader author or its separate Adversarial reviewer. Director `/root` owns product fixes. Separate reviewer `/root/voxel_lead/domain_architect` owns `shader_adversarial*`. Do not modify their files or count their tests as ours.

Worktree: `D:/Project/DBFox-worktrees/creative-shader`, branch `creative/shader`. Independent completed evidence commit: `5fce70bc` (91 exact owner files). Full report: `docs/quality/shader-independent-verification.md`. Complete original manifest: `D:/Project/DBFox-worktrees/creative-program/shader-independent-files.txt`. Preserve all unrelated dirty baseline and the shared desktop node_modules junction.

Last completed product cold verification: `8a412cdb`, signed digest `8a14196f82c580313a08ee98d763a1d37f1cd3f9df00c8e279307201275fb361`. Final canonical reads preserve Native v1, Coral v12 and large v24 hashes/texture bytes. Real native JSON downloads are full-object equivalent. Current large v24 has 62 stages and 128 actually used uniforms; loading took 30 requests / 840 ms. Original cold ActionRun `run_15203363d6854c3e8b26844c40b4beb7` completed one GPU attempt / 609 ms; downloaded 853-byte PNG matches public stream and all 65,536 independently decoded pixels. Do not replay that publication.

Earlier completed evidence includes actual same-Sidecar native Agent error→driver diagnostics→local repair→compile→preview with Dock closed, full Coral human/Agent stress, dirty native drafts/CAS/explicit resolution, uniform editing, historical deletion and read-only diagnostic navigation, real compute cancellation and rejected late handoff, project/session delayed response isolation, native context loss/reconnect/resource disposal, Host disable/restart/enable/restart, and actual executor/process-death reconciliation without replay. Original fixture mistakes remain documented.

Final focused results on `8a412cdb`: 9 independent Python tests / 25.53 s; 13 author + 9 independent frontend tests / 29.01 s; typecheck and Python pyflakes pass; lint zero errors / five old Host warnings. Do not rerun long backend/GPU suites solely for the CSS change below.

## Closed Artifact layout item and installed package

Final screenshot `docs/quality/evidence/shader-independent/final-cold-gpu.png` revealed a long pixel hash expanding the narrow Artifact grid. Director committed CSS-only `cd8c94a7` (root integration `88fcb110`). Independent continuation `/root/shader_evidence_finish` verified completed narrow and wide previews on 2026-09-07 without authoring product code or replaying GPU work.

The package digest remains `7e6f64e5c84e6f190e0a12c59ffe414e65890024d518afff39b4b9239dde683c`; provenance is `evidence/package-provenance-cd8c94a7.json`. The original unavailable-CDP attempt was unsuccessful. A subsequent intermediate narrow capture was still loading, so the driver now waits for enabled Download PNG. Final replacement captures show loaded native pixels at both widths, with client/scroll widths 319/319 and 1440/1440. Compile report, historical document and read-only source also each remain 319/319. These Artifact images are separate from older Studio screenshots.

Completed phase: `browser-artifact-layout.cjs`; output: `evidence/electron-artifact-layout.json`. All five `artifact-*.png` screenshots were visually inspected. `audit_artifact_layout.py` checks the signed archive, loaded CSS hash, recorded bounds, preview readiness, historical source and native DownloadItem completion. The new 1,434-byte JSON download fully equals the independently preserved canonical v1 document plus textures. The phase observed no document mutation/compile/preview POSTs. Result: `evidence/artifact-layout-audit.json`. No remaining Shader layout item requires replaying previous writes or GPU workloads.

## Retained runtime and recovery

External profile/owner data/downloads: `D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime`. It contains metadata.sqlite, electron-profile, signed-package provenance, native `downloads`, and `download-events.jsonl`. Keys, archives, logs and SQLite stay external. The model boundary was not restarted. Native Host Close ended the continuation's Electron; launcher exit 0 and absent 5182/19228 listeners were independently checked. No task Electron remains. Do not kill other owners' processes.

Python: `D:/Project/DBFox/.venv/Scripts/python.exe`. Node/npm are installed under `D:/tools/node.js`. Production renderer dist already exists. No rebuild, dependency install, new signing or GPU execution is needed to verify the currently installed CSS package.

Only if future product changes require fresh evidence, use the retained phase from the Shader worktree:

```powershell
node verification/testkit/shader_independent/browser-launch.mjs D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime --reuse
npx.cmd --no-install --package @playwright/cli playwright-cli -s=shader-independent attach --cdp http://127.0.0.1:19228
npx.cmd --no-install --package @playwright/cli playwright-cli -s=shader-independent run-code --filename verification/testkit/shader_independent/browser-artifact-layout.cjs --raw
```

The launcher uses actual Main/Preload/EngineSupervisor, source Python Sidecar and production dist served on `127.0.0.1:5182` with the exact Host CSP. It is not a packaged-installer/frozen-Sidecar or dbfox-app protocol proof. Close only this task's Electron through the native Host close button afterward.

Other retained limitations: Windows computer-use pipe unavailable prevented native PNG picker completion; native DownloadItem destination was fixture-controlled; no long-run GC/heap bound and no real-LLM intelligence claim. Separate Adversarial status belongs to that reviewer's report. The Director decides integration and release.
