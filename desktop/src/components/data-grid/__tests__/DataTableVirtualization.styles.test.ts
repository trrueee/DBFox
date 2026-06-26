import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");
const packageJson = join(process.cwd(), "package.json");

describe("DataTable virtualization foundation", () => {
  it("uses TanStack Virtual for large result rendering without handwritten row-window math", () => {
    const source = readFileSync(dataTableSource, "utf8");
    const css = readFileSync(dataGridCss, "utf8");
    const manifest = readFileSync(packageJson, "utf8");

    expect(manifest).toContain('"@tanstack/react-virtual"');
    expect(source).toContain('from "@tanstack/react-virtual"');
    expect(source).toContain("useVirtualizer");
    expect(source).toContain("rowVirtualizer");
    expect(source).toContain("virtualRows.map");
    expect(source).not.toContain("visibleRows.map((row, rowIndex)");
    expect(css).toContain(".data-grid-virtual-spacer");
    expect(css).toContain(".data-grid-virtual-spacer-cell");
  });
});
