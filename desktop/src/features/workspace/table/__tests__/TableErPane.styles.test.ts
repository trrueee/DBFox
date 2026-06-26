import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const tableErSource = join(process.cwd(), "src/features/workspace/table/TableErPane.tsx");
const tableErCss = join(process.cwd(), "src/features/workspace/table/TableErPane.css");
const appCss = join(process.cwd(), "src/App.css");

const tableErSelectors = [
  ".table-er-pane",
  ".table-er-pane__state",
  ".table-er-pane__header",
  ".table-er-pane__caption",
  ".table-er-pane__meta",
  ".table-er-pane__toolbar",
  ".table-er-pane__control",
  ".table-er-pane__select",
  ".table-er-pane__toggle",
  ".table-er-pane__canvas",
  ".table-er-pane__diagram-loading",
];

describe("TableErPane styles", () => {
  it("keeps ER diagram styling local and uses shared state components", () => {
    const source = readFileSync(tableErSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).not.toContain('import { ErDiagram } from "../../../components/ErDiagram";');
    expect(source).toContain('lazy(async () =>');
    expect(source).toContain('import("../../../components/ErDiagram")');
    expect(source).toContain("<Suspense");
    expect(source).toContain('import { Button, EmptyState, ErrorState, LoadingState, Select, Toolbar, ToolbarGroup } from "../../../components/ui";');
    expect(source).toContain('import "./TableErPane.css";');
    expect(existsSync(tableErCss)).toBe(true);
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/table-er-node|p-4|text-slate|text-red|bg-red|rounded-lg|rounded-xl|shadow-inner|font-mono|flex-1|flex-wrap|gap-6|min-w-max|w-\[160px\]/);

    const localCss = readFileSync(tableErCss, "utf8");
    for (const selector of tableErSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });
});
