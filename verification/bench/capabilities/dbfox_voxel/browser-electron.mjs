// Isolated profile and read-only debugger entry, then unmodified production Main.
import { app } from "electron";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { appendFileSync } from "node:fs";

app.setPath("userData", join(process.env.DBFOX_RUNTIME_DIR, "electron-profile"));
app.setPath("logs", join(process.env.DBFOX_RUNTIME_DIR, "electron-logs"));
app.commandLine.appendSwitch("remote-debugging-port", process.env.VOXEL_QA_CDP_PORT || "19227");
const destination = process.env.VOXEL_QA_DOWNLOAD_DIR;
if (destination && resolve(destination) !== resolve(process.cwd(), '../verification/bench/capabilities/dbfox_voxel/evidence')) throw new Error('Unsafe download directory');
if (destination) app.on('session-created', session => {
  const onDownload = (_event, item) => {
    if (!/^world_[a-f0-9]{32}-v[0-9]+\.voxel\.json$/.test(item.getFilename())) return;
    item.setSavePath(join(destination, item.getFilename()));
    item.once('done', (_event, state) => {
      appendFileSync(join(process.env.DBFOX_RUNTIME_DIR, 'voxel-download-events.jsonl'), JSON.stringify({filename:item.getFilename(),state,
        totalBytes:item.getTotalBytes(),receivedBytes:item.getReceivedBytes(),boundary:'verification-controlled-native-save-path'})+'\n');
      session.removeListener('will-download', onDownload);
    });
  };
  session.on('will-download', onDownload);
});
await import(pathToFileURL(join(process.cwd(), "dist-electron/main/index.js")).href);
