import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const imageCellSource = join(process.cwd(), "src/components/ImageCell.tsx");
const imageCellCss = join(process.cwd(), "src/components/ImageCell.css");
const appCss = join(process.cwd(), "src/App.css");

describe("ImageCell foundation", () => {
  it("delegates image preview positioning to DBFox HoverCard and lightbox to Dialog", () => {
    const source = readFileSync(imageCellSource, "utf8");

    expect(source).toContain('import "./ImageCell.css";');
    expect(source).toContain("HoverCard");
    expect(source).toContain("HoverCardContent");
    expect(source).toContain("HoverCardTrigger");
    expect(source).toContain("Dialog");
    expect(source).toContain("DialogContent");
    expect(source).not.toContain("createPortal");
    expect(source).not.toContain("getBoundingClientRect");
    expect(source).not.toContain("window.innerWidth");
    expect(source).not.toContain("popoverPos");
  });

  it("keeps image cell presentation local instead of App.css fixed-position popovers", () => {
    expect(existsSync(imageCellCss)).toBe(true);
    const css = readFileSync(imageCellCss, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    for (const selector of [
      ".hifi-img-cell",
      ".hifi-img-thumb",
      ".hifi-img-url",
      ".hifi-img-hover-card",
      ".hifi-img-lightbox",
      ".hifi-img-lightbox-bar",
    ]) {
      expect(css).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
    expect(globalCss).not.toContain(".hifi-img-popover");
  });
});
