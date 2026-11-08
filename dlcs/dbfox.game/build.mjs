import { build } from 'esbuild';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve, sep } from 'node:path';

const directory = import.meta.dirname;
const sourceRoot = resolve(directory, 'node_modules/phaser/src');
const vendor = resolve(directory, 'frontend/vendor');
const reviewedVisibilityHash = '5a520230ec2af86e779655102ea3b7217a989a5cd5cdd06bc3a644fa9b7d1d93';
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const lock = JSON.parse(await readFile(resolve(directory, 'package-lock.json'), 'utf8'));
if (lock.packages['node_modules/phaser']?.version !== '4.2.1') {
  throw new Error('Game requires the reviewed Phaser 4.2.1 source.');
}
await mkdir(vendor, { recursive: true });
let patchedVisibilityHash;
await build({
  entryPoints: [resolve(sourceRoot, 'phaser-esm.js')],
  outfile: resolve(vendor, 'phaser.js'),
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'es2022',
  minify: true,
  legalComments: 'inline',
  plugins: [{
    name: 'reviewed-phaser-canvas-arcade',
    setup(builder) {
      builder.onLoad({ filter: /\.js$/ }, async ({ path }) => {
        if (!path.startsWith(sourceRoot + sep)) return;
        let source = await readFile(path, 'utf8');
        if (path === resolve(sourceRoot, 'core/VisibilityHandler.js')) {
          if (hash(source) !== reviewedVisibilityHash) throw new Error('Reviewed Phaser lifecycle source changed.');
          source = source.replace('window.onblur = function ()', 'var onBlur = function ()')
            .replace('window.onfocus = function ()', 'var onFocus = function ()');
          const anchor = '    //  Automatically give the window focus unless config says otherwise';
          if (!source.includes(anchor)) throw new Error('Phaser visibility cleanup anchor is missing.');
          source = source.replace(anchor, `    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    eventEmitter.once(Events.DESTROY, function () {
        if (hiddenVar) { document.removeEventListener(hiddenVar, onChange, false); }
        window.removeEventListener('blur', onBlur);
        window.removeEventListener('focus', onFocus);
    });

${anchor}`);
          patchedVisibilityHash = hash(source);
        }
        // These expressions match upstream webpack DefinePlugin feature gates.
        for (const [name, value] of Object.entries({ CANVAS_RENDERER: true, WEBGL_RENDERER: false, WEBGL_DEBUG: false, FEATURE_SOUND: false })) {
          source = source.replaceAll(`typeof ${name}`, String(value));
        }
        if (path === resolve(sourceRoot, 'phaser-esm.js')) {
          const physics = "export const Physics = require('./physics');";
          if (!source.includes(physics)) throw new Error('Official Phaser ESM Physics export changed.');
          source = source.replace(physics, "export const Physics = { Arcade: require('./physics/arcade') };");
        }
        return { contents: source, loader: 'js' };
      });
    },
  }],
});
if (!patchedVisibilityHash) throw new Error('Phaser lifecycle patch did not participate in the build.');
await copyFile(resolve(directory, 'node_modules/phaser/LICENSE.md'), resolve(vendor, 'PHASER-LICENSE.txt'));
await copyFile(resolve(directory, 'node_modules/eventemitter3/LICENSE'), resolve(vendor, 'EVENTEMITTER3-LICENSE.txt'));
const bytes = await readFile(resolve(vendor, 'phaser.js'));
const upstream = lock.packages['node_modules/phaser'];
const emitter = lock.packages['node_modules/eventemitter3'];
await writeFile(resolve(vendor, 'provenance.json'), JSON.stringify({
  engine: 'phaser-arcade-4.2.1',
  upstream: { version: upstream.version, archive: upstream.resolved, integrity: upstream.integrity, license: 'MIT' },
  eventemitter3: { version: emitter.version, archive: emitter.resolved, integrity: emitter.integrity, license: 'MIT' },
  build: { esbuild: lock.packages['node_modules/esbuild'].version, entry: 'phaser/src/phaser-esm.js', renderer: 'Canvas', physics: 'Arcade', sound: false, webgl: false },
  lifecycle_patch: { file: 'src/core/VisibilityHandler.js', original_sha256: reviewedVisibilityHash, patched_sha256: patchedVisibilityHash, reason: 'Preserve window onblur/onfocus and remove owned visibility/blur/focus listeners on Game DESTROY.' },
  output: { file: 'phaser.js', bytes: bytes.length, sha256: hash(bytes) },
}, null, 2) + '\n');
process.stdout.write(`Phaser vendor: ${bytes.length} bytes, sha256 ${hash(bytes)}\n`);
