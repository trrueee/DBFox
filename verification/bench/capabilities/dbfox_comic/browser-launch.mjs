import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../../.."), desktop = join(root, "desktop"), directory = resolve(process.argv[2]);
const require = createRequire(join(desktop, "package.json"));
const { createServer } = await import(pathToFileURL(require.resolve("vite")).href);
const env = { ...process.env, DBFOX_RUNTIME_DIR: directory, DBFOX_DATABASE_URL: `sqlite:///${join(directory, "metadata.sqlite").replaceAll("\\", "/")}`,
  DBFOX_TESTING: "1", DBFOX_SYSTEM_DLC_DIR: "", DBFOX_SYSTEM_DLC_MANIFEST: "", DBFOX_ELECTRON_ENGINE_COMMAND: process.env.DBFOX_COMIC_PYTHON || "python",
  DBFOX_ELECTRON_RENDERER_URL: "http://127.0.0.1:5187" };
delete env.DBFOX_ELECTRON_SMOKE; delete env.DBFOX_ELECTRON_DEV_PARENT;
if (!process.argv.includes("--reuse")) {
  const prepared = spawnSync(env.DBFOX_ELECTRON_ENGINE_COMMAND, ["-m", "verification.bench.capabilities.dbfox_comic.browser_fixture", directory], { cwd: root, env, encoding: "utf8", windowsHide: true });
  if (prepared.status !== 0) throw new Error(prepared.stderr);
}
process.chdir(desktop);
const vite = await createServer({ root: desktop, configFile: join(desktop, "vite.config.ts"), server: { host: "127.0.0.1", port: 5187, strictPort: true } });
await vite.listen();
const electron = spawn(require("electron"), [join(here, "browser-electron.mjs")], { cwd: desktop, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
let tail = ""; electron.stderr.on("data", (value) => { tail = (tail + value).slice(-4000); }); electron.stdout.on("data", () => {});
console.log(JSON.stringify({ renderer: "http://127.0.0.1:5187", cdp: "http://127.0.0.1:19233", runtime: directory, electron_pid: electron.pid }));
const close = async () => { electron.kill(); await vite.close(); };
process.once("SIGINT", close); process.once("SIGTERM", close);
electron.once("exit", async (code) => { await vite.close(); if (code) console.error(tail); });
