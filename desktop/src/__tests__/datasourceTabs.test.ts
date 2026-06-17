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
    const tabsHook = read("stores/workspaceStore.ts");
    const router = read("features/appShell/WorkspaceRouter.tsx");

    expect(tabsHook).toMatch(/openConnectionManagerTab[\s\S]*\.tabs\.map\(/);
    expect(tabsHook).toMatch(/openNewConnectionTab[\s\S]*\.tabs\.map\(/);
    expect(router).toContain('initialShowAddForm={activeTab.title === "新建数据源"}');
  });

  it("does not use DOM query or delayed button click hacks to open the add form", () => {
    const app = read("App.tsx");

    expect(app).not.toContain("document.querySelector");
    expect(app).not.toMatch(/setTimeout\(\s*\(\)\s*=>[\s\S]*\.click\(\)/);
  });
});
