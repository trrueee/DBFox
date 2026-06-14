import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = resolve(here, "..");

function read(relativePath: string) {
  return readFileSync(resolve(srcRoot, relativePath), "utf8");
}

describe("datasource settings tab behavior", () => {
  it("updates the reused settings tab title for manager and new-connection modes", () => {
    const app = read("App.tsx");

    expect(app).toMatch(/openConnectionManagerTab[\s\S]*prev\.map\(\(tab\) => \(tab\.id === tabId \? \{ \.\.\.tab, title: "数据源管理" \} : tab\)\)/);
    expect(app).toMatch(/openNewConnectionTab[\s\S]*prev\.map\(\(tab\) => \(tab\.id === tabId \? \{ \.\.\.tab, title: "新建数据源" \} : tab\)\)/);
    expect(app).toContain('initialShowAddForm={activeTab.title === "新建数据源"}');
  });

  it("does not use DOM query or delayed button click hacks to open the add form", () => {
    const app = read("App.tsx");

    expect(app).not.toContain("document.querySelector");
    expect(app).not.toMatch(/setTimeout\(\s*\(\)\s*=>[\s\S]*\.click\(\)/);
  });
});
