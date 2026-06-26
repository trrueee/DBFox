import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const contextMenuSource = join(process.cwd(), "src/components/ui/context-menu.tsx");
const contextMenuCss = join(process.cwd(), "src/components/ui/context-menu.css");

describe("DBFox ContextMenu primitive styles", () => {
  it("wraps Radix ContextMenu with local DBFox classes", () => {
    const source = readFileSync(contextMenuSource, "utf8");
    const css = readFileSync(contextMenuCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-context-menu"');
    expect(source).toContain('import "./context-menu.css"');
    expect(source).toContain('"dbfox-context-menu-content"');
    expect(source).toContain('"dbfox-context-menu-item"');
    expect(source).toContain('"dbfox-context-menu-separator"');
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(source).not.toContain("focus:bg-[hsl(var(--accent))]");
    expect(css).toContain(".dbfox-context-menu-content");
    expect(css).toContain(".dbfox-context-menu-item");
    expect(css).toContain(".dbfox-context-menu-separator");
  });
});
