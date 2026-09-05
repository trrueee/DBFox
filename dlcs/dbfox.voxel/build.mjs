import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = dirname(fileURLToPath(import.meta.url));
const target = join(root, "frontend", "vendor");
const dependency = JSON.parse(await readFile(join(root, "node_modules", "three", "package.json"), "utf8"));
if (dependency.version !== "0.185.1") throw new Error("Use npm ci with the locked Three version");
await mkdir(join(target, "licenses"), { recursive: true });
await build({
  entryPoints: [join(root, "vendor-src", "three.js")],
  outfile: join(target, "three.js"),
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  minify: true,
  legalComments: "eof",
  absWorkingDir: root,
});
await copyFile(join(root, "node_modules", "three", "LICENSE"), join(target, "licenses", "three-MIT.txt"));
const bundle = await readFile(join(target, "three.js"));
if (bundle.length > 2 * 1024 * 1024) throw new Error("Voxel vendor exceeds its 2 MiB budget");
await writeFile(join(target, "provenance.json"), `${JSON.stringify({
  schema_version: 1,
  package: "three",
  version: dependency.version,
  license: "MIT",
  source: "https://github.com/mrdoob/three.js",
  bundle_sha256: createHash("sha256").update(bundle).digest("hex"),
  bundle_bytes: bundle.length,
}, null, 2)}\n`, "utf8");
console.log(`Built Voxel renderer vendor (${bundle.length} bytes).`);
