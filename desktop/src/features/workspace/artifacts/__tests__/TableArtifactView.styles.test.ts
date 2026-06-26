import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const tableArtifactSource = join(process.cwd(), "src/features/workspace/artifacts/TableArtifactView.tsx");
const artifactTableGridSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableGrid.tsx");
const artifactTableToolbarSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx");
const artifactTableFooterSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableFooter.tsx");
const artifactTableCss = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTable.css");
const appCss = join(process.cwd(), "src/App.css");

const artifactTableSelectors = [
  ".artifact-table-grid",
  ".artifact-table-head",
  ".artifact-table-head-button",
  ".artifact-table-column-name",
  ".artifact-table-type-badge",
  ".artifact-table-cell",
  ".artifact-table-null-pill",
  ".artifact-table-meta",
  ".artifact-table-toolbar-stack",
  ".artifact-table-toolbar",
  ".artifact-table-toolbar-main",
  ".artifact-table-inline-toolbar",
  ".artifact-table-search-shell",
  ".artifact-table-search-icon",
  ".artifact-table-search",
  ".artifact-table-control-row",
  ".artifact-table-control-field",
  ".artifact-table-control-select",
  ".artifact-table-control-input",
  ".artifact-table-footer",
  ".artifact-table-footer-text",
  ".artifact-table-footer-controls",
  ".artifact-table-truncated",
  ".artifact-table-pagination",
  ".artifact-table-page-button",
  ".artifact-table-page-number",
  ".artifact-table-page-size",
  ".artifact-table-workspace",
  ".artifact-table-alert",
  ".artifact-table-alert-icon",
  ".artifact-table-container",
  ".artifact-table-loading-bar",
  ".artifact-table-action-button",
  ".artifact-table-inline-error",
  ".artifact-table-inline-table",
];

describe("TableArtifactView styles", () => {
  it("keeps artifact table business styles in a local feature stylesheet", () => {
    const source = readFileSync(tableArtifactSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).toContain('import "./table/ArtifactTable.css";');
    expect(existsSync(artifactTableCss)).toBe(true);

    const localCss = readFileSync(artifactTableCss, "utf8");
    for (const selector of artifactTableSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });

  it("uses UI primitives for artifact table controls instead of raw controls and Tailwind utilities", () => {
    const toolbarSource = readFileSync(artifactTableToolbarSource, "utf8");
    const footerSource = readFileSync(artifactTableFooterSource, "utf8");
    const controlSources = [toolbarSource, footerSource].join("\n");

    expect(toolbarSource).toContain('from "../../../../components/ui";');
    expect(toolbarSource).toContain("Button");
    expect(toolbarSource).toContain("Input");
    expect(toolbarSource).toContain("Select");
    expect(toolbarSource).toContain("Toolbar");
    expect(toolbarSource).toContain("ToolbarGroup");
    expect(toolbarSource).toContain("Popover");
    expect(toolbarSource).toContain("PopoverContent");
    expect(toolbarSource).toContain("PopoverTrigger");
    expect(toolbarSource).not.toContain('from "@radix-ui/react-popover"');
    expect(toolbarSource).not.toContain("filterOpen");
    expect(toolbarSource).not.toContain("sortOpen");
    expect(footerSource).toContain('from "../../../../components/ui";');
    expect(footerSource).toContain("Button");
    expect(footerSource).toContain("Select");

    expect(controlSources).not.toMatch(/<(button|input|select)\b/);
    expect(controlSources).not.toMatch(
      /\b(flex|items-center|justify-center|gap-\d|px-\d|py-\d|mb-\d|h-\d|min-w-\[|pl-\d|pr-\d|text-\[|rounded|relative|absolute|opacity-\d|cursor-not-allowed|animate-spin)\b/,
    );
  });

  it("renders table filter and sort controls in DBFox popover surfaces", () => {
    const toolbarSource = readFileSync(artifactTableToolbarSource, "utf8");
    const css = readFileSync(artifactTableCss, "utf8");

    expect(toolbarSource).toContain('className="artifact-table-popover-content"');
    expect(toolbarSource).toContain('className="artifact-table-popover-actions"');
    expect(css).toContain(".artifact-table-popover-content");
    expect(css).toContain(".artifact-table-popover-actions");
  });

  it("uses TanStack Table as the artifact result table row and column engine", () => {
    const gridSource = readFileSync(artifactTableGridSource, "utf8");

    expect(gridSource).toContain('from "@tanstack/react-table"');
    expect(gridSource).toContain("useReactTable");
    expect(gridSource).toContain("getCoreRowModel");
    expect(gridSource).toContain("flexRender");
    expect(gridSource).toContain("CellValuePreview");
    expect(gridSource).not.toContain("hifi-table");
    expect(gridSource).not.toContain("numericColumns = columns.map");
  });

  it("owns the artifact table visual frame locally instead of inheriting the legacy grid look", () => {
    const css = readFileSync(artifactTableCss, "utf8");

    expect(css).toContain("border-collapse: separate");
    expect(css).toContain("border-spacing: 0");
    expect(css).toContain("box-shadow: inset 0 0 0 1px var(--agent-border)");
    expect(css).toContain(".artifact-table-grid thead th");
    expect(css).toContain(".artifact-table-grid tbody td");
    expect(css).toContain(".artifact-table-row");
  });

  it("keeps TableArtifactView shell and actions on local classes and Button primitives", () => {
    const source = readFileSync(tableArtifactSource, "utf8");

    expect(source).toContain('from "../../../components/ui";');
    expect(source).toContain("Button");
    expect(source).not.toMatch(/<button\b/);
    expect(source).not.toMatch(
      /\b(flex|flex-col|flex-shrink-0|items-center|gap-\d|m-\d|mb-\d|p-\d|h-full|w-full|overflow-hidden|overflow-auto|relative|absolute|top-0|left-0|right-0|mt-\d(?:\.\d)?|text-\[|rounded)\b/,
    );
  });
});
