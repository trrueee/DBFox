import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule } from "../types";

const frontend = resolve(process.cwd(), "../dlcs/dbfox.scene/frontend");
type Input = Record<string, unknown>;
type Node = { id: string; name: string; kind: string; parent_id: string | null; position: number[]; rotation: number[]; scale: number[]; visible: boolean; geometry_id?: string; material_id?: string | null };
const cube = (id = "cube", parent_id: string | null = null): Node => ({ id, name: id === "cube" ? "Cube" : id, kind: "mesh", parent_id, position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1], visible: true, geometry_id: "geometry.box", material_id: null });
type Callback = (...args: unknown[]) => unknown;
let sequence = 0;
let modules: DlcModule[] = [];

afterEach(async () => {
  cleanup();
  for (const module of modules) await module.deactivate?.();
  modules = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function fixture(options: { objects?: Node[]; reject?: boolean; deferred?: boolean; deferredExport?: boolean; missingNavigation?: boolean; styles?: boolean } = {}) {
  initExtensionHostGlobalSdk();
  let version = 7;
  let objects = options.objects || [cube()];
  let reject = options.reject || false;
  let release: (() => void) | undefined;
  const onAsk = vi.fn();
  const openArtifact = vi.fn(async () => undefined);
  const view = { update: vi.fn(), select: vi.fn(), setEnabled: vi.fn(), setMode: vi.fn(), setCamera: vi.fn(), focus: vi.fn(), dispose: vi.fn() };
  let callbacks: Record<string, Callback> = {};
  vi.stubGlobal("__sceneViewport", (_element: HTMLElement, values: Record<string, Callback>) => { callbacks = values; return view; });
  const summary = () => ({ id: "scene-1", project_id: "p1", title: "Test Scene", version, content_hash: "a".repeat(64), object_count: objects.length, material_count: 0 });
  const invoke = vi.fn(async (name: string, input: Input, signal?: AbortSignal): Promise<unknown> => {
    signal?.throwIfAborted();
    if (name === "scenes.list") return { scenes: [summary()], total: 1, offset: 0, limit: 100 };
    if (name === "scenes.get") {
      const section = input.section as string;
      const values = section === "objects" ? objects : section === "geometries" ? [{ id: "geometry.box", primitive: "box" }] : [];
      const offset = input.offset as number;
      return { scene: { ...summary(), version: input.version || version }, settings: { background: [0.025, 0.03, 0.04], default_camera_id: null },
        objects: [], materials: [], geometries: [], [section]: values.slice(offset, offset + 100), total: values.length, offset, limit: 100 };
    }
    if (name === "scenes.artifact") {
      if (options.deferredExport) await new Promise<void>((done) => { release = done; });
      return { artifact_id: "artifact-scene", run_id: "run-1", session_id: "export-session" };
    }
    if (name === "scenes.apply" || name === "scenes.undo") {
      if (options.deferred) await new Promise<void>((done) => { release = done; });
      if (reject) throw new Error("SCENE_STALE: version changed");
      expect(input.expected_version).toBe(version);
      version += 1;
      const operation = input.operation as Input | undefined;
      if (operation?.kind === "object_update") objects = objects.map((object) => object.id === operation.object_id ? { ...object, name: operation.name as string, visible: operation.visible as boolean } : object);
      return { scene: summary(), changed: true, changed_ids: ["cube"], truncated: false };
    }
    if (name === "scenes.create") return { scene: summary(), changed: true, changed_ids: [] };
    throw new Error(`Unexpected ${name}`);
  });
  const source = (await readFile(resolve(frontend, "index.js"), "utf8"))
    .replace('new URL("./index.css", import.meta.url).href', '"https://example.test/dbfox.scene/index.css"');
  const modelUrl = `data:text/javascript;base64,${Buffer.from(await readFile(resolve(frontend, "model.js"), "utf8")).toString("base64")}`;
  const viewportUrl = `data:text/javascript;base64,${Buffer.from("export const createViewport = (...args) => globalThis.__sceneViewport(...args);").toString("base64")}`;
  const url = `data:text/javascript;base64,${Buffer.from(source.replace('"./model.js"', JSON.stringify(modelUrl)).replace('"./viewport.js"', JSON.stringify(viewportUrl)) + `\n// fixture ${sequence++}`).toString("base64")}`;
  const module = await import(/* @vite-ignore */ url) as DlcModule;
  modules.push(module);
  const staged = createStagedExtensionHost("dbfox.scene", {
    invokeOperation: async <TOutput,>(_id: string, name: string, input: unknown, operationOptions?: { signal?: AbortSignal }) => invoke(name, input as Input, operationOptions?.signal) as Promise<TOutput>,
    openDockTab: vi.fn(), pickFolder: vi.fn(), pickFile: vi.fn(), readPickedFile: vi.fn(),
  });
  const pageDocument = document;
  if (!options.styles) vi.stubGlobal("document", undefined);
  await module.register?.({ ...staged.host, workbench: {
    currentScopeId: () => "scope-1", ...(options.missingNavigation ? {} : { openArtifact }),
  } });
  vi.stubGlobal("document", pageDocument);
  const dock = staged.getContributions().dockViews[0];
  const rendered = render(dock.render({ viewKey: "scene:p1", viewType: "dbfox.scene.workbench", title: "Scene", closeable: true, projectId: "p1", target: { type: "object", object: { kind: "dbfox.scene.document", id: "scene-1" } } },
    { activeProjectId: "p1", activeConversationId: null, showToast: vi.fn(), workbenchScopeId: "scope-1", onAsk }));
  await waitFor(() => expect(view.update).toHaveBeenCalled());
  await waitFor(() => expect((screen.getByRole("button", { name: "导出工件" }) as HTMLButtonElement).disabled).toBe(false));
  return { invoke, view, callbacks: () => callbacks, onAsk, openArtifact, staged, module, rendered,
    changeHead: (next: number, nodes = objects) => { version = next; objects = nodes; },
    reject: (next: boolean) => { reject = next; }, release: () => release?.() };
}

describe("dbfox.scene production frontend fixture", () => {
  it("replaces its stylesheet on same-module registration and removes it on deactivate", async () => {
    const { module } = await fixture({ styles: true });
    const selector = 'link[data-dbfox-dlc="dbfox.scene"]';
    const first = document.querySelector(selector);
    expect(first).toBeTruthy();
    await act(async () => {
      await module.register?.(createStagedExtensionHost("dbfox.scene").host);
    });
    expect(document.querySelectorAll(selector)).toHaveLength(1);
    expect(first?.isConnected).toBe(false);
    await act(async () => { await module.deactivate?.(); });
    expect(document.querySelectorAll(selector)).toHaveLength(0);
  });
  it("pins all object/material/geometry pages to the first observed revision", async () => {
    const { invoke, view } = await fixture({ objects: Array.from({ length: 205 }, (_, index) => cube(`node-${index}`)) });
    const reads = invoke.mock.calls.filter(([name]) => name === "scenes.get");
    expect(reads.map(([, input]) => [input.section, input.offset, input.version])).toEqual([
      ["objects", 0, undefined], ["objects", 100, 7], ["objects", 200, 7], ["materials", 0, 7], ["geometries", 0, 7],
    ]);
    expect(view.update.mock.calls.at(-1)?.[0].objects).toHaveLength(205);
    expect(screen.getByRole("tree", { name: "场景对象" })).toBeTruthy();
  });

  it("shares Tree selection with viewport, saves actual displayed CAS, and hands off exact authority", async () => {
    const { invoke, view, onAsk } = await fixture();
    fireEvent.click(screen.getByText("Cube"));
    await screen.findByLabelText("对象名称");
    expect(view.select).toHaveBeenLastCalledWith("cube");
    fireEvent.click(screen.getByRole("button", { name: "引用到 Agent" }));
    expect(onAsk).toHaveBeenCalledWith({ label: "Test Scene / Cube", authority: { kind: "dbfox.scene.document", id: "scene-1" }, object: { kind: "dbfox.scene.object", id: "cube", version: 7 }, locator: "/objects/cube" });
    fireEvent.change(screen.getByLabelText("对象名称"), { target: { value: "Edited cube" } });
    fireEvent.click(screen.getByRole("button", { name: "保存对象" }));
    await waitFor(() => expect(screen.getByLabelText("对象名称")).toHaveProperty("value", "Edited cube"));
    const request = invoke.mock.calls.find(([name]) => name === "scenes.apply")?.[1];
    expect(request).toMatchObject({ scene_id: "scene-1", expected_version: 7, operation: { kind: "object_update", object_id: "cube", name: "Edited cube", visible: true } });
    expect(request?.request_id).toEqual(expect.any(String));
    await screen.findByText("已保存 · v8");
  });

  it("keeps dirty input after stale failure, sends once, and refresh explicitly discards it", async () => {
    const { invoke } = await fixture({ reject: true });
    fireEvent.click(screen.getByText("Cube"));
    fireEvent.change(await screen.findByLabelText("位置 X"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "保存局部变换" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("位置 X")).toHaveProperty("value", "12");
    expect(invoke.mock.calls.filter(([name]) => name === "scenes.apply")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "放弃草稿并刷新" }));
    await waitFor(() => expect(screen.getByLabelText("位置 X")).toHaveProperty("value", "0"));
    expect(invoke.mock.calls.filter(([name]) => name === "scenes.apply")).toHaveLength(1);
  });

  it("commits one drag end and blocks reentrant writes until it settles; failure rolls viewport back", async () => {
    const { invoke, callbacks, view, release } = await fixture({ reject: true, deferred: true });
    await act(async () => { callbacks().onSelect("cube"); });
    await act(async () => { callbacks().onDragStart(); });
    expect(view.setEnabled).not.toHaveBeenLastCalledWith(false);
    await act(async () => {
      callbacks().onDragEnd({ object_id: "cube", position: [3, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] }, 7);
      callbacks().onDragEnd({ object_id: "cube", position: [4, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] }, 7);
    });
    expect(invoke.mock.calls.filter(([name]) => name === "scenes.apply")).toHaveLength(1);
    await act(async () => { release(); });
    await screen.findByRole("alert");
    expect(view.update.mock.calls.at(-1)?.[0].objects[0].position).toEqual([0, 0, 0]);
  });

  it("syncs external edits while clean and preserves dirty forms with a newer-version notice", async () => {
    const timers: Array<() => Promise<void>> = [];
    const originalTimeout = globalThis.setTimeout;
    vi.spyOn(globalThis, "setTimeout").mockImplementation(((handler: TimerHandler, delay?: number, ...args: unknown[]) => {
      if (delay === 5000 && typeof handler === "function") timers.push(handler as () => Promise<void>);
      return originalTimeout(handler, delay, ...args);
    }) as typeof setTimeout);
    const { changeHead, view } = await fixture();
    changeHead(8, [{ ...cube(), name: "Agent cube" }]);
    await act(async () => { await timers.at(-1)?.(); });
    expect(view.update.mock.calls.at(-1)?.[0].scene.version).toBe(8);
    fireEvent.click(screen.getByText("Agent cube"));
    fireEvent.change(await screen.findByLabelText("对象名称"), { target: { value: "Human draft" } });
    changeHead(9, [{ ...cube(), name: "Agent changed again" }]);
    await act(async () => { await timers.at(-1)?.(); });
    expect(screen.getByLabelText("对象名称")).toHaveProperty("value", "Human draft");
    expect(screen.getByText(/场景已有 v9/)).toBeTruthy();
    expect(view.update.mock.calls.at(-1)?.[0].scene.version).toBe(8);
  });

  it("releases viewport and pending read lifecycle on deactivate, and invokes the official Artifact action", async () => {
    const { invoke, view, module, onAsk, openArtifact } = await fixture();
    fireEvent.click(screen.getByRole("button", { name: "导出工件" }));
    await screen.findByRole("button", { name: "引用导出工件" });
    expect(invoke.mock.calls.find(([name]) => name === "scenes.artifact")?.[1]).toMatchObject({ scene_id: "scene-1", expected_version: 7, request_id: expect.any(String) });
    await waitFor(() => expect(openArtifact).toHaveBeenCalledWith({ projectId: "p1", sessionId: "export-session", runId: "run-1", artifactId: "artifact-scene" },
      { workbenchScopeId: "scope-1", signal: invoke.mock.calls.find(([name]) => name === "scenes.artifact")?.[2] }));
    fireEvent.click(screen.getByRole("button", { name: "引用导出工件" }));
    expect(onAsk.mock.calls.at(-1)?.[0]).toMatchObject({ artifactId: "artifact-scene", authority: { kind: "dbfox.scene.document", id: "scene-1" } });
    await act(async () => { await module.deactivate?.(); });
    expect(view.dispose).toHaveBeenCalled();
  });

  it("does not dispatch an export on a Host without Artifact navigation", async () => {
    const { invoke } = await fixture({ missingNavigation: true });
    fireEvent.click(screen.getByRole("button", { name: "导出工件" }));
    expect((await screen.findByRole("alert")).textContent).toContain("当前 Host 不支持打开导出工件");
    expect(invoke.mock.calls.filter(([name]) => name === "scenes.artifact")).toHaveLength(0);
  });

  it("aborts an in-flight export on unmount and cannot navigate after its late response", async () => {
    const { invoke, openArtifact, rendered, release } = await fixture({ deferredExport: true });
    fireEvent.click(screen.getByRole("button", { name: "导出工件" }));
    await waitFor(() => expect(invoke.mock.calls.some(([name]) => name === "scenes.artifact")).toBe(true));
    const signal = invoke.mock.calls.find(([name]) => name === "scenes.artifact")?.[2];
    rendered.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => { release(); });
    expect(openArtifact).not.toHaveBeenCalled();
  });

  it("uses clear_range for a removed light range", async () => {
    const light = { ...cube("light"), kind: "light", geometry_id: undefined, light_type: "spot", color: [1, 1, 1], intensity: 10, range: 20, inner_cone_angle: 0, outer_cone_angle: 0.7 };
    const { invoke } = await fixture({ objects: [light] });
    fireEvent.click(screen.getByText("light", { selector: ".dbfox-tree__label" }));
    fireEvent.change(await screen.findByLabelText("范围（空白为无限）"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存灯光" }));
    await waitFor(() => expect(invoke.mock.calls.some(([name]) => name === "scenes.apply")).toBe(true));
    const operation = invoke.mock.calls.find(([name]) => name === "scenes.apply")?.[1].operation;
    expect(operation).toMatchObject({ kind: "light_update", light_id: "light", clear_range: true });
    expect(operation).not.toHaveProperty("range");
  });

  it("downloads a fixed Artifact through the Host representation stream and releases its object URL", async () => {
    const { staged, rendered } = await fixture();
    rendered.unmount();
    const createObjectURL = vi.fn(() => "blob:scene-export");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL; });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const stream = vi.fn(async () => new Blob(["glTF"], { type: "model/gltf-binary" }));
    const artifactView = staged.getContributions().artifactViews[0];
    const payload = { scene_id: "scene-1", project_id: "p1", version: 7, title: "Fixed Scene", object_count: 1, material_count: 0 };
    const artifact = { id: "artifact-fixed", type: "dbfox.scene.revision", title: "Fixed Scene", payload };
    const shown = render(artifactView.render(artifact, artifactView.parsePayload(payload), { surface: "workspace", onToast: vi.fn(), representations: { available: [], list: vi.fn(), read: vi.fn(), stream } }));
    fireEvent.click(screen.getByRole("button", { name: "下载 GLB" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(stream).toHaveBeenCalledWith("artifact-fixed", "dbfox.scene.document.v1", { operation: "export_glb", parameters: {} }, expect.any(AbortSignal));
    shown.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:scene-export");
  });

  it("applies real Three hierarchy transforms, retains mesh/geometry on edits and disposes GPU resources", async () => {
    type RenderNode = { matrixWorld: { elements: number[] }; geometry: { dispose(): void }; material: { dispose(): void }; getObjectByName(name: string): RenderNode };
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((callback) => { frames.push(callback); return frames.length; });
    const disconnected = vi.fn();
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() { disconnected(); } });
    const canvas = document.createElement("canvas");
    const renderer = { domElement: canvas, setPixelRatio: vi.fn(), setSize: vi.fn(), render: vi.fn<(scene: RenderNode) => void>(), renderLists: { dispose: vi.fn() }, dispose: vi.fn(), forceContextLoss: vi.fn() };
    vi.stubGlobal("__sceneRenderer", renderer);
    const vendorUrl = `data:text/javascript;base64,${Buffer.from(await readFile(resolve(frontend, "vendor/three.js"), "utf8")).toString("base64")}`;
    const proxyUrl = `data:text/javascript;base64,${Buffer.from(`export * from ${JSON.stringify(vendorUrl)}; export class WebGLRenderer { constructor() { return globalThis.__sceneRenderer; } }`).toString("base64")}`;
    const viewportSource = (await readFile(resolve(frontend, "viewport.js"), "utf8")).replace('"./vendor/three.js"', JSON.stringify(proxyUrl));
    const viewportUrl = `data:text/javascript;base64,${Buffer.from(viewportSource).toString("base64")}`;
    const module = await import(/* @vite-ignore */ viewportUrl) as { createViewport(container: HTMLElement, callbacks: Record<string, Callback>): { update(snapshot: unknown): void; select(id: string): void; dispose(): void } };
    const container = document.createElement("div");
    document.body.append(container);
    const view = module.createViewport(container, { onSelect: vi.fn(), onDragEnd: vi.fn(), onError: vi.fn() });
    const snapshot = { scene: { id: "scene-1", version: 1 }, settings: { background: [0.02, 0.03, 0.04] },
      objects: [{ ...cube("parent"), kind: "group", position: [4, 0, 0], rotation: [0, Math.PI / 2, 0] }, { ...cube(), parent_id: "parent", position: [1, 0, 0] }],
      geometries: [{ id: "geometry.box", primitive: "box" }], materials: [] };
    view.update(snapshot);
    frames.shift()?.(0);
    const scene = renderer.render.mock.calls.at(-1)?.[0];
    expect(scene).toBeDefined();
    const mesh = scene!.getObjectByName("Cube");
    expect(mesh.matrixWorld.elements[12]).toBeCloseTo(4);
    expect(mesh.matrixWorld.elements[14]).toBeCloseTo(-1);
    const geometry = mesh.geometry;
    const disposeGeometry = vi.spyOn(geometry, "dispose");
    const disposeMaterial = vi.spyOn(mesh.material, "dispose");
    view.update({ ...snapshot, scene: { id: "scene-1", version: 2 }, objects: [snapshot.objects[0], { ...snapshot.objects[1], position: [2, 0, 0] }] });
    frames.shift()?.(0);
    expect(scene!.getObjectByName("Cube")).toBe(mesh);
    expect(mesh.geometry).toBe(geometry);
    expect(mesh.matrixWorld.elements[14]).toBeCloseTo(-2);
    expect(disposeGeometry).not.toHaveBeenCalled();
    view.dispose();
    view.dispose();
    expect(disposeGeometry).toHaveBeenCalledTimes(1);
    expect(disposeMaterial).toHaveBeenCalledTimes(1);
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    expect(disconnected).toHaveBeenCalledTimes(1);
    expect(container.children).toHaveLength(0);
    container.remove();
  });
});
