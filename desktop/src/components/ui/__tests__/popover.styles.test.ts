import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const popoverSource = join(process.cwd(), "src/components/ui/popover.tsx");
const popoverCss = join(process.cwd(), "src/components/ui/popover.css");

describe("DBFox Popover primitive styles", () => {
  it("wraps Radix Popover with local DBFox classes", () => {
    const source = readFileSync(popoverSource, "utf8");
    const css = readFileSync(popoverCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-popover"');
    expect(source).toContain('import "./popover.css"');
    expect(source).toContain('"dbfox-popover-content"');
    expect(source).toContain('"dbfox-popover-arrow"');
    expect(source).not.toContain("min-w-64");
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(css).toContain(".dbfox-popover-content");
    expect(css).toContain(".dbfox-popover-arrow");
  });
});
