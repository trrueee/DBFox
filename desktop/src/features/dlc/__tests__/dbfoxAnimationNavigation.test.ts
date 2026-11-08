import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule } from "../types";

const frontend = resolve(process.cwd(), "../dlcs/dbfox.animation/frontend");
const dataUrl = (source: string) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
let module: DlcModule | undefined;
let sequence = 0;

afterEach(async () => {
  cleanup();
  await module?.deactivate?.();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function loadFrontend(playbackSource: string) {
  initExtensionHostGlobalSdk();
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
  const model = dataUrl(await readFile(resolve(frontend, "model.js"), "utf8"));
  const source = (await readFile(resolve(frontend, "index.js"), "utf8"))
    .replace('"./model.js"', JSON.stringify(model)).replace('"./playback.js"', JSON.stringify(dataUrl(playbackSource)))
    .replace('new URL("./index.css",import.meta.url).href', '"https://example.test/animation.css"');
  module = await import(/* @vite-ignore */ dataUrl(`${source}\n// navigation ${sequence++}`)) as DlcModule;
  return module;
}

describe("Animation library navigation", () => {
  it.each(["create", "select"])("opens a stable named object tab after %s", async (action) => {
    // This test stays in the library: constructing playback would be a regression.
    const module = await loadFrontend("export const createPlayback = () => { throw new Error('library started playback'); }; export const curveTrack = () => {}; export const advance = () => {};");
    const animation = { id: "animation-1", project_id: "p1", title: "Clock loop", version: 1 };
    const invoke = vi.fn(async (_owner: string, name: string) => {
      if (name === "animations.list") return { animations: [animation] };
      if (name === "animations.create") return { animation };
      throw new Error(`Library must not read a mutable document: ${name}`);
    });
    const staged = createStagedExtensionHost("dbfox.animation", { openDockTab: vi.fn(), invokeOperation: async <TOutput,>(owner: string, name: string) => invoke(owner, name) as Promise<TOutput> });
    const open = vi.fn();
    await module.register?.({ ...staged.host, dockViews: { ...staged.host.dockViews, open } });
    render(staged.getContributions().dockViews[0].render({ viewKey: "library", viewType: "dbfox.animation.workbench", title: "Animation Studio", projectId: "p1", closeable: true },
      { activeProjectId: "p1", activeConversationId: null, workbenchScopeId: "scope-1", showToast: vi.fn(), onAsk: vi.fn() }));
    await screen.findByRole("option", { name: "Clock loop · v1" });
    if (action === "create") {
      fireEvent.change(screen.getByLabelText("新动画名称"), { target: { value: "Clock loop" } });
      fireEvent.click(screen.getByRole("button", { name: "创建" }));
    } else fireEvent.change(screen.getByLabelText("动画"), { target: { value: "animation-1" } });
    await waitFor(() => expect(open).toHaveBeenCalledWith(expect.objectContaining({
      viewKey: "dbfox.animation.workbench:p1:animation-1", title: "Clock loop", projectId: "p1",
      target: { type: "object", object: { kind: "dbfox.animation.document", id: "animation-1" }, authority: { kind: "dbfox.animation.document", id: "animation-1" } },
    })));
  });

  it("keeps the current document mounted and editing locked until a save is read back", async () => {
    const module = await loadFrontend("export const createPlayback = () => ({start:0,end:6000,targets:new Map(),seek(){},dispose(){}}); export const curveTrack = () => {}; export const advance = () => {};");
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const context = { scale: vi.fn(), fillRect: vi.fn(), strokeRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fillText: vi.fn(), measureText: () => ({ width: 10 }) };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => context as unknown as CanvasRenderingContext2D);
    let version = 1, readStarted = false;
    let release = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const summary = () => ({ id: "animation-1", project_id: "p1", title: "Clock loop", version, content_hash: "a".repeat(64) });
    const invoke = vi.fn(async (_owner: string, name: string, input: unknown) => {
      if (name === "animations.list") return { animations: [summary()] };
      if (name === "animations.apply") { version = 2; return { animation: summary(), changed: true }; }
      if (name === "animations.get") {
        if (version === 2) { readStarted = true; await gate; }
        const section = (input as { section: string }).section;
        return { animation: summary(), timing: { duration: 6000, fps: 30, rate: 1, loop: true },
          items: section === "tracks" ? [{ id: "track", target_id: "target", name: "Angle", property: "rotation.z", enabled: true }] : section === "targets" ? [{ id: "target", name: "Clock" }] : [], has_more: false };
      }
      throw new Error(`Unexpected ${name}`);
    });
    const staged = createStagedExtensionHost("dbfox.animation", { openDockTab: vi.fn(), invokeOperation: async <TOutput,>(owner: string, name: string, input: unknown) => invoke(owner, name, input) as Promise<TOutput> });
    await module.register?.(staged.host);
    render(staged.getContributions().dockViews[0].render({ viewKey: "animation-1", viewType: "dbfox.animation.workbench", title: "Clock loop", projectId: "p1", closeable: true, target: { type: "object", object: { kind: "dbfox.animation.document", id: "animation-1" } } },
      { activeProjectId: "p1", activeConversationId: null, workbenchScopeId: "scope-1", showToast: vi.fn(), onAsk: vi.fn() }));
    const disclosure = (await screen.findByText("关键帧列表 · 0（键盘可操作）")).closest("details")!;
    fireEvent.click(disclosure.querySelector("summary")!);
    fireEvent.click(screen.getByRole("button", { name: "关键帧 +" }));
    await waitFor(() => expect(readStarted).toBe(true));
    expect(disclosure.isConnected).toBe(true);
    expect(disclosure.open).toBe(true);
    expect((screen.getByRole("button", { name: "关键帧 +" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { release(); });
    await waitFor(() => expect((screen.getByRole("button", { name: "关键帧 +" }) as HTMLButtonElement).disabled).toBe(false));
    expect(disclosure.isConnected).toBe(true);
    expect(disclosure.open).toBe(true);
    expect(invoke.mock.calls.filter(([, name]) => name === "animations.apply")).toHaveLength(1);
  });
});
