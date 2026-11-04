import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

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
  cleanup();
  vi.unstubAllGlobals();
});

describe("dbfox.workspace System DLC frontend fixture", () => {
  it("continues bounded Unicode reads without skipping characters and shares the exact file reference", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#unicode`) as DlcModule;
    const reads: unknown[] = [];
    const binding = { id: "root-1", root_digest: "digest", root_path: "D:/workspace" };
    const staged = createStagedExtensionHost("dbfox.workspace", {
      openDockTab: vi.fn(),
      invokeOperation: async <T,>(_owner: string, name: string, input: unknown) => {
        if (name === "binding.get") return { binding } as T;
        if (name === "files.list") return { entries: [], truncated: false } as T;
        if (name === "files.read") {
          reads.push(input);
          const offset = (input as { offset?: number }).offset ?? 0;
          return { content: offset === 0 ? "记录😀" : "已完成", content_truncated: offset === 0, sha256: "a".repeat(64) } as T;
        }
        throw new Error(`Unexpected operation: ${name}`);
      },
    });
    await module.register?.(staged.host);
    vi.unstubAllGlobals();
    const onAsk = vi.fn();
    render(React.createElement(React.Fragment, null, staged.getContributions().dockViews[0].render({
      viewKey: "unicode-file", viewType: "dbfox.workspace.file", title: "记录.txt", projectId: "project-1", stateKey: "unicode-file", closeable: true,
      target: { type: "object", object: { kind: "dbfox.workspace.file", id: "记录.txt", version: "digest" }, authority: { kind: "dbfox.workspace.root", id: "root-1" }, locator: "记录.txt" },
    }, { activeProjectId: "project-1", activeConversationId: null, workbenchScopeId: "scope", showToast: vi.fn(), onAsk })));
    fireEvent.click(await screen.findByRole("button", { name: "继续读取" }));
    await waitFor(() => expect(reads).toEqual([{ path: "记录.txt" }, { path: "记录.txt", offset: 3 }]));
    expect(await screen.findByText("记录😀已完成")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "加入对话" }));
    expect(onAsk).toHaveBeenCalledWith({ label: "记录.txt", authority: { kind: "dbfox.workspace.root", id: "root-1" }, object: { kind: "dbfox.workspace.file", id: "记录.txt", version: "digest" }, locator: "记录.txt" });
  });

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
