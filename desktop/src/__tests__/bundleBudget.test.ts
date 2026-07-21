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
  it("accepts a split entry, chart renderer, and required workspace route chunks", () => {
    const distDir = makeBundle({
      "index-entry.js": "console.log('entry')",
      "ChartArtifactView-chart.js": "console.log('chart')",
      "ConversationWorkspace-route.js": "export {}",
      "TableWorkspace-route.js": "export {}",
      "DataSourcesPage-route.js": "export {}",
      "AgentEvalPage-route.js": "export {}",
    });

    expect(inspectBundle(distDir)).toMatchObject({
      entry: { file: "index-entry.js" },
      chart: { file: "ChartArtifactView-chart.js" },
    });
  });

  it("rejects an entry that exceeds its size budget", () => {
    const distDir = makeBundle({
      "index-entry.js": "a".repeat(700 * 1024),
      "ChartArtifactView-chart.js": "console.log('chart')",
      "ConversationWorkspace-route.js": "export {}",
      "TableWorkspace-route.js": "export {}",
      "DataSourcesPage-route.js": "export {}",
      "AgentEvalPage-route.js": "export {}",
    });

    expect(() => inspectBundle(distDir)).toThrow("Initial desktop entry exceeds its bundle budget");
  });

  it("rejects a build that folds the chart renderer back into the entry", () => {
    const distDir = makeBundle({
      "index-entry.js": "console.log('entry')",
      "ConversationWorkspace-route.js": "export {}",
      "TableWorkspace-route.js": "export {}",
      "DataSourcesPage-route.js": "export {}",
      "AgentEvalPage-route.js": "export {}",
    });

    expect(() => inspectBundle(distDir)).toThrow("ChartArtifactView must remain an independently deferred chart chunk");
  });
});
