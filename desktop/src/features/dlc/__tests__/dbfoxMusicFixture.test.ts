import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule } from "../types";

const fixturePath = resolve(process.cwd(), "../dlcs/dbfox.music/frontend/index.js");

function moduleUrl(source: string): string {
  return `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("dbfox.music System DLC frontend fixture", () => {
  it("owns its Music Connector, Piano Studio, and Artifact renderers", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const root = resolve(fixturePath, "..");
    const vexflowUrl = moduleUrl(await readFile(resolve(root, "vendor/vexflow.js"), "utf8"));
    const notationUrl = moduleUrl((await readFile(resolve(root, "notation.js"), "utf8"))
      .replace('"./vendor/vexflow.js"', JSON.stringify(vexflowUrl)));
    const playbackUrl = moduleUrl(await readFile(resolve(root, "playback.js"), "utf8"));
    const source = (await readFile(fixturePath, "utf8"))
      .replace('"./notation.js"', JSON.stringify(notationUrl))
      .replace('"./playback.js"', JSON.stringify(playbackUrl));
    const module = await import(/* @vite-ignore */ moduleUrl(source)) as DlcModule;
    const staged = createStagedExtensionHost("dbfox.music", {
      invokeOperation: vi.fn(),
      openDockTab: vi.fn(),
      pickFolder: vi.fn(),
      pickFile: vi.fn(),
      readPickedFile: vi.fn(),
    });
    await module.register?.(staged.host);
    const contributions = staged.getContributions();
    expect(contributions.connectors.map((item) => item.id)).toEqual(["dbfox.music"]);
    expect(contributions.dockViews.map((item) => item.viewType)).toEqual(["dbfox.music.piano-studio"]);
    expect(contributions.artifactRenderers.map((item) => item.type)).toEqual([
      "dbfox.music.score_revision",
      "dbfox.music.transcription",
    ]);
    expect(contributions.artifactRenderers[0].parsePayload({
      scoreId: "score-1", revision: 2, title: "Moonlit Window",
    })).toMatchObject({ scoreId: "score-1", revision: 2 });
  });
});
