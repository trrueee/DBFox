# Independent Animation native verification

The fixture owns renderer 5188 / CDP 19234 and CLI session
`animation-independent`. It never starts a model request. Use only a new,
explicitly named isolated runtime, or `--reuse` for that same runtime.

Reuse decisions: package seeding is the existing Animation full signed fixture;
the production renderer/CSP launch pattern is the already validated Comic/Game
transport. `launch.mjs` imports the actual Host `CONTENT_SECURITY_POLICY` and
serves production `desktop/dist` with that unmodified header. Production
Main/Preload/EngineSupervisor and HTTP/domain operations execute normally.
Only profile/CDP, actual `BrowserWindow.setSize`, graceful `app.quit`, and native
save-dialog destination are controlled. Business responses are not mocked.

Build using existing dependencies (`cd desktop; npm run build`). From repository
root in a separate launcher terminal:

```powershell
$env:DBFOX_ANIMATION_PYTHON='D:/Project/DBFox/.venv/Scripts/python.exe'
node verification/testkit/animation_native_independent/launch.mjs <absolute-runtime>
```

Write UTF-8 `{"width":960}` or `{"width":1440}` to
`<runtime>/window-control.json` to resize the actual native window to that width
and 840px height. Write `{"close":true}` to close only that native application;
replace it with a size command before any `--reuse` restart. The launcher exits
when its Electron exits. Do not use browser `close-all` or viewport emulation.

```powershell
npx --no-install --package @playwright/cli playwright-cli -s=animation-independent attach --cdp http://127.0.0.1:19234
npx --no-install --package @playwright/cli playwright-cli -s=animation-independent snapshot
```

The independently executed progression, using fresh UI snapshots:

1. In `animation-browser-project`, open Animation Studio and choose
   `Fox gesture · v7`. Export a fixed Artifact, download its JSON, and use
   `打开工作台`. It opens the exact bound work tab.
2. Open the three-key table, select `contact`, fill key time `4200` and value
   `8`. Resize 960→1440 with the unsaved draft and assert both values remain.
   Save in the `关键帧` fieldset (v8), export/download. Return, undo (v9),
   export/download. For hidden v7, use the actual Host `更多标签` menu, download
   v7 again, then `打开工作台` and verify the current work is v9.
3. `playback.cjs` was executed at v9: seek 0/4000/7900, play to 8000, restart,
   pause, reset. Record SQLite owner table counts immediately before and after;
   playback must not write. These read-only counts are separate from UI control.
4. Open the key table and choose `begin`. At 960px fill `控制点 1 时间` with
   `0.4`; `curve.cjs` saves v10, undoes to .25 as v11, exports/downloads v11.
   The script intentionally expects that exact prepared phase.
5. Collapse/expand navigation, then select `animation-large-project`. Open its
   Studio and choose `2048 key timing study · v11`. Open the key table, move to
   page 2 (`k50`) and back to page 1 (`k0`), edit k0 value to `12.5`, save v12,
   and export/download. Measure at actual 960 and 1440 native widths.

```powershell
npx --no-install --package @playwright/cli playwright-cli -s=animation-independent run-code --filename verification/testkit/animation_native_independent/measure.cjs
npx --no-install --package @playwright/cli playwright-cli -s=animation-independent console warning
python verification/testkit/animation_native_independent/audit.py <absolute-runtime>
```

The audit is read-only and expects the completed recorded progression. It
compares whole domain documents and actual download bytes to the corresponding
SQLite canonical revision/hash. It reads no other profile. The server must
still be running for its CSP header check. Save screenshots under
`output/playwright/animation-independent/`; committed copies and measurements
are linked by `evidence.json`. The exact initial fill/click progression is
documented here; this is not a claim that an unexecuted monolithic UI test ran.

The recorded run encountered the known shared Host overflow-menu dynamic-style
CSP error. The menu still selected the old Artifact. Never relax the policy or
describe the console as clean. No new Animation-specific product defect was
confirmed. Mouse dragging, a full accessibility audit and packaged installer
behavior are outside this bounded run.
