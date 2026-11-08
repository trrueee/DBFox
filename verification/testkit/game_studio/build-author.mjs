// Reuse Host React/Tree and compile the exact Game module for author browser QA.
import { createRequire } from 'node:module';
import { mkdir, copyFile, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = fileURLToPath(new URL('.', import.meta.url));
const root = resolve(here, '../../..');
const output = join(root, '.tmp/game-phaser-review');
await mkdir(output, { recursive: true });
const require = createRequire(join(root, 'desktop/package.json'));
await require('esbuild').build({ entryPoints: [join(here, 'author-entry.jsx')], tsconfig: join(root, 'desktop/tsconfig.app.json'), bundle: true, format: 'esm', jsx: 'automatic', outfile: join(output, 'studio.js'), logLevel: 'error' });
await copyFile(join(root, 'dlcs/dbfox.game/frontend/index.css'), join(output, 'index.css'));
await writeFile(join(output, 'studio.html'), '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Game Studio author verification</title><link rel="stylesheet" href="./studio.css"></head><body><div id="root"></div><script type="module" src="./studio.js"></script></body></html>');
console.log('Built author-only Studio fixture. Actual installed Electron evidence uses browser-launch.mjs.');
