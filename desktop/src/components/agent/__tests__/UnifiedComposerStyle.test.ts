import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

describe("UnifiedComposer style contract", () => {
  it("uses CSP-safe native field sizing with a bounded scroll fallback", () => {
    const css = readFileSync(
      join(process.cwd(), "src/components/agent/unified-composer.css"),
      "utf8",
    );

    expect(css).toContain("field-sizing: content");
    expect(css).toContain("max-height: 160px");
    expect(css).toContain("overflow-y: auto");
  });
});
