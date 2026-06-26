import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const smartQueryHomeSource = join(process.cwd(), "src/features/workspace/SmartQueryHome.tsx");
const smartQueryHeroSource = join(process.cwd(), "src/features/workspace/smartQuery/SmartQueryHero.tsx");
const askInputSource = join(process.cwd(), "src/features/workspace/smartQuery/AskInputBox.tsx");
const localCss = join(process.cwd(), "src/features/workspace/SmartQueryHome.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".smart-query-home",
  ".smart-query-home__content",
  ".smart-query-hero",
  ".smart-query-hero__fox",
  ".smart-query-hero__title",
  ".smart-query-gradient-text",
  ".smart-query-hero__subtitle",
  ".smart-query-hero__pattern",
  ".ask-input",
  ".ask-input__textarea",
  ".ask-input__textarea:focus",
  ".ask-input__send",
];

const retiredAppSelectors = [
  ".hifi-query-home",
  ".hifi-query-home-content",
  ".hifi-hero",
  ".hifi-hero-fox",
  ".hifi-hero-title",
  ".hifi-gradient-text",
  ".hifi-hero-subtitle",
  ".hifi-hero-pattern",
  ".hifi-ask-input-container",
  ".hifi-ask-input",
  ".hifi-ask-send-btn",
  ".hifi-section-header",
  ".hifi-text-btn",
  ".hifi-recommend-grid",
  ".hifi-recommend-card",
  ".hifi-recommend-icon",
  ".hifi-recommend-text",
  ".hifi-tag",
  ".hifi-recent-tabs",
  ".hifi-recent-tab",
  ".hifi-recent-grid",
  ".hifi-recent-card",
  ".hifi-recent-name",
  ".hifi-recent-desc",
];

describe("SmartQueryHome styles", () => {
  it("keeps smart-query home, hero, and input styles local", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const sources = [
      readFileSync(smartQueryHomeSource, "utf8"),
      readFileSync(smartQueryHeroSource, "utf8"),
      readFileSync(askInputSource, "utf8"),
    ];

    for (const source of sources) {
      expect(source).toContain("SmartQueryHome.css");
      expect(source).not.toContain("style=");
      expect(source).not.toMatch(/hifi-query-home|hifi-hero|hifi-gradient-text|hifi-ask-input|hifi-tab-pane/);
    }

    const askInput = readFileSync(askInputSource, "utf8");
    expect(askInput).toContain('from "../../../components/ui";');
    expect(askInput).toContain("<Button");
    expect(askInput).not.toMatch(/<button\b/);
  });

  it("removes migrated and unused smart-query business selectors from App.css", () => {
    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});
