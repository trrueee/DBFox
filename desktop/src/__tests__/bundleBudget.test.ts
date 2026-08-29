import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { inspectBundle } from "../../scripts/bundleBudget.mjs";

const temporaryDirectories: string[] = [];

function makeBundle(files: Record<string, string>): string {
  const distDir = mkdtempSync(join(tmpdir(), "dbfox-bundle-budget-"));
  temporaryDirectories.push(distDir);
  const assetsDir = join(distDir, "assets");
  mkdirSync(assetsDir);
  writeFileSync(
    join(distDir, "index.html"),
    '<!doctype html><script type="module" src="./assets/index-entry.js"></script>',
  );
  for (const [name, content] of Object.entries(files)) {
    writeFileSync(join(assetsDir, name), content);
  }
  return distDir;
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("bundle budget contract", () => {
  it("accepts a bounded entry and required workspace route chunks", () => {
    const distDir = makeBundle({
      "index-entry.js": "console.log('entry')",
      "ConversationWorkspace-route.js": "export {}",
    });

    expect(inspectBundle(distDir)).toMatchObject({
      entry: { file: "index-entry.js" },
    });
  });

  it("rejects an entry that exceeds its size budget", () => {
    const distDir = makeBundle({
      "index-entry.js": "a".repeat(700 * 1024),
      "ConversationWorkspace-route.js": "export {}",
    });

    expect(() => inspectBundle(distDir)).toThrow("Initial desktop entry exceeds its bundle budget");
  });

  it("rejects a build without the independently loaded workspace route", () => {
    const distDir = makeBundle({
      "index-entry.js": "console.log('entry')",
    });

    expect(() => inspectBundle(distDir)).toThrow("Core workspace routes must remain independently loaded");
  });
});
