import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  createStagedExtensionHost,
  initExtensionHostGlobalSdk,
} from "../extensionHost";
import type { DlcModule } from "../types";

const fixturePath = resolve(
  process.cwd(),
  "../test-fixtures/dlc/acme.echo/frontend/index.js",
);

describe("acme.echo packaged frontend fixture", () => {
  it("registers visible Dock and Artifact contributions through the public host", async () => {
    initExtensionHostGlobalSdk();
    const source = await readFile(fixturePath, "utf8");
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
    const module = await import(/* @vite-ignore */ moduleUrl) as DlcModule;
    const staged = createStagedExtensionHost("acme.echo");

    await module.register?.(staged.host);

    const contributions = staged.getContributions();
    expect(contributions.dockViews).toHaveLength(1);
    expect(contributions.dockViews[0].viewType).toBe("acme.echo.dock");
    expect(contributions.dockViews[0].isVisible(
      {
        viewKey: "echo",
        viewType: "acme.echo.dock",
        title: "Echo",
        closeable: true,
      },
      {
        activeProjectId: "project-1",
        activeConversationId: null,
      },
    )).toBe(true);

    expect(contributions.artifactRenderers).toHaveLength(1);
    const renderer = contributions.artifactRenderers[0];
    expect(renderer.type).toBe("acme.echo.message");
    expect(renderer.supportedSchemaVersions).toEqual([1]);
    expect(renderer.parsePayload({ message: "hello" })).toEqual({ message: "hello" });
    expect(() => renderer.parsePayload({ message: "" })).toThrow(/requires message/);
  });
});
