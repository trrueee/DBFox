import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const toastSource = join(process.cwd(), "src/components/Toast.tsx");
const toastCss = join(process.cwd(), "src/components/Toast.css");
const packageJson = join(process.cwd(), "package.json");

const requiredSelectors = [
  ".dbfox-toast-viewport",
  ".dbfox-toast-root",
  ".dbfox-toast-root--success",
  ".dbfox-toast-root--error",
  ".dbfox-toast-root--warning",
  ".dbfox-toast-root--info",
  ".dbfox-toast-icon",
  ".dbfox-toast-message",
  ".dbfox-toast-close",
];

describe("Toast Radix foundation", () => {
  it("wraps Radix Toast while keeping DBFox presentation in local CSS", () => {
    const source = readFileSync(toastSource, "utf8");
    const css = readFileSync(toastCss, "utf8");
    const pkg = readFileSync(packageJson, "utf8");

    expect(pkg).toContain('"@radix-ui/react-toast"');
    expect(source).toContain('from "@radix-ui/react-toast"');
    expect(source).toContain('import "./Toast.css"');
    expect(source).not.toContain('from "gsap"');
    expect(source).not.toContain("style={{");
    expect(source).not.toContain("onMouseEnter");
    expect(source).not.toContain("onMouseLeave");
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});
