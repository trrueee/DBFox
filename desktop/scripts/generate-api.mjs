import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(desktopRoot, "..");
const openApiPath = resolve(desktopRoot, "src/lib/api/generated/openapi.json");
const generatorConfigPath = resolve(desktopRoot, "openapi-ts.config.ts");
const generatorEntry = resolve(
  desktopRoot,
  "node_modules",
  "@hey-api",
  "openapi-ts",
  "bin",
  "run.js",
);

const run = (command, args, cwd) => {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    shell: false,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
};

run(
  "python",
  ["-m", "engine.scripts.export_openapi", openApiPath],
  repositoryRoot,
);
run(
  process.execPath,
  [
    generatorEntry,
    "-f",
    generatorConfigPath,
  ],
  desktopRoot,
);
