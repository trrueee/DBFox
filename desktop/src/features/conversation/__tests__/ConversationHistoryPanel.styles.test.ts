import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/features/conversation/ConversationHistoryPanel.tsx");
const cssPath = join(process.cwd(), "src/features/conversation/ConversationHistoryPanel.css");
const appCssPath = join(process.cwd(), "src/App.css");

const selectors = [
  ".conversation-history",
  ".conversation-history__body",
  ".conversation-history__toolbar",
  ".conversation-history__count",
  ".conversation-history__list",
  ".conversation-history__item",
  ".conversation-history__item--active",
  ".conversation-history__item-head",
  ".conversation-history__title",
  ".conversation-history__preview",
  ".conversation-history__meta",
  ".conversation-history__delete",
];

describe("ConversationHistoryPanel styles", () => {
  it("uses WorkspaceShell and local CSS without Tailwind or global guide chip styles", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./ConversationHistoryPanel.css";');
    expect(source).toContain("WorkspaceShell");
    expect(source).toContain("from \"../../components/ui\"");
    expect(source).toContain("<Button");
    expect(source).toContain("<EmptyState");
    for (const token of [
      "hifi-",
      "p-4",
      "flex flex-col",
      "text-slate",
      "bg-white",
      "rounded-xl",
      "hover:",
      "group",
      "line-clamp",
    ]) {
      expect(source).not.toContain(token);
    }

    expect(existsSync(cssPath)).toBe(true);
    const css = readFileSync(cssPath, "utf8");
    for (const selector of selectors) {
      expect(css).toContain(selector);
    }

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).not.toContain("hifi-guide-chip-prod");
  });
});
