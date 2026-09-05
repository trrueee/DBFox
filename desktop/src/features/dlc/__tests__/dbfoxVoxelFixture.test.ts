import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule, DlcOperationInvokeOptions } from "../types";

type Bounds = { min: number[]; max: number[] };
type Chunk = { layer_id: string; coord: number[]; hash: string; values: number[] | null };
type World = ReturnType<typeof makeWorld>;
type Snapshot = { world: World; chunks: Map<string, Omit<Chunk, "values"> & { values: Uint8Array }> };
type Projection = { size: number[]; values: Uint8Array };
type Invoke = (name: string, input: Record<string, unknown>, signal?: AbortSignal) => Promise<unknown>;
interface DataModule {
  chunkOffset(x: number, y: number, z: number): number;
  volumeOffset(x: number, y: number, z: number, size: number[]): number;
  loadWorld(invoke: Invoke, id: string, options?: { previous?: Snapshot; signal?: AbortSignal }): Promise<Snapshot>;
  composeVisible(snapshot: Snapshot, hidden: Set<string>, signal?: AbortSignal): Promise<Projection>;
  surfaceInstances(projection: Projection, bounds?: Bounds | null, signal?: AbortSignal, maximum?: number): Promise<{ count: number; truncated: boolean; positions: Uint16Array }>;
  strokeBounds(axis: string, slice: number, start: number[], end: number[]): Bounds;
  voxelAt(chunks: Snapshot["chunks"], layer: string, point: number[]): number;
}
interface RendererEvidence { created: number; disposed: number; lost: number; renders: number }
const fixtureRoot = resolve(process.cwd(), "../dlcs/dbfox.voxel/frontend");
const moduleUrl = (source: string) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
let module: DlcModule;
let data: DataModule;
let evidence: RendererEvidence;

function makeWorld(version = 1) {
  return {
    world_id: "world_fixture", project_id: "p1", version, parent_version: version > 1 ? version - 1 : null,
    title: "狐狸神社", status: "active", size: [16, 16, 16], content_hash: `hash-${version}`,
    chunk_count: 1, nonzero_count: 1, layer_count: 2, palette_count: 3, region_count: 0,
    document: { schema_version: 1, size: [16, 16, 16], title: "狐狸神社", status: "active",
      layers: [{ id: "base", name: "Base", locked: false }, { id: "roof", name: "Roof", locked: false }],
      palette: [{ index: 0, name: "Air", color: "#000000" }, { index: 1, name: "Stone", color: "#64748b" }, { index: 2, name: "Pink", color: "#f472b6" }],
      regions: [] as { id: string; name: string; bounds: Bounds }[], metadata: { description: "", tags: [] as string[] } },
  };
}
function chunk(layer = "base", point = [1, 2, 3], color = 1): Chunk {
  const values = Array<number>(4096).fill(0);
  values[point[0] + 16 * point[2] + 256 * point[1]] = color;
  return { layer_id: layer, coord: [0, 0, 0], hash: "chunk", values };
}
function page(world: World, chunks: Chunk[], since: unknown = null, after: string | null = null) {
  return { world_id: world.world_id, version: world.version, since_version: since, chunks, next_after: after, metadata_changed: false };
}

beforeAll(async () => {
  // Actual Three geometry, matrices, instance attributes and OrbitControls run.
  // Only the browser's WebGL device is substituted; this is not a GPU visual test.
  const vendorUrl = moduleUrl(await readFile(resolve(fixtureRoot, "vendor/three.js"), "utf8"));
  const deviceUrl = moduleUrl(`export * from ${JSON.stringify(vendorUrl)};
    export class WebGLRenderer {
      constructor() { if(globalThis.__voxelRejectGpu) throw new Error('GPU unavailable'); this.domElement = document.createElement('canvas'); this.evidence = globalThis.__voxelRendererEvidence; this.evidence.created++; }
      setPixelRatio() {} setClearColor() {} setSize() {}
      render() { this.evidence.renders++; }
      dispose() { this.evidence.disposed++; }
      forceContextLoss() { this.evidence.lost++; }
    }`);
  const dataUrl = moduleUrl(await readFile(resolve(fixtureRoot, "world-data.js"), "utf8"));
  data = await import(/* @vite-ignore */ dataUrl) as DataModule;
  const viewportUrl = moduleUrl((await readFile(resolve(fixtureRoot, "viewport.js"), "utf8"))
    .replace('"./vendor/three.js"', JSON.stringify(deviceUrl)).replace('"./world-data.js"', JSON.stringify(dataUrl)));
  const entryUrl = moduleUrl((await readFile(resolve(fixtureRoot, "index.js"), "utf8"))
    .replace('"./viewport.js"', JSON.stringify(viewportUrl)).replace('"./world-data.js"', JSON.stringify(dataUrl)));
  module = await import(/* @vite-ignore */ entryUrl) as DlcModule;
});
beforeEach(() => {
  evidence = { created: 0, disposed: 0, lost: 0, renders: 0 };
  vi.stubGlobal("__voxelRendererEvidence", evidence);
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ({
    clearRect: vi.fn(), fillRect: vi.fn(), strokeRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(),
  }) as unknown as CanvasRenderingContext2D);
});
afterEach(async () => {
  cleanup();
  await module.deactivate?.();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function setup({ empty = false, locked = false, reject = false, hold = false, navigation = true, holdSnapshot = false } = {}) {
  let current = makeWorld();
  let readFailure = false;
  current.document.layers[0].locked = locked;
  const calls: { name: string; input: Record<string, unknown>; options?: DlcOperationInvokeOptions }[] = [];
  let release: (() => void) | undefined;
  const invokeOperation = async <TOutput,>(_owner: string, name: string, input: unknown, options?: DlcOperationInvokeOptions): Promise<TOutput> => {
    const request = input as Record<string, unknown>;
    calls.push({ name, input: request, options });
    if (name === "worlds.get") { if (readFailure) throw new Error("离线"); return structuredClone(current) as TOutput; }
    if (name === "worlds.list") return { worlds: [current], next_after: null } as TOutput;
    if (name === "worlds.chunks") return page(current, [chunk()], request.since_version) as TOutput;
    if (name === "worlds.revisions") return { revisions: [{ version: 1 }, { version: current.version }] } as TOutput;
    if (name === "worlds.create") return current as TOutput;
    if (name === "worlds.snapshot") {
      if (holdSnapshot) await new Promise<void>((resolve) => { release = resolve; });
      return { run_id: "run1", session_id: "s1", artifact_ids: ["a1"] } as TOutput;
    }
    if (["worlds.apply", "worlds.configure", "worlds.undo"].includes(name)) {
      if (hold) await new Promise<void>((resolve) => { release = resolve; });
      if (reject) { current = makeWorld(current.version + 1); throw new Error("STALE_VERSION: 世界已被修改"); }
      const next = makeWorld(current.version + 1);
      next.document = structuredClone(current.document);
      const operation = request.operation as { kind?: string; layer?: World["document"]["layers"][number] } | undefined;
      if (operation?.kind === "layer_put" && operation.layer) next.document.layers = next.document.layers.map((layer) => layer.id === operation.layer?.id ? operation.layer : layer);
      current = next;
      return { ...current, changed: true } as TOutput;
    }
    throw new Error(`Unexpected ${name}`);
  };
  initExtensionHostGlobalSdk();
  const staged = createStagedExtensionHost("dbfox.voxel", { invokeOperation, openDockTab: vi.fn() });
  const openArtifact = vi.fn(async () => undefined);
  const extensionHost = { ...staged.host, workbench: { currentScopeId: () => "scope1", ...(navigation ? { openArtifact } : {}) } };
  const savedDocument = document;
  vi.stubGlobal("document", undefined);
  await module.register?.(extensionHost);
  vi.stubGlobal("document", savedDocument);
  const context = { activeProjectId: "p1", activeConversationId: null, showToast: vi.fn(), workbenchScopeId: "scope1", onAsk: vi.fn() };
  const contributions = staged.getContributions();
  const view = { viewKey: "voxel-fixture", viewType: "dbfox.voxel.studio", title: "体素", projectId: "p1", closeable: true,
    ...(!empty ? { target: { type: "object" as const, object: { kind: "dbfox.voxel.world", id: current.world_id, version: 1 } } } : {}) };
  const rendered = render(contributions.dockViews[0].render(view, context));
  if (!empty) await ready();
  return { calls, context, contributions, rendered, openArtifact, release: () => release?.(),
    changeScope: (scope: string) => rendered.rerender(contributions.dockViews[0].render(view, { ...context, workbenchScopeId: scope })),
    failReads: (value: boolean) => { readFailure = value; }, externalEdit: () => { current = makeWorld(current.version + 1); } };
}
async function ready() {
  await waitFor(() => expect((screen.getByRole("button", { name: "应用到选区" }) as HTMLButtonElement).disabled).toBe(false));
}
function sliceCanvas() {
  const canvas = screen.getByRole("application", { name: /体素切片/ });
  vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 160, 160));
  return canvas;
}
function drag(canvas: HTMLElement) {
  fireEvent.pointerDown(canvas, { button: 0, clientX: 15, clientY: 145, pointerId: 1 });
  fireEvent.pointerMove(canvas, { clientX: 35, clientY: 125, pointerId: 1 });
  fireEvent.pointerUp(canvas, { clientX: 35, clientY: 125, pointerId: 1 });
}

describe("Voxel fixed-version projection", () => {
  it("decodes x + 16*z + 256*y and composes visible layers bottom to top", async () => {
    const world = makeWorld();
    const result = await data.loadWorld(async (name) => name === "worlds.get" ? world : page(world, [chunk(), chunk("roof", [1, 2, 3], 2)]), world.world_id);
    expect(data.chunkOffset(1, 2, 3)).toBe(561);
    expect(data.voxelAt(result.chunks, "base", [1, 2, 3])).toBe(1);
    expect(data.voxelAt(result.chunks, "base", [1, 3, 2])).toBe(0);
    const composed = await data.composeVisible(result, new Set());
    const hidden = await data.composeVisible(result, new Set(["roof"]));
    expect(composed.values[data.volumeOffset(1, 2, 3, world.size)]).toBe(2);
    expect(hidden.values[data.volumeOffset(1, 2, 3, world.size)]).toBe(1);
    expect(data.strokeBounds("x", 4, [3, 2], [1, 0])).toEqual({ min: [4, 0, 1], max: [5, 3, 4] });
  });
  it("reads all delta pages at one version, applies tombstones, and keeps previous state immutable", async () => {
    const world = makeWorld();
    const previous = await data.loadWorld(async (name) => name === "worlds.get" ? world : page(world, [chunk()]), world.world_id);
    const current = makeWorld(2);
    const invoke = vi.fn<Invoke>(async (name, input) => name === "worlds.get" ? current : input.after
      ? page(current, [chunk("roof", [3, 2, 1], 2)], 1) : page(current, [{ ...chunk(), values: null }], 1, "opaque-next"));
    const result = await data.loadWorld(invoke, world.world_id, { previous });
    expect(previous.chunks.has("base:0,0,0")).toBe(true);
    expect(result.chunks.has("base:0,0,0")).toBe(false);
    expect(result.chunks.has("roof:0,0,0")).toBe(true);
    expect(invoke.mock.calls.filter(([name]) => name === "worlds.chunks").map(([, input]) => input)).toEqual([
      { world_id: world.world_id, version: 2, since_version: 1, limit: 16, after: null },
      { world_id: world.world_id, version: 2, since_version: 1, limit: 16, after: "opaque-next" },
    ]);
  });
  it("rejects mixed revisions, repeated cursors and cancellation without publishing partial data", async () => {
    const world = makeWorld();
    await expect(data.loadWorld(async (name) => name === "worlds.get" ? world : { ...page(world, []), version: 2 }, world.world_id)).rejects.toThrow("版本不一致");
    await expect(data.loadWorld(async (name) => name === "worlds.get" ? world : page(world, [], null, "repeat"), world.world_id)).rejects.toThrow("游标重复");
    const abort = new AbortController();
    await expect(data.loadWorld(async (name) => {
      if (name === "worlds.get") return world;
      abort.abort(); return page(world, [chunk()]);
    }, world.world_id, { signal: abort.signal })).rejects.toMatchObject({ name: "AbortError" });
  });
  it("culls enclosed voxels, enforces the instance cap and bounds temporary crop input", async () => {
    const solid = { size: [3, 3, 3], values: new Uint8Array(27).fill(1) };
    expect((await data.surfaceInstances(solid)).count).toBe(26);
    expect(await data.surfaceInstances(solid, null, undefined, 5)).toMatchObject({ count: 5, truncated: true });
    expect((await data.surfaceInstances(solid, { min: [-999, -999, -999], max: [999, 999, 999] })).count).toBe(26);
  });
});

describe("Voxel Studio official Host fixture", () => {
  it("registers its connector, Dock and immutable Artifact card and creates once", async () => {
    const fixture = await setup({ empty: true });
    expect(fixture.contributions.connectors[0].id).toBe("dbfox.voxel");
    expect(fixture.contributions.artifactViews[0].id).toBe("dbfox.voxel.snapshot");
    fireEvent.change(screen.getByLabelText("世界名称"), { target: { value: "新神社" } });
    fireEvent.click(screen.getByRole("button", { name: "创建世界" }));
    await ready();
    const writes = fixture.calls.filter((call) => call.name === "worlds.create");
    expect(writes).toHaveLength(1);
    expect(writes[0].input).toMatchObject({ title: "新神社", size: [64, 64, 64], expected_version: 0, mutation_id: expect.any(String) });
    expect(writes[0].options?.projectId).toBe("p1");
  });
  it("submits one bounded rectangle per stroke with the selected material, layer and version", async () => {
    const fixture = await setup();
    fireEvent.click(screen.getByRole("button", { name: "Pink (2)" }));
    drag(sliceCanvas());
    await ready();
    const writes = fixture.calls.filter((call) => call.name === "worlds.apply");
    expect(writes).toHaveLength(1);
    expect(writes[0].input).toEqual({ world_id: "world_fixture", expected_version: 1, mutation_id: expect.any(String),
      operation: { kind: "fill", layer_id: "base", bounds: { min: [1, 0, 1], max: [4, 1, 4] }, palette_index: 2 } });
    expect(fixture.calls.find((call) => call.name === "worlds.chunks" && call.input.version === 2)?.input.since_version).toBe(1);
  });
  it("keeps selection and layer visibility local and gives onAsk only the world authority", async () => {
    const fixture = await setup();
    fireEvent.click(screen.getByRole("button", { name: "选择区域" }));
    drag(sliceCanvas());
    fireEvent.click(screen.getByRole("checkbox", { name: "显示 Roof" }));
    fireEvent.click(screen.getByRole("button", { name: "询问 DBFox" }));
    expect(fixture.calls.some((call) => ["worlds.apply", "worlds.configure"].includes(call.name))).toBe(false);
    expect(fixture.context.onAsk).toHaveBeenCalledWith({ label: "狐狸神社 · Base · 选区", authority: { kind: "dbfox.voxel.world", id: "world_fixture" },
      object: { kind: "dbfox.voxel.layer", id: "base", version: 1 }, locator: 'bounds={"min":[1,0,1],"max":[4,1,4]}' });
  });
  it("persists layer locking and prevents pointer and Delete edits while still permitting selection", async () => {
    const fixture = await setup();
    fireEvent.click(screen.getByRole("button", { name: "锁定 Base" }));
    await screen.findByText("当前层已锁定，仍可选择区域。解锁后可绘制。");
    expect(fixture.calls.find((call) => call.name === "worlds.configure")?.input).toMatchObject({ expected_version: 1,
      operation: { kind: "layer_put", layer: { id: "base", name: "Base", locked: true } } });
    drag(sliceCanvas());
    fireEvent.click(screen.getByRole("button", { name: "选择区域" }));
    fireEvent.keyDown(screen.getByRole("application"), { key: "Delete" });
    drag(screen.getByRole("application"));
    expect(fixture.calls.some((call) => call.name === "worlds.apply")).toBe(false);
  });
  it("blocks duplicate submissions and refreshes a stale rejection without replay", async () => {
    const fixture = await setup({ reject: true, hold: true });
    const apply = screen.getByRole("button", { name: "应用到选区" });
    fireEvent.click(apply); fireEvent.click(apply);
    expect(fixture.calls.filter((call) => call.name === "worlds.apply")).toHaveLength(1);
    await act(async () => fixture.release());
    await screen.findByText(/修改未确认/);
    await ready();
    expect(fixture.calls.filter((call) => call.name === "worlds.apply")).toHaveLength(1);
    expect(screen.getByText(/16 × 16 × 16.*v2/)).not.toBeNull();
  });
  it("keeps manual refresh available after a read failure while blocking stale edits", async () => {
    const fixture = await setup();
    fixture.failReads(true);
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await screen.findByRole("alert");
    expect((screen.getByRole("button", { name: "应用到选区" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "刷新" }) as HTMLButtonElement).disabled).toBe(false);
    fixture.failReads(false);
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await ready();
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("opens only the returned durable Artifact through the captured Host scope", async () => {
    const fixture = await setup();
    fireEvent.click(screen.getByRole("button", { name: "保存快照" }));
    await screen.findByText("不可变世界快照已保存并打开。");
    expect(fixture.openArtifact).toHaveBeenCalledWith({ projectId: "p1", sessionId: "s1", runId: "run1", artifactId: "a1" },
      { workbenchScopeId: "scope1", signal: expect.any(AbortSignal) });
    const snapshotCall = fixture.calls.find((call) => call.name === "worlds.snapshot");
    expect(snapshotCall?.input).toMatchObject({ version: 1, mutation_id: expect.any(String) });
    expect(fixture.openArtifact.mock.calls[0]).toEqual([{ projectId: "p1", sessionId: "s1", runId: "run1", artifactId: "a1" },
      { workbenchScopeId: "scope1", signal: snapshotCall?.options?.signal }]);
  });
  it("states the Host navigation limitation without private Artifact loading or replay", async () => {
    const fixture = await setup({ navigation: false });
    fireEvent.click(screen.getByRole("button", { name: "保存快照" }));
    await screen.findByText("快照已保存。当前 Host 尚不支持从工作台打开成果。");
    expect(fixture.openArtifact).not.toHaveBeenCalled();
    expect(fixture.calls.filter((call) => call.name === "worlds.snapshot")).toHaveLength(1);
  });
  it.each(["unmount", "scope"])("cancels snapshot navigation after %s even when export responds late", async (change) => {
    const fixture = await setup({ holdSnapshot: true });
    fireEvent.click(screen.getByRole("button", { name: "保存快照" }));
    await waitFor(() => expect(fixture.calls.some((call) => call.name === "worlds.snapshot")).toBe(true));
    const signal = fixture.calls.find((call) => call.name === "worlds.snapshot")?.options?.signal;
    if (change === "unmount") fixture.rendered.unmount();
    else {
      fixture.changeScope("scope2");
      fixture.changeScope("scope1");
    }
    expect(signal?.aborted).toBe(true);
    await act(async () => { fixture.release(); });
    expect(fixture.openArtifact).not.toHaveBeenCalled();
    expect(fixture.calls.filter((call) => call.name === "worlds.snapshot")).toHaveLength(1);
  });
  it("provides an editable slice when WebGL is unavailable and cancels abandoned pointer strokes", async () => {
    vi.stubGlobal("__voxelRejectGpu", true);
    const fixture = await setup();
    expect(await screen.findByText(/三维预览暂不可用/)).not.toBeNull();
    const canvas = sliceCanvas();
    fireEvent.pointerDown(canvas, { button: 0, clientX: 15, clientY: 145 });
    fireEvent.pointerCancel(canvas);
    fireEvent.pointerUp(canvas, { clientX: 35, clientY: 125 });
    expect(fixture.calls.some((call) => call.name === "worlds.apply")).toBe(false);
    fireEvent.keyDown(canvas, { key: " ", repeat: true });
    expect(fixture.calls.some((call) => call.name === "worlds.apply")).toBe(false);
    fireEvent.keyDown(canvas, { key: " " });
    await ready();
    expect(fixture.calls.filter((call) => call.name === "worlds.apply")).toHaveLength(1);
  });
  it("refreshes external edits, restores a parent revision and releases Three resources on deactivation", async () => {
    const fixture = await setup();
    fixture.externalEdit();
    fireEvent(window, new Event("focus"));
    await screen.findByText(/16 × 16 × 16.*v2/);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "撤销到 v1" }));
    await ready();
    expect(fixture.calls.find((call) => call.name === "worlds.undo")?.input).toMatchObject({ expected_version: 2, target_version: 1 });
    expect(evidence.created).toBe(1);
    await act(async () => module.deactivate?.());
    expect(evidence.disposed).toBe(1);
    expect(evidence.lost).toBe(1);
    const count = fixture.calls.length;
    fireEvent(window, new Event("focus"));
    expect(fixture.calls).toHaveLength(count);
    expect(fixture.calls.filter((call) => call.options?.signal).every((call) => call.options?.signal?.aborted)).toBe(true);
  });
});
