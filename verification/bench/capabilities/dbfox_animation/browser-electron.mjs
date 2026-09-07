import {app} from "electron";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {appendFileSync,mkdirSync} from "node:fs";
app.setPath("userData",join(process.env.DBFOX_RUNTIME_DIR,"electron-profile"));
app.setPath("logs",join(process.env.DBFOX_RUNTIME_DIR,"electron-logs"));
app.commandLine.appendSwitch("remote-debugging-port","19241");
if(process.env.DBFOX_ANIMATION_QA_DOWNLOAD==="1")app.on("session-created",(session)=>{
  session.on("will-download",(_event,item)=>{
    if(!/^animation-[a-f0-9]{32}-v[0-9]+\.json$/.test(item.getFilename()))return;
    const directory=join(process.env.DBFOX_RUNTIME_DIR,"downloads");mkdirSync(directory,{recursive:true});
    item.setSavePath(join(directory,item.getFilename()));
    item.once("done",()=>appendFileSync(join(process.env.DBFOX_RUNTIME_DIR,"download-evidence.jsonl"),JSON.stringify({boundary:"controlled-native-save-path",filename:item.getFilename(),state:item.getState(),bytes:item.getReceivedBytes(),path:item.getSavePath()})+"\n"));
  });
});
await import(pathToFileURL(join(process.cwd(),"dist-electron/main/index.js")).href);
