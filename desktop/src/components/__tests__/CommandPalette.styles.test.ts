import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const sourcePath = join(process.cwd(), "src/components/CommandPalette.tsx");
const cssPath = join(process.cwd(), "src/components/CommandPalette.css");
const commandCssPath = join(process.cwd(), "src/components/ui/command.css");
const appCssPath = join(process.cwd(), "src/App.css");

const commandSelectors = [
  ".dbfox-command-panel",
  ".dbfox-command-search",
  ".dbfox-command-search-icon",
  ".dbfox-command-input",
  ".dbfox-command-kbd",
  ".dbfox-command-list",
  ".dbfox-command-empty",
  ".dbfox-command-group",
  ".dbfox-command-category",
  ".dbfox-command-item",
  ".dbfox-command-item-icon",
  ".dbfox-command-item-label",
];

describe("CommandPalette styles and foundation", () => {
  it("uses cmdk for command palette behavior and keeps DBFox presentation local", () => {
    const source = readFileSync(sourcePath, "utf8");
    const appCss = readFileSync(appCssPath, "utf8");

    expect(source).not.toContain('from "cmdk"');
    expect(source).toContain('from "./ui"');
    expect(source).toContain('import "./CommandPalette.css";');
    expect(existsSync(cssPath)).toBe(true);
    expect(existsSync(commandCssPath)).toBe(true);

    expect(source).not.toMatch(/selectedIndex|flatIndexMap|filteredCommands|listRef|window\.addEventListener\("keydown"/);
    expect(source).not.toMatch(/hifi-command-/);
    expect(appCss).not.toMatch(/hifi-command-|dbfox-command-/);

    const localCss = readFileSync(cssPath, "utf8");
    expect(localCss).toContain(".dbfox-command-overlay");
    expect(localCss).toContain(".dbfox-command-footer");
    expect(localCss).not.toContain(".dbfox-command-item");

    const commandCss = readFileSync(commandCssPath, "utf8");
    for (const selector of commandSelectors) {
      expect(commandCss).toContain(selector);
    }
  });
});
