// Real Host Main/Preload + EngineSupervisor + signed Animation payload.
import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,"../../../.."),desktop=join(root,"desktop");
const directory=resolve(process.argv[2]),python=process.argv[3]?.startsWith("--")?"D:/Project/DBFox/.venv/Scripts/python.exe":process.argv[3]||"D:/Project/DBFox/.venv/Scripts/python.exe";
const require=createRequire(join(desktop,"package.json"));
const {createServer}=await import(pathToFileURL(require.resolve("vite")).href);
const env={...process.env,DBFOX_RUNTIME_DIR:directory,DBFOX_DATABASE_URL:`sqlite:///${join(directory,"metadata.sqlite").replaceAll("\\","/")}`,DBFOX_TESTING:"1",DBFOX_SYSTEM_DLC_DIR:"",DBFOX_SYSTEM_DLC_MANIFEST:"",DBFOX_ELECTRON_ENGINE_COMMAND:python,DBFOX_ELECTRON_RENDERER_URL:"http://127.0.0.1:5191"};
delete env.DBFOX_ELECTRON_SMOKE;delete env.DBFOX_ELECTRON_DEV_PARENT;
if(process.argv.includes("--accept-downloads"))env.DBFOX_ANIMATION_QA_DOWNLOAD="1";
if(!process.argv.includes("--reuse")){const result=spawnSync(python,["-m","verification.bench.capabilities.dbfox_animation.browser_fixture",directory],{cwd:root,env,encoding:"utf8",windowsHide:true});if(result.status!==0)throw new Error(result.stderr);}
process.chdir(desktop);
const vite=await createServer({root:desktop,configFile:join(desktop,"vite.config.ts"),server:{host:"127.0.0.1",port:5191,strictPort:true}});await vite.listen();
const electron=spawn(require("electron"),[join(here,"browser-electron.mjs")],{cwd:desktop,env,windowsHide:true,stdio:["ignore","pipe","pipe"]});
let tail="";electron.stderr.on("data",(value)=>{tail=(tail+value.toString()).slice(-3000);});electron.stdout.on("data",()=>{});
console.log(JSON.stringify({renderer:"http://127.0.0.1:5191",cdp:"http://127.0.0.1:19241",runtime:directory,pid:electron.pid}));
const close=async()=>{electron.kill();await vite.close();};process.once("SIGINT",close);process.once("SIGTERM",close);
electron.once("exit",async(code)=>{await vite.close();if(code)console.error(tail);});
