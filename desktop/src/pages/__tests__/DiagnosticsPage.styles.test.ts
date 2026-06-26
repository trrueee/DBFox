import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/pages/DiagnosticsPage.tsx");
const localCss = join(process.cwd(), "src/pages/DiagnosticsPage.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".diagnostics-page",
  ".diagnostics-page--workspace",
  ".diagnostics-page-header",
  ".diagnostics-page-title",
  ".diagnostics-page-subtitle",
  ".diagnostics-actions",
  ".diagnostics-toggle-label",
  ".diagnostics-toggle-checkbox",
  ".diagnostics-badge",
  ".diagnostics-error",
  ".diagnostics-summary",
  ".diagnostics-metric",
  ".diagnostics-source-toolbar",
  ".diagnostics-source-picker",
  ".diagnostics-source-trigger",
  ".diagnostics-source-menu",
  ".diagnostics-source-option",
  ".diagnostics-source-option.is-active",
  ".diagnostics-source-count",
  ".diagnostics-sources",
  ".diagnostics-source",
  ".diagnostics-source-header",
  ".diagnostics-log-status",
  ".diagnostics-log-status--ok",
  ".diagnostics-log-status--missing",
  ".diagnostics-source-content",
  ".diagnostics-empty",
];

describe("DiagnosticsPage styles", () => {
  it("keeps diagnostics page styling local and out of App.css", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./DiagnosticsPage.css";');
    expect(source).not.toContain("style=");

    const globalCss = readFileSync(appCss, "utf8");
    expect(globalCss).not.toMatch(/\.hifi-diagnostics-|\.hifi-log-status/);
  });

  it("uses shared UI primitives for diagnostic actions and states", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('from "../components/ui";');
    expect(source).toContain("<Button");
    expect(source).toContain("<ErrorState");
    expect(source).toContain("<EmptyState");
    expect(source).not.toMatch(/<button\b/);
    expect(source).not.toContain("hifi-btn");
    expect(source).not.toContain("hifi-page-header");
    expect(source).not.toContain("workspace-page-toolbar");
  });
});
