import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createStagedExtensionHost,
  initExtensionHostGlobalSdk,
} from "../extensionHost";
import type { DlcModule } from "../types";

const fixturePath = resolve(
  process.cwd(),
  "../dlcs/dbfox.workspace/frontend/index.js",
);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dbfox.workspace System DLC frontend fixture", () => {
  it("owns its Connector, Dock and Artifact renderer contributions", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
    const module = await import(/* @vite-ignore */ moduleUrl) as DlcModule;
    const staged = createStagedExtensionHost("dbfox.workspace");

    await module.register?.(staged.host);

    const contributions = staged.getContributions();
    expect(contributions.connectors.map((item) => item.id)).toEqual(["dbfox.workspace"]);
    expect(contributions.dockViews.map((item) => item.viewType)).toEqual([
      "dbfox.workspace.file",
    ]);
    expect(contributions.artifactViews.map((item) => item.id)).toEqual([
      "dbfox.workspace.file-snapshot",
      "dbfox.workspace.code-patch",
    ]);

    const snapshot = contributions.artifactViews[0];
    expect(snapshot.parsePayload({
      relativePath: "src/main.py",
      sha256: "a".repeat(64),
      sizeBytes: 32,
      truncated: false,
    })).toMatchObject({ relativePath: "src/main.py" });
    expect(() => snapshot.parsePayload({ relativePath: "src/main.py" })).toThrow(
      /requires sha256/,
    );
  });
});
