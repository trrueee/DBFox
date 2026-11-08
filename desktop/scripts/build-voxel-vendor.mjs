import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, version as esbuildVersion } from 'esbuild';

const version = '0.185.1';
const integrity = 'sha512-5aojFCXKwnjBRZvUnt3WFfEcvUJgkN5LlijRFN95hMy8WVkG4I0QNcJE+OuWvuJ0bOdStrbfXn0pkd6/QyiAlg==';
const url = `https://registry.npmjs.org/three/-/three-${version}.tgz`;
if (esbuildVersion !== '0.28.2') throw new Error('Voxel vendor build requires esbuild 0.28.2');
const output = fileURLToPath(new URL('../../dlcs/dbfox.voxel/frontend/vendor/', import.meta.url));
const temporary = await mkdtemp(join(tmpdir(), 'dbfox-voxel-vendor-'));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
try {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Three archive HTTP ${response.status}`);
  const archive = Buffer.from(await response.arrayBuffer());
  if (`sha512-${createHash('sha512').update(archive).digest('base64')}` !== integrity) {
    throw new Error('Three archive integrity mismatch');
  }
  const archivePath = join(temporary, 'three.tgz');
  await writeFile(archivePath, archive);
  execFileSync('tar', ['-xzf', archivePath, '-C', temporary], { windowsHide: true });
  const sourceRoot = join(temporary, 'package');
  const controlsPath = join(sourceRoot, 'examples/jsm/controls/OrbitControls.js');
  const original = await readFile(controlsPath, 'utf8');
  const before = "document.removeEventListener( 'keydown', this._interceptControlDown, { capture: true } );";
  const after = before + "\n\t\tdocument.removeEventListener( 'keyup', this._interceptControlUp, { capture: true } );\n\t\tthis._controlActive = false;";
  if (original.split(before).length !== 2) throw new Error('OrbitControls patch source changed');
  const patched = original.replace(before, after);
  await writeFile(controlsPath, patched);
  const result = await build({
    stdin: { contents: "export * from './build/three.module.js'; export { OrbitControls } from './examples/jsm/controls/OrbitControls.js';", resolveDir: sourceRoot, loader: 'js' },
    bundle: true, format: 'esm', platform: 'browser', target: 'es2022', minify: true, write: false,
  });
  const bundle = result.outputFiles[0].contents;
  await writeFile(join(output, 'three.js'), bundle);
  await writeFile(join(output, 'licenses/three-MIT.txt'), await readFile(join(sourceRoot, 'LICENSE')));
  await writeFile(join(output, 'provenance.json'), JSON.stringify({
    schema_version: 1, package: 'three', version, license: 'MIT', source: 'https://github.com/mrdoob/three.js',
    archive: url, integrity, bundle_sha256: sha(bundle), bundle_bytes: bundle.byteLength,
    build: { script: 'desktop/scripts/build-voxel-vendor.mjs', esbuild: '0.28.2', target: 'es2022' },
    patches: [{
      source: 'examples/jsm/controls/OrbitControls.js', original_sha256: sha(original), patched_sha256: sha(patched),
      reason: 'Disconnect must release the Control-held keyup interceptor as well as keydown.',
      owner: 'dbfox.voxel',
      removal: 'Upgrade to a fixed upstream OrbitControls and remove the guarded source replacement after both independent native listener lifecycle regressions pass.',
    }],
  }, null, 2) + '\n');
  process.stdout.write(`Voxel Three ${bundle.byteLength} bytes SHA256 ${sha(bundle)}\n`);
} finally {
  const resolved = resolve(temporary);
  if (resolve(tmpdir()) !== resolve(join(resolved, '..')) || !resolved.includes('dbfox-voxel-vendor-')) {
    throw new Error('Refusing to remove an unexpected build directory');
  }
  await rm(resolved, { recursive: true, force: true });
}
