# Animation independent native verification

状态：当前

Date: 2026-09-07. Independent reviewer `/root/game_independent_review`, not the
Animation implementation author. The bounded native **functional** gate passes:
timeline/curve numeric editing, exact undo, playback, fixed historical Artifact,
real downloads, and narrow/wide usability. One known shared Host CSP violation
remains recorded below; this is not a clean security-console or release claim.

## Candidate and isolation

- Base `32693b8e`; branch `codex/animation-native-verification`, worktree
  `D:/Project/DBFox-worktrees/creative-animation-native-verification`.
- Only author `1aa66a3c5e0644ee619ed529c113291dac19090c` and engineering correction
  `57087c4bc776067750bae317ad2d35ab5ae4c0f8` were cherry-picked, respectively as
  `d60d6a9d` and `b4a01611`. No Animation product code was edited by the reviewer.
- Root's 39 changed/untracked baseline files were copied and hashed. All 39
  remain byte-identical at completion. Existing dependencies were reused via
  one correctly located `desktop/node_modules` junction; nothing was installed.
  Generated vendor byte normalization from the normal build is not committed.
- Isolated runtime:
  `D:/Project/DBFox-worktrees/creative-program/animation-native-independent`.
  Full signed Animation 1.0.2 package digest:
  `6036bd40d9aa999b6f931d4a0cce4d7b9a9d7e94a5f047951759491d63ad0abc`.
  The author seeding helper was reused, not the author's interaction assertions,
  screenshot conclusions or test scores.

## Actual host and original policy

`npm run build` passed, including Electron bundles, production token check and
bundle budget. From the first native launch, production `desktop/dist` was
served with the actual Host-exported `CONTENT_SECURITY_POLICY` verbatim. The
header was captured; no duplicate or relaxed CSP was introduced. It retains
`script-src 'self' dlc-asset:` and `style-src-elem 'self' dlc-asset:`, and excludes
`unsafe-eval`. Actual Electron Main, sandboxed Preload and EngineSupervisor ran
the Python sidecar. DLC installation, operations, Artifact ActionRuns and
Representation download streams were real.

Only the isolated profile/CDP, native save-dialog destination and OS window
size/shutdown were test controlled. No model was called. HTTP production
renderer preview with the real policy is not the installed `dbfox-app:` protocol
or frozen sidecar/NSIS distribution; those are not claimed by this run.

## Independent functional evidence

1. `Fox gesture` v7's fixed Artifact was downloaded, then its public
   `打开工作台` action opened the matching work by stable identity.
2. The actual keyframe inspector changed only `contact.tick` 4000→4200 and
   `contact.value` 6→8 (v8). Both unsaved fields survived native 960→1440 resize.
   A real downloaded v8 JSON and read-only durable audit show every other field
   unchanged. Undo produced v9, whose entire canonical document equals v7.
3. v7 was retrieved through the actual Host overflow menu after later edits;
   its download still matched the original hash. `打开工作台` from that old
   Artifact selected the same animation's current v9, not the frozen old head.
4. Actual Three playback projection was checked by seeking 0 and 4000ms:
   the visible object's translation changed 0→72px. Playback from 7900 reached
   8000 and stopped; another Play restarted from the beginning (observed 121ms),
   Pause worked, and Start restored tick 0. Owner database counts before and
   after playback were identical: 2 documents, 20 revisions, 2058 identities,
   20 receipts. Playback did not create durable edits.
5. The Bézier inspector changed only the first control point's x from .25→.4
   (v10). The real curve canvas redrew. Undo restored .25 as v11; its complete
   downloaded JSON again equals v7. The audit checks that no other curve,
   keyframe, clip, marker, target, track or timing field changed.
6. A separate Project's 2048-key document loaded. Its table paged from k0 to k50
   and back; k0's value was edited to 12.5 through its inspector (v12). The
   complete downloaded document retains 2048 keys and differs from v11 only in
   that value. No per-key DOM expansion was used: 50 table rows, 432–456
   descendant DOM elements in the measured states.

The five downloaded JSON files all exactly equal the corresponding persisted
canonical UTF-8 bytes and hash. Six native download events completed (v7 was
downloaded twice). No fake download or clipboard replacement was used.

| Document/version | Bytes | SHA-256 |
| --- | --- | --- |
| Fox v7 / v9 / v11 | 781 each | `83d4db55ab160e24c0d39d0029c4110c89db22790448f39281dfbb906c058cf9` |
| Fox v8 | 781 | `97aa96ede571b00b4ed953c1cebdceeb412530977f2d6bbd6c30a20889614bf7` |
| Large v12 | 148409 | `92fc1d34228ab1c15c83a069d406cc47f91f2a5e5c743cb30d2912bffe04fdeb` |

## Native layout and known shared limitation

These are actual `BrowserWindow.setSize` changes, not viewport emulation.
No fullscreen workaround was used. At 960px, the small editor measured
695.34px wide with expanded navigation (687/687 client/scroll), and 483.33px
with collapsed navigation (475/475). The large editor measured 719.33px at
960px (711/711), and 666.85px at 1440px (659/659). Whole-document width matched
the viewport in every measurement. Native DPI is 1.5; screenshot pixel width is
therefore larger than CSS viewport width. Vertical scrolling makes timeline,
table and property sections accessible; screenshots do not claim they all fit
at once. The preview is the declared local XY illustration, not full Scene 3D.

**Known shared Host issue, explicitly not attributed to Animation:** opening
`更多标签（2 个）` produced one CSP console error for injected inline style under
`style-src-elem 'self' dlc-asset:` from `assets/switch-bTgLtbJD.js:5`.
The reported blocked-style hash was
`sha256-nzTgYzXYDNe6BAHiiI7NNlfK8n/auuOAhh2t92YvuXo=`. The actual menu still opened
and selected the historical Artifact successfully. The coordinator confirmed
this is the already observed shared Host/Radix issue. Final console: **1 error,
0 warnings**; no claim of zero CSP violations. No policy bypass was attempted.

## Evidence, checks and limits

All linked screenshots were independently opened and visually inspected:

- [960px curve edit](../images/animation-independent/narrow-curve.png)
- [Fixed historical Artifact](../images/animation-independent/historical-artifact.png)
- [2048 keys at 960px](../images/animation-independent/large-narrow.png)
- [2048 keys at 1440px](../images/animation-independent/large-wide.png)

[Reproduction steps and owned fixture](../../verification/testkit/animation_native_independent/README.md),
[download/layout/CSP evidence](../../verification/testkit/animation_native_independent/evidence.json),
and [read-only canonical audit](../../verification/testkit/animation_native_independent/audit.py)
are committed separately from product code. The canonical audit passed, as did
fixture JS syntax and Python pyflakes. This run does not count the author's
19 backend or 12 capability cases as independent native tests, and does not
repeat the separately assigned backend review or Core cancellation repair.

Native Electron closed normally through the owned fixture's `app.quit` and its
launcher exited 0. Final check found no listeners on owned ports 5188/19234.
No unrelated services, profiles or user work were touched.

Mouse dragging, arbitrary long-session performance, full keyboard/accessibility
coverage, real-model creation quality, complete Scene+Animation RunLoop
composition, packaged installer behavior and the overall 20-DLC program are
outside this bounded result. No new Animation-specific functional blocker was
confirmed; the known shared Host CSP issue remains separately tracked.
