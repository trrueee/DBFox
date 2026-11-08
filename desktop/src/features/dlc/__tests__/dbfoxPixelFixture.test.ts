import { readFile } from "node:fs/promises";
import "@testing-library/jest-dom/vitest";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule, DlcOperationInvokeOptions } from "../types";
import type { ArtifactRepresentationAccess, ArtifactEnvelope } from "../../../../../sdk/frontend";

type Frame = { id: string; duration_ms: number; cels: { layer_id: string; pixels: number[] }[] };
type Doc = ReturnType<typeof makeDocument>;
type Call = { name: string; input: Record<string, unknown>; options?: DlcOperationInvokeOptions };
type Operation = Record<string, unknown> & { kind: string };
interface Model {
  composite(document: Doc, frame: Frame): Uint8Array;
  readFrame(invoke: (name: string, input: unknown, signal?: AbortSignal) => Promise<unknown>, snapshot: unknown, frameId: string, signal?: AbortSignal): Promise<Frame>;
}
const root = resolve(process.cwd(), "../dlcs/dbfox.pixel/frontend");
const moduleUrl = (source: string) => `data:text/javascript;base64,${Buffer.from(source + "\n//# sourceURL=pixel-fixture-module.js").toString("base64")}`;
let module: DlcModule;
let model: Model;
let canvas: { fillRect: ReturnType<typeof vi.fn>; clearRect: ReturnType<typeof vi.fn>; imageSmoothingEnabled: boolean };
let animation: Map<number, FrameRequestCallback>;
let nextAnimation: number;
let createdUrls: ReturnType<typeof vi.fn<() => string>>;
let revokedUrls: ReturnType<typeof vi.fn<(url: string) => void>>;

function makeDocument(): { schema_version: number; title: string; canvas: { width: number; height: number }; palette: { name: string; color: string }[]; layers: { id: string; name: string; visible: boolean; locked: boolean }[]; frames: Frame[]; tags: { id: string; name: string; frame_ids: string[]; loop: boolean }[] } {
  return { schema_version: 1, title: "狐狸骑士", canvas: { width: 8, height: 8 }, palette: [{ name: "Transparent", color: "#00000000" }, { name: "Ink", color: "#181825FF" }, { name: "Orange", color: "#E58A38FF" }],
    layers: [{ id: "layer_1", name: "轮廓", visible: true, locked: false }, { id: "layer_2", name: "铠甲", visible: true, locked: false }],
    frames: [1, 2].map((id) => ({ id: `frame_${id}`, duration_ms: id === 1 ? 100 : 200, cels: [1, 2].map((layer) => ({ layer_id: `layer_${layer}`, pixels: Array.from({ length: 64 }, (_, i) => i === id + layer ? layer : 0) })) })),
    tags: [{ id: "idle", name: "Idle", frame_ids: ["frame_2", "frame_1"], loop: false }] };
}
function summary(document: Doc, revision = 1, documentId = "pixel_fixture") {
  return { project_id: "p1", document_id: documentId, revision, parent_revision: revision > 1 ? revision - 1 : null, content_hash: revision.toString(16).padStart(64, "0"), title: document.title,
    width: document.canvas.width, height: document.canvas.height, frame_count: document.frames.length, layer_count: document.layers.length, palette_count: document.palette.length, tag_count: document.tags.length, status: "active" };
}
function metadata(document: Doc) { return { ...document, frames: document.frames.map(({ id, duration_ms }) => ({ id, duration_ms })) }; }

beforeAll(async () => {
  const modelUrl = moduleUrl(await readFile(resolve(root, "model.js"), "utf8"));
  model = await import(/* @vite-ignore */ modelUrl) as Model;
  const source = (await readFile(resolve(root, "index.js"), "utf8")).replace('"./model.js"', JSON.stringify(modelUrl)).replace('new URL("./index.css", import.meta.url).href', '"https://example.test/pixel/index.css"');
  module = await import(/* @vite-ignore */ moduleUrl(source)) as DlcModule;
});
beforeEach(() => {
  class PixelPointerEvent extends MouseEvent { pointerId: number; constructor(type: string, options: PointerEventInit = {}) { super(type, options); this.pointerId = options.pointerId || 1; } }
  vi.stubGlobal("PointerEvent", PixelPointerEvent);
  const captures = new WeakMap<Element, number>();
  Object.defineProperty(HTMLCanvasElement.prototype, "setPointerCapture", { configurable: true, value(id: number) { captures.set(this, id); } });
  Object.defineProperty(HTMLCanvasElement.prototype, "hasPointerCapture", { configurable: true, value(id: number) { return captures.get(this) === id; } });
  Object.defineProperty(HTMLCanvasElement.prototype, "releasePointerCapture", { configurable: true, value() { captures.delete(this); } });
  canvas = { fillRect: vi.fn(), clearRect: vi.fn(), imageSmoothingEnabled: true };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ({ ...canvas, save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), strokeRect: vi.fn(), setLineDash: vi.fn() }) as unknown as CanvasRenderingContext2D);
  animation = new Map(); nextAnimation = 0;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { animation.set(++nextAnimation, callback); return nextAnimation; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => animation.delete(id));
  createdUrls = vi.fn(() => `blob:pixel-${createdUrls.mock.calls.length}`); revokedUrls = vi.fn();
  vi.stubGlobal("URL", class extends URL { static createObjectURL = createdUrls; static revokeObjectURL = revokedUrls; });
});
afterEach(async () => {
  cleanup(); await module.deactivate?.(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  delete (HTMLCanvasElement.prototype as Partial<HTMLCanvasElement>).setPointerCapture;
  delete (HTMLCanvasElement.prototype as Partial<HTMLCanvasElement>).hasPointerCapture;
  delete (HTMLCanvasElement.prototype as Partial<HTMLCanvasElement>).releasePointerCapture;
});

async function setup(options: { empty?: boolean; locked?: boolean; reject?: boolean; hold?: string; navigation?: boolean; frameMismatch?: boolean; huge?: boolean; frameCount?: number; exportFailure?: boolean; navigationFailure?: boolean } = {}) {
  let doc = makeDocument(), revision = 1, scope = "scope1", released: (() => void) | undefined;
  let holdNext: string | undefined;
  if (options.locked) doc.layers[0].locked = true;
  if (options.frameCount) doc.frames = Array.from({ length: options.frameCount }, (_, index) => ({ ...structuredClone(doc.frames[0]), id: `frame_${index + 1}` }));
  if (options.huge) {
    doc.canvas = { width: 128, height: 128 };
    doc.frames = Array.from({ length: 8 }, (_, i) => ({ id: `frame_${i + 1}`, duration_ms: 100, cels: doc.layers.map((layer) => ({ layer_id: layer.id, pixels: Array<number>(16384).fill(0) })) }));
  }
  const history = new Map<number, Doc>([[1, structuredClone(doc)]]);
  const calls: Call[] = [];
  const invokeOperation = async <TOutput,>(_owner: string, name: string, input: unknown, operationOptions?: DlcOperationInvokeOptions): Promise<TOutput> => {
    const request = input as Record<string, unknown>; calls.push({ name, input: structuredClone(request), options: operationOptions });
    if (name === options.hold || name === holdNext) {
      holdNext = undefined;
      await new Promise<void>((resolve) => { released = resolve; });
    }
    if (name === "documents.list") return { documents: [summary(doc, revision)], has_more: false } as TOutput;
    if (name === "documents.head") return { document_id: "pixel_fixture", revision, content_hash: summary(doc, revision).content_hash, status: "active" } as TOutput;
    if (name === "documents.get") { const at = request.revision as number || revision; const stored = history.get(at)!; return { summary: summary(stored, at), document: metadata(stored) } as TOutput; }
    if (name === "frames.read") { const at = request.revision as number, stored = history.get(at)!; return { document_id: "pixel_fixture", revision: options.frameMismatch ? at + 1 : at, content_hash: summary(stored, at).content_hash, canvas: stored.canvas, palette: stored.palette, frame: stored.frames.find((frame) => frame.id === request.frame_id) } as TOutput; }
    if (name === "documents.revisions") return { revisions: [...history.entries()].reverse().map(([version, item]) => summary(item, version)), next_before_revision: null } as TOutput;
    if (name === "documents.export") { if (options.exportFailure) throw new Error("PIXEL_EXPORT_UNKNOWN"); return { session_id: "s1", run_id: "run1", artifact_ids: ["artifact1"] } as TOutput; }
    if (name === "documents.create") return { ...summary(doc), changed: true } as TOutput;
    if (name === "documents.delete") return { ...summary(doc, revision + 1), status: "deleted", changed: true } as TOutput;
    if (["documents.apply", "documents.undo", "documents.restore"].includes(name)) {
      if (options.reject) { revision++; history.set(revision, structuredClone(doc)); throw new Error("PIXEL_CONFLICT: 当前版本已被修改"); }
      if (request.expected_version !== revision) throw new Error("PIXEL_CONFLICT");
      doc = structuredClone(doc);
      if (name === "documents.undo") doc = structuredClone(history.get(request.restore_revision as number)!);
      // Typed transport fixture: only enough committed responses to drive UI transitions;
      // canonical drawing, transaction and locking algorithms are exercised by backend tests.
      for (const op of (request.operations || []) as Operation[]) {
        const frame = doc.frames.find((item) => item.id === op.frame_id), layer = doc.layers.find((item) => item.id === op.layer_id);
        if (op.kind === "layer_update") Object.assign(layer!, Object.fromEntries(Object.entries(op).filter(([key]) => !["kind", "layer_id"].includes(key))));
        if (op.kind === "layer_create") { doc.layers.push({ id: op.layer_id as string, name: op.name as string, locked: false, visible: true }); for (const item of doc.frames) item.cels.push({ layer_id: op.layer_id as string, pixels: Array<number>(64).fill(0) }); }
        if (op.kind === "layer_delete") { doc.layers = doc.layers.filter((item) => item.id !== op.layer_id); for (const item of doc.frames) item.cels = item.cels.filter((cel) => cel.layer_id !== op.layer_id); }
        if (op.kind === "frame_update") frame!.duration_ms = op.duration_ms as number || frame!.duration_ms;
        if (op.kind === "frame_duplicate" || op.kind === "frame_create") { const source = structuredClone(doc.frames.find((item) => item.id === op.source_frame_id) || doc.frames[0]); source.id = op.frame_id as string; doc.frames.splice(op.position as number, 0, source); }
        if (op.kind === "frame_delete") { doc.frames = doc.frames.filter((item) => item.id !== op.frame_id); doc.tags = doc.tags.map((tag) => ({ ...tag, frame_ids: tag.frame_ids.filter((id) => id !== op.frame_id) })).filter((tag) => tag.frame_ids.length); }
        if (op.kind === "palette_set") doc.palette[op.index as number] = { name: op.name as string, color: op.color as string };
        if (op.kind === "tag_set") { doc.tags = doc.tags.filter((tag) => tag.id !== op.tag_id); doc.tags.push({ id: op.tag_id as string, name: op.name as string, frame_ids: op.frame_ids as string[], loop: op.loop as boolean }); }
        if (op.kind === "tag_delete") doc.tags = doc.tags.filter((tag) => tag.id !== op.tag_id);
      }
      revision++; history.set(revision, structuredClone(doc));
      return { ...summary(doc, revision), changed: true } as TOutput;
    }
    throw new Error(`Unexpected operation ${name}`);
  };
  initExtensionHostGlobalSdk();
  const openDock = vi.fn<(view: object) => void>();
  const staged = createStagedExtensionHost("dbfox.pixel", { invokeOperation, openDockTab: openDock });
  const openArtifact = vi.fn(async () => { if (options.navigationFailure) throw new Error("Navigation unavailable"); });
  const extensionHost = { ...staged.host, workbench: { currentScopeId: () => scope, ...(options.navigation === false ? {} : { openArtifact }) } };
  await module.register?.(extensionHost);
  const contributions = staged.getContributions();
  const context = { activeProjectId: "p1", activeConversationId: null, showToast: vi.fn(), workbenchScopeId: scope, onAsk: vi.fn() };
  const view = { viewKey: "pixel-fixture", viewType: "dbfox.pixel.studio", title: "Pixel", projectId: "p1", closeable: true,
    ...(!options.empty ? { target: { type: "object" as const, object: { kind: "dbfox.pixel.document", id: "pixel_fixture" } } } : {}) };
  const rendered = render(contributions.dockViews[0].render(view, context));
  if (!options.empty && !options.frameMismatch && options.hold !== "documents.get") await ready();
  return { calls, context, contributions, rendered, extensionHost, openArtifact, openDock, view, doc: () => doc, release: () => released?.(),
    holdNext: (name: string) => { holdNext = name; },
    changeScope: (value: string) => { scope = value; rendered.rerender(contributions.dockViews[0].render(view, { ...context, workbenchScopeId: scope })); },
    externalEdit: () => { revision++; doc = structuredClone(doc); doc.title = "Agent 新版本"; history.set(revision, structuredClone(doc)); },
  };
}
async function ready() { await waitFor(() => expect((screen.getByRole("button", { name: "导出成果" }) as HTMLButtonElement).disabled).toBe(false)); }
function pixelCanvas() {
  const item = screen.getByRole("application", { name: /像素画布/ });
  vi.spyOn(item, "getBoundingClientRect").mockReturnValue(new DOMRect(10, 20, 80, 80));
  return item;
}
function gesture(element = pixelCanvas(), end = { x: 3, y: 4 }) {
  fireEvent.pointerDown(element, { pointerId: 7, button: 0, clientX: 25, clientY: 45 });
  fireEvent.pointerMove(element, { pointerId: 7, clientX: 10 + end.x * 10 + 5, clientY: 20 + end.y * 10 + 5 });
  fireEvent.pointerUp(element, { pointerId: 7, clientX: 10 + end.x * 10 + 5, clientY: 20 + end.y * 10 + 5 });
}
function writes(calls: Call[]) { return calls.filter((call) => call.name === "documents.apply"); }
async function clickSave(label: string) { fireEvent.click(screen.getByRole("button", { name: label })); await ready(); }
async function tick(time: number) { await act(async () => { const entries = [...animation.entries()]; animation.clear(); for (const [, callback] of entries) callback(time); }); }

describe("Pixel immutable frontend projection", () => {
  it("pages hundreds of timeline thumbnails and edits the final frame by its stable identity", async () => {
    const { calls } = await setup({ frameCount: 256 });
    expect(screen.getAllByRole("button", { name: /^选择第 \d+ 帧$/ })).toHaveLength(32);
    expect(screen.queryByRole("button", { name: "选择第 256 帧" })).toBeNull();
    fireEvent.change(screen.getByLabelText("跳转帧页"), { target: { value: "7" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "选择第 256 帧" })).toBeEnabled());
    expect(screen.getAllByRole("button", { name: /^选择第 \d+ 帧$/ })).toHaveLength(32);
    fireEvent.click(screen.getByRole("button", { name: "选择第 256 帧" }));
    fireEvent.change(screen.getByLabelText("帧时长 ms"), { target: { value: "180" } });
    await clickSave("设置帧时长");
    expect(writes(calls)).toHaveLength(1);
    expect(writes(calls)[0].input.operations).toEqual([{ kind: "frame_update", frame_id: "frame_256", duration_ms: 180 }]);
    expect(screen.getByRole("button", { name: "选择第 256 帧" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "新建帧" })).toBeDisabled();
  });
  it("composes only visible nontransparent layers in canonical order", () => {
    const document = makeDocument(); document.frames[0].cels[0].pixels[0] = 1; document.frames[0].cels[1].pixels[0] = 2;
    expect(model.composite(document, document.frames[0])[0]).toBe(2);
    document.layers[1].visible = false;
    expect(model.composite(document, document.frames[0])[0]).toBe(1);
    expect(model.composite(document, document.frames[0])[63]).toBe(0);
  });
  it("rejects mixed frame revisions instead of rendering mismatched pixels", async () => {
    await setup({ frameMismatch: true });
    expect(await screen.findByRole("alert")).toHaveTextContent("帧与文档版本不一致");
    expect(screen.queryByRole("application")).toBeNull();
  });
  it("creates documents with strict integers and unique mutation identity, then opens the real canvas", async () => {
    const fixture = await setup({ empty: true });
    await screen.findByText("项目作品");
    fireEvent.change(screen.getByLabelText("宽度"), { target: { value: "32" } });
    fireEvent.click(screen.getByRole("button", { name: "创建像素作品" }));
    await waitFor(() => expect(fixture.openDock).toHaveBeenCalledOnce());
    expect(fixture.calls.find((call) => call.name === "documents.create")?.input).toMatchObject({ width: 32, height: 32, expected_version: 0, title: "狐狸骑士", mutation_id: expect.stringMatching(/^pixel_/) });
    expect(fixture.openDock).toHaveBeenCalledOnce();
    const opened = fixture.openDock.mock.calls[0][0] as typeof fixture.view;
    expect(opened.title).toBe("狐狸骑士");
    expect(opened.target).toMatchObject({ type: "object", object: { kind: "dbfox.pixel.document", id: "pixel_fixture" } });
    fixture.rendered.unmount();
    render(fixture.contributions.dockViews[0].render(opened, fixture.context));
    await ready();
    expect(screen.getByRole("application")).toBeInTheDocument();
  });
  it("commits one atomic stroke using down-time frame/layer/revision and scaled coordinates", async () => {
    const { calls } = await setup(); const element = pixelCanvas();
    fireEvent.pointerDown(element, { pointerId: 7, button: 0, clientX: 25, clientY: 45 });
    expect(screen.getByText("临时笔迹 · 未提交")).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(0);
    fireEvent.pointerMove(element, { pointerId: 7, clientX: 45, clientY: 65 });
    fireEvent.pointerUp(element, { pointerId: 7, clientX: 45, clientY: 65 });
    await ready();
    expect(writes(calls)).toHaveLength(1);
    expect(writes(calls)[0].input).toMatchObject({ document_id: "pixel_fixture", expected_version: 1, operations: [{ kind: "line", frame_id: "frame_1", layer_id: "layer_1", palette_index: 1, x0: 1, y0: 2, x1: 3, y1: 4 }] });
    expect(calls.filter((call) => call.name === "frames.read").slice(-2).every((call) => call.input.revision === 2)).toBe(true);
    expect(screen.queryByText("临时笔迹 · 未提交")).toBeNull();
  });
  it.each(["pointerCancel", "lostPointerCapture"] as const)("discards unfinished strokes on %s without any mutation", async (event) => {
    const { calls } = await setup(); const element = pixelCanvas();
    fireEvent.pointerDown(element, { pointerId: 7, button: 0, clientX: 25, clientY: 45 });
    fireEvent[event](element, { pointerId: 7 }); fireEvent.pointerUp(element, { pointerId: 7 });
    expect(writes(calls)).toHaveLength(0); expect(screen.queryByText("临时笔迹 · 未提交")).toBeNull();
  });
  it("rejects the entire overlong gesture rather than truncating a committed stroke", async () => {
    const { calls } = await setup(); const element = pixelCanvas();
    fireEvent.pointerDown(element, { pointerId: 7, button: 0, clientX: 25, clientY: 45 });
    for (let index = 0; index < 130; index++) fireEvent.pointerMove(element, { pointerId: 7, clientX: index % 2 ? 25 : 35, clientY: 45 });
    fireEvent.pointerUp(element, { pointerId: 7, clientX: 35, clientY: 45 });
    expect(writes(calls)).toHaveLength(0); expect(screen.getByRole("alert")).toHaveTextContent("超过 128 段");
  });
  it("supports eraser, flood and rectangle through their exact typed operations", async () => {
    const { calls } = await setup();
    fireEvent.click(screen.getByRole("button", { name: "橡皮 E" })); gesture(); await ready();
    expect((writes(calls).at(-1)?.input.operations as Operation[])[0].palette_index).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "填充 F" })); gesture(); await ready();
    expect(writes(calls).at(-1)?.input.operations).toEqual([{ kind: "fill", frame_id: "frame_1", layer_id: "layer_1", palette_index: 1, x: 1, y: 2 }]);
    fireEvent.click(screen.getByRole("button", { name: "矩形 R" })); gesture(); await ready();
    expect(writes(calls).at(-1)?.input.operations).toEqual([{ kind: "rect", frame_id: "frame_1", layer_id: "layer_1", palette_index: 1, rect: { x: 1, y: 2, width: 3, height: 3 }, filled: true }]);
  });
  it("locks painting/deletion but permits selecting a precise parent-authorized Agent reference", async () => {
    const { calls, context } = await setup({ locked: true }); gesture(); expect(writes(calls)).toHaveLength(0);
    expect(screen.getByRole("button", { name: "删除当前帧" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "选区 V" })); gesture();
    fireEvent.click(screen.getByRole("button", { name: "交给 Agent" }));
    expect(context.onAsk).toHaveBeenCalledWith({ label: expect.stringContaining("3×3 选区"), authority: { kind: "dbfox.pixel.document", id: "pixel_fixture" }, object: { kind: "dbfox.pixel.frame", id: "frame_1", version: "1" }, locator: "pixel://pixel_fixture;revision=1;frame=frame_1;layer=layer_1;rect=1,2,3,3" });
  });
  it("uses strict region move/rotation contracts and explicit clipping", async () => {
    const { calls } = await setup(); fireEvent.click(screen.getByRole("button", { name: "选区 V" })); gesture();
    fireEvent.change(screen.getByLabelText("目标 X"), { target: { value: "4" } });
    fireEvent.click(screen.getByLabelText("裁掉目标越界像素")); await clickSave("应用区域变换");
    expect(writes(calls).at(-1)?.input.operations).toEqual([{ kind: "region_transform", frame_id: "frame_1", layer_id: "layer_1", rect: { x: 1, y: 2, width: 3, height: 3 }, transform: "translate", destination: { x: 4, y: 2 }, mode: "move", clip: true }]);
    gesture(); await clickSave("顺时针旋转");
    expect((writes(calls).at(-1)?.input.operations as Operation[])[0]).toMatchObject({ transform: "rotate_cw", mode: "move", clip: false });
  });
  it("edits palette/layer structure against successive committed revisions", async () => {
    const { calls } = await setup();
    fireEvent.change(screen.getByLabelText("颜色名称"), { target: { value: "狐棕" } }); await clickSave("保存颜色");
    expect(writes(calls)[0].input.operations).toEqual([{ kind: "palette_set", index: 1, name: "狐棕", color: "#181825FF" }]);
    await clickSave("锁定图层 轮廓"); expect(screen.getByRole("button", { name: "解锁图层 轮廓" })).toBeInTheDocument();
    await clickSave("隐藏图层 铠甲"); expect(screen.getByRole("button", { name: "显示图层 铠甲" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("添加图层", { selector: "summary" })); await clickSave("创建图层");
    expect(writes(calls).at(-1)?.input).toMatchObject({ expected_version: 4, operations: [{ kind: "layer_create", layer_id: expect.stringMatching(/^layer_/), name: "新图层", position: 2 }] });
  });
  it("edits frame duration, duplicates with fresh identity and makes deletion of tagged frames explicit", async () => {
    const { calls } = await setup();
    fireEvent.change(screen.getByLabelText("帧时长 ms"), { target: { value: "160" } }); await clickSave("设置帧时长");
    expect(writes(calls)[0].input.operations).toEqual([{ kind: "frame_update", frame_id: "frame_1", duration_ms: 160 }]);
    await clickSave("复制当前帧"); expect(screen.getByRole("button", { name: "选择第 3 帧" })).toBeInTheDocument();
    expect((writes(calls).at(-1)?.input.operations as Operation[])[0]).toMatchObject({ kind: "frame_duplicate", source_frame_id: "frame_1", frame_id: expect.stringMatching(/^frame_/), position: 1 });
    expect(screen.getByRole("button", { name: "删除当前帧" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText("删除时从动画标签移除")); await clickSave("删除当前帧");
    expect((writes(calls).at(-1)?.input.operations as Operation[])[0]).toEqual({ kind: "frame_delete", frame_id: "frame_1", remove_from_tags: true });
  });
  it("preserves explicit animation-tag order and durations, and stops nonloop playback without writes", async () => {
    const { calls } = await setup(); await waitFor(() => expect(screen.getByRole("button", { name: "播放动画" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("播放动画标签"), { target: { value: "idle" } });
    fireEvent.click(screen.getByRole("button", { name: "播放动画" }));
    await tick(0); expect(screen.getByRole("img", { name: "动画预览 frame_2" })).toBeInTheDocument();
    await tick(199); expect(screen.getByRole("img", { name: "动画预览 frame_2" })).toBeInTheDocument();
    await tick(200); expect(screen.getByRole("img", { name: "动画预览 frame_1" })).toBeInTheDocument();
    await tick(300); expect(screen.getByRole("button", { name: "播放动画" })).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(0); expect(animation.size).toBe(0);
    fireEvent.click(screen.getByText("动画标签 (1/16)", { selector: "summary" }));
    fireEvent.change(screen.getByLabelText("编辑动画标签"), { target: { value: "idle" } });
    fireEvent.click(screen.getByRole("button", { name: "前移标签中的帧 1" })); await clickSave("保存动画标签");
    expect((writes(calls).at(-1)?.input.operations as Operation[])[0]).toMatchObject({ kind: "tag_set", tag_id: "idle", frame_ids: ["frame_1", "frame_2"], loop: false });
  });
  it("does not hijack text inputs and allows keyboard pixel positioning and undo", async () => {
    const { calls } = await setup(); const input = screen.getByLabelText("颜色名称");
    fireEvent.keyDown(input, { key: "e" }); expect(screen.getByRole("button", { name: "画笔 B" })).toHaveAttribute("aria-pressed", "true");
    const element = pixelCanvas(); fireEvent.keyDown(element, { key: "e" }); expect(screen.getByRole("button", { name: "橡皮 E" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(element, { key: "ArrowRight" }); fireEvent.keyDown(element, { key: "Enter" }); await ready();
    expect((writes(calls)[0].input.operations as Operation[])[0]).toMatchObject({ palette_index: 0, x0: 1, y0: 0, x1: 1, y1: 0 });
    fireEvent.keyDown(screen.getByLabelText("颜色名称"), { key: "z", ctrlKey: true }); expect(calls.some((call) => call.name === "documents.undo")).toBe(false);
    fireEvent.keyDown(pixelCanvas(), { key: "z", ctrlKey: true }); await ready();
    expect(calls.find((call) => call.name === "documents.undo")?.input).toMatchObject({ expected_version: 2, restore_revision: 1 });
  });
  it("clears a conflicting draft, reads committed head and never retries the mutation", async () => {
    const { calls } = await setup({ reject: true }); gesture(); await ready();
    expect(writes(calls)).toHaveLength(1); expect(screen.getByRole("alert")).toHaveTextContent("PIXEL_CONFLICT");
    expect(screen.getByRole("alert")).toHaveTextContent("未自动重发"); expect(screen.getByText(/已提交状态/)).toBeInTheDocument();
    expect(calls.filter((call) => call.name === "documents.get").at(-1)?.input).toEqual({ document_id: "pixel_fixture" });
    expect(screen.queryByText("临时笔迹 · 未提交")).toBeNull();
  });
  it("polls only lightweight head then synchronizes a new immutable revision", async () => {
    const fixture = await setup(); fixture.externalEdit(); vi.useFakeTimers();
    // Existing real timer was already installed; hide/show explicitly restarts the visibility-bound polling effect.
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" }); fireEvent(document, new Event("visibilitychange"));
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); fireEvent(document, new Event("visibilitychange"));
    await act(async () => { await vi.advanceTimersByTimeAsync(1001); });
    expect(fixture.calls.some((call) => call.name === "documents.head")).toBe(true);
    expect(screen.getByText("Agent 新版本")).toBeInTheDocument(); expect(writes(fixture.calls)).toHaveLength(0);
    vi.useRealTimers();
  });
  it("disables structural growth at the total pixel budget", async () => {
    await setup({ huge: true });
    expect(screen.getByRole("button", { name: "新建帧" })).toBeDisabled(); expect(screen.getByRole("button", { name: "创建图层" })).toBeDisabled();
    expect(screen.getByText("262,144 / 262,144 像素槽")).toBeInTheDocument();
  });
  it("keeps a manual read locked when an idle background poll finishes", async () => {
    const fixture = await setup(); vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" }); fireEvent(document, new Event("visibilitychange"));
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); fireEvent(document, new Event("visibilitychange"));
    fixture.holdNext("documents.get");
    fireEvent.click(screen.getByRole("button", { name: /^刷新$/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1001); });
    expect(screen.getByRole("button", { name: "导出成果" })).toBeDisabled();
    expect(screen.getByRole("application")).toHaveAttribute("aria-disabled", "true");
    await act(async () => fixture.release());
    expect(screen.getByRole("button", { name: "导出成果" })).toBeEnabled();
  });
  it("does not discard a live stroke when an older background head read returns", async () => {
    const fixture = await setup({ hold: "documents.head" }); fixture.externalEdit(); vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" }); fireEvent(document, new Event("visibilitychange"));
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); fireEvent(document, new Event("visibilitychange"));
    await act(async () => { await vi.advanceTimersByTimeAsync(1001); });
    expect(fixture.calls.filter((call) => call.name === "documents.head")).toHaveLength(1);
    const element = pixelCanvas() as HTMLCanvasElement;
    fireEvent.pointerDown(element, { pointerId: 7, button: 0, clientX: 25, clientY: 45 });
    expect(element.hasPointerCapture(7)).toBe(true);
    await act(async () => fixture.release());
    expect(element.hasPointerCapture(7)).toBe(true);
    expect(screen.getByText("临时笔迹 · 未提交")).toBeInTheDocument();
    expect(fixture.calls.filter((call) => call.name === "documents.get")).toHaveLength(1);
    fireEvent.pointerCancel(element, { pointerId: 7 });
    expect(writes(fixture.calls)).toHaveLength(0);
  });
  it("checks missing Host navigation before export and passes one captured signal across successful export/navigation", async () => {
    const missing = await setup({ navigation: false }); fireEvent.click(screen.getByRole("button", { name: "导出成果" }));
    expect(missing.calls.some((call) => call.name === "documents.export")).toBe(false); expect(screen.getByRole("alert")).toHaveTextContent("尚未创建导出 Run");
    missing.rendered.unmount();
    const fixture = await setup(); fireEvent.click(screen.getByRole("button", { name: "导出成果" })); await ready();
    const exported = fixture.calls.find((call) => call.name === "documents.export")!;
    expect(fixture.openArtifact).toHaveBeenCalledWith({ projectId: "p1", sessionId: "s1", runId: "run1", artifactId: "artifact1" }, { workbenchScopeId: "scope1", signal: exported.options?.signal });
  });
  it.each(["unmount", "scope", "deactivate"] as const)("aborts export on %s and ignores a late success", async (change) => {
    const fixture = await setup({ hold: "documents.export" }); fireEvent.click(screen.getByRole("button", { name: "导出成果" }));
    const call = fixture.calls.find((item) => item.name === "documents.export")!;
    if (change === "unmount") fixture.rendered.unmount(); else if (change === "scope") fixture.changeScope("scope2"); else await act(async () => module.deactivate?.());
    expect(call.options?.signal?.aborted).toBe(true); await act(async () => fixture.release());
    expect(fixture.openArtifact).not.toHaveBeenCalled(); expect(fixture.calls.filter((item) => item.name === "documents.export")).toHaveLength(1);
  });
  it("blocks replacement exports when a result is unknown and only reopens known exported identities after navigation failure", async () => {
    const unknown = await setup({ exportFailure: true }); fireEvent.click(screen.getByRole("button", { name: "导出成果" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "导出待查证" })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "导出待查证" })); expect(unknown.calls.filter((call) => call.name === "documents.export")).toHaveLength(1);
    unknown.rendered.unmount();
    const known = await setup({ navigationFailure: true }); fireEvent.click(screen.getByRole("button", { name: "导出成果" })); await ready();
    fireEvent.click(screen.getByRole("button", { name: "打开已导出成果" }));
    await waitFor(() => expect(known.openArtifact).toHaveBeenCalledTimes(2));
    expect(known.calls.filter((call) => call.name === "documents.export")).toHaveLength(1);
  });
  it("ignores late writes after scope change, resets local view state and cancels playback", async () => {
    const fixture = await setup({ hold: "documents.apply" });
    fireEvent.click(screen.getByRole("button", { name: "橡皮 E" })); gesture();
    const call = writes(fixture.calls)[0]; fixture.changeScope("scope2"); expect(call.options?.signal?.aborted).toBe(true);
    await act(async () => fixture.release()); await ready();
    expect(screen.getByRole("button", { name: "画笔 B" })).toHaveAttribute("aria-pressed", "true"); expect(writes(fixture.calls)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "播放动画" })); expect(animation.size).toBe(1);
    fixture.rendered.unmount(); expect(animation.size).toBe(0);
  });
  it("releases active pointer capture immediately on deactivate, even before Host removes the component", async () => {
    const fixture = await setup(); const element = pixelCanvas() as HTMLCanvasElement;
    fireEvent.pointerDown(element, { pointerId: 7, button: 0, clientX: 25, clientY: 45 }); expect(element.hasPointerCapture(7)).toBe(true);
    await act(async () => module.deactivate?.());
    expect(element.hasPointerCapture(7)).toBe(false); expect(screen.queryByText("临时笔迹 · 未提交")).toBeNull();
    fireEvent.pointerUp(element, { pointerId: 7, clientX: 35, clientY: 45 }); expect(writes(fixture.calls)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "交给 Agent" })); expect(fixture.context.onAsk).not.toHaveBeenCalled();
  });
  it("aborts initial reads and never fetches pixels after an unmounted metadata response", async () => {
    const fixture = await setup({ hold: "documents.get" }); fixture.rendered.unmount();
    expect(fixture.calls[0].options?.signal?.aborted).toBe(true); await act(async () => fixture.release());
    expect(fixture.calls.some((call) => call.name === "frames.read")).toBe(false);
  });
  it("re-registers one owned stylesheet, deactivates prior component effects and removes styles on teardown", async () => {
    const fixture = await setup(); const old = document.querySelector('[data-dbfox-dlc="dbfox.pixel"]');
    await act(async () => module.register?.({ ...fixture.extensionHost, connectors: { register: vi.fn() }, dockViews: { ...fixture.extensionHost.dockViews, register: vi.fn() }, artifactViews: { register: vi.fn() } }));
    expect(document.querySelectorAll('[data-dbfox-dlc="dbfox.pixel"]')).toHaveLength(1); expect(old?.isConnected).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "导出成果" })); expect(fixture.calls.some((call) => call.name === "documents.export")).toBe(false);
    await act(async () => module.deactivate?.()); expect(document.querySelectorAll('[data-dbfox-dlc="dbfox.pixel"]')).toHaveLength(0);
  });
});

describe("Pixel immutable Artifact view", () => {
  it("reads only public fixed-revision representations and streams real download blobs", async () => {
    const fixture = await setup(); fixture.rendered.unmount(); const doc = makeDocument(), payload = summary(doc);
    const representation: ArtifactRepresentationAccess = {
      available: [], list: vi.fn(async () => []),
      read: vi.fn(async (_id, _type, request) => ({ representation_type: "dbfox.pixel.sprite.v1", representation_version: 1, operation: request.operation, consistency: "durable_snapshot" as const, read_at: "now", read_id: "read", source_version: "1", source_fingerprint: payload.content_hash,
        payload: request.operation === "sheet_layout" ? { width: 16, height: 8, frames: doc.frames.map((frame, index) => ({ frame_id: frame.id, x: index * 8, y: 0, width: 8, height: 8, duration_ms: frame.duration_ms })) } : { items: doc.tags } })),
      stream: vi.fn(async () => new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" })),
    };
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const contribution = fixture.contributions.artifactViews[0], artifact: ArtifactEnvelope = { id: "artifact1", type: "dbfox.pixel.revision", title: "狐狸骑士", payload };
    const rendered = render(contribution.render(artifact, contribution.parsePayload(payload), { representations: representation, onToast: vi.fn(), surface: "workspace" }));
    await screen.findByRole("img", { name: /固定 r1/ });
    fixture.externalEdit(); fireEvent.click(screen.getByRole("button", { name: "下载 Sprite Sheet" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(representation.stream).toHaveBeenLastCalledWith("artifact1", "dbfox.pixel.sprite.v1", { operation: "sheet", parameters: {} }, expect.any(AbortSignal));
    expect(fixture.calls.some((call) => call.name === "documents.export")).toBe(false);
    expect(screen.getByRole("img", { name: /固定 r1/ })).toBeInTheDocument();
    rendered.unmount(); expect(revokedUrls.mock.calls.length).toBe(createdUrls.mock.calls.length);
  });
});
