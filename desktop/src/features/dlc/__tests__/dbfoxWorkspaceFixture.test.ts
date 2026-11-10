import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

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

async function renderFileFixture(
  identity: string,
  operation: (name: string, input: unknown) => Promise<unknown>,
) {
  initExtensionHostGlobalSdk();
  vi.stubGlobal("document", undefined);
  const source = await readFile(fixturePath, "utf8");
  const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#${identity}`) as DlcModule;
  const staged = createStagedExtensionHost("dbfox.workspace", {
    openDockTab: vi.fn(),
    invokeOperation: async <T,>(_owner: string, name: string, input: unknown) => await operation(name, input) as T,
  });
  await module.register?.(staged.host);
  vi.unstubAllGlobals();
  const renderView = (path: string) => React.createElement(React.Fragment, null, staged.getContributions().dockViews[0].render({
    viewKey: `${identity}:${path}`, viewType: "dbfox.workspace.file", title: path, projectId: "project-1", closeable: true,
    target: { type: "object", object: { kind: "dbfox.workspace.file", id: path, version: "digest" }, authority: { kind: "dbfox.workspace.root", id: "root-1" }, locator: path },
  }, { activeProjectId: "project-1", activeConversationId: null, workbenchScopeId: "scope", showToast: vi.fn(), onAsk: vi.fn() }));
  const rendering = render(renderView("记录.txt"));
  return (path: string) => rendering.rerender(renderView(path));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("dbfox.workspace System DLC frontend fixture", () => {
  it("retries an unreadable binding without treating it as an unbound folder", async () => {
    let attempts = 0;
    await renderFileFixture("binding-retry", async (name) => {
      if (name === "binding.get") {
        if (++attempts === 1) throw new Error("服务暂时不可用");
        return { binding: { id: "root-1", binding_generation: "digest", root_path: "D:/workspace" } };
      }
      if (name === "files.list") return { entries: [], truncated: false };
      if (name === "files.read") return { content: "已恢复读取", content_truncated: false, sha256: "a".repeat(64) };
      throw new Error(`Unexpected operation: ${name}`);
    });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "选择文件夹" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("已恢复读取")).toBeTruthy();
    expect(attempts).toBe(2);
  });

  it("refreshes both the directory and an already open file", async () => {
    let content = "旧版内容";
    let directoryReads = 0;
    const open = await renderFileFixture("refresh", async (name) => {
      if (name === "binding.get") return { binding: { id: "root-1", binding_generation: "digest", root_path: "D:/workspace" } };
      if (name === "files.list") { directoryReads++; return { entries: [], truncated: false }; }
      if (name === "files.read") return { content, content_truncated: false, sha256: "a".repeat(64) };
      throw new Error(`Unexpected operation: ${name}`);
    });
    expect(await screen.findByText("旧版内容")).toBeTruthy();
    open("记录.md");
    fireEvent.click(await screen.findByRole("button", { name: "源码" }));
    const before = directoryReads;
    content = "人工保存的新版内容";
    fireEvent.click(screen.getByRole("button", { name: "刷新文件" }));
    expect(await screen.findByText("人工保存的新版内容")).toBeTruthy();
    expect(screen.queryByText("旧版内容")).toBeNull();
    expect(directoryReads).toBeGreaterThan(before);
    expect(screen.getByRole("button", { name: "源码" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("preserves the read prefix on conflict and recovers only after explicit refresh", async () => {
    let fresh = false;
    const reads: unknown[] = [];
    await renderFileFixture("pagination-conflict", async (name, input) => {
      if (name === "binding.get") return { binding: { id: "root-1", binding_generation: "digest", root_path: "D:/workspace" } };
      if (name === "files.list") return { entries: [], truncated: false };
      if (name === "files.read") {
        reads.push(input);
        if (fresh) return { content: "重新读取后的内容", content_truncated: false, sha256: "b".repeat(64) };
        return { content: (input as { offset?: number }).offset ? "禁止拼接的新版本" : "旧版😀", content_truncated: true,
          sha256: ((input as { offset?: number }).offset ? "b" : "a").repeat(64) };
      }
      throw new Error(`Unexpected operation: ${name}`);
    });
    fireEvent.click(await screen.findByRole("button", { name: "继续读取" }));
    expect((await screen.findByRole("alert")).textContent).toContain("文件已变更");
    expect(screen.getByText("旧版😀")).toBeTruthy();
    expect(screen.queryByText(/禁止拼接的新版本/)).toBeNull();
    expect(reads).toEqual([{ path: "记录.txt" }, { path: "记录.txt", offset: 3 }]);
    fresh = true;
    fireEvent.click(screen.getByRole("button", { name: "刷新文件" }));
    expect(await screen.findByText("重新读取后的内容")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(reads).toHaveLength(3);
  });

  it("discards a pagination response that arrives after a fresh read", async () => {
    let fresh = false;
    let resolvePage!: (value: unknown) => void;
    await renderFileFixture("late-pagination", async (name, input) => {
      if (name === "binding.get") return { binding: { id: "root-1", binding_generation: "digest", root_path: "D:/workspace" } };
      if (name === "files.list") return { entries: [], truncated: false };
      if (name === "files.read") {
        if ((input as { offset?: number }).offset) return new Promise(resolve => { resolvePage = resolve; });
        return { content: fresh ? "当前版本" : "旧版", content_truncated: !fresh, sha256: (fresh ? "b" : "a").repeat(64) };
      }
      throw new Error(`Unexpected operation: ${name}`);
    });
    fireEvent.click(await screen.findByRole("button", { name: "继续读取" }));
    await waitFor(() => expect(resolvePage).toBeTypeOf("function"));
    fresh = true;
    fireEvent.click(screen.getByRole("button", { name: "刷新文件" }));
    expect(await screen.findByText("当前版本")).toBeTruthy();
    await act(async () => resolvePage({ content: "迟到的旧分页", content_truncated: false, sha256: "a".repeat(64) }));
    expect(screen.getByText("当前版本")).toBeTruthy();
    expect(screen.queryByText(/迟到的旧分页/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reads each canonical file target without a second file identity cache", async () => {
    const opened: string[] = [];
    const open = await renderFileFixture("canonical-target", async (name, input) => {
      if (name === "binding.get") return { binding: { id: "root-1", binding_generation: "digest", root_path: "D:/workspace" } };
      if (name === "files.list") return { entries: [], truncated: false };
      if (name === "files.read") {
        const path = (input as { path: string }).path;
        opened.push(path);
        return { content: path === "记录.txt" ? "第一份文件" : "第二份文件", content_truncated: false, sha256: "a".repeat(64) };
      }
      throw new Error(`Unexpected operation: ${name}`);
    });
    expect(await screen.findByText("第一份文件")).toBeTruthy();
    open("另一份.txt");
    expect(await screen.findByText("第二份文件")).toBeTruthy();
    expect(screen.queryByText("第一份文件")).toBeNull();
    expect(opened).toEqual(["记录.txt", "另一份.txt"]);
  });

  it.each([0, 1])("opens saved Markdown through its versioned representation (%s)", async (index) => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#preview-${index}`) as DlcModule;
    const staged = createStagedExtensionHost("dbfox.workspace");
    await module.register?.(staged.host);
    vi.unstubAllGlobals();
    const view = staged.getContributions().artifactViews[index];
    const payload = { relativePath: "发布清单.md", sha256: "a".repeat(64), newSha256: "a".repeat(64),
      sizeBytes: 40, created: true, workspaceId: "root-1", workspaceVersion: "digest" };
    const artifact = { id: "saved-markdown", session_id: "session-1", title: "发布清单.md",
      type: index === 0 ? "dbfox.workspace.file_snapshot" : "dbfox.workspace.code_patch", payload };
    const read = vi.fn().mockResolvedValue({ payload: { content: "# 发布前必须完成\n\nCSV 导出和草稿自动保存。", content_truncated: false } });
    render(React.createElement(React.Fragment, null, view.render(artifact, payload, {
      surface: "workspace", onToast: vi.fn(), representations: { available: [], list: vi.fn(), read, stream: vi.fn() },
    })));

    expect(await screen.findByRole("heading", { name: "发布前必须完成" })).toBeTruthy();
    expect(screen.getByText("CSV 导出和草稿自动保存。")).toBeTruthy();
    expect(read).toHaveBeenCalledWith("saved-markdown", "dbfox.workspace.file.v1", { operation: "read" }, expect.any(AbortSignal));
  });

  it("continues bounded Unicode reads without skipping characters and shares the exact file reference", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#unicode`) as DlcModule;
    const reads: unknown[] = [];
    const binding = { id: "root-1", binding_generation: "digest", root_path: "D:/workspace" };
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
