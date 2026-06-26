import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/features/workspace/WorkspaceTabs.tsx");
const localCss = join(process.cwd(), "src/features/workspace/WorkspaceTabs.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".workspace-tabs",
  ".workspace-tabs__root",
  ".workspace-tabs__scroll",
  ".workspace-tab",
  ".workspace-tab.is-active",
  ".workspace-tab__main",
  ".workspace-tab__icon",
  ".workspace-tab__icon--table",
  ".workspace-tab__icon--sql",
  ".workspace-tab__title",
  ".workspace-tab__close",
  ".workspace-tabs__add",
];

const retiredAppSelectors = [
  ".hifi-workspace-tab-bar",
  ".hifi-workspace-tabs-scroll",
  ".hifi-workspace-tab",
  ".hifi-tab-close",
  ".hifi-tab-add-btn",
  ".hifi-workspace-tab-actions",
  ".hifi-right-drawer-toggle-btn",
];

describe("WorkspaceTabs styles", () => {
  it("keeps workspace tab chrome styles local without inline styles or Tailwind residue", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./WorkspaceTabs.css";');
    expect(source).toContain('from "../../components/ui";');
    expect(source).toContain("Tabs");
    expect(source).toContain("TabsList");
    expect(source).toContain("TabsTrigger");
    expect(source).toContain("Tooltip");
    expect(source).toContain("TooltipTrigger");
    expect(source).toContain("TooltipContent");
    expect(source).toContain("<Button");
    expect(source).not.toContain('title={`关闭 ${tab.title}`}');
    expect(source).not.toContain('title="新建 SQL 查询"');
    expect(source).not.toContain('role="tablist"');
    expect(source).not.toContain('role="tab"');
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/hifi-workspace-tab|hifi-tab-close|hifi-tab-add-btn/);
    expect(source).not.toMatch(/text-(blue|green|orange|purple|indigo|pink|rose)-500|truncate|max-w-|ml-|opacity-/);

    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});
