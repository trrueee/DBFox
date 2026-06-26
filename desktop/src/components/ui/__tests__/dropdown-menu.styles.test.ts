import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dropdownMenuSource = join(process.cwd(), "src/components/ui/dropdown-menu.tsx");
const dropdownMenuCss = join(process.cwd(), "src/components/ui/dropdown-menu.css");

describe("DBFox DropdownMenu primitive styles", () => {
  it("wraps Radix DropdownMenu with local DBFox classes", () => {
    const source = readFileSync(dropdownMenuSource, "utf8");
    const css = readFileSync(dropdownMenuCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-dropdown-menu"');
    expect(source).toContain('import "./dropdown-menu.css"');
    expect(source).toContain('"dbfox-dropdown-menu-content"');
    expect(source).toContain('"dbfox-dropdown-menu-item"');
    expect(source).toContain('"dbfox-dropdown-menu-separator"');
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(source).not.toContain("focus:bg-[hsl(var(--accent))]");
    expect(css).toContain(".dbfox-dropdown-menu-content");
    expect(css).toContain(".dbfox-dropdown-menu-item");
    expect(css).toContain(".dbfox-dropdown-menu-separator");
  });
});
