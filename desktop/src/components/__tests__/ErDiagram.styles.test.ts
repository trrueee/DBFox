import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/components/ErDiagram.tsx");
const cssPath = join(process.cwd(), "src/components/ErDiagram.css");

const erDiagramSelectors = [
  ".er-diagram",
  ".er-diagram__viewport",
  ".er-card",
  ".er-card--focus",
  ".er-card--secondary",
  ".er-card__handle",
  ".er-card__header",
  ".er-card__status",
  ".er-card__title",
  ".er-card__annotate",
  ".er-card__fields",
  ".er-card__field",
  ".er-card__field-marker",
  ".er-card__field-marker--pk",
  ".er-card__field-marker--fk",
  ".er-card__field-name",
  ".er-card__field-name--primary",
  ".er-card__field-type",
  ".er-card__toggle",
  ".er-card__comment",
  ".er-edge-label",
  ".er-edge-label--inferred",
  ".er-flow-controls",
  ".er-flow-minimap",
];

describe("ErDiagram styles", () => {
  it("keeps React Flow diagram presentation in local CSS without JSX inline styles", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./ErDiagram.css";');
    expect(existsSync(cssPath)).toBe(true);
    expect(source).not.toContain("style={{");
    expect(source).not.toContain("style={");
    expect(source).not.toContain("currentTarget.style");
    expect(source).not.toMatch(/onMouseEnter|onMouseLeave/);
    expect(source).not.toContain('viewMode === "module"');
    expect(source).not.toContain("moduleGroups");

    const css = readFileSync(cssPath, "utf8");
    for (const selector of erDiagramSelectors) {
      expect(css).toContain(selector);
    }
  });
});
