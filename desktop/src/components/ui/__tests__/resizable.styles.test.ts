import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const resizableSource = join(process.cwd(), "src/components/ui/resizable.tsx");
const resizableCss = join(process.cwd(), "src/components/ui/resizable.css");

const requiredSelectors = [
  ".dbfox-resizable-panel-group",
  ".dbfox-resizable-panel",
  ".dbfox-resizable-handle",
  ".dbfox-resizable-handle__rail",
  ".dbfox-resizable-handle__grip",
];

describe("DBFox Resizable primitive styles", () => {
  it("wraps react-resizable-panels with local DBFox classes", () => {
    const source = readFileSync(resizableSource, "utf8");
    const css = readFileSync(resizableCss, "utf8");

    expect(source).toContain('from "react-resizable-panels"');
    expect(source).toContain('import "./resizable.css"');
    expect(source).toContain('"dbfox-resizable-panel-group"');
    expect(source).toContain('"dbfox-resizable-panel"');
    expect(source).toContain('"dbfox-resizable-handle"');
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});
