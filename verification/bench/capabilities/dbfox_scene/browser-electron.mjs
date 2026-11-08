// Verification entry: isolate app profile, then load the unmodified real Main/Preload.
import { app } from "electron";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { appendFileSync } from "node:fs";

app.setPath("userData", join(process.env.DBFOX_RUNTIME_DIR, "electron-profile"));
app.setPath("logs", join(process.env.DBFOX_RUNTIME_DIR, "electron-logs"));
app.commandLine.appendSwitch("remote-debugging-port", process.env.SCENE_QA_CDP_PORT || "19223");
// Default is passive. Explicit --accept-downloads controls only the native Save
// dialog destination; Electron itself receives and writes the downloaded bytes.
const downloadDirectory = process.env.SCENE_QA_DOWNLOAD_DIR;
if (downloadDirectory && resolve(downloadDirectory) !== resolve(process.cwd(), "../output/playwright")) throw new Error("Unsafe verification download directory");
app.on("session-created", session => {
 let completed = 0;
 const onDownload = (event, item) => {
  if (!/^scene-[a-f0-9]{32}-v[0-9]+\.(glb|gltf)$/.test(item.getFilename())) return;
  if (downloadDirectory) item.setSavePath(join(downloadDirectory, item.getFilename().endsWith(".glb") ? "interactive-scene.glb" : "interactive-scene.gltf"));
  const record = phase => {
    appendFileSync(join(process.env.DBFOX_RUNTIME_DIR, "browser-download-observations.jsonl"), JSON.stringify({
      phase, time: Date.now(), filename: item.getFilename(), state: item.getState(),
      savePath: item.getSavePath(), totalBytes: item.getTotalBytes(), receivedBytes: item.getReceivedBytes(),
      userGesture: item.hasUserGesture(), defaultPrevented: event.defaultPrevented,
      boundary: downloadDirectory ? "controlled-native-save-path" : "passive",
    }) + "\n");
  };
  record("will-download");
  item.on("updated", () => record("updated"));
  item.once("done", () => { record("done"); if (downloadDirectory && ++completed === 2) session.removeListener("will-download", onDownload); });
 };
 session.on("will-download", onDownload);
});
await import(pathToFileURL(join(process.cwd(), "dist-electron/main/index.js")).href);
