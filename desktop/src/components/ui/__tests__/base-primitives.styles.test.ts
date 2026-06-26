import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const uiDir = join(process.cwd(), "src/components/ui");

const utilityClassPattern =
  /\b(?:inline-flex|flex|grid|items-|justify-|gap-\d|px-\d|py-\d|p-\d|m-\d|mt-\d|min-h-|h-\d|w-\d|size-|rounded|border(?:\b|-\[)|bg-\[|text-\[|font-|leading-|transition-|duration-|ease-|focus-visible:|hover:|disabled:|active:|animate-spin|whitespace-|shrink-0|max-w-|overflow-|opacity-|cursor-|\[&_svg\])/;

const primitiveStyleContracts = [
  {
    sourcePath: join(uiDir, "button.tsx"),
    cssPath: join(uiDir, "button.css"),
    importStatement: 'import "./button.css"',
    forbidden: ["class-variance-authority", "bg-[", "text-[", "px-", "[&_svg]"],
    selectors: [
      ".dbfox-button",
      ".dbfox-button--default",
      ".dbfox-button--destructive",
      ".dbfox-button--outline",
      ".dbfox-button--secondary",
      ".dbfox-button--ghost",
      ".dbfox-button--link",
      ".dbfox-button--sm",
      ".dbfox-button--lg",
      ".dbfox-button--icon",
      ".dbfox-button--icon-sm",
    ],
  },
  {
    sourcePath: join(uiDir, "input.tsx"),
    cssPath: join(uiDir, "input.css"),
    importStatement: 'import "./input.css"',
    forbidden: ["bg-transparent", "focus-visible:", "placeholder:", "file:"],
    selectors: [".dbfox-input"],
  },
  {
    sourcePath: join(uiDir, "label.tsx"),
    cssPath: join(uiDir, "label.css"),
    importStatement: 'import "./label.css"',
    forbidden: ["class-variance-authority", "peer-disabled:", "leading-none"],
    selectors: [".dbfox-label"],
  },
  {
    sourcePath: join(uiDir, "state.tsx"),
    cssPath: join(uiDir, "state.css"),
    importStatement: 'import "./state.css"',
    forbidden: ["bg-[", "border-[", "animate-spin", "max-w-md", "mt-"],
    selectors: [
      ".dbfox-empty-state",
      ".dbfox-empty-state__icon",
      ".dbfox-empty-state__title",
      ".dbfox-empty-state__description",
      ".dbfox-empty-state__action",
      ".dbfox-error-state",
      ".dbfox-error-state__icon",
      ".dbfox-error-state__content",
      ".dbfox-error-state__title",
      ".dbfox-error-state__description",
      ".dbfox-error-state__retry",
      ".dbfox-loading-state",
      ".dbfox-loading-state__icon",
    ],
  },
];

describe("base UI primitive styles", () => {
  it("keeps base primitive presentation in local CSS files", () => {
    for (const contract of primitiveStyleContracts) {
      const source = readFileSync(contract.sourcePath, "utf8");
      const css = readFileSync(contract.cssPath, "utf8");

      expect(source).toContain(contract.importStatement);
      expect(source).not.toMatch(utilityClassPattern);
      for (const forbidden of contract.forbidden) {
        expect(source).not.toContain(forbidden);
      }
      for (const selector of contract.selectors) {
        expect(css).toContain(selector);
      }
    }
  });
});
