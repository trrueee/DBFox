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
  ".sql-console-status",
  ".sql-console-status.is-warning",
  ".sql-console-input-stack",
  ".sql-console-highlight",
  ".sql-console-input",
  ".sql-console-statement",
  ".sql-console-statement--read",
  ".sql-console-statement--write",
  ".sql-console-statement--ddl",
  ".sql-console-token-keyword",
  ".sql-console-token-function",
  ".sql-console-token-string",
  ".sql-console-token-number",
  ".sql-console-token-comment",
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
    expect(source).not.toContain("SqlEditor");
    expect(source).toContain("<textarea");

    const globalCss = readFileSync(appCss, "utf8");
    expect(globalCss).not.toMatch(/\.hifi-sql-workspace|\.sql-console/);
  });

  it("does not draw a boxed editor surface in the terminal prompt", () => {
    const css = readFileSync(localCss, "utf8");

    expect(css).not.toContain(".sql-console-editor-inline");
    expect(css).not.toContain("height: 188px");
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?background:\s*transparent;/);
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?border:\s*0;/);
  });

  it("renders syntax highlighting as a transparent overlay behind the textarea", () => {
    const css = readFileSync(localCss, "utf8");
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('aria-label="SQL 高亮预览"');
    expect(source).toContain("renderSqlConsoleHighlight");
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?color:\s*transparent;/);
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?caret-color:\s*#34d399;/);
    expect(css).toMatch(/\.sql-console-highlight\s*{[\s\S]*?pointer-events:\s*none;/);
    expect(css).toMatch(/\.sql-console-token-keyword\s*{[\s\S]*?color:\s*#93c5fd;/);
    expect(css).toMatch(/\.sql-console-token-string\s*{[\s\S]*?color:\s*#86efac;/);
    expect(css).toMatch(/\.sql-console-token-number\s*{[\s\S]*?color:\s*#fdba74;/);
  });
});
