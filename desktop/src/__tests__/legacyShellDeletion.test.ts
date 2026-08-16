import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

function sourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== "__tests__" && entry !== "node_modules") {
        files.push(...sourceFiles(full));
      }
    } else if (/\.(ts|tsx)$/.test(entry) && !entry.endsWith(".d.ts")) {
      files.push(full);
    }
  }
  return files;
}

describe("legacy Workspace Shell deletion", () => {
  it("has no production imports of WorkspaceTabs or WorkspaceRouter", () => {
    const root = process.cwd();
    const failures: string[] = [];
    for (const file of sourceFiles(root)) {
      const source = readFileSync(file, "utf8");
      if (/from\s+["'][^"']*(WorkspaceTabs|WorkspaceRouter)["']/.test(source)) {
        failures.push(relative(root, file));
      }
    }
    expect(failures).toEqual([]);
  });

  it("does not render the deleted legacy files", () => {
    const root = process.cwd();
    expect(() => readFileSync(join(root, "features/workspace/WorkspaceTabs.tsx"), "utf8")).toThrow();
    expect(() => readFileSync(join(root, "features/appShell/WorkspaceRouter.tsx"), "utf8")).toThrow();
  });
});


  it("removes legacy WorkspaceTab and internal ArtifactDock wiring from production", () => {
    const root = process.cwd();
    const failures: string[] = [];
    for (const file of sourceFiles(root)) {
      const relativePath = relative(root, file).replaceAll("\\", "/");
      if (relativePath === "types/workspace.ts") continue;
      const source = readFileSync(file, "utf8");
      if (source.includes("WorkspaceTab")) {
        failures.push(`${relativePath}: WorkspaceTab`);
      }
      if (source.includes("showArtifactDock")) {
        failures.push(`${relativePath}: showArtifactDock`);
      }
    }
    expect(failures).toEqual([]);
  });
