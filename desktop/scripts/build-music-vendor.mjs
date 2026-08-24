import { copyFile, cp, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const scriptRoot = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(scriptRoot, "..");
const musicRoot = resolve(desktopRoot, "..", "dlcs", "dbfox.music", "frontend");
const vendorRoot = join(musicRoot, "vendor");
const sourceRoot = join(musicRoot, "vendor-src");

const basicPitchRoot = join(desktopRoot, "node_modules", "@spotify", "basic-pitch");
const pianoRoot = join(desktopRoot, "node_modules", "@audio-samples", "piano-mp3-velocity8");
const vexFlowRoot = join(desktopRoot, "node_modules", "vexflow");

await rm(vendorRoot, { recursive: true, force: true });
await mkdir(vendorRoot, { recursive: true });

for (const entry of ["basic-pitch", "vexflow"]) {
  const outfile = join(vendorRoot, `${entry}.js`);
  await build({
    entryPoints: [join(sourceRoot, `${entry}.js`)],
    outfile,
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    minify: true,
    legalComments: "none",
    absWorkingDir: desktopRoot,
    nodePaths: [join(desktopRoot, "node_modules")],
  });
  const bundledSource = await readFile(outfile, "utf8");
  await writeFile(outfile, bundledSource.replace(/[ \t]+(?=\r?\n|$)/g, ""), "utf8");
}

await cp(join(basicPitchRoot, "model"), join(vendorRoot, "basic-pitch-model"), { recursive: true });
const generatedModelPath = join(vendorRoot, "basic-pitch-model", "model.json");
const model = JSON.parse(await readFile(generatedModelPath, "utf8"));
for (const group of model.weightsManifest ?? []) {
  group.paths = group.paths.map((path) => path === "group1-shard1of1.bin" ? "group1-shard1of1.weights" : path);
}
await rename(
  join(vendorRoot, "basic-pitch-model", "group1-shard1of1.bin"),
  join(vendorRoot, "basic-pitch-model", "group1-shard1of1.weights"),
);
await writeFile(generatedModelPath, `${JSON.stringify(model)}\n`, "utf8");
await cp(join(pianoRoot, "audio"), join(vendorRoot, "piano"), { recursive: true });
for (const fileName of await readdir(join(vendorRoot, "piano"))) {
  if (fileName.includes("#")) {
    await rename(
      join(vendorRoot, "piano", fileName),
      join(vendorRoot, "piano", fileName.replace("#", "s")),
    );
  }
}
await mkdir(join(vendorRoot, "licenses"), { recursive: true });
await Promise.all([
  copyFile(join(basicPitchRoot, "LICENSE"), join(vendorRoot, "licenses", "basic-pitch-Apache-2.0.txt")),
  copyFile(join(vexFlowRoot, "LICENSE"), join(vendorRoot, "licenses", "vexflow-MIT.txt")),
  copyFile(join(pianoRoot, "LICENSE"), join(vendorRoot, "licenses", "piano-package-MIT.txt")),
]);
