# Comic independent backend verification

状态：当前

Independent reviewer: `/root/game_independent_review`, not the Comic implementation author.
Date: 2026-09-07. This closes the bounded backend/red-team and deterministic
Story-to-Comic composition review. It does **not** approve complete Comic native
UI, visual quality, online-model creativity, or the full creative DLC program.

## Exact candidate and reproducible environment

- Base: `a9630358`; independent branch `codex/comic-verification` in
  `D:/Project/DBFox-worktrees/creative-comic-verification` (no `.codegraph` index).
- Comic author: `196f949f1da802d95b3ad907d51e3e248f03a444`, cherry-picked as
  `52726fad`; documentation correction `ae07b554`, cherry-picked as
  `3ab465ad55146e42798e047caaeb981466a08b65`.
- The root's 39 preexisting changed/untracked baseline files were copied and
  SHA-256 checked before verification. They include Story's existing chapter
  work and SDK/Core baseline; they are not attributed to Comic or committed by
  this reviewer. Final audit: 36 remain byte-identical; only the three Story
  backend files below contain the separately authored fixes.
- Story fixes `ffea18d5` and `d4c98a6b` are applied to this tree's copied baseline,
  but are **not committed here**. Exact textual deltas were checked against root
  before copying `store.py`, `tools.py`, and `chapter_tools.py`. This includes the
  declaration on the baseline's eighth append tool, whose implementation is
  preexisting uncommitted user work. A clean checkout of this report's commit
  alone does not reproduce that user baseline.
- Windows checkout added 15 CRLF bytes to Visualization's unrelated
  `frontend/vendor/vega-runtime.js`. After verifying that removing CRLF matched
  root bytes exactly, the file was copied byte-for-byte from root. No manifest,
  vendor content, or tracked Git diff was changed to relax the engineering gate.
- Python: existing root `.venv`; migrated temporary metadata and per-test signed
  DLC installation/storage. No package installation, real user data, credentials,
  paid model call, or native Electron process was used.

Signed package digests used in the passing full composition:

| Owner | SHA-256 package digest |
| --- | --- |
| dbfox.story | `f86b4084fc88d750162d21f1ae2557f191fa0bf591e57deacf8519e2b4faa95e` |
| dbfox.comic | `7cbc28e9914c8e4b9b7a5f110d7a813040fecc8fa01622c5eebe461c5c3841bc` |

The baseline hash inventory and JUnit output are local run evidence under
`D:/Project/DBFox-worktrees/creative-program/` (`comic-review-baseline.json` and
`comic-independent-final.xml`); executable tests and this report are durable
review artifacts. Test fixtures sign the complete package using a fixture-only
publisher key, install/trust/enable it through production `DlcPackageService`,
and load actual production contributions. They do not import another DLC's
private domain code.

## Findings and source corrections

1. **Story admission was broken before any model request.** The first composition
   attempt failed in `authorize_project_resources` with
   `AttributeError: 'WorldDescriptor' object has no attribute 'to_scope_ref'`.
   Story returned a private lookalike instead of the SDK descriptor. Root fixed
   the source in `ffea18d5` by directly using `ProjectResourceDescriptor`.
2. **Story's tools lacked invocation resource requirements.** After fixing
   admission, the same Run reached `story_chapters_list` but failed because its
   invocation had no Story scopes. The error misleadingly requested `world_id`
   despite one world. Production binding derives authority from
   `ToolExecutionSpec.required_resources`; Story had declared none. Root fixed
   Story's declarations in `d4c98a6b`, using the public SDK requirement and
   `world_id` selector. The relation proposal input has no `world_id`, so it now
   uses a selector-free requirement and resolves that canonical scope directly.
   Independent tests cover real binding with absent/foreign resources, direct
   runtime rejection, successful proposal without the nonexistent field, and
   persisted Story-only invocation authority in the full Run.
3. **Comic's architecture document failed the current-doc gate.** The author
   candidate placed status `历史` in a current architecture file. `ae07b554`
   correctly preserves the accepted investigation with status `已接受` and points
   to the current implementation document. Engineering gates then pass.

The two production failures were exposed by the original unmodified composition
path, then retested on the same path after source corrections. No Core/SDK
compatibility shim, manually inserted invocation scopes, extra RunLoop, fabricated
Story Artifact, or weaker assertion was introduced to make them pass. No further
confirmed Comic backend blocker was found in the bounded attacks below.

## Independent attacks and outcomes

Seven Comic red-team cases pass through real package contributions, resource
admission, `ToolRuntime`, public operations, ActionRun, and Representation:

- Foreign Project admission/operation access and wrong frozen Comic selection
  reject without new revisions, receipts, or object identities.
- Two concurrent edits from the same version yield one winner; a frozen Agent
  cannot overwrite it by supplying a fresh `expected_version`.
- Cancellation at the production precommit check leaves no state; cancellation
  after commit reports cancellation but exact receipt reconciliation recovers
  the durable result without duplicating it. These target deterministic checks,
  not arbitrary OS process-kill timing.
- Invalid multi-placement, deletion of a referenced speaker, and moving an
  existing element through the wrong panel reject atomically.
- A 60 KB UTF-8 CJK page is projected into complete entries within the 24 KB
  observation bound; offsets progress and every entry is retrieved exactly once.
- A real ActionRun artifact rejects forged producer identity, Project, resource
  scopes, and version-override parameters. HTML escapes injected script/image
  text. The exact historical JSON survives Comic deletion and normal disable /
  re-enable. This is a representation check, not a live-browser XSS audit.

The additional Story regression independently exercises production binding and
runtime with no scope, a foreign world selector, and a valid relation proposal.

## Real Story-to-Comic composition and supported boundary

The complete signed Story and Comic packages share one actual production Run.
Only the external OpenAI HTTP/SSE boundary is deterministic. It emits native
Responses `tool_search_call` / `tool_search_output` and function calls against
the actual deferred schemas; the real adapter, compiler, discovery, dispatcher,
resource authorization, budget accounting, durable invocations, and Artifact
repository execute normally. There is no second search protocol or RunLoop.

The model script consumes the actual Story chapter-list and chapter-read
observations, including source identity and SHA-256, then calls Comic create,
all eight original named editing tools, and export. It preserves a fixed Chinese
chapter's dialogue and scene description, links a bubble to its placed character,
and verifies the final panel order in the immutable exported document.

- 12 successful invocations; 13 HTTP requests; 10 real Comic Artifacts.
- Default prompt budget is unchanged at 32,768 estimated tokens; measured peak
  is 19,827 with both complete packages present (Comic contributes 20 tools).
- Both persisted Story calls carry exactly one Story-world scope. Each Comic
  producer carries only its exact Comic scope; Artifact refs match the producer.
- Updating the source chapter through the public Story operation and disabling
  Story leave Comic JSON and HTML bytes unchanged.

**Actual support boundary:** this Story baseline exposes public chapter Tool
observations but no Story Artifact Representation provider. Therefore the test
proves observation-to-Comic creation plus real Comic Representation. It does not
claim Representation-to-Representation import or durable Story `DERIVED_FROM`
lineage; it explicitly rejects fabricated lineage. The root coordinator approved
this accurate characterization. The script verifies domain execution and data
integrity, not autonomous creative decisions from an online LLM.

## Gates and remaining scope

From this worktree root, using `D:/Project/DBFox/.venv/Scripts/python.exe`:

```powershell
python -m pytest verification/tests/system/test_story_comic_composition.py verification/tests/system/test_comic_independent_redteam.py verification/tests/system/test_engineering_contracts.py -q --tb=short
python -m pyflakes verification/testkit/comic_independent.py verification/tests/system/test_comic_independent_redteam.py verification/tests/system/test_story_comic_composition.py
```

Results: **54 passed in 21.80s** (9 independent tests + 45 engineering contracts);
pyflakes passes. Author baseline `test_comic_dlc.py`: **24 passed in 8.66s**,
recorded separately and not counted as independent attacks.

Native Electron interaction, browser rendering, accessibility, frontend tests,
and live-model quality are outside this review. The previously observed 960 px
window squeezing the shared Host Dock to 43 px remains a separate Host acceptance
item until its author's repair receives independent native verification. These
backend results must not be used to close that UI gate or to declare the entire
Comic DLC / 20-DLC program complete.
