import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dataGridCellSource = join(process.cwd(), "src/components/data-grid/DataGridCell.tsx");
const cellValuePreviewSource = join(process.cwd(), "src/components/data-grid/CellValuePreview.tsx");
const cellValuePreviewCss = join(process.cwd(), "src/components/data-grid/CellValuePreview.css");
const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");

describe("DataGridCell preview foundation", () => {
  it("delegates long content positioning to the shared DBFox HoverCard preview", () => {
    const source = readFileSync(dataGridCellSource, "utf8");
    const previewSource = readFileSync(cellValuePreviewSource, "utf8");

    expect(source).toContain("CellValuePreview");
    expect(source).not.toContain("HoverCard");
    expect(previewSource).toContain("HoverCard");
    expect(previewSource).toContain("HoverCardContent");
    expect(previewSource).toContain("HoverCardTrigger");
    expect(source).not.toContain("onPreviewChange");
    expect(source).not.toContain("getBoundingClientRect");
    expect(source).not.toContain("DOMRect");
    expect(source).not.toContain("style={{");
    expect(previewSource).not.toContain("style={{");
  });

  it("removes the parent-level fixed preview overlay and keeps preview styling local", () => {
    const tableSource = readFileSync(dataTableSource, "utf8");
    const css = readFileSync(cellValuePreviewCss, "utf8");

    expect(tableSource).not.toContain("const [preview");
    expect(tableSource).not.toContain("setPreview");
    expect(tableSource).not.toContain("window.innerWidth");
    expect(tableSource).not.toContain("data-grid-preview animate-fade-in");

    expect(css).toContain(".dbfox-cell-preview-trigger");
    expect(css).toContain(".dbfox-cell-preview-card");
    expect(css).toContain(".dbfox-cell-preview-header");
    expect(css).toContain(".dbfox-cell-preview-body");
    expect(css).toContain(".dbfox-cell-preview-footer");
    expect(css).not.toContain("position: fixed");
  });
});
