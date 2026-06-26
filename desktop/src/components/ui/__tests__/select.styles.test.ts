import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const selectSource = join(process.cwd(), "src/components/ui/select.tsx");
const selectCss = join(process.cwd(), "src/components/ui/select.css");

describe("Select primitive foundation", () => {
  it("wraps Radix Select behind the DBFox Select API", () => {
    const source = readFileSync(selectSource, "utf8");

    expect(source).toContain('from "@radix-ui/react-select"');
    expect(source).toContain("SelectPrimitive.Root");
    expect(source).toContain("SelectPrimitive.Trigger");
    expect(source).toContain("SelectPrimitive.Content");
    expect(source).toContain("SelectPrimitive.Item");
    expect(source).not.toContain("<select");
  });

  it("keeps Select visual styling in local CSS", () => {
    const css = readFileSync(selectCss, "utf8");

    expect(css).toContain(".dbfox-select-trigger");
    expect(css).toContain(".dbfox-select-content");
    expect(css).toContain(".dbfox-select-item");
    expect(css).toContain(".dbfox-select-scroll-button");
  });
});
