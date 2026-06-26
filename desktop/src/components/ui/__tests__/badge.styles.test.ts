import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const badgeSource = join(process.cwd(), "src/components/ui/badge.tsx");
const badgeCss = join(process.cwd(), "src/components/ui/badge.css");

const utilityClassPattern =
  /\b(?:inline-flex|items-|rounded|px-\d|py-\d|text-\[|font-|transition-|focus:|focus-visible:|ring-|bg-\[|border(?:\b|-\[))/;

const requiredSelectors = [
  ".dbfox-badge",
  ".dbfox-badge--default",
  ".dbfox-badge--secondary",
  ".dbfox-badge--success",
  ".dbfox-badge--warning",
  ".dbfox-badge--destructive",
  ".dbfox-badge--outline",
];

describe("Badge primitive styles", () => {
  it("keeps Badge presentation in local CSS while preserving the variants helper", () => {
    const source = readFileSync(badgeSource, "utf8");
    const css = readFileSync(badgeCss, "utf8");

    expect(source).toContain('import "./badge.css"');
    expect(source).toContain("function badgeVariants");
    expect(source).not.toContain("class-variance-authority");
    expect(source).not.toMatch(utilityClassPattern);
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});
