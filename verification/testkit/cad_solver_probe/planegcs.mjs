/** Investigative probe, not a product dependency or CAD acceptance test.
 * Run with Node and an extracted, integrity-checked @salusoft89/planegcs 1.2.0.
 * Published or rebuilt upstream code performs every solve; assertions measure geometry.
 */
import assert from "node:assert/strict";
import { runSolverCases } from "./cases.mjs";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const packageRoot = resolve(process.argv[2] || "output/cad-solver-probe/package");
const wasm = await readFile(resolve(packageRoot, "dist/planegcs_dist/planegcs.wasm"));
const metadata = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8"));
assert.equal(metadata.version, "1.2.0");
const { init_planegcs_module, GcsWrapper, SolveStatus } = await import(
  pathToFileURL(resolve(packageRoot, "dist/index.js")).href
);
const diagnostics = [];
const module = await init_planegcs_module({ wasmBinary: wasm, print: line => diagnostics.push(line), printErr: line => diagnostics.push(line) });
const results = runSolverCases(module, GcsWrapper, SolveStatus, assert);
const report = JSON.stringify({
  scope: "upstream Node solver only; no DBFox integration, browser CSP, CAD solid or export acceptance",
  package: `${metadata.name}@${metadata.version}`,
  node: process.version,
  wasm_bytes: wasm.length,
  wasm_sha256: createHash("sha256").update(wasm).digest("hex"),
  passed: results.length,
  diagnostics,
  results,
}, null, 2) + "\n";
// Upstream native diagnostics can write directly to stdout, independently of print.
if (process.argv[3]) await writeFile(resolve(process.argv[3]), report, "utf8");
else process.stdout.write(report);
