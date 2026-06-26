import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const scrollAreaSource = join(process.cwd(), "src/components/ui/scroll-area.tsx");
const scrollAreaCss = join(process.cwd(), "src/components/ui/scroll-area.css");

describe("DBFox ScrollArea primitive styles", () => {
  it("wraps Radix ScrollArea with local DBFox classes", () => {
    const source = readFileSync(scrollAreaSource, "utf8");
    const css = readFileSync(scrollAreaCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-scroll-area"');
    expect(source).toContain('import "./scroll-area.css"');
    expect(source).toContain('"dbfox-scroll-area"');
    expect(source).toContain('"dbfox-scroll-area-viewport"');
    expect(source).toContain('"dbfox-scroll-area-scrollbar"');
    expect(source).toContain('"dbfox-scroll-area-thumb"');
    expect(source).not.toContain("h-full w-full");
    expect(source).not.toContain("bg-[hsl(var(--border))]");
    expect(css).toContain(".dbfox-scroll-area");
    expect(css).toContain(".dbfox-scroll-area-viewport");
    expect(css).toContain(".dbfox-scroll-area-scrollbar");
    expect(css).toContain(".dbfox-scroll-area-thumb");
  });
});
