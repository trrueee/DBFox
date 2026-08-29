import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The DLC SDK contract is consumed through exactly one door per domain:
 * features/resources/types.ts (connectors), features/dlc/types.ts (extension
 * host + activation), features/dock/types.ts (dock views),
 * features/workspace/artifacts/types.ts (artifact renderers),
 * types/workspace.ts (workbench wire types) and lib/api/credentials.ts
 * (credential enrollment). Leaf modules must import from those doors so the
 * contract keeps a single re-export point.
 */
const SDK_IMPORT_PATTERN = /from\s+"[^"]*sdk\/frontend\/index"/;

// Paths relative to src/, forward slashes.
const DOOR_FILES = new Set([
  "features/resources/types.ts",
  "features/dlc/types.ts",
  "features/dock/types.ts",
  "features/workspace/artifacts/types.ts",
  "types/workspace.ts",
  "lib/api/credentials.ts",
]);

function productionSourceFiles(directory: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(directory)) {
    if (entry === "__tests__" || entry === "design-lab") continue;
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      files.push(...productionSourceFiles(path));
    } else if (/\.(?:ts|tsx)$/.test(entry) && !entry.endsWith(".d.ts")) {
      files.push(path);
    }
  }
  return files;
}

describe("sdk import doors", () => {
  it("imports sdk/frontend types only through domain doors", () => {
    const sourceRoot = join(process.cwd(), "src");
    const violations = productionSourceFiles(sourceRoot)
      .map((path) => {
        const source = readFileSync(path, "utf8");
        return SDK_IMPORT_PATTERN.test(source) ? path : null;
      })
      .filter((path): path is string => path !== null)
      .map((path) => relative(sourceRoot, path).replaceAll("\\", "/"))
      .filter((file) => !DOOR_FILES.has(file));

    expect(violations).toEqual([]);
  });
});
