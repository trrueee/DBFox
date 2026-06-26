import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const commandSource = join(process.cwd(), "src/components/ui/command.tsx");
const commandCss = join(process.cwd(), "src/components/ui/command.css");

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

describe("DBFox Command primitive styles", () => {
  it("wraps cmdk with local DBFox classes", () => {
    const source = readFileSync(commandSource, "utf8");
    const css = readFileSync(commandCss, "utf8");

    expect(source).toContain('from "cmdk"');
    expect(source).toContain('import "./command.css"');
    expect(source).toContain('"dbfox-command-panel"');
    expect(source).toContain('"dbfox-command-input"');
    expect(source).toContain('"dbfox-command-item"');
    expect(source).not.toContain("cmdk-command");
    for (const selector of commandSelectors) {
      expect(css).toContain(selector);
    }
  });
});
