// Build-time dependencies stay outside the distributable DLC payload.
import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build, version as esbuildVersion } from "esbuild";
import { createPrimitive, PRIMITIVE_NAMES } from "./frontend/vendor-src/three.js";

const root = dirname(fileURLToPath(import.meta.url));
const vendorRoot = join(root, "frontend", "vendor");
const backendRoot = join(root, "backend");
const threePackage = JSON.parse(await readFile(join(root, "node_modules", "three", "package.json"), "utf8"));
if (threePackage.version !== "0.185.1") throw new Error("Run npm ci for the locked Three version");
if (esbuildVersion !== "0.28.2") throw new Error("Run npm ci for the locked esbuild version");
const controlsPath = join(root, "node_modules", "three", "examples", "jsm", "controls", "OrbitControls.js");
const originalControls = await readFile(controlsPath, "utf8");
const before = "document.removeEventListener( 'keydown', this._interceptControlDown, { capture: true } );";
const after = before + "\n\t\tdocument.removeEventListener( 'keyup', this._interceptControlUp, { capture: true } );\n\t\tthis._controlActive = false;";
if (originalControls.split(before).length !== 2) throw new Error("OrbitControls cleanup patch source changed");
const patchedControls = originalControls.replace(before, after);

await mkdir(join(vendorRoot, "licenses"), { recursive: true });
await mkdir(backendRoot, { recursive: true });
await build({
  entryPoints: [join(root, "frontend", "vendor-src", "three.js")],
  outfile: join(vendorRoot, "three.js"),
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  minify: true,
  legalComments: "eof",
  absWorkingDir: root,
  plugins: [{
    name: "orbit-controls-disconnect",
    setup(builder) {
      builder.onLoad({ filter: /[/\\]controls[/\\]OrbitControls\.js$/ }, async (args) => {
        if (args.path !== controlsPath) throw new Error("Unexpected OrbitControls build source");
        return { contents: patchedControls, loader: "js", resolveDir: dirname(controlsPath) };
      });
    },
  }],
});
await copyFile(join(root, "node_modules", "three", "LICENSE"), join(vendorRoot, "licenses", "three-MIT.txt"));

const primitives = {};
for (const name of PRIMITIVE_NAMES) {
  const geometry = createPrimitive(name);
  try {
    const positions = Array.from(geometry.getAttribute("position").array);
    const normals = Array.from(geometry.getAttribute("normal").array);
    const index = geometry.getIndex();
    if (!index) throw new Error(`Primitive ${name} must have indexed geometry`);
    const indices = Array.from(index.array);
    if (positions.length !== normals.length || positions.length % 3 !== 0
      || positions.length / 3 > 4096 || indices.length % 3 !== 0
      || !positions.every(Number.isFinite) || !normals.every(Number.isFinite)
      || !indices.every((value) => Number.isInteger(value) && value >= 0 && value < positions.length / 3)) {
      throw new Error(`Primitive ${name} violates the bounded geometry contract`);
    }
    primitives[name] = { positions, normals, indices };
  } finally {
    geometry.dispose();
  }
}
await writeFile(join(backendRoot, "primitives.json"), `${JSON.stringify({
  schema_version: 1, generator: `three@${threePackage.version}`, primitives,
})}\n`, "utf8");

const bundle = await readFile(join(vendorRoot, "three.js"));
if (bundle.length > 2 * 1024 * 1024) throw new Error("Scene renderer vendor exceeds its 2 MiB budget");
const geometryBytes = await readFile(join(backendRoot, "primitives.json"));
await writeFile(join(vendorRoot, "provenance.json"), `${JSON.stringify({
  schema_version: 1,
  package: "three",
  version: threePackage.version,
  license: "MIT",
  source: "https://github.com/mrdoob/three.js",
  bundle_sha256: createHash("sha256").update(bundle).digest("hex"),
  bundle_bytes: bundle.length,
  primitive_sha256: createHash("sha256").update(geometryBytes).digest("hex"),
  primitive_bytes: geometryBytes.length,
  build: { script: "dlcs/dbfox.scene/build.mjs", esbuild: esbuildVersion, target: "es2022" },
  patches: [{
    source: "examples/jsm/controls/OrbitControls.js",
    original_sha256: createHash("sha256").update(originalControls).digest("hex"),
    patched_sha256: createHash("sha256").update(patchedControls).digest("hex"),
    reason: "Disconnect must release the Control-held keyup interceptor as well as keydown.",
    owner: "dbfox.scene",
    removal: "Upgrade to fixed upstream OrbitControls and remove the guarded build patch after native listener and React DOM lifecycle regressions pass.",
  }],
}, null, 2)}\n`, "utf8");
console.log(`Built Scene vendor (${bundle.length} bytes) and ${PRIMITIVE_NAMES.length} official primitives (${geometryBytes.length} bytes).`);
