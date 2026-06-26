import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const tableWorkspaceSource = join(process.cwd(), "src/features/workspace/TableWorkspace.tsx");
const tableWorkspaceCss = join(process.cwd(), "src/features/workspace/TableWorkspace.css");
const tableSchemaSource = join(process.cwd(), "src/features/workspace/table/TableSchemaPane.tsx");
const tableSchemaCss = join(process.cwd(), "src/features/workspace/table/TableSchemaPane.css");
const askContextSource = join(process.cwd(), "src/features/workspace/smartQuery/AskContextDropZone.tsx");
const askContextCss = join(process.cwd(), "src/features/workspace/smartQuery/AskContextDropZone.css");
const appCss = join(process.cwd(), "src/App.css");

const tableWorkspaceSelectors = [
  ".table-workspace",
  ".table-workspace__tabs",
  ".table-workspace__tab",
  ".table-workspace__tab.is-active",
  ".table-workspace__body",
];

const tableSchemaSelectors = [
  ".table-schema-pane",
  ".table-schema-pane__caption",
  ".table-schema-pane__loading",
  ".table-schema-pane__error",
  ".table-schema-table",
  ".table-schema-table__type",
  ".table-schema-constraints",
  ".table-schema-constraint",
  ".table-schema-constraint--primary",
  ".table-schema-constraint--foreign",
  ".table-schema-muted",
  ".table-schema-confidence",
  ".table-schema-confidence--high",
  ".table-schema-confidence--medium",
  ".table-schema-confidence--low",
  ".table-schema-tag",
];

const askContextSelectors = [
  ".ask-context-dropzone",
  ".ask-context-dropzone:hover",
  ".ask-context-dropzone__icon",
  ".ask-context-dropzone__label",
  ".ask-context-dropzone__placeholder",
  ".ask-context-dropzone__chips",
  ".ask-context-chip",
  ".ask-context-chip__remove",
  ".ask-context-dropzone__clear",
];

const retiredAppSelectors = [
  ".hifi-breadcrumb",
  ".hifi-subtabs",
  ".hifi-subtab",
  ".hifi-constraint-badge",
  ".hifi-er-container",
  ".hifi-er-zoom-controls",
  ".hifi-er-zoom-btn",
  ".hifi-table-workspace",
  ".hifi-workspace-subtabs",
  ".hifi-workspace-subtab",
  ".hifi-subtab-content",
  ".hifi-drop-zone",
  ".hifi-context-chip",
];

describe("workspace local styles", () => {
  it("keeps table workspace layout styles local", () => {
    expect(existsSync(tableWorkspaceCss)).toBe(true);

    const source = readFileSync(tableWorkspaceSource, "utf8");
    expect(source).toContain('import "./TableWorkspace.css";');
    expect(source).not.toMatch(/hifi-table-workspace|hifi-workspace-subtabs|hifi-workspace-subtab|hifi-subtab-content/);
    expect(source).not.toMatch(/flex-1|overflow-auto|hifi-tab-pane/);

    const css = readFileSync(tableWorkspaceCss, "utf8");
    for (const selector of tableWorkspaceSelectors) {
      expect(css).toContain(selector);
    }
  });

  it("keeps schema pane styling local without inline styles", () => {
    expect(existsSync(tableSchemaCss)).toBe(true);

    const source = readFileSync(tableSchemaSource, "utf8");
    expect(source).toContain('import "./TableSchemaPane.css";');
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/hifi-table|hifi-constraint-badge|text-slate|text-blue|bg-red|rounded-lg|font-mono|ml-1/);

    const css = readFileSync(tableSchemaCss, "utf8");
    for (const selector of tableSchemaSelectors) {
      expect(css).toContain(selector);
    }
  });

  it("keeps smart-query drop zone styling local", () => {
    expect(existsSync(askContextCss)).toBe(true);

    const source = readFileSync(askContextSource, "utf8");
    expect(source).toContain('import "./AskContextDropZone.css";');
    expect(source).not.toMatch(/hifi-drop-zone|hifi-context-chip/);
    expect(source).not.toMatch(/text-indigo|text-slate|bg-indigo|border-indigo|flex-wrap|rounded|font-mono|ml-1/);

    const css = readFileSync(askContextCss, "utf8");
    for (const selector of askContextSelectors) {
      expect(css).toContain(selector);
    }
  });

  it("keeps migrated workspace business selectors out of App.css", () => {
    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});
