// Only isolate profile/CDP and the optional native Save destination; load real Main unchanged.
import { app } from "electron";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { appendFileSync, mkdirSync } from "node:fs";

app.setPath("userData", join(process.env.DBFOX_RUNTIME_DIR, "electron-profile"));
app.setPath("logs", join(process.env.DBFOX_RUNTIME_DIR, "electron-logs"));
app.commandLine.appendSwitch("remote-debugging-port", process.env.PIXEL_QA_CDP_PORT || "19225");
const downloadDirectory = process.env.PIXEL_QA_DOWNLOAD_DIR;
if (downloadDirectory && resolve(downloadDirectory) !== resolve(process.cwd(), "../output/playwright")) throw new Error("Unsafe verification download directory");
if (downloadDirectory) mkdirSync(downloadDirectory, { recursive: true });
app.on("session-created", session => {
  const onDownload = (event, item) => {
    const match = /^pixel_[a-f0-9]{32}-r[0-9]+-(png|sheet)\.png$/.exec(item.getFilename());
    if (!match) return;
    if (downloadDirectory) item.setSavePath(join(downloadDirectory, match[1] === "png" ? "interactive-pixel.png" : "interactive-pixel-sheet.png"));
    const record = phase => appendFileSync(join(process.env.DBFOX_RUNTIME_DIR, "browser-download-observations.jsonl"), JSON.stringify({
      phase, time: Date.now(), filename: item.getFilename(), state: item.getState(), savePath: item.getSavePath(),
      totalBytes: item.getTotalBytes(), receivedBytes: item.getReceivedBytes(), userGesture: item.hasUserGesture(),
      defaultPrevented: event.defaultPrevented, boundary: downloadDirectory ? "controlled-native-save-path" : "passive",
    }) + "\n");
    record("will-download");
    item.on("updated", () => record("updated"));
    item.once("done", () => record("done"));
  };
  session.on("will-download", onDownload);
  app.once("will-quit", () => session.removeListener("will-download", onDownload));
});
await import(pathToFileURL(join(process.cwd(), "dist-electron/main/index.js")).href);
