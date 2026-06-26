import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/features/assistant/ContextDrawer.tsx");
const localCss = join(process.cwd(), "src/features/assistant/ContextDrawer.css");
const appCss = join(process.cwd(), "src/App.css");

const drawerSelectors = [
  ".context-drawer",
  ".context-drawer.is-open",
  ".context-drawer.is-closed",
  ".context-drawer__surface",
  ".context-drawer__header",
  ".context-drawer__title",
  ".context-drawer__icon",
  ".context-drawer__close",
  ".context-drawer__body",
  ".context-drawer__stack",
  ".context-drawer__eyebrow",
  ".context-drawer__empty",
  ".context-drawer__info-list",
  ".context-drawer__info-row",
  ".context-drawer__info-row--long",
  ".context-drawer__info-label",
  ".context-drawer__info-value",
];

const retiredAppSelectors = [
  ".hifi-assistant-panel",
  ".hifi-assistant-header",
  ".hifi-assistant-title",
  ".hifi-ai-badge",
  ".hifi-context-bar",
  ".hifi-context-chips",
  ".hifi-assistant-messages",
  ".hifi-assistant-footer",
  ".hifi-ai-bubble",
  ".hifi-ai-msg-container",
  ".hifi-ai-avatar",
  ".hifi-ai-msg-bubble",
  ".hifi-user-bubble",
  ".hifi-suggest-chip",
  ".hifi-chat-input-wrapper",
  ".hifi-chat-input",
  ".hifi-chat-send-btn",
];

describe("ContextDrawer styles", () => {
  it("keeps assistant drawer styling local without hifi assistant selectors", () => {
    expect(existsSync(localCss)).toBe(true);

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./ContextDrawer.css";');
    expect(source).not.toMatch(/hifi-assistant-(header|title)/);
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/text-slate|bg-slate|border-slate|flex-1|p-3|gap-1\.5|font-bold/);

    const css = readFileSync(localCss, "utf8");
    for (const selector of drawerSelectors) {
      expect(css).toContain(selector);
    }

    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});
