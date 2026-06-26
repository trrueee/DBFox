import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const hoverCardSource = join(process.cwd(), "src/components/ui/hover-card.tsx");
const hoverCardCss = join(process.cwd(), "src/components/ui/hover-card.css");

describe("DBFox HoverCard primitive styles", () => {
  it("wraps Radix HoverCard with local DBFox classes", () => {
    const source = readFileSync(hoverCardSource, "utf8");
    const css = readFileSync(hoverCardCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-hover-card"');
    expect(source).toContain('import "./hover-card.css"');
    expect(source).toContain('"dbfox-hover-card-content"');
    expect(source).toContain('"dbfox-hover-card-arrow"');
    expect(source).not.toContain("min-w-64");
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(css).toContain(".dbfox-hover-card-content");
    expect(css).toContain(".dbfox-hover-card-arrow");
  });
});
