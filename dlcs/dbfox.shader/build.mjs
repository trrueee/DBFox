import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = dirname(fileURLToPath(import.meta.url));
const output = join(root, 'frontend/vendor');
await mkdir(output, { recursive: true });
await build({ absWorkingDir: root, entryPoints: ['frontend/vendor-src/codemirror.js'], outfile: 'frontend/vendor/codemirror.js', bundle: true, format: 'esm', target: 'es2022', platform: 'browser', minify: true, legalComments: 'inline', metafile: true });
const lock = JSON.parse(await readFile(join(root, 'package-lock.json'), 'utf8'));
const packages = [];
const licenses = [];
for (const [path, entry] of Object.entries(lock.packages)) {
  if (!path || entry.dev || entry.optional) continue;
  const files = await readdir(join(root, path));
  const license = files.find((name) => /^licen[sc]e(?:\.(?:md|txt))?$/i.test(name));
  if (!license) throw new Error(`Upstream license missing: ${path}`);
  const bytes = await readFile(join(root, path, license));
  licenses.push(`${path} @ ${entry.version}\n${bytes.toString('utf8')}\n`);
  packages.push({ name: path.replace(/^node_modules\//, ''), version: entry.version, resolved: entry.resolved, integrity: entry.integrity, license: entry.license, license_sha256: createHash('sha256').update(bytes).digest('hex') });
}
await writeFile(join(output, 'LICENSES.txt'), licenses.join('\n').replace(/\n+$/, '\n'), 'utf8');
const bundle = await readFile(join(output, 'codemirror.js'));
await writeFile(join(output, 'provenance.json'), JSON.stringify({ build: 'npm ci && npm run build', esbuild: '0.28.2', source: 'frontend/vendor-src/codemirror.js', bundle_bytes: bundle.length, bundle_sha256: createHash('sha256').update(bundle).digest('hex'), packages }, null, 2) + '\n');
process.stdout.write(`CodeMirror bundle: ${bundle.length} bytes; ${packages.length} upstream licenses retained.\n`);
