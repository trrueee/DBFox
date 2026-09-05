import { DOCUMENT, VIEW, ARTIFACT, REPRESENTATION, requestId, errorText, listDocuments, readFrame, drawFrame, pointAt, rectBetween, gestureOperations, referenceFor, parseSummary } from "./model.js";

let React;
let runtime;
let stylesheet;
let epoch = 0;
const h = (...args) => React.createElement(...args);
const tools = [["brush", "画笔 B"], ["eraser", "橡皮 E"], ["fill", "填充 F"], ["rectangle", "矩形 R"], ["select", "选区 V"]];
const zoomLevels = [1, 2, 4, 6, 8, 12, 16, 24, 32];
const button = (label, onClick, disabled = false, props = {}) => h("button", { type: "button", onClick, disabled, ...props }, label);
const field = (label, props) => h("label", { className: "dbfox-pixel__field" }, h("span", null, label), h("input", { "aria-label": label, ...props }));
const number = (label, value, onChange, min, max) => field(label, { type: "number", value, min, max, step: 1, required: true, onChange: (event) => onChange(event.target.value) });
const check = (label, checked, onChange) => h("label", { className: "dbfox-pixel__check" }, h("input", { type: "checkbox", checked, onChange: (event) => onChange(event.target.checked) }), label);
function icon() { return h("svg", { viewBox: "0 0 24 24", width: 18, height: 18, fill: "none", stroke: "currentColor", strokeWidth: 1.6, "aria-hidden": true }, h("path", { d: "M4 4h16v16H4zM4 10h16M10 4v16M16 4v16M4 16h16" })); }
function openWorkbench(rt, projectId, summary) {
  if (!rt.active) return;
  rt.host.dockViews.open({ viewKey: `${VIEW}:${projectId}:${summary?.document_id || "library"}`, viewType: VIEW, title: summary?.title || "Pixel Studio", projectId, closeable: true,
    ...(summary ? { target: { type: "object", object: { kind: DOCUMENT, id: summary.document_id }, authority: { kind: DOCUMENT, id: summary.document_id } } } : {}) });
}

function useLife(rt, projectId, scope) {
  const ref = React.useRef({ alive: true, controllers: new Set() });
  const valid = React.useCallback(() => ref.current.alive && rt.active && (scope === undefined || rt.host.workbench.currentScopeId() === scope), [rt, scope]);
  React.useEffect(() => {
    ref.current.alive = true;
    const stop = () => { ref.current.alive = false; for (const controller of ref.current.controllers) controller.abort(); ref.current.controllers.clear(); };
    rt.stops.add(stop);
    return () => { stop(); rt.stops.delete(stop); };
  }, [rt, projectId, scope]);
  const controller = React.useCallback(() => { const value = new AbortController(); ref.current.controllers.add(value); return value; }, []);
  const release = React.useCallback((value) => ref.current.controllers.delete(value), []);
  const invoke = React.useCallback((name, input, signal) => {
    if (!valid() || signal?.aborted) return Promise.reject(new DOMException("工作台作用域已失效", "AbortError"));
    return rt.host.operations.invoke(name, input, { projectId, signal });
  }, [rt, projectId, valid]);
  return React.useMemo(() => ({ valid, controller, release, invoke }), [valid, controller, release, invoke]);
}

function useVisible(rt, root) {
  const [visible, setVisible] = React.useState(true);
  React.useEffect(() => {
    let intersects = true;
    const update = () => setVisible(rt.active && intersects && document.visibilityState !== "hidden");
    const observer = typeof IntersectionObserver === "function" ? new IntersectionObserver((entries) => { intersects = entries.some((entry) => entry.isIntersecting); update(); }) : null;
    if (root.current) observer?.observe(root.current);
    document.addEventListener("visibilitychange", update);
    update();
    const stop = () => { observer?.disconnect(); document.removeEventListener("visibilitychange", update); setVisible(false); };
    rt.stops.add(stop);
    return () => { rt.stops.delete(stop); observer?.disconnect(); document.removeEventListener("visibilitychange", update); };
  }, [rt, root]);
  return visible;
}

function Form({ title, initial, submitLabel, onSubmit, disabled, children }) {
  const [value, setValue] = React.useState(initial);
  return h("form", { className: "dbfox-pixel__form", onSubmit: (event) => { event.preventDefault(); if (!disabled) onSubmit(value); } },
    h("fieldset", { disabled }, title ? h("legend", null, title) : null,
      children(value, (patch) => setValue((previous) => ({ ...previous, ...patch }))), h("button", { type: "submit" }, submitLabel)));
}

function Library({ rt, projectId, scope, onOpen }) {
  const life = useLife(rt, projectId, scope);
  const [items, setItems] = React.useState([]), [loading, setLoading] = React.useState(true), [busy, setBusy] = React.useState(false), [error, setError] = React.useState("");
  const [includeDeleted, setIncludeDeleted] = React.useState(false), [refresh, setRefresh] = React.useState(0);
  const working = React.useRef(false);
  React.useEffect(() => {
    const controller = life.controller();
    setLoading(true);
    listDocuments(life.invoke, controller.signal, includeDeleted).then((result) => { if (life.valid() && !controller.signal.aborted) setItems(result); })
      .catch((caught) => { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); })
      .finally(() => { life.release(controller); if (life.valid() && !controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [life, includeDeleted, refresh]);
  async function mutate(name, input) {
    if (working.current || !life.valid()) return;
    working.current = true; setBusy(true); setError("");
    const controller = life.controller(), mutation_id = requestId();
    try {
      const result = await life.invoke(name, { ...input, mutation_id }, controller.signal);
      if (!life.valid() || controller.signal.aborted) return;
      onOpen(result.document_id);
    } catch (caught) { if (life.valid() && !controller.signal.aborted) { setError(`${errorText(caught)} 请求 ${mutation_id} 未自动重发。`); setRefresh((value) => value + 1); } }
    finally { life.release(controller); working.current = false; if (life.valid()) setBusy(false); }
  }
  return h("section", { className: "dbfox-pixel__library" },
    h("div", { className: "dbfox-pixel__library-heading" }, icon(), h("h2", null, "像素画与 Sprite 动画")),
    h("p", null, "从一个像素开始。用图层、帧与动画标签，把角色变成可持续编辑的作品。"),
    h(Form, { title: "创建作品", initial: { title: "狐狸骑士", width: 32, height: 32 }, submitLabel: "创建像素作品", disabled: busy, onSubmit: (value) => mutate("documents.create", { title: value.title.trim(), width: Number(value.width), height: Number(value.height), expected_version: 0 }) },
      (value, change) => h(React.Fragment, null, field("作品名称", { value: value.title, maxLength: 160, required: true, onChange: (event) => change({ title: event.target.value }) }),
        h("div", { className: "dbfox-pixel__row" }, number("宽度", value.width, (width) => change({ width }), 1, 128), number("高度", value.height, (height) => change({ height }), 1, 128)),
        h("small", null, "建议 32 × 32；透明背景，初始 1 帧 / 1 层。"))),
    h("div", { className: "dbfox-pixel__row" }, h("h3", null, "项目作品"), check("显示已删除作品", includeDeleted, setIncludeDeleted), button("刷新目录", () => setRefresh((value) => value + 1), loading || busy)),
    error ? h("p", { role: "alert", className: "dbfox-pixel__error" }, error) : null,
    loading ? h("p", { role: "status" }, "正在读取作品目录…") : items.length ? h("div", { className: "dbfox-pixel__document-list" }, items.map((item) => h("div", { key: item.document_id, className: "dbfox-pixel__document-card" },
      h("div", null, h("strong", null, item.title), h("small", null, `${item.width} × ${item.height} · ${item.frame_count} 帧 · ${item.layer_count} 层 · r${item.revision}${item.status === "deleted" ? " · 已删除" : ""}`)),
      button(item.status === "deleted" ? "恢复作品" : "打开作品", () => item.status === "deleted" ? mutate("documents.restore", { document_id: item.document_id, expected_version: item.revision }) : onOpen(item.document_id), busy)))) : h("p", { className: "dbfox-pixel__empty" }, "此项目还没有像素作品。创建作品后即可绘制，也可交给 Agent 继续修改。"));
}

function Studio({ rt, projectId, initialId, context }) {
  const [documentId, setDocumentId] = React.useState(initialId || "");
  return h("div", { className: "dbfox-pixel" }, documentId
    ? h(Editor, { key: `${context.workbenchScopeId}:${projectId}:${documentId}`, rt, projectId, documentId, context, onLibrary: () => setDocumentId("") })
    : h(Library, { rt, projectId, scope: context.workbenchScopeId, onOpen: setDocumentId }));
}

function MiniCanvas({ document, frame, label, zoom = 2, className = "" }) {
  const ref = React.useRef(null);
  React.useEffect(() => { drawFrame(ref.current, document, frame, zoom); }, [document, frame, zoom]);
  return h("canvas", { ref, className: `dbfox-pixel__mini ${className}`, role: "img", "aria-label": label });
}

function PixelCanvas({ rt, snapshot, frame, frameId, layerId, tool, color, zoom, filled, selection, onSelect, disabled, onApply, onDraft, onError }) {
  const ref = React.useRef(null), draft = React.useRef(null);
  const helpId = React.useId();
  const [preview, setPreview] = React.useState(null), [cursor, setCursor] = React.useState({ x: 0, y: 0 });
  const { document } = snapshot;
  const locked = document.layers.find((layer) => layer.id === layerId)?.locked;
  const clear = React.useCallback(() => {
    const gesture = draft.current;
    draft.current = null;
    if (gesture && ref.current?.hasPointerCapture?.(gesture.pointerId)) ref.current.releasePointerCapture(gesture.pointerId);
    setPreview(null); onDraft(false);
  }, [onDraft]);
  React.useEffect(() => {
    rt.stops.add(clear);
    return () => { clear(); rt.stops.delete(clear); };
  }, [rt, clear]);
  React.useEffect(() => { clear(); }, [snapshot.summary.revision, frameId, layerId, tool, clear]);
  React.useEffect(() => {
    try {
      drawFrame(ref.current, document, frame, zoom);
      const ctx = ref.current?.getContext("2d");
      if (!ctx) return;
      const selected = preview?.tool === "select" ? rectBetween(preview.points[0], preview.points[preview.points.length - 1]) : selection;
      if (preview && preview.tool !== "select") {
        const points = preview.points, first = points[0], last = points[points.length - 1];
        ctx.save(); ctx.globalAlpha = 0.65;
        ctx.fillStyle = preview.tool === "eraser" ? "#808080" : document.palette[preview.color].color;
        ctx.strokeStyle = ctx.fillStyle; ctx.lineWidth = zoom; ctx.lineCap = "square"; ctx.lineJoin = "miter";
        if (preview.tool === "rectangle") {
          const rect = rectBetween(first, last);
          if (preview.filled) ctx.fillRect(rect.x * zoom, rect.y * zoom, rect.width * zoom, rect.height * zoom);
          else ctx.strokeRect((rect.x + 0.5) * zoom, (rect.y + 0.5) * zoom, (rect.width - 1) * zoom, (rect.height - 1) * zoom);
        } else if (preview.tool === "fill") ctx.fillRect(first.x * zoom, first.y * zoom, zoom, zoom);
        else { ctx.beginPath(); ctx.moveTo((first.x + 0.5) * zoom, (first.y + 0.5) * zoom); for (const point of points) ctx.lineTo((point.x + 0.5) * zoom, (point.y + 0.5) * zoom); ctx.stroke(); ctx.fillRect(first.x * zoom, first.y * zoom, zoom, zoom); }
        ctx.restore();
      }
      if (selected) {
        ctx.save(); ctx.lineWidth = 1; ctx.strokeStyle = "#FFFFFF"; ctx.setLineDash([4, 4]);
        ctx.strokeRect(selected.x * zoom + 0.5, selected.y * zoom + 0.5, selected.width * zoom - 1, selected.height * zoom - 1);
        ctx.strokeStyle = "#181825"; ctx.lineDashOffset = 4; ctx.strokeRect(selected.x * zoom + 0.5, selected.y * zoom + 0.5, selected.width * zoom - 1, selected.height * zoom - 1); ctx.restore();
      }
    } catch (caught) { onError(errorText(caught)); }
  }, [document, frame, zoom, preview, selection, onError]);
  function start(event) {
    if (event.button !== 0 || draft.current || disabled || !frame || (locked && tool !== "select")) return;
    const point = pointAt(event, ref.current, document.canvas, false);
    if (!point) return;
    event.preventDefault(); ref.current.focus();
    try { ref.current.setPointerCapture(event.pointerId); } catch { onError("未能捕获指针，本次绘制未开始。"); return; }
    draft.current = { pointerId: event.pointerId, documentId: snapshot.summary.document_id, revision: snapshot.summary.revision, frameId, layerId, tool, color, filled, points: [point] };
    setCursor(point); setPreview({ ...draft.current }); onDraft(true);
  }
  function move(event) {
    const gesture = draft.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const point = pointAt(event, ref.current, document.canvas);
    if (!point) return;
    const last = gesture.points[gesture.points.length - 1];
    if (point.x === last.x && point.y === last.y) return;
    if (gesture.tool === "brush" || gesture.tool === "eraser") {
      if (gesture.points.length >= 129) { clear(); onError("本次笔迹超过 128 段，已全部取消。请分成较短笔迹重新绘制。"); return; }
      gesture.points.push(point);
    } else if (gesture.tool !== "fill") gesture.points = [gesture.points[0], point];
    setCursor(point); setPreview({ ...gesture, points: [...gesture.points] });
  }
  function end(event) {
    if (!draft.current || draft.current.pointerId !== event.pointerId) return;
    move(event);
    const gesture = draft.current;
    if (!gesture) return;
    clear();
    if (gesture.tool === "select") onSelect(rectBetween(gesture.points[0], gesture.points[gesture.points.length - 1]));
    else onApply(gestureOperations(gesture), gesture.revision);
  }
  function keyboard(event) {
    if (event.key === "Escape") { clear(); onSelect(null); event.preventDefault(); return; }
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault(); event.stopPropagation();
      const next = { x: Math.max(0, Math.min(document.canvas.width - 1, cursor.x + (event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0))), y: Math.max(0, Math.min(document.canvas.height - 1, cursor.y + (event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0))) };
      setCursor(next); onSelect({ ...next, width: 1, height: 1 });
    } else if (event.key === "Enter" && !disabled && frame && (!locked || tool === "select")) {
      event.preventDefault();
      if (tool === "select") onSelect({ ...cursor, width: 1, height: 1 });
      else onApply(gestureOperations({ tool, points: [cursor], color, filled, frameId, layerId }), snapshot.summary.revision);
    }
  }
  return h("div", { className: "dbfox-pixel__canvas-area" }, h("div", { className: "dbfox-pixel__canvas-scroll" }, h("canvas", { ref, role: "application", tabIndex: 0, "aria-label": `像素画布 ${document.canvas.width} × ${document.canvas.height}`, "aria-describedby": helpId, "aria-disabled": disabled || (locked && tool !== "select"), onPointerDown: start, onPointerMove: move, onPointerUp: end, onPointerCancel: clear, onLostPointerCapture: clear, onKeyDown: keyboard })),
    h("div", { className: "dbfox-pixel__canvas-status", role: "status" }, preview ? "临时笔迹 · 未提交" : locked ? "当前图层已锁定 · 可选择，解锁后绘制" : `${cursor.x}, ${cursor.y} · ${zoom}× · r${snapshot.summary.revision}`),
    h("small", { id: helpId, className: "dbfox-pixel__canvas-help" }, "方向键定位，Enter 绘制一格，Esc 取消。拖动最多 128 段，超限整笔取消。"));
}

function Editor({ rt, projectId, documentId, context, onLibrary }) {
  const root = React.useRef(null), life = useLife(rt, projectId, context.workbenchScopeId), visible = useVisible(rt, root);
  const [snapshot, setSnapshot] = React.useState(null), [frames, setFrames] = React.useState({}), [frameId, setFrameId] = React.useState(""), [layerId, setLayerId] = React.useState("");
  const [loading, setLoading] = React.useState(true), [busy, setBusy] = React.useState(false), [drafting, setDrafting] = React.useState(false), [error, setError] = React.useState(""), [notice, setNotice] = React.useState("");
  const [tool, setTool] = React.useState("brush"), [color, setColor] = React.useState(1), [zoom, setZoom] = React.useState(6), [filled, setFilled] = React.useState(true), [selection, setSelection] = React.useState(null);
  const zoomEdited = React.useRef(false);
  const [unknownExport, setUnknownExport] = React.useState(false), [exportTarget, setExportTarget] = React.useState(null);
  const [playing, setPlaying] = React.useState(false), [playIndex, setPlayIndex] = React.useState(0), [tagId, setTagId] = React.useState("");
  const [history, setHistory] = React.useState([]), [historyBefore, setHistoryBefore] = React.useState(null), [historyOpen, setHistoryOpen] = React.useState(false);
  const current = React.useRef({ snapshot: null, busy: false, drafting: false, loading: true, frameId: "", layerId: "", read: null, fill: null });
  current.current.frameId = frameId; current.current.layerId = layerId;
  const setDraft = React.useCallback((value) => { current.current.drafting = value; setDrafting(value); }, []);
  const reportError = React.useCallback((message) => setError(message), []);
  const fitCanvas = React.useCallback(() => {
    const area = root.current?.querySelector(".dbfox-pixel__canvas-scroll");
    const size = current.current.snapshot?.document.canvas;
    if (!area || !size || !area.clientWidth || !area.clientHeight) return;
    const maximum = Math.min((area.clientWidth - 48) / size.width, (area.clientHeight - 48) / size.height);
    setZoom([...zoomLevels].reverse().find((value) => value <= maximum) || 1);
  }, []);
  React.useLayoutEffect(() => {
    const area = root.current?.querySelector(".dbfox-pixel__canvas-scroll");
    if (!area || typeof ResizeObserver !== "function") return undefined;
    const observer = new ResizeObserver(() => { if (!zoomEdited.current && !current.current.drafting) fitCanvas(); });
    observer.observe(area);
    if (!zoomEdited.current) fitCanvas();
    const stop = () => observer.disconnect(); rt.stops.add(stop);
    return () => { stop(); rt.stops.delete(stop); };
  }, [snapshot, fitCanvas, rt]);
  const refresh = React.useCallback(async (signal, revision) => {
    const next = await life.invoke("documents.get", { document_id: documentId, ...(revision ? { revision } : {}) }, signal);
    if (!life.valid() || signal.aborted) return;
    parseSummary(next.summary);
    if (next.summary.project_id !== projectId || next.summary.document_id !== documentId || (revision && next.summary.revision !== revision)) throw new Error("文档身份或修订不一致。");
    if (next.summary.status !== "active") { current.current.snapshot = null; setSnapshot(null); throw new Error("作品已被删除。返回作品目录可查看并恢复。"); }
    const selectedFrame = next.document.frames.some((frame) => frame.id === current.current.frameId) ? current.current.frameId : next.document.frames[0].id;
    const selectedLayer = next.document.layers.some((layer) => layer.id === current.current.layerId) ? current.current.layerId : next.document.layers[0].id;
    const first = await readFrame(life.invoke, next, selectedFrame, signal);
    if (!life.valid() || signal.aborted) return;
    current.current.fill?.abort();
    current.current.snapshot = next;
    setSnapshot(next); setFrames({ [selectedFrame]: first }); setFrameId(selectedFrame); setLayerId(selectedLayer); setPlaying(false); setPlayIndex(0); setSelection(null);
    setColor((value) => Math.min(value, next.document.palette.length - 1));
    setTagId((value) => next.document.tags.some((tag) => tag.id === value) ? value : "");
    setHistoryOpen(false); setHistory([]); setHistoryBefore(null);
    const fillController = life.controller(); current.current.fill = fillController;
    // Two concurrent bounded frame reads. Total pixels are constrained by the canonical 262144-slot budget.
    const remaining = next.document.frames.filter((frame) => frame.id !== selectedFrame);
    const worker = async () => {
      while (remaining.length && !fillController.signal.aborted) {
        const item = remaining.shift();
        const frame = await readFrame(life.invoke, next, item.id, fillController.signal);
        if (!life.valid() || fillController.signal.aborted || current.current.snapshot !== next) return;
        setFrames((previous) => ({ ...previous, [item.id]: frame }));
      }
    };
    Promise.all([worker(), worker()]).catch((caught) => { if (life.valid() && !fillController.signal.aborted && current.current.snapshot === next) { fillController.abort(); setError(`帧预览读取失败：${errorText(caught)}，请刷新。`); } }).finally(() => life.release(fillController));
  }, [life, documentId, projectId]);
  React.useEffect(() => {
    const controller = life.controller(); current.current.read = controller;
    refresh(controller.signal).catch((caught) => { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); })
      .finally(() => { life.release(controller); if (life.valid() && !controller.signal.aborted) { current.current.loading = false; setLoading(false); } });
    return () => { controller.abort(); current.current.fill?.abort(); };
  }, [refresh, life]);
  React.useEffect(() => {
    if (!visible) return undefined;
    let stopped = false, timer, controller;
    const poll = async () => {
      try {
        const previous = current.current.snapshot;
        const editingText = root.current?.contains(globalThis.document.activeElement) && globalThis.document.activeElement?.matches("input,textarea,select,[contenteditable=true]");
        if (!stopped && life.valid() && previous && !current.current.busy && !current.current.drafting && !current.current.loading && !editingText) {
          controller = life.controller();
          const head = await life.invoke("documents.head", { document_id: documentId }, controller.signal);
          if (!stopped && life.valid() && !controller.signal.aborted && previous === current.current.snapshot && !current.current.busy && !current.current.drafting && head.revision !== previous.summary.revision) {
            current.current.loading = true; setLoading(true);
            await refresh(controller.signal);
            if (!stopped && life.valid()) setNotice(`已同步外部修改 · r${head.revision}`);
          }
        }
      } catch (caught) { if (!stopped && life.valid() && !controller?.signal.aborted) setError(`同步失败：${errorText(caught)}`); }
      finally { if (controller) life.release(controller); if (!stopped && life.valid()) { current.current.loading = false; setLoading(false); timer = setTimeout(poll, 1000); } }
    };
    timer = setTimeout(poll, 1000);
    const stop = () => { stopped = true; clearTimeout(timer); controller?.abort(); };
    rt.stops.add(stop);
    return () => { stop(); rt.stops.delete(stop); };
  }, [visible, life, refresh, documentId, rt]);
  const mutate = React.useCallback(async (name, input, expectedVersion) => {
    const before = current.current.snapshot;
    if (!before || !life.valid() || current.current.busy || current.current.loading) return;
    current.current.busy = true; setBusy(true); setPlaying(false); setError("");
    current.current.read?.abort(); current.current.fill?.abort();
    const controller = life.controller(), mutation_id = requestId();
    try {
      const result = await life.invoke(name, { document_id: documentId, expected_version: expectedVersion ?? before.summary.revision, mutation_id, ...input }, controller.signal);
      if (!life.valid() || controller.signal.aborted) return;
      if (name === "documents.delete") { onLibrary(); return; }
      await refresh(controller.signal, result.revision);
      if (life.valid() && !controller.signal.aborted) setNotice(result.changed ? `已保存 · r${result.revision}` : `内容未改变 · r${result.revision}`);
    } catch (caught) {
      if (!life.valid() || controller.signal.aborted) return;
      setSelection(null);
      setError(`${errorText(caught)} 本次请求 ${mutation_id} 未自动重发；正在读取已提交状态。`);
      try { await refresh(controller.signal); } catch (readError) { if (life.valid() && !controller.signal.aborted) setNotice(`读回失败：${errorText(readError)}。可手动刷新查证，勿重复提交未知结果。`); }
    } finally { life.release(controller); current.current.busy = false; if (life.valid()) setBusy(false); }
  }, [life, documentId, refresh, onLibrary]);
  const apply = React.useCallback((operations, expectedVersion) => mutate("documents.apply", { operations }, expectedVersion), [mutate]);
  async function loadHistory(more = false) {
    if (current.current.busy || !life.valid()) return;
    const captured = current.current.snapshot, controller = life.controller();
    try {
      const result = await life.invoke("documents.revisions", { document_id: documentId, limit: 32, ...(more && historyBefore ? { before_revision: historyBefore } : {}) }, controller.signal);
      if (!life.valid() || controller.signal.aborted || captured !== current.current.snapshot) return;
      setHistory((previous) => more ? [...previous, ...result.revisions] : result.revisions); setHistoryBefore(result.next_before_revision); setHistoryOpen(true);
    } catch (caught) { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); }
    finally { life.release(controller); }
  }
  async function undo() {
    const before = current.current.snapshot;
    if (!before?.summary.parent_revision || current.current.drafting || current.current.busy || !life.valid()) return;
    const controller = life.controller();
    try {
      const result = await life.invoke("documents.revisions", { document_id: documentId, before_revision: before.summary.revision, limit: 32 }, controller.signal);
      if (!life.valid() || controller.signal.aborted || current.current.snapshot !== before) return;
      const previous = result.revisions.find((item) => item.revision < before.summary.revision && item.status === "active");
      if (previous) await mutate("documents.undo", { restore_revision: previous.revision }, before.summary.revision);
      else setNotice("没有可撤销的有效历史修订。");
    } catch (caught) { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); }
    finally { life.release(controller); }
  }
  async function exportArtifact() {
    if (!life.valid() || current.current.busy || current.current.loading || current.current.drafting || !current.current.snapshot || unknownExport) return;
    const capturedHost = rt.host, capturedScope = context.workbenchScopeId;
    if (typeof capturedHost.workbench.openArtifact !== "function") { setError("此 Host 不支持成果导航，请升级后导出。尚未创建导出 Run。"); return; }
    const before = current.current.snapshot, controller = life.controller(), mutation_id = requestId("export");
    current.current.busy = true; setBusy(true); setPlaying(false); setError("");
    let produced = false;
    try {
      const result = await life.invoke("documents.export", { document_id: documentId, expected_version: before.summary.revision, mutation_id }, controller.signal);
      if (!life.valid() || controller.signal.aborted) return;
      const target = { projectId, sessionId: result.session_id, runId: result.run_id, artifactId: result.artifact_ids[0] };
      produced = true; setExportTarget(target);
      await capturedHost.workbench.openArtifact(target, { workbenchScopeId: capturedScope, signal: controller.signal });
      if (life.valid() && !controller.signal.aborted) setNotice(`已打开 r${before.summary.revision} 成果，可下载 PNG 或 Sprite Sheet。`);
    } catch (caught) { if (life.valid() && !controller.signal.aborted) { if (!produced) setUnknownExport(true); setError(`${errorText(caught)} 导出请求 ${mutation_id} 未自动重发；${produced ? "成果已生成，可重新打开。" : "结果待查证，已停用本工作台的新导出，请检查成果记录。"}`); } }
    finally { life.release(controller); current.current.busy = false; if (life.valid()) setBusy(false); }
  }
  async function reopenExport() {
    if (!life.valid() || current.current.busy || !exportTarget) return;
    const controller = life.controller();
    try { await rt.host.workbench.openArtifact(exportTarget, { workbenchScopeId: context.workbenchScopeId, signal: controller.signal }); }
    catch (caught) { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); }
    finally { life.release(controller); }
  }
  const tag = snapshot?.document.tags.find((item) => item.id === tagId);
  const playbackIds = tag?.frame_ids || snapshot?.document.frames.map((item) => item.id) || [];
  const canPlay = playbackIds.length > 0 && playbackIds.every((id) => frames[id]);
  const playbackKey = playbackIds.join(":");
  React.useEffect(() => {
    if (!playing || !visible || !canPlay || !snapshot) return undefined;
    let stopped = false, index = 0, start = null, raf;
    const durations = new Map(snapshot.document.frames.map((item) => [item.id, item.duration_ms]));
    setPlayIndex(0);
    const tick = (time) => {
      if (stopped || !life.valid()) return;
      if (start === null) start = time;
      let budget = 64;
      while (time - start >= durations.get(playbackIds[index]) && budget-- > 0) {
        start += durations.get(playbackIds[index]);
        if (index === playbackIds.length - 1 && tag && !tag.loop) { setPlaying(false); return; }
        index = (index + 1) % playbackIds.length; setPlayIndex(index);
      }
      if (budget <= 0) start = time;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const stop = () => { stopped = true; cancelAnimationFrame(raf); };
    rt.stops.add(stop);
    return () => { stop(); rt.stops.delete(stop); };
  }, [playing, visible, canPlay, snapshot, playbackKey, tag, life, rt]);
  React.useEffect(() => { if (!visible) setPlaying(false); }, [visible]);
  function keyboard(event) {
    if (event.target.closest("input,textarea,select,[contenteditable=true]") || event.altKey) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (!busy && !loading && !drafting) undo(); return; }
    if (event.ctrlKey || event.metaKey) return;
    const selectedTool = { b: "brush", e: "eraser", f: "fill", r: "rectangle", v: "select" }[event.key.toLowerCase()];
    if (selectedTool && !drafting) { event.preventDefault(); setTool(selectedTool); }
    if (event.code === "Space" && event.target.tagName !== "BUTTON" && canPlay && !busy && !drafting) { event.preventDefault(); setPlaying((value) => !value); }
  }
  const locked = busy || loading || drafting;
  const document = snapshot?.document, frame = frames[frameId], layer = document?.layers.find((item) => item.id === layerId);
  const allocation = document ? document.canvas.width * document.canvas.height * document.frames.length * document.layers.length : 0;
  return h("section", { className: "dbfox-pixel__editor", ref: root, onKeyDown: keyboard, "aria-label": "Pixel 工作台" },
    h("header", { className: "dbfox-pixel__header" }, button("作品目录", onLibrary, busy || drafting), h("div", { className: "dbfox-pixel__heading" }, h("strong", null, snapshot?.summary.title || "Pixel Studio"), h("small", null, snapshot ? `${snapshot.summary.width} × ${snapshot.summary.height} · ${document.frames.length} 帧 · ${document.layers.length} 层 · r${snapshot.summary.revision}` : "读取作品")),
      button("撤销", undo, locked || !snapshot?.summary.parent_revision, { "aria-keyshortcuts": "Control+Z Meta+Z" }), button("历史", () => loadHistory(), locked || !snapshot),
      button("刷新", async () => { if (locked) return; const controller = life.controller(); current.current.loading = true; setLoading(true); try { await refresh(controller.signal); } catch (caught) { if (life.valid()) setError(errorText(caught)); } finally { life.release(controller); current.current.loading = false; if (life.valid()) setLoading(false); } }, locked),
      button(unknownExport ? "导出待查证" : "导出成果", exportArtifact, locked || !snapshot || unknownExport, { className: "dbfox-pixel__primary" }), exportTarget ? button("打开已导出成果", reopenExport, locked) : null),
    error ? h("div", { className: "dbfox-pixel__error", role: "alert" }, error, button("关闭提示", () => setError(""))) : null,
    notice ? h("div", { className: "dbfox-pixel__notice", role: "status" }, notice) : null,
    loading ? h("div", { className: "dbfox-pixel__notice", role: "status" }, "正在读取已提交版本…") : null,
    historyOpen ? h("section", { className: "dbfox-pixel__history", "aria-label": "修订历史" }, h("div", { className: "dbfox-pixel__row" }, h("strong", null, "恢复历史会追加新修订"), button("收起历史", () => setHistoryOpen(false))),
      history.map((item) => button(`恢复 r${item.revision}${item.status === "deleted" ? "（已删除）" : ""}`, () => mutate("documents.undo", { restore_revision: item.revision }), locked || item.status !== "active" || item.revision === snapshot?.summary.revision, { key: item.revision })), historyBefore ? button("更早修订", () => loadHistory(true), locked) : null) : null,
    document ? h(React.Fragment, null, h("div", { className: "dbfox-pixel__body" },
      h("aside", { className: "dbfox-pixel__left", "aria-label": "调色板与图层" }, h(Palette, { key: `${snapshot.summary.revision}:${color}`, document, color, setColor, disabled: locked, apply }),
        h(Layers, { key: `${snapshot.summary.revision}:${layerId}`, document, layerId, setLayerId: (id) => { setLayerId(id); setSelection(null); }, disabled: locked, apply, allocation })),
      h("main", { className: "dbfox-pixel__main" }, h("div", { className: "dbfox-pixel__toolbar", "aria-label": "绘图工具" }, tools.map(([id, label]) => button(label, () => setTool(id), locked, { key: id, "aria-pressed": tool === id })),
        h("label", { className: "dbfox-pixel__zoom" }, "缩放", h("select", { "aria-label": "画布缩放", value: zoom, disabled: drafting, onChange: (event) => { zoomEdited.current = true; setZoom(Number(event.target.value)); } }, zoomLevels.map((value) => h("option", { key: value, value }, `${value}×`)))), button("适应画布", () => { zoomEdited.current = false; fitCanvas(); }, drafting),
        tool === "rectangle" ? check("实心矩形", filled, setFilled) : null),
        h(PixelCanvas, { rt, snapshot, frame, frameId, layerId, tool, color, zoom, filled, selection, onSelect: setSelection, disabled: busy || loading || playing || !frame, onApply: apply, onDraft: setDraft, onError: reportError })),
      h("aside", { className: "dbfox-pixel__right", "aria-label": "选区与动画" },
        h("section", { className: "dbfox-pixel__section" }, h("h3", null, "动画预览"), h("div", { className: "dbfox-pixel__preview" }, h(MiniCanvas, { document, frame: frames[playing ? playbackIds[playIndex] : frameId], label: `动画预览 ${playing ? playbackIds[playIndex] : frameId}`, zoom: Math.max(1, Math.floor(160 / Math.max(document.canvas.width, document.canvas.height))) })),
          h("select", { "aria-label": "播放动画标签", value: tagId, disabled: locked, onChange: (event) => { setPlaying(false); setTagId(event.target.value); setPlayIndex(0); } }, h("option", { value: "" }, "全部帧"), document.tags.map((item) => h("option", { key: item.id, value: item.id }, item.name))),
          button(playing ? "暂停播放" : "播放动画", () => setPlaying((value) => !value), !canPlay || locked, { "aria-pressed": playing, "aria-keyshortcuts": "Space" }), h("small", null, canPlay ? `${playbackIds.length} 帧 · ${tag && !tag.loop ? "播放一次" : "循环播放"}` : `读取帧预览 ${Object.keys(frames).length}/${document.frames.length}…`)),
        h(Selection, { key: `${snapshot.summary.revision}:${frameId}:${layerId}:${JSON.stringify(selection)}`, snapshot, frameId, layerId, selection, setSelection, disabled: locked || layer?.locked, askDisabled: locked, apply, onAsk: () => { if (life.valid() && !locked) context.onAsk(referenceFor(snapshot, frameId, layerId, selection)); } }),
        h(Tags, { key: snapshot.summary.revision, document, frameId, disabled: locked, apply }),
        h("details", null, h("summary", null, "作品设置"), h(Form, { title: "作品名称", initial: { title: document.title }, submitLabel: "重命名作品", disabled: locked, onSubmit: (value) => apply([{ kind: "rename", title: value.title.trim() }]) }, (value, change) => field("新作品名称", { value: value.title, maxLength: 160, required: true, onChange: (event) => change({ title: event.target.value }) })),
          button("删除作品", () => mutate("documents.delete", {}), locked), h("small", null, "删除后可在作品目录恢复；历史成果保留。")))),
      h(Timeline, { key: snapshot.summary.revision, document, frames, frameId, setFrameId: (id) => { setFrameId(id); setSelection(null); setPlaying(false); }, disabled: locked, apply, allocation }),
      h("footer", { className: "dbfox-pixel__footer" }, h("span", null, `${allocation.toLocaleString()} / 262,144 像素槽`), h("span", null, busy ? "正在保存…" : "B 画笔 · E 橡皮 · F 填充 · R 矩形 · V 选区 · Space 播放"))) : !loading ? h("div", { className: "dbfox-pixel__empty" }, "作品暂不可用。可手动刷新，或返回作品目录。") : null);
}

function Palette({ document, color, setColor, disabled, apply }) {
  const entry = document.palette[color];
  return h("section", { className: "dbfox-pixel__section" }, h("div", { className: "dbfox-pixel__row" }, h("h3", null, "调色板"), h("small", null, `${document.palette.length}/256`)),
    h("div", { className: "dbfox-pixel__palette", role: "group", "aria-label": "颜色槽" }, document.palette.map((item, index) => button(h("span", { className: "dbfox-pixel__swatch", style: { backgroundColor: item.color } }, index === 0 ? "∅" : ""), () => setColor(index), disabled, { key: index, "aria-label": `颜色 ${index} ${item.name}`, "aria-pressed": color === index, title: `${index} · ${item.name} · ${item.color}` }))),
    color === 0 ? h("small", null, "0 · 固定透明色") : h(Form, { initial: { name: entry.name, color: entry.color.slice(0, 7) }, submitLabel: "保存颜色", disabled, onSubmit: (value) => apply([{ kind: "palette_set", index: color, name: value.name.trim(), color: `${value.color}FF` }]) },
      (value, change) => h(React.Fragment, null, field("颜色名称", { value: value.name, maxLength: 80, required: true, onChange: (event) => change({ name: event.target.value }) }), field("颜色值", { type: "color", value: value.color, onChange: (event) => change({ color: event.target.value }) }))),
    h("details", null, h("summary", null, "添加颜色"), h(Form, { initial: { name: "新颜色", color: "#E58A38" }, submitLabel: "添加颜色槽", disabled: disabled || document.palette.length >= 256, onSubmit: (value) => apply([{ kind: "palette_set", index: document.palette.length, name: value.name.trim(), color: `${value.color}FF` }]) },
      (value, change) => h(React.Fragment, null, field("新颜色名称", { value: value.name, maxLength: 80, required: true, onChange: (event) => change({ name: event.target.value }) }), field("新颜色值", { type: "color", value: value.color, onChange: (event) => change({ color: event.target.value }) })))));
}

function Layers({ document, layerId, setLayerId, disabled, apply, allocation }) {
  const selected = document.layers.find((layer) => layer.id === layerId), position = document.layers.findIndex((layer) => layer.id === layerId);
  const canAdd = document.layers.length < 16 && allocation + document.canvas.width * document.canvas.height * document.frames.length <= 262144;
  return h("section", { className: "dbfox-pixel__section" }, h("div", { className: "dbfox-pixel__row" }, h("h3", null, "图层"), h("small", null, "上方覆盖下方")),
    h("div", { className: "dbfox-pixel__layers", role: "group", "aria-label": "图层栈" }, [...document.layers].reverse().map((layer) => h("div", { key: layer.id, className: "dbfox-pixel__layer", "data-selected": layer.id === layerId },
      button(layer.name, () => setLayerId(layer.id), disabled, { "aria-pressed": layer.id === layerId, className: "dbfox-pixel__layer-name" }),
      button(layer.visible ? "显" : "隐", () => apply([{ kind: "layer_update", layer_id: layer.id, visible: !layer.visible }]), disabled, { "aria-label": `${layer.visible ? "隐藏" : "显示"}图层 ${layer.name}`, "aria-pressed": layer.visible }),
      button(layer.locked ? "锁" : "开", () => apply([{ kind: "layer_update", layer_id: layer.id, locked: !layer.locked }]), disabled, { "aria-label": `${layer.locked ? "解锁" : "锁定"}图层 ${layer.name}`, "aria-pressed": layer.locked })))),
    h("div", { className: "dbfox-pixel__row" }, button("上移图层", () => apply([{ kind: "layer_update", layer_id: layerId, position: position + 1 }]), disabled || position === document.layers.length - 1), button("下移图层", () => apply([{ kind: "layer_update", layer_id: layerId, position: position - 1 }]), disabled || position === 0)),
    h(Form, { initial: { name: selected.name }, submitLabel: "重命名图层", disabled, onSubmit: (value) => apply([{ kind: "layer_update", layer_id: layerId, name: value.name.trim() }]) }, (value, change) => field("图层名称", { value: value.name, required: true, maxLength: 80, onChange: (event) => change({ name: event.target.value }) })),
    h("details", null, h("summary", null, "添加图层"), h(Form, { initial: { name: "新图层" }, submitLabel: "创建图层", disabled: disabled || !canAdd, onSubmit: (value) => apply([{ kind: "layer_create", layer_id: requestId("layer"), name: value.name.trim(), position: document.layers.length }]) }, (value, change) => field("新图层名称", { value: value.name, required: true, maxLength: 80, onChange: (event) => change({ name: event.target.value }) })), !canAdd ? h("small", null, "图层数或总像素槽已达上限。") : null),
    button("删除当前图层", () => apply([{ kind: "layer_delete", layer_id: layerId }]), disabled || selected.locked || document.layers.length === 1));
}

function Selection({ snapshot, frameId, layerId, selection, setSelection, disabled, askDisabled, apply, onAsk }) {
  const { width, height } = snapshot.document.canvas;
  return h("section", { className: "dbfox-pixel__section" }, h("h3", null, "选区"), h("small", { className: "dbfox-pixel__identity" }, `${frameId} / ${layerId}`),
    h(Form, { initial: selection || { x: 0, y: 0, width: 1, height: 1 }, submitLabel: "设置选区", disabled: false, onSubmit: (value) => {
      const rect = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, Number(item)]));
      if (rect.x + rect.width <= width && rect.y + rect.height <= height) setSelection(rect);
    } }, (value, change) => h("div", { className: "dbfox-pixel__grid-two" }, number("选区 X", value.x, (x) => change({ x }), 0, width - Number(value.width)), number("选区 Y", value.y, (y) => change({ y }), 0, height - Number(value.height)), number("选区宽度", value.width, (widthValue) => change({ width: widthValue }), 1, width - Number(value.x)), number("选区高度", value.height, (heightValue) => change({ height: heightValue }), 1, height - Number(value.y)))),
    selection ? h(React.Fragment, null, h("div", { className: "dbfox-pixel__row" }, [ ["flip_x", "水平镜像"], ["flip_y", "垂直镜像"], ["rotate_cw", "顺时针旋转"] ].map(([transform, label]) => button(label, () => apply([{ kind: "region_transform", frame_id: frameId, layer_id: layerId, rect: selection, transform, destination: { x: selection.x, y: selection.y }, mode: "move", clip: false }]), disabled || (transform === "rotate_cw" && (selection.x + selection.height > width || selection.y + selection.width > height)), { key: transform }))),
      h(Form, { title: "移动或复制", initial: { x: selection.x, y: selection.y, mode: "move", clip: false }, submitLabel: "应用区域变换", disabled, onSubmit: (value) => apply([{ kind: "region_transform", frame_id: frameId, layer_id: layerId, rect: selection, transform: "translate", destination: { x: Number(value.x), y: Number(value.y) }, mode: value.mode, clip: value.clip }]) },
        (value, change) => h(React.Fragment, null, h("div", { className: "dbfox-pixel__grid-two" }, number("目标 X", value.x, (x) => change({ x }), -128, 255), number("目标 Y", value.y, (y) => change({ y }), -128, 255)),
          h("select", { "aria-label": "变换模式", value: value.mode, onChange: (event) => change({ mode: event.target.value }) }, h("option", { value: "move" }, "移动"), h("option", { value: "copy" }, "复制")),
          check("裁掉目标越界像素", value.clip, (clip) => change({ clip })), value.clip && value.mode === "move" ? h("small", null, "移动时越界部分会被丢弃，可用撤销恢复。") : null)), button("清除选区", () => setSelection(null))) : h("small", null, "用 V 拖动框选，或输入整数范围。"),
    button("交给 Agent", onAsk, askDisabled, { className: "dbfox-pixel__primary" }));
}

function Timeline({ document, frames, frameId, setFrameId, disabled, apply, allocation }) {
  const position = document.frames.findIndex((frame) => frame.id === frameId), selected = document.frames[position];
  const canAdd = document.frames.length < 64 && allocation + document.canvas.width * document.canvas.height * document.layers.length <= 262144;
  const [removeTags, setRemoveTags] = React.useState(false);
  const tagged = document.tags.some((tag) => tag.frame_ids.includes(frameId));
  return h("section", { className: "dbfox-pixel__timeline", "aria-label": "帧时间线" },
    h("div", { className: "dbfox-pixel__row" }, h("h3", null, "帧时间线"), button("新建帧", () => apply([{ kind: "frame_create", frame_id: requestId("frame"), position: position + 1, duration_ms: selected.duration_ms }]), disabled || !canAdd),
      button("复制当前帧", () => apply([{ kind: "frame_duplicate", source_frame_id: frameId, frame_id: requestId("frame"), position: position + 1 }]), disabled || !canAdd),
      button("前移帧", () => apply([{ kind: "frame_update", frame_id: frameId, position: position - 1 }]), disabled || position === 0), button("后移帧", () => apply([{ kind: "frame_update", frame_id: frameId, position: position + 1 }]), disabled || position === document.frames.length - 1),
      !canAdd ? h("small", null, "帧数或总像素槽已达上限。") : null),
    h("div", { className: "dbfox-pixel__frame-strip", role: "group", "aria-label": "选择帧" }, document.frames.map((frame, index) => button(h(React.Fragment, null, h(MiniCanvas, { document, frame: frames[frame.id], label: `第 ${index + 1} 帧缩略图`, zoom: 1 }), h("strong", null, String(index + 1).padStart(2, "0")), h("small", null, `${frame.duration_ms} ms`)), () => setFrameId(frame.id), disabled || !frames[frame.id], { key: frame.id, "aria-label": `选择第 ${index + 1} 帧`, "aria-pressed": frame.id === frameId, title: frame.id }))),
    h("div", { className: "dbfox-pixel__frame-properties" }, h(Form, { key: frameId, initial: { duration: selected.duration_ms }, submitLabel: "设置帧时长", disabled, onSubmit: (value) => apply([{ kind: "frame_update", frame_id: frameId, duration_ms: Number(value.duration) }]) }, (value, change) => number("帧时长 ms", value.duration, (duration) => change({ duration }), 20, 2000)),
      tagged ? check("删除时从动画标签移除", removeTags, setRemoveTags) : null,
      button("删除当前帧", () => apply([{ kind: "frame_delete", frame_id: frameId, remove_from_tags: removeTags }]), disabled || document.frames.length === 1 || document.layers.some((layer) => layer.locked) || (tagged && !removeTags)),
      document.layers.some((layer) => layer.locked) ? h("small", null, "删除帧前须解锁全部图层。") : null));
}

function Tags({ document, frameId, disabled, apply }) {
  const [selectedId, setSelectedId] = React.useState("");
  const selected = document.tags.find((tag) => tag.id === selectedId);
  return h("details", { className: "dbfox-pixel__section" }, h("summary", null, `动画标签 (${document.tags.length}/16)`),
    h("select", { "aria-label": "编辑动画标签", value: selectedId, disabled, onChange: (event) => setSelectedId(event.target.value) }, h("option", { value: "" }, "新建标签"), document.tags.map((tag) => h("option", { key: tag.id, value: tag.id }, tag.name))),
    h(Form, { key: selectedId, initial: selected ? { name: selected.name, frame_ids: [...selected.frame_ids], loop: selected.loop } : { name: "Idle", frame_ids: [frameId], loop: true }, submitLabel: selected ? "保存动画标签" : "创建动画标签", disabled: disabled || (!selected && document.tags.length >= 16), onSubmit: (value) => { if (value.frame_ids.length) apply([{ kind: "tag_set", tag_id: selectedId || requestId("tag"), ...value, name: value.name.trim() }]); } },
      (value, change) => h(React.Fragment, null, field("标签名称", { value: value.name, maxLength: 80, required: true, onChange: (event) => change({ name: event.target.value }) }), check("循环", value.loop, (loop) => change({ loop })),
        h("small", null, "勾选帧按加入顺序播放；下方可调整标签内顺序。"),
        h("div", { className: "dbfox-pixel__tag-checks" }, document.frames.map((frame, index) => h(React.Fragment, { key: frame.id }, check(`帧 ${index + 1}`, value.frame_ids.includes(frame.id), (enabled) => change({ frame_ids: enabled ? [...value.frame_ids, frame.id] : value.frame_ids.filter((id) => id !== frame.id) }))))),
        h("ol", { className: "dbfox-pixel__tag-order" }, value.frame_ids.map((id, index) => h("li", { key: id }, h("span", null, `帧 ${document.frames.findIndex((frame) => frame.id === id) + 1}`), button("↑", () => { const ids = [...value.frame_ids]; [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]; change({ frame_ids: ids }); }, index === 0, { "aria-label": `前移标签中的帧 ${document.frames.findIndex((frame) => frame.id === id) + 1}` })))),
        value.frame_ids.length ? null : h("small", { role: "alert" }, "至少选择一帧。"))),
    selected ? button("删除动画标签", () => apply([{ kind: "tag_delete", tag_id: selectedId }]), disabled) : null);
}

function PixelArtifact({ rt, artifact, payload, context }) {
  const life = useLife(rt, undefined, undefined);
  const [layout, setLayout] = React.useState(null), [tags, setTags] = React.useState([]), [tagId, setTagId] = React.useState(""), [frameId, setFrameId] = React.useState(""), [url, setUrl] = React.useState(""), [error, setError] = React.useState(""), [busy, setBusy] = React.useState(false);
  const owned = React.useRef(new Set()), working = React.useRef(false), lastDownload = React.useRef("");
  React.useEffect(() => {
    const urls = owned.current;
    const stop = () => { for (const value of urls) URL.revokeObjectURL(value); urls.clear(); };
    rt.stops.add(stop); return () => { stop(); rt.stops.delete(stop); };
  }, [rt]);
  React.useEffect(() => {
    const controller = life.controller(); setLayout(null);
    const read = (operation, parameters) => context.representations.read(artifact.id, REPRESENTATION, { operation, parameters }, controller.signal).then((result) => {
      if (result.consistency !== "durable_snapshot" || result.source_version !== String(payload.revision) || result.source_fingerprint !== payload.content_hash) throw new Error("成果表示与固定修订不一致。");
      return result.payload;
    });
    Promise.all([read("sheet_layout", tagId ? { tag_id: tagId } : {}), read("metadata", { kind: "tags", page: 0, page_size: 16 })]).then(([next, tagPage]) => {
      if (!life.valid() || controller.signal.aborted) return;
      setLayout(next); setTags(tagPage.items); setFrameId((id) => next.frames.some((frame) => frame.frame_id === id) ? id : next.frames[0].frame_id);
    }).catch((caught) => { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); }).finally(() => life.release(controller));
    return () => controller.abort();
  }, [life, artifact.id, payload.revision, payload.content_hash, context.representations, tagId]);
  React.useEffect(() => {
    if (!frameId) return undefined;
    const controller = life.controller(); let objectUrl;
    setUrl("");
    context.representations.stream(artifact.id, REPRESENTATION, { operation: "png", parameters: { frame_id: frameId } }, controller.signal).then((blob) => {
      if (!life.valid() || controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob); owned.current.add(objectUrl); setUrl(objectUrl);
    }).catch((caught) => { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); }).finally(() => life.release(controller));
    return () => { controller.abort(); if (objectUrl && owned.current.delete(objectUrl)) URL.revokeObjectURL(objectUrl); };
  }, [life, artifact.id, frameId, context.representations]);
  async function download(operation) {
    if (!life.valid() || working.current) return;
    working.current = true; setBusy(true); setError("");
    const controller = life.controller();
    try {
      const blob = await context.representations.stream(artifact.id, REPRESENTATION, { operation, parameters: operation === "png" ? { frame_id: frameId } : tagId ? { tag_id: tagId } : {} }, controller.signal);
      if (!life.valid() || controller.signal.aborted) return;
      if (lastDownload.current && owned.current.delete(lastDownload.current)) URL.revokeObjectURL(lastDownload.current);
      const href = URL.createObjectURL(blob); owned.current.add(href); lastDownload.current = href;
      const anchor = document.createElement("a"); anchor.href = href; anchor.download = `${payload.document_id}-r${payload.revision}-${operation}.png`; anchor.click();
      context.onToast("已交给浏览器下载，请选择保存位置。");
    } catch (caught) { if (life.valid() && !controller.signal.aborted) setError(errorText(caught)); }
    finally { life.release(controller); working.current = false; if (life.valid()) setBusy(false); }
  }
  return h("article", { className: "dbfox-pixel dbfox-pixel__artifact" }, h("header", { className: "dbfox-pixel__row" }, icon(), h("h3", null, `${payload.title} · r${payload.revision}`), h("small", null, "固定修订")),
    h("p", null, `${payload.width} × ${payload.height} · ${payload.frame_count} 帧 · ${payload.layer_count} 层`),
    url ? h("img", { className: "dbfox-pixel__artifact-image", src: url, alt: `${payload.title} ${frameId} 固定 r${payload.revision}` }) : h("p", { role: "status" }, "读取成果预览…"),
    h("div", { className: "dbfox-pixel__row" }, h("select", { "aria-label": "成果动画标签", value: tagId, disabled: busy, onChange: (event) => setTagId(event.target.value) }, h("option", { value: "" }, "全部帧"), tags.map((tag) => h("option", { key: tag.id, value: tag.id }, tag.name))),
      h("select", { "aria-label": "成果预览帧", value: frameId, disabled: busy || !layout, onChange: (event) => setFrameId(event.target.value) }, layout?.frames.map((frame, index) => h("option", { key: frame.frame_id, value: frame.frame_id }, `${index + 1} · ${frame.duration_ms} ms`)))),
    layout ? h("small", null, `Sprite Sheet ${layout.width} × ${layout.height} · ${layout.frames.length} 帧按标签顺序横向排列`) : null,
    h("div", { className: "dbfox-pixel__row" }, button("下载当前帧 PNG", () => download("png"), busy || !frameId), button("下载 Sprite Sheet", () => download("sheet"), busy || !layout), button("编辑当前作品", () => openWorkbench(rt, payload.project_id, payload), busy)),
    error ? h("p", { role: "alert", className: "dbfox-pixel__error" }, error) : null);
}

export function register(host) {
  if (runtime) { runtime.active = false; for (const stop of runtime.stops) stop(); runtime.stops.clear(); }
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("Pixel Studio requires the public Host React API.");
  const rt = { host, active: true, stops: new Set(), epoch: ++epoch }; runtime = rt;
  if (typeof document !== "undefined") { stylesheet?.remove(); stylesheet = document.createElement("link"); stylesheet.rel = "stylesheet"; stylesheet.href = new URL("./index.css", import.meta.url).href; stylesheet.dataset.dbfoxDlc = "dbfox.pixel"; document.head.append(stylesheet); }
  host.connectors.register({ id: "dbfox.pixel", title: "Pixel Studio", icon: icon(), addLabel: "创建像素作品", onAdd: ({ projectId }) => openWorkbench(rt, projectId),
    render: ({ projectId }) => h("div", { className: "dbfox-pixel dbfox-pixel__connector" }, h("p", null, "像素画 · 图层 · Sprite 动画"), button("打开 Pixel Studio", () => openWorkbench(rt, projectId))),
    listResources: async ({ projectId }) => (await listDocuments((name, input, signal) => rt.host.operations.invoke(name, input, { projectId, signal }))).map((item) => ({ kind: DOCUMENT, id: item.document_id, name: item.title, detail: `${item.width}×${item.height} · ${item.frame_count} 帧 · r${item.revision}` })),
  });
  host.dockViews.register({ viewType: VIEW, icon, resolveTitle: (view) => view.title, isVisible: (view, context) => view.projectId === context.activeProjectId,
    render: (view, context) => h(Studio, { key: `${rt.epoch}:${context.workbenchScopeId}:${view.projectId}:${view.viewKey}`, rt, projectId: view.projectId, initialId: view.target?.type === "object" ? view.target.object.id : "", context }) });
  host.artifactViews.register({ id: "dbfox.pixel.revision-view", title: "Pixel Sprite", priority: 100, surfaces: ["inline", "workspace"], artifactTypes: [{ type: ARTIFACT, schemaVersions: [1] }], representationTypes: [REPRESENTATION], parsePayload: parseSummary,
    render: (artifact, payload, context) => h(PixelArtifact, { key: `${rt.epoch}:${artifact.id}`, rt, artifact, payload, context }) });
}
export function deactivate() {
  if (runtime) { runtime.active = false; for (const stop of runtime.stops) stop(); runtime.stops.clear(); }
  stylesheet?.remove(); stylesheet = null;
}
