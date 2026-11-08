# Workspace inventory at handoff

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Creative DLC AI handoff

Snapshot taken during documentation closeout. Other agents may add only their final checkpoint commits afterward; see [agent closeout](agent-closeout.md). Do not assume a branch tip includes user uncommitted baseline.

## Worktrees

```text
worktree D:/Project/DBFox
HEAD e4732e46e1653f61ccc3bebe3f485258dc85c2a7
branch refs/heads/codex/creative-program

worktree D:/Project/DBFox-worktrees/creative-animation
HEAD 1b175d7354d64c033b591d3ea4bb2c913ebd1139
branch refs/heads/creative/animation

worktree D:/Project/DBFox-worktrees/creative-artifact-authority
HEAD e1bbff4e5edebc42823285a255814b442e4fd798
branch refs/heads/codex/creative-artifact-authority

worktree D:/Project/DBFox-worktrees/creative-cad
HEAD f67edd5755038db5809dad62fd8254ea4bbde90d
branch refs/heads/creative/cad

worktree D:/Project/DBFox-worktrees/creative-comic
HEAD dffeb6036c6786317877fba80e28a4a4aba1f7bc
branch refs/heads/creative/comic

worktree D:/Project/DBFox-worktrees/creative-composition
HEAD 362244756eaf7f167aaf357e813338cf4c7ce24b
branch refs/heads/codex/creative-composition

worktree D:/Project/DBFox-worktrees/creative-game
HEAD 813452586f81c47668c0e0f0325d7a1470ac4907
branch refs/heads/creative/game

worktree D:/Project/DBFox-worktrees/creative-host-artifacts
HEAD 00d43bfe0e89ba77bf18a4072f0f3c3f2c102af3
branch refs/heads/creative/host-artifacts

worktree D:/Project/DBFox-worktrees/creative-pixel
HEAD 13e2fcf96a1ca541f7df96a6d2dd5e57a24b7c83
branch refs/heads/creative/pixel

worktree D:/Project/DBFox-worktrees/creative-scene
HEAD 0a4eca4fff9b21e0cd971ce940a9e95e069e5ff9
branch refs/heads/creative/scene

worktree D:/Project/DBFox-worktrees/creative-shader
HEAD a293e46f27cf3e80b61c1f7ee80cd6261d0ab552
branch refs/heads/creative/shader

worktree D:/Project/DBFox-worktrees/creative-voxel
HEAD 0b5813e649b8ba004ec44ab56aea9fc25622d18a
branch refs/heads/creative/voxel

worktree D:/Project/DBFox-worktrees/evaluation-spider-retrieval-benchmark
HEAD 68c5f31817c6bb22de56b9daca63252781d30e7d
branch refs/heads/evaluation/spider-retrieval-benchmark

```

## Pre-existing root changes to preserve

Only names/status are recorded; no mixed diff, credentials, runtime database or logs are copied.

```text
 M .github/pull_request_template.md
 M CONTRIBUTING.md
 M dbfox_dlc_api.py
 M desktop/package-lock.json
 M desktop/src/lib/api/generated/types.gen.ts
 M desktop/src/lib/api/generated/zod.gen.ts
 M dlcs/dbfox.story/README.md
 M dlcs/dbfox.story/backend/chapter_tools.py
 M dlcs/dbfox.story/backend/contracts.py
 M dlcs/dbfox.story/backend/contributions.py
 M dlcs/dbfox.story/backend/store.py
 M dlcs/dbfox.story/backend/tools.py
 M dlcs/dbfox.story/frontend/index.css
 M dlcs/dbfox.story/frontend/index.js
 M dlcs/dbfox.story/manifest.template.json
 M dlcs/dbfox.workspace/README.md
 M dlcs/dbfox.workspace/backend/contracts.py
 M dlcs/dbfox.workspace/backend/contributions.py
 M dlcs/dbfox.workspace/backend/service.py
 M dlcs/dbfox.workspace/manifest.template.json
 M docs/architecture/README.md
 M docs/architecture/agent-core-capability-dlc-contract.md
 M docs/architecture/agent-runtime.md
 M docs/architecture/backend.md
 M docs/architecture/dlc-sdk-cli.md
 M docs/architecture/implementation-map.md
 M docs/architecture/runtime-dlc-platform.md
 M engine/agent/repositories/events.py
 M engine/agent/run_item.py
 M engine/dlc/api.py
 M engine/dlc/compiler.py
 M verification/tests/system/test_dbfox_workspace_dlc_package.py
 M verification/tests/system/test_engineering_contracts.py
 M verification/tests/system/test_story_dlc.py
 M verification/tests/system/test_system_dlc_bootstrap.py
?? desktop/src/features/dlc/__tests__/dbfoxStoryFixture.test.ts
?? dlcs/dbfox.story/backend/consistency.py
?? docs/architecture/core-kernel-constitution.md
?? verification/tests/system/fixtures/dlc_api_v2_surface.txt
```

## External originals

`D:/Project/DBFox-worktrees/creative-program/` preserves the eight original Lead instructions, baseline-head/status/untracked files and mixed patches. Do not commit or forward those mixed patches without checking ownership and sensitive content. The eight public task templates and original user brief have been copied into this directory for portability.

`D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime` contains retained native verification runtime data. It is deliberately not part of this documentation bundle. See the Shader closeout for exact reuse instructions.
