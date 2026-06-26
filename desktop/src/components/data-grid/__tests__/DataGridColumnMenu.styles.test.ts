import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const headerCellSource = join(process.cwd(), "src/components/data-grid/DataGridHeaderCell.tsx");
const columnMenuSource = join(process.cwd(), "src/components/data-grid/DataGridColumnMenu.tsx");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");

describe("DataGrid column menu foundation", () => {
  it("uses DBFox DropdownMenu instead of parent-managed menu state", () => {
    const tableSource = readFileSync(dataTableSource, "utf8");
    const headerSource = readFileSync(headerCellSource, "utf8");
    const menuSource = readFileSync(columnMenuSource, "utf8");

    expect(headerSource).toContain("DropdownMenu");
    expect(headerSource).toContain("DropdownMenuTrigger");
    expect(headerSource).toContain("Tooltip");
    expect(headerSource).toContain("TooltipTrigger");
    expect(headerSource).toContain("TooltipContent");
    expect(headerSource).toContain("列操作");
    expect(menuSource).toContain("DropdownMenuContent");
    expect(menuSource).toContain("DropdownMenuItem");
    expect(menuSource).not.toContain('className="data-grid-menu" onClick');

    expect(tableSource).not.toContain("openColumnMenu");
    expect(tableSource).not.toContain("setOpenColumnMenu");
    expect(headerSource).not.toContain("menuOpen");
    expect(headerSource).not.toContain("onToggleMenu");
  });

  it("lets Radix own overlay positioning while DBFox owns menu appearance", () => {
    const css = readFileSync(dataGridCss, "utf8");

    expect(css).toContain(".data-grid-menu");
    expect(css).toContain(".data-grid-menu-item");
    expect(css).not.toContain("position: absolute");
    expect(css).not.toContain("top: 30px");
    expect(css).not.toContain("right: 0");
  });
});
