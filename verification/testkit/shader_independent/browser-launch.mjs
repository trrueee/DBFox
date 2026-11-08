// Uses unmodified production Main/Preload/EngineSupervisor and a task-owned profile.
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const desktop = join(root, 'desktop');
const directory = resolve(process.argv[2]);
const python = process.argv[3] && !process.argv[3].startsWith('--') ? process.argv[3] : 'D:/Project/DBFox/.venv/Scripts/python.exe';
const require = createRequire(join(desktop, 'package.json'));
const { preview } = await import(pathToFileURL(require.resolve('vite')).href);
await mkdir(directory, { recursive: true });
const env = { ...process.env, DBFOX_RUNTIME_DIR: directory,
  DBFOX_DATABASE_URL: `sqlite:///${join(directory, 'metadata.sqlite').replaceAll('\\', '/')}`,
  DBFOX_TESTING: '1', DBFOX_SYSTEM_DLC_DIR: '', DBFOX_SYSTEM_DLC_MANIFEST: '',
  DBFOX_ALLOW_LOOPBACK_LLM_HTTP: '1',
  DBFOX_ELECTRON_ENGINE_COMMAND: python, DBFOX_ELECTRON_RENDERER_URL: 'http://127.0.0.1:5182',
  SHADER_QA_CDP_PORT: '19228' };
delete env.DBFOX_ELECTRON_SMOKE;
delete env.DBFOX_ELECTRON_DEV_PARENT;
const prepared = process.argv.includes('--reuse') ? { status: 0 } : spawnSync(python,
  ['-m', 'verification.testkit.shader_independent.prepare', directory],
  { cwd: root, env, encoding: 'utf8', windowsHide: true });
if (prepared.status !== 0) throw new Error(`Shader QA setup failed: ${prepared.stderr}`);
if (prepared.stdout) process.stdout.write(prepared.stdout);
// Compile the existing exported policy verbatim; do not maintain a second CSP.
await require('esbuild').build({ entryPoints: [join(desktop, 'main/appProtocol.ts')],
  outfile: join(directory, 'app-policy.mjs'), platform: 'node', format: 'esm', logLevel: 'silent' });
const { CONTENT_SECURITY_POLICY } = await import(pathToFileURL(join(directory, 'app-policy.mjs')).href);
process.chdir(desktop);
const vite = await preview({ root: desktop, configFile: join(desktop, 'vite.config.ts'),
  preview: { host: '127.0.0.1', port: 5182, strictPort: true,
    headers: { 'Content-Security-Policy': CONTENT_SECURITY_POLICY } } });
const closePreview = () => new Promise(resolveClose => vite.httpServer.close(resolveClose));
const electron = spawn(require('electron'), [join(here, 'browser-electron.mjs')],
  { cwd: desktop, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let tail = '';
electron.stderr.on('data', value => { tail = (tail + value.toString()).slice(-4000); });
electron.stdout.on('data', () => {});
console.log(JSON.stringify({ renderer: 'http://127.0.0.1:5182', rendererBuild: 'production dist with verbatim Host CSP', cdp: 'http://127.0.0.1:19228', runtime: directory, electron_pid: electron.pid }));
const close = async () => { electron.kill(); await closePreview(); };
process.once('SIGINT', close);
process.once('SIGTERM', close);
electron.once('exit', async code => { await closePreview(); if (code) console.error(`Electron exited ${code}: ${tail}`); });
