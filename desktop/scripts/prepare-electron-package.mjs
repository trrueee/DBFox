import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";

const root = process.cwd();
const stagingRoot = join(root, "electron-app");
const sourcePackage = JSON.parse(await readFile(join(root, "package.json"), "utf8"));

await rm(stagingRoot, { recursive: true, force: true });
await mkdir(stagingRoot, { recursive: true });
await cp(join(root, "dist"), join(stagingRoot, "dist"), { recursive: true });
await cp(join(root, "dist-electron"), join(stagingRoot, "dist-electron"), {
  recursive: true,
});
await cp(join(root, "src-tauri", "icons"), join(stagingRoot, "build-resources"), {
  recursive: true,
});
await cp(join(root, "electron-resources", "sidecar"), join(stagingRoot, "sidecar"), {
  recursive: true,
});

const stagedPackage = {
  name: "dbfox",
  productName: "DBFox",
  description: "Local-first AI database workspace",
  author: "DBFox",
  version: sourcePackage.version,
  private: true,
  type: "module",
  main: "dist-electron/main/index.js",
};
await writeFile(
  join(stagingRoot, "package.json"),
  `${JSON.stringify(stagedPackage, null, 2)}\n`,
  "utf8",
);

console.log("  ✓ Staged dependency-free Electron application");
