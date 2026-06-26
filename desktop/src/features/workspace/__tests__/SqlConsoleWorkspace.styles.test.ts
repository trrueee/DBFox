import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/features/workspace/SqlConsoleWorkspace.tsx");
const localCss = join(process.cwd(), "src/features/workspace/SqlConsoleWorkspace.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".hifi-sql-workspace",
  ".sql-console-toolbar",
  ".sql-console-action-icon",
  ".sql-console-datasource-label",
  ".sql-console-selection-meta",
  ".sql-console",
  ".sql-console-scroll",
  ".sql-console-editor-inline",
  ".sql-console-info",
  ".sql-console-info.warn",
  ".sql-console-stmt",
  ".sql-console-prompt-label",
  ".sql-console-sql",
  ".sql-console-running",
  ".sql-console-error",
  ".sql-console-result",
  ".sql-console-result-meta",
  ".sql-console-table-wrap",
  ".sql-console-table",
  ".sql-console-null",
  ".sql-console-empty",
  ".sql-console-prompt",
];

describe("SqlConsoleWorkspace styles", () => {
  it("keeps SQL console styling local instead of in App.css", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./SqlConsoleWorkspace.css";');
    expect(source).not.toContain("h-full");
    expect(source).not.toContain("overflow-hidden");
    expect(source).not.toContain("border-0");
    expect(source).not.toContain("bg-transparent");
    expect(source).not.toContain("size-3.5");

    const globalCss = readFileSync(appCss, "utf8");
    expect(globalCss).not.toMatch(/\.hifi-sql-workspace|\.sql-console/);
  });
});
