import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/pages/AgentEvalPage.tsx");
const cssPath = join(process.cwd(), "src/pages/AgentEvalPage.css");
const appCssPath = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".agent-eval-page",
  ".agent-eval-header",
  ".agent-eval-header__title",
  ".agent-eval-header__datasource",
  ".agent-eval-header__actions",
  ".agent-eval-form",
  ".agent-eval-form__row",
  ".agent-eval-form__inline",
  ".agent-eval-body",
  ".agent-eval-panel",
  ".agent-eval-list",
  ".agent-eval-task",
  ".agent-eval-task__name",
  ".agent-eval-task__question",
  ".agent-eval-chip",
  ".agent-eval-chip--keyword",
  ".agent-eval-run",
  ".agent-eval-run__head",
  ".agent-eval-run__rate",
  ".agent-eval-run__rate--good",
  ".agent-eval-run__rate--warn",
  ".agent-eval-run__rate--bad",
  ".agent-eval-case",
  ".agent-eval-case__status",
  ".agent-eval-case__status--passed",
  ".agent-eval-case__status--failed",
  ".agent-eval-case__status--error",
  ".agent-eval-case__reasons",
];

describe("AgentEvalPage styles", () => {
  it("keeps agent evaluation presentation local and uses shared UI primitives", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./AgentEvalPage.css";');
    expect(source).toContain("from \"../components/ui\"");
    for (const primitive of ["Button", "Input", "Panel", "PanelBody", "PanelHeader", "PanelTitle", "EmptyState", "LoadingState"]) {
      expect(source).toContain(`<${primitive}`);
    }
    expect(source).not.toContain("hifi-eval");
    expect(source).not.toContain("hifi-agent-running-spinner");

    expect(existsSync(cssPath)).toBe(true);
    const localCss = readFileSync(cssPath, "utf8");
    for (const selector of localSelectors) {
      expect(localCss).toContain(selector);
    }
    expect(localCss).not.toContain("hifi-eval");

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).not.toContain("hifi-eval");
  });
});
