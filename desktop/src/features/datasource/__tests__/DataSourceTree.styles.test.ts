import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/features/datasource/DataSourceTree.tsx");
const cssPath = join(process.cwd(), "src/features/datasource/DataSourceTree.css");

describe("DataSourceTree mature interaction foundation", () => {
  it("uses DBFox primitives for datasource dropdown, scroll body, and icon hints", () => {
    const source = readFileSync(sourcePath, "utf8");
    const css = readFileSync(cssPath, "utf8");

    expect(source).toContain("DropdownMenu");
    expect(source).toContain("DropdownMenuTrigger");
    expect(source).toContain("DropdownMenuContent");
    expect(source).toContain("DropdownMenuItem");
    expect(source).toContain("ScrollArea");
    expect(source).toContain("Tooltip");
    expect(source).toContain("TooltipTrigger");
    expect(source).toContain("TooltipContent");
    expect(source).not.toContain("dbDropdownOpen");
    expect(source).not.toContain("dbDropdownRef");
    expect(source).not.toContain("document.addEventListener");
    expect(source).not.toContain('style={{ display: "flex", alignItems: "center" }}');
    expect(source).not.toContain("cursor-pointer");
    expect(css).toContain(".ds-tree-scroll-area");
    expect(css).toContain(".ds-db-dropdown");
    expect(css).toContain(".ds-tree-status");
  });
});
