// Isolate only profile/CDP; execute the unmodified production Main and Preload.
import { app, session } from "electron";
import { mkdirSync } from "node:fs";
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
