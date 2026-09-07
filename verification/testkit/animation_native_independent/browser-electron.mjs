import {app,BrowserWindow} from "electron";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {appendFileSync,mkdirSync,readFileSync} from "node:fs";
app.setPath("userData",join(process.env.DBFOX_RUNTIME_DIR,"electron-profile"));
app.setPath("logs",join(process.env.DBFOX_RUNTIME_DIR,"electron-logs"));
app.commandLine.appendSwitch("remote-debugging-port","19234");
if(process.env.DBFOX_ANIMATION_QA_DOWNLOAD==="1")app.on("session-created",(session)=>{
  session.on("will-download",(_event,item)=>{
    if(!/^animation-[a-f0-9]{32}-v[0-9]+\.json$/.test(item.getFilename()))return;
    const directory=join(process.env.DBFOX_RUNTIME_DIR,"downloads");mkdirSync(directory,{recursive:true});
    item.setSavePath(join(directory,item.getFilename()));
    item.once("done",()=>appendFileSync(join(process.env.DBFOX_RUNTIME_DIR,"download-evidence.jsonl"),JSON.stringify({boundary:"controlled-native-save-path",filename:item.getFilename(),state:item.getState(),bytes:item.getReceivedBytes(),path:item.getSavePath()})+"\n"));
  });
});
await import(pathToFileURL(join(process.cwd(),"dist-electron/main/index.js")).href);

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
