import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/features/workspace/MultiTableWorkspace.tsx");
const cssPath = join(process.cwd(), "src/features/workspace/MultiTableWorkspace.css");
const appCssPath = join(process.cwd(), "src/App.css");

const selectors = [
  ".multi-table-workspace",
  ".multi-table-workspace__summary",
  ".multi-table-workspace__summary-icon",
  ".multi-table-workspace__summary-title",
  ".multi-table-workspace__summary-copy",
  ".multi-table-workspace__actions",
  ".multi-table-workspace__action",
  ".multi-table-workspace__action-title",
  ".multi-table-workspace__action-copy",
  ".multi-table-workspace__prompt",
  ".multi-table-workspace__prompt-title",
  ".multi-table-workspace__prompt-row",
];

describe("MultiTableWorkspace styles", () => {
  it("uses the workspace shell, shared controls, and local CSS without Tailwind or App.css business styles", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./MultiTableWorkspace.css";');
    expect(source).toContain("WorkspaceShell");
    expect(source).toContain("from \"../../components/ui\"");
    for (const primitive of ["Button", "Input", "EmptyState"]) {
      expect(source).toContain(`<${primitive}`);
    }
    expect(source).not.toMatch(/hifi-|bg-|border-|rounded-|grid-cols-|text-|flex-|gap-|p-|mt-|mb-|opacity-/);

    expect(existsSync(cssPath)).toBe(true);
    const localCss = readFileSync(cssPath, "utf8");
    for (const selector of selectors) {
      expect(localCss).toContain(selector);
    }

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).not.toContain("hifi-multi-table-workspace");
  });
});
