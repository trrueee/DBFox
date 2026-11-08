import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../.."), desktop = join(root, "desktop"), directory = resolve(process.argv[2]);
const require = createRequire(join(desktop, "package.json"));
const { preview } = await import(pathToFileURL(require.resolve("vite")).href);
const env = { ...process.env, DBFOX_RUNTIME_DIR: directory, DBFOX_DATABASE_URL: `sqlite:///${join(directory, "metadata.sqlite").replaceAll("\\", "/")}`,
  DBFOX_TESTING: "1", DBFOX_SYSTEM_DLC_DIR: "", DBFOX_SYSTEM_DLC_MANIFEST: "", DBFOX_ELECTRON_ENGINE_COMMAND: process.env.DBFOX_ANIMATION_PYTHON || "python",
  DBFOX_ELECTRON_RENDERER_URL: "http://127.0.0.1:5188" };
env.DBFOX_ANIMATION_QA_DOWNLOAD="1";
delete env.DBFOX_ELECTRON_SMOKE; delete env.DBFOX_ELECTRON_DEV_PARENT;
if (!process.argv.includes("--reuse")) {
  const prepared = spawnSync(env.DBFOX_ELECTRON_ENGINE_COMMAND, ["-m", "verification.bench.capabilities.dbfox_animation.browser_fixture", directory], { cwd: root, env, encoding: "utf8", windowsHide: true });
  if (prepared.status !== 0) throw new Error(prepared.stderr);
}
// Reuse the Host's actual policy, with production renderer assets.
await require("esbuild").build({ entryPoints: [join(desktop, "main/appProtocol.ts")], outfile: join(directory, "app-policy.mjs"), platform: "node", format: "esm", logLevel: "silent" });
const { CONTENT_SECURITY_POLICY } = await import(pathToFileURL(join(directory, "app-policy.mjs")).href);
process.chdir(desktop);
const vite = await preview({ root: desktop, configFile: join(desktop, "vite.config.ts"), preview: { host: "127.0.0.1", port: 5188, strictPort: true, headers: { "Content-Security-Policy": CONTENT_SECURITY_POLICY } } });
const closePreview = () => new Promise(done => vite.httpServer.close(done));
const electron = spawn(require("electron"), [join(here, "browser-electron.mjs")], { cwd: desktop, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
let tail = ""; electron.stderr.on("data", (value) => { tail = (tail + value).slice(-4000); }); electron.stdout.on("data", () => {});
console.log(JSON.stringify({ renderer: "http://127.0.0.1:5188", cdp: "http://127.0.0.1:19234", runtime: directory, electron_pid: electron.pid }));
const close = async () => { electron.kill(); await closePreview(); };
process.once("SIGINT", close); process.once("SIGTERM", close);
electron.once("exit", async (code) => { await closePreview(); if (code) console.error(tail); });
