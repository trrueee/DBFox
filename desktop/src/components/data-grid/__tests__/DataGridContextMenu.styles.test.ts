import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const contextMenuSource = join(process.cwd(), "src/components/data-grid/DataGridContextMenu.tsx");
const typesSource = join(process.cwd(), "src/components/data-grid/types.ts");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");

describe("DataGrid context menu foundation", () => {
  it("uses DBFox ContextMenu instead of parent-managed x/y state", () => {
    const tableSource = readFileSync(dataTableSource, "utf8");
    const menuSource = readFileSync(contextMenuSource, "utf8");
    const types = readFileSync(typesSource, "utf8");

    expect(tableSource).toContain("ContextMenu");
    expect(tableSource).toContain("ContextMenuTrigger");
    expect(menuSource).toContain("ContextMenuContent");
    expect(menuSource).toContain("ContextMenuItem");
    expect(menuSource).toContain("ContextMenuSeparator");

    expect(tableSource).not.toContain("setContextMenu");
    expect(tableSource).not.toContain("contextMenu");
    expect(tableSource).not.toContain("clientX");
    expect(tableSource).not.toContain("clientY");
    expect(types).not.toContain("DataGridContextMenuState");
  });

  it("removes fixed backdrop positioning while keeping DBFox menu styling local", () => {
    const menuSource = readFileSync(contextMenuSource, "utf8");
    const css = readFileSync(dataGridCss, "utf8");
    const contextMenuCss = css.match(/\.data-grid-context-menu\s*\{[\s\S]*?\}/)?.[0] ?? "";

    expect(menuSource).not.toContain('style={{ position: "fixed"');
    expect(menuSource).not.toContain("style={{ left:");
    expect(menuSource).not.toContain("onClose");
    expect(contextMenuCss).toContain(".data-grid-context-menu");
    expect(contextMenuCss).not.toContain("position: fixed");
    expect(contextMenuCss).not.toContain("z-index: 3000");
  });
});
