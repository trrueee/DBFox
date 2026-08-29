import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(desktopRoot, "..");
const sourceRoot = join(repositoryRoot, "dlcs", "dbfox.visualization", "frontend");
const vendorRoot = join(sourceRoot, "vendor");
const licenseRoot = join(vendorRoot, "licenses");

await mkdir(licenseRoot, { recursive: true });
await build({
  entryPoints: [join(sourceRoot, "vendor-src", "vega-runtime.js")],
  outfile: join(vendorRoot, "vega-runtime.js"),
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "chrome142",
  minify: true,
  legalComments: "eof",
  nodePaths: [join(desktopRoot, "node_modules")],
});

for (const [packageName, destination] of [
  ["vega", "vega-BSD-3-Clause.txt"],
  ["vega-lite", "vega-lite-BSD-3-Clause.txt"],
  ["vega-interpreter", "vega-interpreter-BSD-3-Clause.txt"],
]) {
  await copyFile(
    join(desktopRoot, "node_modules", packageName, "LICENSE"),
    join(licenseRoot, destination),
  );
}

const bundle = await readFile(join(vendorRoot, "vega-runtime.js"));
await writeFile(
  join(vendorRoot, "bundle-manifest.json"),
  `${JSON.stringify({ schemaVersion: 1, bytes: bundle.byteLength }, null, 2)}\n`,
  "utf8",
);
