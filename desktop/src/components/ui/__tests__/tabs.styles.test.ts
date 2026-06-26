import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const tabsSource = join(process.cwd(), "src/components/ui/tabs.tsx");
const tabsCss = join(process.cwd(), "src/components/ui/tabs.css");

describe("DBFox Tabs primitive styles", () => {
  it("wraps Radix Tabs with local DBFox classes", () => {
    const source = readFileSync(tabsSource, "utf8");
    const css = readFileSync(tabsCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-tabs"');
    expect(source).toContain('import "./tabs.css"');
    expect(source).toContain('"dbfox-tabs-list"');
    expect(source).toContain('"dbfox-tabs-trigger"');
    expect(source).toContain('"dbfox-tabs-content"');
    expect(source).not.toContain("inline-flex items-center");
    expect(source).not.toContain("focus-visible:ring-2");
    expect(source).not.toContain("disabled:pointer-events-none");
    expect(source).not.toContain("outline-none");
    expect(css).toContain(".dbfox-tabs-list");
    expect(css).toContain(".dbfox-tabs-trigger");
    expect(css).toContain(".dbfox-tabs-content");
  });
});
