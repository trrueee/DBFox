import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dialogSource = join(process.cwd(), "src/components/ui/dialog.tsx");
const dialogCss = join(process.cwd(), "src/components/ui/dialog.css");

describe("DBFox Dialog primitive styles", () => {
  it("wraps Radix Dialog with local DBFox classes", () => {
    const source = readFileSync(dialogSource, "utf8");
    const css = readFileSync(dialogCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-dialog"');
    expect(source).toContain('import "./dialog.css"');
    expect(source).toContain('"dbfox-dialog-overlay"');
    expect(source).toContain('"dbfox-dialog-content"');
    expect(source).toContain('"dbfox-dialog-close"');
    expect(source).toContain('"dbfox-dialog-header"');
    expect(source).toContain('"dbfox-dialog-footer"');
    expect(source).toContain('"dbfox-dialog-title"');
    expect(source).toContain('"dbfox-dialog-description"');
    expect(source).not.toContain("fixed inset-0");
    expect(source).not.toContain("left-[50%]");
    expect(source).not.toContain("shadow-panel-elevated");
    expect(source).not.toContain("absolute right-4");
    expect(source).not.toContain("space-y-1.5");
    expect(source).not.toContain("sm:flex-row");
    expect(css).toContain(".dbfox-dialog-overlay");
    expect(css).toContain(".dbfox-dialog-content");
    expect(css).toContain(".dbfox-dialog-close");
    expect(css).toContain(".dbfox-dialog-title");
    expect(css).toContain(".dbfox-dialog-description");
  });
});
