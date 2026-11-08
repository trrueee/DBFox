# Independent Comic native fixture

This owns only ports 5187 (renderer) / 19233 (Electron CDP), an explicit isolated
runtime directory, and Playwright CLI sessions `comic-independent` and
`comic-independent-export`. Never use `close-all`. No model call is required.

Reuse decisions: source preparation is the existing full-package Comic fixture;
Main/Preload/EngineSupervisor remain production code. The final launcher serves
the production `desktop/dist` with the **verbatim exported Host CSP**, following
the established Game verification transport. It does not maintain its own CSP.
Only the native save destination, profile/CDP and OS window size are controlled.

Prerequisites: build `desktop` using `npm run build`; use existing dependencies.
From repository root, with a fresh absolute runtime path:

```powershell
$env:DBFOX_COMIC_PYTHON='D:/Project/DBFox/.venv/Scripts/python.exe'
$env:DBFOX_COMIC_NARROW='1'
node verification/testkit/comic_native_independent/launch.mjs <runtime>
npx --no-install --package @playwright/cli playwright-cli -s=comic-independent attach --cdp http://127.0.0.1:19233
npx --no-install --package @playwright/cli playwright-cli -s=comic-independent snapshot
```

The launcher blocks while the owned Electron is open; run browser commands in
another terminal. Screenshots need `output/playwright/comic-independent/`.
Use fresh snapshots to locate controls. The author interaction assertions are
not imported. Independent tested steps:

1. Open Comic Studio, then `灯塔归途 · 2 页 · v3`. Select the first dialogue and
   `编辑对象`. Fill `文字内容` with `独立验收：灯光仍在。第二行保留对白。`.
2. While the draft remains unsaved, write `{"width":1440}` then
   `{"width":960}` to `<runtime>/window-control.json` (UTF-8). This invokes
   Electron `BrowserWindow.setSize`, not Chromium viewport emulation. Collapse
   and expand main navigation; assert the textbox retains its exact value.
   `measure.cjs` checks whole-document and Studio horizontal bounds.
3. Save (v4), export the Artifact, download both JSON and HTML through their UI
   buttons. Switch to the work's stable tab, select page 2, and change its title
   to `独立验收改名：清晨` (v5).
4. Switch to the v4 Artifact, select `留下的光`, assert the old title/content.
   Return to the work tab, wait for v5, open `历史与恢复`, compare target 4
   (one page-title change), then `恢复为新版本` (v6). Export/download again.
   Compare **complete JSON bytes**, not just displayed text.
5. Close via `{"close":true}` in the control file. Before restart replace it
   with `{"width":960}`; invoke the launcher with the same runtime and `--reuse`.
   Open Comic Studio. `production-check.cjs` is the independently executed v6
   continuation: production CSP edit v7, restore v6 as v8, both downloads,
   second-page Artifact preview, and return to the stable v8 work tab.

```powershell
npx --no-install --package @playwright/cli playwright-cli -s=comic-independent run-code --filename verification/testkit/comic_native_independent/production-check.cjs
npx --no-install --package @playwright/cli playwright-cli -s=comic-independent console warning
```

The published run initially used the author's dev transport to v6, then closed
and reopened with this production-renderer transport for v7/v8. Do not label the
initial development CSP warning a production pass. The final transport has zero
console errors/warnings. Production HTTP preview is not an installed NSIS build.

For external HTML verification, serve **only `<runtime>/downloads`** using a
loopback read-only HTTP server (the recorded run used port 19334); open the
actual filename in `comic-independent-export`. Direct `file:` navigation was
unsupported. Assert two rendered SVG pages; the only recorded error was favicon
404. Close that exact session and stop that exact owned server.

`evidence.json` records measured widths, publisher package digest, download
hashes and screenshot hashes. The full initial edit sequence is described here;
the retained executable continuation expects an already verified v6 fixture.

No user baseline is owned by this fixture. See the independent backend report
for copied baseline dependencies. A mistakenly created, unused local junction
`desktop/desktop/node_modules` remains outside Git after automatic cleanup was
rejected; it is not needed for these commands and must not be recursively
deleted through its target.
