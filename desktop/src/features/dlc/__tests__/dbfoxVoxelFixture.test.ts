import { readFile } from "node:fs/promises";
import { createHash, webcrypto } from "node:crypto";
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
  loadSnapshot(access: { read: (...args: unknown[]) => Promise<unknown> }, id: string, payload: World, signal?: AbortSignal): Promise<Snapshot>;
  snapshotFile(snapshot: Snapshot, id: string): Blob;
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

// Independent fixture encoding of the published canonical JSON/hash contract.
// Never import a product fingerprint implementation to create expected bytes.
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
function pin<T extends { document: unknown; content_hash: string; chunk_count: number; nonzero_count: number }>(world: T, chunks: Chunk[]): T {
  const live = chunks.filter(chunk => chunk.values !== null).sort((a, b) => a.layer_id < b.layer_id ? -1 : a.layer_id > b.layer_id ? 1
    : a.coord[0] - b.coord[0] || a.coord[1] - b.coord[1] || a.coord[2] - b.coord[2]);
  const hash = createHash("sha256").update(canonical(world.document));
  for (const chunk of live) hash.update(`\n${canonical([chunk.layer_id, ...chunk.coord, chunk.hash])}`);
  return { ...world, content_hash: `sha256:${hash.digest("hex")}`, chunk_count: live.length,
    nonzero_count: live.reduce((sum, chunk) => sum + chunk.values!.filter(Boolean).length, 0) };
}

function makeWorld(version = 1) {
  return pin({
    world_id: "world_fixture", project_id: "p1", version, parent_version: version > 1 ? version - 1 : null,
    title: "狐狸神社", status: "active", size: [16, 16, 16], content_hash: `hash-${version}`,
    chunk_count: 1, nonzero_count: 1, layer_count: 2, palette_count: 3, region_count: 0,
    document: { schema_version: 1, size: [16, 16, 16], title: "狐狸神社", status: "active",
      layers: [{ id: "base", name: "Base", locked: false }, { id: "roof", name: "Roof", locked: false }],
      palette: [{ index: 0, name: "Air", color: "#000000" }, { index: 1, name: "Stone", color: "#64748b" }, { index: 2, name: "Pink", color: "#f472b6" }],
      regions: [] as { id: string; name: string; bounds: Bounds }[], metadata: { description: "", tags: [] as string[] } },
  }, [chunk()]);
}
function chunk(layer = "base", point = [1, 2, 3], color = 1): Chunk {
  const values = Array<number>(4096).fill(0);
  values[point[0] + 16 * point[2] + 256 * point[1]] = color;
  return { layer_id: layer, coord: [0, 0, 0], hash: `sha256:${createHash("sha256").update(Uint8Array.from(values)).digest("hex")}`, values };
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
  vi.stubGlobal("crypto", webcrypto);
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
  current = pin(current, [chunk()]);
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
      current = pin(next, [chunk()]);
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
  it("independently loads an Artifact through only its fixed representation and exports all layers", async () => {
    const world = pin(makeWorld(4), [chunk(), chunk("roof", [1, 2, 3], 2)]);
    const read = vi.fn(async (_id: unknown, _type: unknown, request: unknown) => {
      const operation = (request as { operation: string }).operation;
      return { representation_type: "dbfox.voxel.world.v1", representation_version: 1, operation,
        consistency: "durable_snapshot", source_version: "4", source_fingerprint: world.content_hash,
        payload: operation === "manifest" ? world : page(world, [chunk(), chunk("roof", [1, 2, 3], 2)]) };
    });
    const snapshot = await data.loadSnapshot({ read }, "artifact-fixed", world);
    expect(read.mock.calls.map((call) => (call[2] as { operation: string }).operation)).toEqual(["manifest", "chunks"]);
    expect(read.mock.calls.every((call) => call[0] === "artifact-fixed" && call[1] === "dbfox.voxel.world.v1")).toBe(true);
    expect(snapshot.world.version).toBe(4);
    await data.composeVisible(snapshot, new Set(["roof"]));
    const blob = data.snapshotFile(snapshot, "artifact-fixed");
    const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(blob); });
    const exported = JSON.parse(content);
    expect(exported.artifact_id).toBe("artifact-fixed");
    expect(exported.manifest.version).toBe(4);
    expect(exported.chunks).toHaveLength(2);
    expect(exported.chunks[1].values[561]).toBe(2);
  });
  it.each(["source_version", "source_fingerprint", "representation_type", "consistency", "project_id", "missing_chunks"])("rejects inconsistent immutable representation %s", async (fault) => {
    const world = makeWorld(4);
    const read = async (_id: unknown, _type: unknown, request: unknown) => {
      const operation = (request as { operation: string }).operation;
      const result: Record<string, unknown> = { representation_type: "dbfox.voxel.world.v1", representation_version: 1, operation,
        consistency: "durable_snapshot", source_version: "4", source_fingerprint: world.content_hash,
        payload: operation === "manifest" ? {...world, ...(fault === "project_id" ? {project_id:"other-project"} : {})} : page(world, fault === "missing_chunks" ? [] : [chunk()]) };
      if (!["project_id", "missing_chunks"].includes(fault)) result[fault] = "invalid";
      return result;
    };
    await expect(data.loadSnapshot({ read }, "artifact-fixed", world)).rejects.toThrow();
  });
  it("rejects a late immutable chunk response after cancellation without publishing a snapshot", async () => {
    const world=makeWorld(4); const controller=new AbortController();
    let release: ((value: unknown) => void) | undefined;
    const envelope=(operation: string, payload: unknown)=>({representation_type:"dbfox.voxel.world.v1",representation_version:1,operation,
      consistency:"durable_snapshot",source_version:"4",source_fingerprint:world.content_hash,payload});
    const read=vi.fn(async (_id:unknown,_type:unknown,request:unknown)=>{
      const operation=(request as {operation:string}).operation;
      if(operation==="manifest")return envelope(operation,world);
      return new Promise(resolve=>{release=resolve;});
    });
    const pending=data.loadSnapshot({read},"artifact-fixed",world,controller.signal);
    const rejected=expect(pending).rejects.toMatchObject({name:"AbortError"});
    await waitFor(()=>expect(read).toHaveBeenCalledTimes(2));
    controller.abort(); release?.(envelope("chunks",page(world,[chunk()])));
    await rejected;
  });
  it("decodes x + 16*z + 256*y and composes visible layers bottom to top", async () => {
    const world = pin(makeWorld(), [chunk(), chunk("roof", [1, 2, 3], 2)]);
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
    const current = pin(makeWorld(2), [chunk("roof", [3, 2, 1], 2)]);
    const invoke = vi.fn<Invoke>(async (name, input) => name === "worlds.get" ? current : input.after
      ? page(current, [chunk("roof", [3, 2, 1], 2)], 1) : page(current, [{ ...chunk(), hash: `sha256:${createHash("sha256").update(new Uint8Array(4096)).digest("hex")}`, values: null }], 1, "opaque-next"));
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
  it("rejects missing Host navigation before creating any durable snapshot", async () => {
    const fixture = await setup({ navigation: false });
    fireEvent.click(screen.getByRole("button", { name: "保存快照" }));
    await screen.findByText(/当前 Host 尚不支持从工作台打开成果/);
    expect(fixture.openArtifact).not.toHaveBeenCalled();
    expect(fixture.calls.filter((call) => call.name === "worlds.snapshot")).toHaveLength(0);
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
  it.each([false, true])("removes native keyboard listeners on view unmount (Control held: %s)", async (controlHeld) => {
    const listeners: { target: EventTarget; type: string; listener: EventListenerOrEventListenerObject | null; capture: boolean }[] = [];
    const add = EventTarget.prototype.addEventListener;
    const remove = EventTarget.prototype.removeEventListener;
    const capture = (options?: boolean | EventListenerOptions) => typeof options === "boolean" ? options : Boolean(options?.capture);
    vi.spyOn(EventTarget.prototype, "addEventListener").mockImplementation(function (this: EventTarget, type, listener, options) {
      if (["keydown", "keyup"].includes(type) && (this instanceof HTMLCanvasElement || this instanceof Document)) {
        listeners.push({ target: this, type, listener, capture: capture(options) });
      }
      add.call(this, type, listener, options);
    });
    vi.spyOn(EventTarget.prototype, "removeEventListener").mockImplementation(function (this: EventTarget, type, listener, options) {
      const index = listeners.findIndex((entry) => entry.target === this && entry.type === type && entry.listener === listener && entry.capture === capture(options));
      if (index >= 0) listeners.splice(index, 1);
      remove.call(this, type, listener, options);
    });
    const fixture = await setup();
    const canvas = screen.getByLabelText(/^体素三维视口/);
    if (controlHeld) fireEvent.keyDown(canvas, { key: "Control" });
    fixture.rendered.unmount();
    const remaining = listeners.map(({ target, type }) => ({ target: target instanceof Document ? "document" : "canvas", type }));
    // Remove failed-run listeners so this regression does not pollute later tests.
    for (const entry of listeners) remove.call(entry.target, entry.type, entry.listener, entry.capture);
    expect(remaining).toEqual([]);
  });
});

describe("Independent final adversarial generation crossover", () => {
  it.each(["write", "snapshot"])("drops a late %s across scope change, deactivation and registration", async kind => {
    const old = await setup({ hold: kind === "write", holdSnapshot: kind === "snapshot" });
    fireEvent.click(screen.getByRole("button", { name: kind === "write" ? "应用到选区" : "保存快照" }));
    const operation = kind === "write" ? "worlds.apply" : "worlds.snapshot";
    await waitFor(() => expect(old.calls.filter(call => call.name === operation)).toHaveLength(1));
    const signal = old.calls.find(call => call.name === operation)!.options!.signal!;
    old.changeScope("replacement-scope");
    old.rendered.unmount();
    await module.deactivate?.();
    const oldCalls = old.calls.length;
    const fresh = await setup();
    expect(signal.aborted).toBe(true);
    const freshCalls = fresh.calls.length;
    await act(async () => old.release());
    expect(old.calls).toHaveLength(oldCalls);
    expect(fresh.calls).toHaveLength(freshCalls);
    expect(old.openArtifact).not.toHaveBeenCalled();
    expect(fresh.openArtifact).not.toHaveBeenCalled();
    expect(fresh.calls.some(call => ["worlds.apply", "worlds.snapshot"].includes(call.name))).toBe(false);
    expect(screen.getByText(/16 × 16 × 16.*v1/)).not.toBeNull();
    expect(evidence.disposed).toBe(1);
    expect(evidence.lost).toBe(1);
  });
});
