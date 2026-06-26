import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const componentDir = join(process.cwd(), "src/components");

const utilityClassPattern = /\b(?:sm:max-w-|p-\d|px-\d|py-\d|gap-\d|space-y-|border-\[|bg-\[|text-\[|font-semibold|font-mono|rounded(?:-|\b)|flex items-|items-center|items-start|justify-|whitespace-pre-wrap|overflow-auto|max-h-\[|w-\d|h-\d|shrink-0|mt-\d)/;

const surfaces = [
  {
    sourcePath: join(componentDir, "SettingsDialog.tsx"),
    cssPath: join(componentDir, "SettingsDialog.css"),
    importStatement: 'import "./SettingsDialog.css"',
    selectors: [
      ".settings-dialog-content",
      ".settings-dialog-header",
      ".settings-dialog-title",
      ".settings-dialog-title-icon",
      ".settings-dialog-footer",
      ".settings-dialog-actions",
      ".settings-dialog-save",
      ".settings-button-indicator",
    ],
  },
  {
    sourcePath: join(componentDir, "ConfirmDialog.tsx"),
    cssPath: join(componentDir, "ConfirmDialog.css"),
    importStatement: 'import "./ConfirmDialog.css"',
    selectors: [
      ".confirm-dialog-content",
      ".confirm-dialog-title-row",
      ".confirm-dialog-icon",
      ".confirm-dialog-icon--danger",
      ".confirm-dialog-icon--warning",
      ".confirm-dialog-icon--info",
      ".confirm-dialog-message",
    ],
  },
  {
    sourcePath: join(componentDir, "DangerConfirmDialog.tsx"),
    cssPath: join(componentDir, "DangerConfirmDialog.css"),
    importStatement: 'import "./DangerConfirmDialog.css"',
    selectors: [
      ".danger-confirm-dialog-content",
      ".danger-confirm-dialog-title-row",
      ".danger-confirm-dialog-summary",
      ".danger-confirm-dialog-code",
      ".danger-confirm-dialog-input",
      ".danger-confirm-dialog-input--valid",
      ".danger-confirm-dialog-warning",
    ],
  },
];

describe("dialog business surfaces", () => {
  it("keeps dialog-specific presentation in local CSS files", () => {
    for (const surface of surfaces) {
      const source = readFileSync(surface.sourcePath, "utf8");
      const css = readFileSync(surface.cssPath, "utf8");

      expect(source).toContain(surface.importStatement);
      expect(source).not.toMatch(utilityClassPattern);
      for (const selector of surface.selectors) {
        expect(css).toContain(selector);
      }
    }
  });
});
