// Isolate only profile/CDP; execute the unmodified production Main and Preload.
import { app, session, BrowserWindow } from "electron";
import { mkdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { pathToFileURL } from "node:url";
app.setPath("userData", join(process.env.DBFOX_RUNTIME_DIR, "electron-profile"));
app.setPath("logs", join(process.env.DBFOX_RUNTIME_DIR, "electron-logs"));
app.commandLine.appendSwitch("remote-debugging-port", "19233");
// Deterministic OS save-dialog destination; the production blob/stream path is unchanged.
app.whenReady().then(() => {
  const downloads = join(process.env.DBFOX_RUNTIME_DIR, "downloads");
  mkdirSync(downloads, { recursive: true });
  session.defaultSession.on("will-download", (_event, item) => item.setSavePath(join(downloads, basename(item.getFilename()))));
});
if (process.env.DBFOX_COMIC_NARROW === "1") app.on("browser-window-created", (_event, window) => {
  window.once("ready-to-show", () => window.setSize(960, 840));
});
await import(pathToFileURL(join(process.cwd(), "dist-electron/main/index.js")).href);

// Test-only OS window sizing and graceful shutdown, never renderer emulation.
let prior = "";
const control = setInterval(() => {
  try {
    const raw = readFileSync(join(process.env.DBFOX_RUNTIME_DIR, "window-control.json"), "utf8");
    if (raw === prior) return; prior = raw;
    const command = JSON.parse(raw);
    if (command.close) { clearInterval(control); app.quit(); return; }
    if (![960, 1440].includes(command.width)) throw new Error("Invalid fixture size");
    for (const window of BrowserWindow.getAllWindows()) { window.unmaximize(); window.setSize(command.width, 840); }
  } catch (error) { if (error.code !== "ENOENT") console.error(error.message); }
}, 250);
