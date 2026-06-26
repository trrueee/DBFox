import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const tooltipSource = join(process.cwd(), "src/components/ui/tooltip.tsx");
const tooltipCss = join(process.cwd(), "src/components/ui/tooltip.css");

describe("DBFox Tooltip primitive styles", () => {
  it("wraps Radix Tooltip behind a local DBFox stylesheet", () => {
    const source = readFileSync(tooltipSource, "utf8");
    const css = readFileSync(tooltipCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-tooltip"');
    expect(source).toContain("TooltipPrimitive.Provider");
    expect(source).toContain("TooltipPrimitive.Content");
    expect(source).toContain('import "./tooltip.css"');
    expect(source).toContain('"dbfox-tooltip-content"');
    expect(source).not.toContain("bg-[hsl(var(--foreground))]");
    expect(source).not.toContain("animate-in");
    expect(css).toContain(".dbfox-tooltip-content");
    expect(css).toContain(".dbfox-tooltip-arrow");
  });
});
