import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");
const packageJson = join(process.cwd(), "package.json");

describe("DataTable TanStack core", () => {
  it("uses TanStack Table for sorting, filtering, column visibility, and row modeling", () => {
    const source = readFileSync(dataTableSource, "utf8");
    const manifest = readFileSync(packageJson, "utf8");

    expect(manifest).toContain('"@tanstack/react-table"');
    expect(source).toContain('from "@tanstack/react-table"');
    expect(source).toContain("useReactTable");
    expect(source).toContain("getCoreRowModel");
    expect(source).toContain("getFilteredRowModel");
    expect(source).toContain("getSortedRowModel");
    expect(source).toContain("table.getRowModel().rows");
    expect(source).not.toContain("useDataTableView");
    expect(source).not.toContain("visibleRows.map");
  });

  it("keeps the data-grid visual frame polished with local CSS boundaries", () => {
    const css = readFileSync(dataGridCss, "utf8");

    expect(css).toMatch(/\.data-grid-root\s*{[^}]*border:\s*1px solid var\(--border-light\);/s);
    expect(css).toMatch(/\.data-grid-root\s*{[^}]*border-radius:\s*8px;/s);
    expect(css).toMatch(/\.data-grid-root\s*{[^}]*box-shadow:/s);
    expect(css).toMatch(/\.data-grid-table\s*{[^}]*border-collapse:\s*separate;/s);
    expect(css).toMatch(/\.data-grid-table\s*{[^}]*border-spacing:\s*0;/s);
  });
});
