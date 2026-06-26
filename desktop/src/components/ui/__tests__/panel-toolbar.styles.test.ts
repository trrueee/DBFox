import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const uiDir = join(process.cwd(), "src/components/ui");

const utilityClassPattern =
  /\b(?:flex|grid|items-|justify-|gap-\d|min-h-|min-w-|shrink-0|flex-\d|rounded|border(?:\b|-\[)|bg-\[|text-\[|font-|leading-|truncate|p-\d|px-\d|py-\d|m-\d)/;

const contracts = [
  {
    sourcePath: join(uiDir, "panel.tsx"),
    cssPath: join(uiDir, "panel.css"),
    importStatement: 'import "./panel.css"',
    selectors: [
      ".dbfox-panel",
      ".dbfox-panel__header",
      ".dbfox-panel__title",
      ".dbfox-panel__description",
      ".dbfox-panel__body",
      ".dbfox-panel__footer",
    ],
  },
  {
    sourcePath: join(uiDir, "toolbar.tsx"),
    cssPath: join(uiDir, "toolbar.css"),
    importStatement: 'import "./toolbar.css"',
    selectors: [
      ".dbfox-toolbar",
      ".dbfox-toolbar__title",
      ".dbfox-toolbar__group",
    ],
  },
];

describe("Panel and Toolbar primitive styles", () => {
  it("keeps foundational layout and typography in local CSS", () => {
    for (const contract of contracts) {
      const source = readFileSync(contract.sourcePath, "utf8");
      const css = readFileSync(contract.cssPath, "utf8");

      expect(source).toContain(contract.importStatement);
      expect(source).not.toMatch(utilityClassPattern);
      for (const selector of contract.selectors) {
        expect(css).toContain(selector);
      }
    }
  });
});
