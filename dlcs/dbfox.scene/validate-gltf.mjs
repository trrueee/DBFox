// Development gate: validate exports with the official Khronos validator.
import { readFile, stat } from "node:fs/promises";
import { basename } from "node:path";
import validator from "gltf-validator";

const files = process.argv.slice(2);
if (!files.length) throw new Error("Usage: node validate-gltf.mjs <export.gltf|export.glb> [...]");
for (const path of files) {
  if ((await stat(path)).size > 32 * 1024 * 1024) throw new Error("Export exceeds the Scene 32 MiB limit");
  const report = await validator.validateBytes(new Uint8Array(await readFile(path)), {
    uri: basename(path),
    maxIssues: 100,
    externalResourceFunction: async () => { throw new Error("Scene exports must be self-contained"); },
  });
  console.log(JSON.stringify({
    file: basename(path),
    validator: validator.version(),
    errors: report.issues.numErrors,
    warnings: report.issues.numWarnings,
    infos: report.issues.numInfos,
    messages: report.issues.messages,
  }));
  if (report.issues.numErrors > 0 || report.issues.numWarnings > 0) process.exitCode = 1;
}
