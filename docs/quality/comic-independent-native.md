# Comic independent native verification

状态：当前

Date: 2026-09-07. Reviewer `/root/game_independent_review` did not implement
Comic. The bounded native gate now passes: real editing, historical preview,
return to the work, exact restore, real downloads, original Host CSP, and
960/1440 window plus navigation transitions. No new Comic product defect was
confirmed in these interactions. This supplements [backend/red-team evidence](comic-independent-verification.md),
not an online-model creativity or full-program release decision.

## Candidate and isolation

- Comic `196f949f1da802d95b3ad907d51e3e248f03a444`, documentation `ae07b554`,
  and independent backend commit `7f6835ec` in `creative-comic-verification`.
- Host `60456cf9` applied **only** to
  `desktop/src/features/appShell/ConversationWorkspaceLayout.tsx`, its matching
  `__tests__/ConversationWorkspaceLayout.test.tsx`, and
  `docs/architecture/frontend.md`, committed here as `bd30db1e`. Game product,
  Game screenshots and Game fixture changes were not imported.
- Build boundary fix `809fa7ea` cherry-picked as `e17f06b5`.
- Story's already reviewed corrections remain atop the copied user baseline;
  this native fixture only installs Comic. All 36 unaffected baseline files
  still match their initial SHA-256; the other three retain only root's Story
  corrections. No baseline product changes are included in this evidence commit.
- Isolated runtime:
  `D:/Project/DBFox-worktrees/creative-program/comic-native-independent`.
  Complete signed package digest:
  `7eba83e991ac08f61a7d46d92f458b17c17dd52f4a67d54844df34ed6a1aa5eb`.
  Different fixture publishers can produce a different package digest from the
  backend fixture; this digest identifies the actual native installation.

## Actual native path and CSP

Real Electron Main/Preload/EngineSupervisor launched the Python sidecar with an
isolated migrated database and signed Comic package. UI operations and Artifact
ActionRuns use production HTTP services and Representation streaming. Only
profile/CDP, native save-dialog destination, and `BrowserWindow.setSize` were
controlled by the test fixture. No business operation or frontend response was
stubbed; no model/API payment or user data was involved.

The initial v3-v6 interaction used the existing author's Vite development
transport: zero console errors, one Electron CSP warning. To close the requested
original-CSP gate, the reviewer ran **`npm run build` successfully**, including
the production token and bundle-budget checks, closed the first native window,
and reopened the same durable runtime using production `dist` assets. The
fixture imports `CONTENT_SECURITY_POLICY` from the actual Host source and
serves it verbatim as the response header, with no copied policy or relaxation.
The recorded header includes `script-src 'self' dlc-asset:` and
`script-src-attr 'none'`, without `unsafe-eval`. Under this policy the real
native v6-v8 edit/restore/export path completes with **0 errors, 0 warnings**.

This is a production renderer with original Host policy in the real unpackaged
Electron host and Python sidecar. It is not an NSIS installation or frozen
sidecar packaging test and does not claim `dbfox-app:` protocol deployment.

## Independent assertions

1. First-page dialogue was edited through the actual inspector from v3 to v4.
   The unsaved text remained exact through OS 960→1440→960 transitions and main
   navigation collapse/expand. Save remained usable in the narrow layout.
2. v4 was exported to a real immutable Artifact. Editing the second-page title
   produced v5; v4's second-page preview retained `留下的光`. Returning through
   the work's stable tab loaded the same current Comic, not the library or a
   different resource. This asserts work identity; per-object selection and
   uncommitted drafts across a full tab unmount are not a promised feature.
3. History comparison showed exactly one change, `page2.title`. Restoring target
   4 created v6. Real downloaded v4/v6 JSON bytes were identical.
4. Normal shutdown/restart preserved v6. Under the verbatim Host CSP, a real
   page-title edit created v7; restoring 6 created v8. Export, both download
   buttons, second-page Artifact rendering, and return to the v8 work succeeded.
5. **All three complete downloaded JSON files, v4/v6/v8, are 3012 bytes with
   SHA-256 `3813bed715944b480e020eebfff88c6420868b11684501be5af52da97bc864ae`.**
   HTML files are 8264 bytes each; their hashes differ because their truthful
   revision labels differ. Exact hashes are in the evidence manifest.
6. The actual downloaded v6 HTML was reopened through a loopback read-only
   server: both pages, all four panels, Chinese dialogue and character labels
   rendered. Only the missing favicon generated a 404; no page-script error.

The original shared Host 43px failure is no longer reproduced. Measured
960px/native-navigation-expanded Studio width was 719.33px (client/scroll
719/719), and navigation-collapsed width was 483.33px (483/483). The production
CSP native window also displays the editable second-page storyboard at 960px;
at 1440px its measured Studio width is 653.42px (653/653), with the same page and
view still selected. Whole-document width never exceeds the measured viewport.
No fullscreen workaround was used. OS display scale is 1.5, so 960px screenshots
are 1440 physical pixels wide; these are actual webContents screenshots.

## Viewed evidence and reproduction

All four images below were opened and visually inspected by the independent
reviewer. They show storyboard placeholders, not AI-generated illustrations.
Vertical canvas/inspector scrolling is part of the workbench; screenshots do not
claim every offscreen control fits simultaneously.

- [960px production CSP Studio](../images/comic-independent/production-csp-studio.png)
- [960px production CSP Artifact](../images/comic-independent/production-csp-artifact.png)
- [1440px production CSP split workspace](../images/comic-independent/production-csp-wide.png)
- [Actually downloaded HTML reopened](../images/comic-independent/export-reopened.png)

[Fixture and steps](../../verification/testkit/comic_native_independent/README.md),
[machine-readable hashes and measurements](../../verification/testkit/comic_native_independent/evidence.json),
and [executed production continuation](../../verification/testkit/comic_native_independent/production-check.cjs)
are committed with this report. The own native window closed normally via
`app.quit`; its launcher exited 0. The export browser and own read-only server
were closed. Final socket inspection found no listeners on owned ports
5187, 19233, or 19334. Root's unrelated native windows/ports were not touched.

Environment note: a mistaken unused local junction at
`D:/Project/DBFox-worktrees/creative-comic-verification/desktop/desktop/node_modules`
was left in place after automatic review rejected a cleanup command with
`blocked by policy`. The command intended non-recursive removal of that checked
junction and its empty parent; it was not retried through another tool or shell.
It is outside Git and has no execution role. The correct dependency junction is
`desktop/node_modules`. Production build only restored generated vendor bytes;
no vendor manifest/content diff was committed.

No full accessibility audit, all-browser/device matrix, installed-package
security test, or live LLM creation assessment was performed. The native scope
and previously completed backend scope can now be assessed together; they do
not imply all 20 DLCs are complete.
