import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const tablePreviewSource = join(process.cwd(), "src/features/workspace/table/TablePreviewPane.tsx");
const tablePreviewCss = join(process.cwd(), "src/features/workspace/table/TablePreviewPane.css");
const appCss = join(process.cwd(), "src/App.css");

const tablePreviewSelectors = [
  ".hifi-table-preview-pane",
  ".hifi-table-toolbar",
  ".hifi-preview-toolbar-btn",
  ".hifi-preview-search",
  ".hifi-preview-control-row",
  ".table-preview-grid",
  ".table-preview-head",
  ".table-preview-row",
  ".table-preview-cell",
  ".table-preview-null-pill",
  ".hifi-table-footer",
  ".hifi-pagination",
  ".hifi-page-num",
  ".hifi-preview-page-btn",
];

describe("TablePreviewPane styles", () => {
  it("keeps table preview business styles in a local feature stylesheet", () => {
    const source = readFileSync(tablePreviewSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).toContain('import "./TablePreviewPane.css";');
    expect(existsSync(tablePreviewCss)).toBe(true);

    const localCss = readFileSync(tablePreviewCss, "utf8");
    for (const selector of tablePreviewSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });

  it("uses TanStack Table for the preview table body and owns the visual frame locally", () => {
    const source = readFileSync(tablePreviewSource, "utf8");
    const css = readFileSync(tablePreviewCss, "utf8");

    expect(source).toContain('from "@tanstack/react-table"');
    expect(source).toContain("useReactTable");
    expect(source).toContain("getCoreRowModel");
    expect(source).toContain("flexRender");
    expect(source).toContain("Popover");
    expect(source).toContain("PopoverContent");
    expect(source).toContain("PopoverTrigger");
    expect(source).toContain("CellValuePreview");
    expect(source).not.toContain('from "@radix-ui/react-popover"');
    expect(source).not.toContain("filterOpen");
    expect(source).not.toContain("sortOpen");
    expect(source).not.toContain('className="hifi-table hifi-preview-table"');

    expect(css).toContain("border-collapse: separate");
    expect(css).toContain("border-spacing: 0");
    expect(css).toContain(".table-preview-grid thead th");
    expect(css).toContain(".table-preview-grid tbody td");
    expect(css).toContain(".table-preview-popover-content");
    expect(css).toContain(".table-preview-popover-actions");
    expect(css).toContain("box-shadow: inset 0 0 0 1px var(--agent-border)");
  });
});
