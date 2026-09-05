import { createVoxelViewport } from "./viewport.js";
import { WORLD_KIND, REPRESENTATION, axisIndex, planeAxes, loadWorld, loadSnapshot, snapshotFile, composeVisible, voxelAt, slicePoint, strokeBounds, validateBounds } from "./world-data.js";

const DLC_ID = "dbfox.voxel";
const VIEW = "dbfox.voxel.studio";
const ARTIFACT = "dbfox.voxel.snapshot";
let host;
let React;
const disposers = new Set();
const listeners = new Set();
const h = (...args) => React.createElement(...args);
const identity = () => crypto.randomUUID();
const message = (error) => error instanceof Error ? error.message : "操作未完成，请刷新当前版本。";
const notify = (projectId, worldId) => { for (const listener of listeners) listener(projectId, worldId); };

function own(cleanup) {
  let live = true;
  const dispose = () => { if (live) { live = false; disposers.delete(dispose); cleanup(); } };
  disposers.add(dispose);
  return dispose;
}

function Icon() {
  return h("svg", { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6, "aria-hidden": true },
    h("path", { d: "M12 2 22 7.5v9L12 22 2 16.5v-9L12 2Zm0 11L2 7.5M12 13l10-5.5M12 13v9M7 4.75l10 5.5" }));
}

function Button({ children, primary, ...props }) {
  return h("button", { type: "button", className: primary ? "voxel-button voxel-button--primary" : "voxel-button", ...props }, children);
}

function NumberField({ label, value, onChange, min = 0, max = 256, disabled }) {
  return h("label", { className: "voxel-field" }, h("span", null, label),
    h("input", { type: "number", step: 1, min, max, value, disabled, onChange: (event) => onChange(event.target.value === "" ? "" : Number(event.target.value)) }));
}

function openWorld(projectId, world = null) {
  const scope = host.workbench.currentScopeId();
  const id = world?.world_id || "new";
  host.dockViews.open({ viewKey: `voxel:${scope}:${projectId}:${id}`, viewType: VIEW,
    title: world?.title || "Voxel Studio", closeable: true, projectId,
    stateKey: `voxel:${scope}:${projectId}:${id}`,
    ...(world ? { target: { type: "object", object: { kind: WORLD_KIND, id, version: world.version },
      authority: { kind: WORLD_KIND, id } } } : {}),
  });
}

async function listWorlds(projectId, signal) {
  const worlds = [];
  let after = null;
  const seen = new Set();
  do {
    const page = await host.operations.invoke("worlds.list", { limit: 32, after }, { projectId, signal });
    if (!Array.isArray(page.worlds) || worlds.length + page.worlds.length > 128) throw new Error("世界目录超过加载上限。");
    worlds.push(...page.worlds);
    after = page.next_after;
    if (after != null) {
      if (seen.has(after)) throw new Error("世界目录分页重复。");
      seen.add(after);
    }
  } while (after != null);
  return worlds;
}

function Connector({ projectId }) {
  const [worlds, setWorlds] = React.useState([]);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [epoch, setEpoch] = React.useState(0);
  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    listWorlds(projectId, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setWorlds(result); setError(""); }
    }).catch((reason) => { if (!controller.signal.aborted) setError(message(reason)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return own(() => controller.abort());
  }, [projectId, epoch]);
  React.useEffect(() => {
    const changed = (project) => { if (project === projectId) setEpoch((value) => value + 1); };
    listeners.add(changed);
    return own(() => listeners.delete(changed));
  }, [projectId]);
  const root = { world_id: "root", title: "体素世界", children: worlds };
  return h("section", { className: "dbfox-voxel voxel-connector", "aria-label": "体素世界目录" },
    loading ? h("p", { role: "status" }, "正在读取体素世界…") : null,
    worlds.length ? h(host.ui.Tree, {
      rootItem: root, ariaLabel: "体素世界", getItemId: (item) => item.world_id,
      getItemLabel: (item) => item.title, getItemChildren: (item) => item.children || [],
      renderItemIcon: () => h(Icon), renderItemMeta: (item) => item.version ? h("small", null, `v${item.version}`) : null,
      onItemSelect: (item) => { if (item.world_id !== "root") openWorld(projectId, item); },
    }) : !loading ? h("p", { className: "voxel-muted" }, "还没有世界。创建画布，开始搭建。") : null,
    h(Button, { onClick: () => openWorld(projectId) }, "新建体素世界"),
    error ? h("div", { role: "alert" }, error, h(Button, { onClick: () => setEpoch((value) => value + 1) }, "刷新目录")) : null);
}

function CreateWorld({ projectId, onCreated }) {
  const [title, setTitle] = React.useState("我的体素世界");
  const [size, setSize] = React.useState([64, 64, 64]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const pending = React.useRef(false);
  const alive = React.useRef(true);
  const abort = React.useRef(null);
  React.useEffect(() => { alive.current = true; return own(() => { alive.current = false; abort.current?.abort(); }); }, []);
  async function create(event) {
    event.preventDefault();
    if (pending.current) return;
    if (!title.trim() || size.some((n) => !Number.isInteger(n) || n < 1 || n > 256)) {
      setError("请输入名称和 1–256 之间的整数尺寸。"); return;
    }
    pending.current = true; setBusy(true); setError("");
    abort.current = new AbortController();
    try {
      const result = await host.operations.invoke("worlds.create", { title: title.trim(), size,
        expected_version: 0, mutation_id: identity() }, { projectId, signal: abort.current.signal });
      if (alive.current) { notify(projectId, result.world_id); onCreated(result); }
    } catch (reason) {
      if (alive.current) setError(`创建结果未确认。请先刷新世界目录，避免重复创建。${message(reason)}`);
    } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return h("form", { className: "dbfox-voxel voxel-create", onSubmit: create },
    h(Icon), h("h2", null, "从一块方块开始"), h("p", { className: "voxel-muted" }, "搭建体素世界，在三维中环绕检查，在切片中精确绘制。"),
    h("label", { className: "voxel-field" }, h("span", null, "世界名称"), h("input", { value: title, maxLength: 80, onChange: (event) => setTitle(event.target.value), disabled: busy })),
    h("div", { className: "voxel-vector" }, ...["宽 X", "高 Y", "深 Z"].map((label, i) => h(NumberField, { key: label, label, value: size[i], min: 1, max: 256, disabled: busy,
      onChange: (value) => setSize((current) => current.map((n, j) => i === j ? value : n)) }))),
    h(Button, { type: "submit", primary: true, disabled: busy }, busy ? "正在创建…" : "创建世界"),
    error ? h("p", { role: "alert" }, error) : null);
}

function SliceCanvas({ snapshot, activeLayer, brush, axis, slice, mode, disabled, locked, selection, setSelection, perform, interaction }) {
  const canvasRef = React.useRef(null);
  const baseCanvasRef = React.useRef(null);
  const strokeRef = React.useRef(null);
  const [preview, setPreview] = React.useState(null);
  const [cursor, setCursor] = React.useState([0, 0]);
  const [a, b] = planeAxes(axis);
  const size = snapshot.world.document.size;
  const columns = size[a]; const rows = size[b];
  const pixelScale = Math.max(1, Math.min(16, 768 / Math.max(columns, rows)));
  const width = Math.round(columns * pixelScale);
  const height = Math.round(rows * pixelScale);
  React.useEffect(() => {
    strokeRef.current = null; setPreview(null); interaction.current = false;
    setCursor((current) => [Math.min(current[0], columns - 1), Math.min(current[1], rows - 1)]);
  }, [axis, slice, activeLayer, columns, rows, interaction]);
  React.useEffect(() => () => { interaction.current = false; }, [interaction]);
  React.useEffect(() => {
    const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
    baseCanvasRef.current = canvas;
    const context = canvas?.getContext("2d");
    if (!context) return;
    const colors = new Map(snapshot.world.document.palette.map((entry) => [entry.index, entry.color]));
    const unitX = width / columns; const unitY = height / rows;
    for (let v = 0; v < rows; v += 1) {
      for (let u = 0; u < columns; u += 1) {
        const index = voxelAt(snapshot.chunks, activeLayer, slicePoint(axis, slice, u, v));
        if (index) { context.fillStyle = colors.get(index); context.fillRect(u * unitX, (rows - 1 - v) * unitY, unitX + 0.2, unitY + 0.2); }
      }
    }
    if (columns <= 128 && rows <= 128) {
      context.strokeStyle = "rgba(128,144,164,0.22)"; context.lineWidth = 1;
      context.beginPath();
      for (let u = 0; u <= columns; u += 1) { context.moveTo(u * unitX, 0); context.lineTo(u * unitX, height); }
      for (let v = 0; v <= rows; v += 1) { context.moveTo(0, v * unitY); context.lineTo(width, v * unitY); }
      context.stroke();
    }
    return () => { canvas.width = 1; canvas.height = 1; baseCanvasRef.current = null; };
  }, [snapshot, activeLayer, axis, slice, width, height, columns, rows]);
  React.useEffect(() => {
    const context = canvasRef.current?.getContext("2d");
    if (!context) return;
    const unitX = width / columns; const unitY = height / rows;
    context.clearRect(0, 0, width, height);
    if (baseCanvasRef.current) context.drawImage(baseCanvasRef.current, 0, 0);
    const region = preview || selection;
    if (region && slice >= region.min[axisIndex(axis)] && slice < region.max[axisIndex(axis)]) {
      context.fillStyle = "rgba(34,211,238,0.15)"; context.strokeStyle = "#22d3ee"; context.lineWidth = 2;
      const x = region.min[a] * unitX; const y = (rows - region.max[b]) * unitY;
      const w = (region.max[a] - region.min[a]) * unitX; const ht = (region.max[b] - region.min[b]) * unitY;
      context.fillRect(x, y, w, ht); context.strokeRect(x + 1, y + 1, Math.max(w - 2, 0), Math.max(ht - 2, 0));
    }
    context.strokeStyle = "#fbbf24"; context.lineWidth = 2;
    context.strokeRect(cursor[0] * unitX + 1, (rows - cursor[1] - 1) * unitY + 1, Math.max(unitX - 2, 1), Math.max(unitY - 2, 1));
  });

  function point(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    return [Math.min(columns - 1, Math.max(0, Math.floor((event.clientX - rect.left) / Math.max(rect.width, 1) * columns))),
      Math.min(rows - 1, Math.max(0, rows - 1 - Math.floor((event.clientY - rect.top) / Math.max(rect.height, 1) * rows)))];
  }
  function down(event) {
    if (event.button !== 0 || disabled || strokeRef.current) return;
    event.preventDefault(); event.currentTarget.focus();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const start = point(event);
    strokeRef.current = { start, end: start, version: snapshot.world.version, layer: activeLayer, brush, mode, pointer: event.pointerId };
    interaction.current = true; setCursor(start); setPreview(strokeBounds(axis, slice, start, start));
  }
  function move(event) {
    const next = point(event); setCursor(next);
    const stroke = strokeRef.current;
    if (!stroke || stroke.pointer !== event.pointerId) return;
    stroke.end = next; setPreview(strokeBounds(axis, slice, stroke.start, next));
  }
  function cancel() { strokeRef.current = null; interaction.current = false; setPreview(null); }
  function up(event) {
    const stroke = strokeRef.current;
    if (!stroke || stroke.pointer !== event.pointerId) return;
    const bounds = strokeBounds(axis, slice, stroke.start, point(event));
    cancel(); event.currentTarget.releasePointerCapture?.(event.pointerId);
    setSelection(bounds);
    if (stroke.mode !== "select") void perform("worlds.apply", { operation: { kind: "fill", layer_id: stroke.layer,
      bounds, palette_index: stroke.mode === "erase" ? 0 : stroke.brush } }, stroke.version);
  }
  function keydown(event) {
    if (disabled || strokeRef.current) return;
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    if (directions[event.key]) {
      event.preventDefault(); const [dx, dy] = directions[event.key];
      setCursor(([x, y]) => [Math.min(columns - 1, Math.max(0, x + dx)), Math.min(rows - 1, Math.max(0, y + dy))]);
    } else if (event.key === " " || event.key === "Delete") {
      event.preventDefault();
      if (event.repeat) return;
      const bounds = strokeBounds(axis, slice, cursor, cursor); setSelection(bounds);
      if (!locked && (mode !== "select" || event.key === "Delete")) void perform("worlds.apply", { operation: { kind: "fill", layer_id: activeLayer,
        bounds, palette_index: event.key === "Delete" || mode === "erase" ? 0 : brush } }, snapshot.world.version);
    } else if (event.key === "Escape") cancel();
  }
  return h("div", { className: "voxel-slice" },
    h("canvas", { ref: canvasRef, width, height, tabIndex: 0, role: "application",
      "aria-label": "体素切片：方向键移动，空格绘制或选择，Delete 擦除", "aria-disabled": disabled,
      style: { aspectRatio: `${columns} / ${rows}` }, onPointerDown: down, onPointerMove: move,
      onPointerUp: up, onPointerCancel: cancel, onLostPointerCapture: cancel, onKeyDown: keydown }),
    h("p", { className: "voxel-caption" }, `${["X", "Y", "Z"][a]} → · ${["X", "Y", "Z"][b]} ↑　`,
      `光标 ${slicePoint(axis, slice, ...cursor).join(", ")} · 当前层`,
      h("span", null, mode === "select" ? "拖动选择矩形；不会修改方块。" : mode === "erase" ? "拖动擦除矩形；释放后提交一次修改。" : "拖动填充矩形；释放后提交一次修改。")));
}

function Viewport({ projection, palette, selection, crop, viewportRef, onPick }) {
  const element = React.useRef(null);
  const pick = React.useRef(onPick);
  pick.current = onPick;
  const [status, setStatus] = React.useState("正在启动三维预览…");
  const [state, setState] = React.useState("loading");
  React.useLayoutEffect(() => {
    const viewport = createVoxelViewport(element.current, (text, kind) => { setStatus(text); setState(kind); }, (point) => pick.current?.(point));
    viewportRef.current = viewport;
    return own(() => { viewport?.dispose(); viewportRef.current = null; });
  }, [viewportRef]);
  React.useEffect(() => {
    if (projection) void viewportRef.current?.update(projection, palette, crop ? selection : null);
  }, [projection, palette, crop, crop ? selection : null, viewportRef]);
  React.useEffect(() => { viewportRef.current?.setSelection(selection); }, [selection, viewportRef]);
  return h("div", { className: "voxel-viewport-shell" },
    h("div", { className: "voxel-viewport", ref: element }),
    h("p", { className: `voxel-viewport-status voxel-viewport-status--${state}`, role: "status" }, status),
    h("div", { className: "voxel-view-actions" },
      h(Button, { onClick: () => viewportRef.current?.fit() }, "适合世界"),
      selection ? h(Button, { onClick: () => viewportRef.current?.fit(selection) }, "聚焦选区") : null));
}

function Studio({ projectId, worldId, context }) {
  const [snapshot, setSnapshot] = React.useState(null);
  const [readError, setReadError] = React.useState("");
  const [editError, setEditError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [progress, setProgress] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const [activeLayer, setActiveLayer] = React.useState("base");
  const [brush, setBrush] = React.useState(1);
  const [hidden, setHidden] = React.useState(new Set());
  const [axis, setAxis] = React.useState("y");
  const [slice, setSlice] = React.useState(0);
  const [mode, setMode] = React.useState("paint");
  const [selection, setSelection] = React.useState({ min: [0, 0, 0], max: [8, 1, 8] });
  const [crop, setCrop] = React.useState(false);
  const [projection, setProjection] = React.useState(null);
  const [shape, setShape] = React.useState("fill");
  const [hollow, setHollow] = React.useState(false);
  const [radius, setRadius] = React.useState(3);
  const [sourceLayer, setSourceLayer] = React.useState("base");
  const [booleanMode, setBooleanMode] = React.useState("union");
  const [directionAxis, setDirectionAxis] = React.useState("y");
  const [depth, setDepth] = React.useState(1);
  const [destination, setDestination] = React.useState([0, 0, 0]);
  const [fromIndex, setFromIndex] = React.useState(1);
  const [layerName, setLayerName] = React.useState("");
  const [paletteName, setPaletteName] = React.useState("");
  const [paletteColor, setPaletteColor] = React.useState("#22d3ee");
  const [regionName, setRegionName] = React.useState("");
  const [revisions, setRevisions] = React.useState([]);
  const [targetVersion, setTargetVersion] = React.useState(1);
  const latest = React.useRef(null);
  const busyRef = React.useRef(false);
  const reading = React.useRef(false);
  const interaction = React.useRef(false);
  const alive = React.useRef(true);
  const generation = React.useRef(0);
  const readAbort = React.useRef(null);
  const actionAbort = React.useRef(null);
  const historyAbort = React.useRef(null);
  const viewportRef = React.useRef(null);
  const refreshRef = React.useRef(null);

  async function refresh(force = false) {
    if (!alive.current || (!force && (busyRef.current || interaction.current || reading.current))) return false;
    readAbort.current?.abort(); const controller = new AbortController(); readAbort.current = controller;
    const epoch = ++generation.current; reading.current = true; setLoading(true); setProgress(0);
    try {
      const next = await loadWorld((name, input, signal) => host.operations.invoke(name, input, { projectId, signal }), worldId,
        { previous: latest.current, signal: controller.signal, onProgress: (count) => { if (alive.current && generation.current === epoch) setProgress(count); } });
      if (!alive.current || epoch !== generation.current) return false;
      latest.current = next; setSnapshot(next); setReadError("");
      return true;
    } catch (reason) {
      if (alive.current && epoch === generation.current && reason.name !== "AbortError") setReadError(message(reason));
      return false;
    } finally {
      if (alive.current && epoch === generation.current) { reading.current = false; setLoading(false); }
    }
  }
  refreshRef.current = refresh;
  React.useEffect(() => {
    alive.current = true; void refreshRef.current(true);
    const changed = (project, world) => { if (project === projectId && (!world || world === worldId)) void refreshRef.current(); };
    const focus = () => { void refreshRef.current(); };
    listeners.add(changed); window.addEventListener("focus", focus);
    const timer = setInterval(() => { if (document.visibilityState !== "hidden") void refreshRef.current(); }, 3000);
    return own(() => { alive.current = false; generation.current += 1; readAbort.current?.abort(); actionAbort.current?.abort(); historyAbort.current?.abort();
      clearInterval(timer); listeners.delete(changed); window.removeEventListener("focus", focus); });
  }, [projectId, worldId]);
  React.useEffect(() => () => actionAbort.current?.abort(), [context.workbenchScopeId]);
  React.useEffect(() => {
    if (!snapshot) return;
    const doc = snapshot.world.document;
    setActiveLayer((value) => doc.layers.some((layer) => layer.id === value) ? value : doc.layers[0].id);
    setSourceLayer((value) => doc.layers.some((layer) => layer.id === value) ? value : doc.layers[0].id);
    setBrush((value) => doc.palette.some((entry) => entry.index === value) ? value : doc.palette[0].index);
    setSlice((value) => Math.min(Math.max(value, 0), doc.size[axisIndex(axis)] - 1));
    setSelection((bounds) => ({ min: bounds.min.map((n, i) => Math.min(Math.max(Number(n) || 0, 0), doc.size[i] - 1)),
      max: bounds.max.map((n, i) => Math.min(Math.max(Number(n) || 1, 1), doc.size[i])) }));
  }, [snapshot, axis]);
  React.useEffect(() => {
    if (!snapshot) return;
    const controller = new AbortController();
    composeVisible(snapshot, hidden, controller.signal).then((result) => { if (!controller.signal.aborted && alive.current) setProjection(result); })
      .catch((error) => { if (error.name !== "AbortError" && alive.current) setReadError("无法构建世界显示数据。"); });
    return own(() => controller.abort());
  }, [snapshot, hidden]);

  async function perform(name, values, expectedVersion = latest.current?.world.version) {
    if (busyRef.current || !latest.current || !alive.current) return;
    if (readError || expectedVersion !== latest.current.world.version) { setEditError("显示版本已改变，请重新选择后操作。"); return; }
    busyRef.current = true; setBusy(true); setEditError(""); setNotice("");
    actionAbort.current = new AbortController();
    try {
      const result = await host.operations.invoke(name, { world_id: worldId, expected_version: expectedVersion,
        mutation_id: identity(), ...values }, { projectId, signal: actionAbort.current.signal });
      if (!alive.current) return;
      await refresh(true);
      if (alive.current) {
        setNotice(result.changed === false ? "内容相同，版本保持不变。" : `已保存版本 ${result.version}。`);
        notify(projectId, worldId);
      }
    } catch (reason) {
      if (!alive.current) return;
      setEditError(`修改未确认。正在检查当前版本，请勿重复提交。${message(reason)}`);
      const refreshed = await refresh(true);
      if (alive.current) setEditError(`修改未确认。${refreshed ? "已重新读取当前版本，请检查后再次操作。" : "当前版本读取失败，请先刷新。"}${message(reason)}`);
    } finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }

  async function snapshotArtifact() {
    if (busyRef.current || !latest.current || !alive.current) return;
    const navigationHost = host;
    if (!navigationHost.workbench.openArtifact) {
      setEditError("当前 Host 尚不支持从工作台打开成果；未创建快照。");
      return;
    }
    const workbenchScopeId = context.workbenchScopeId;
    busyRef.current = true; setBusy(true); setEditError("");
    const controller = new AbortController(); actionAbort.current = controller;
    let saved = false;
    try {
      const result = await navigationHost.operations.invoke("worlds.snapshot", { world_id: worldId, version: latest.current.world.version, mutation_id: identity() },
        { projectId, signal: controller.signal });
      saved = true;
      if (!alive.current) return;
      controller.signal.throwIfAborted();
      if (!result.artifact_ids?.[0]) throw new Error("快照操作未返回成果标识。");
      await navigationHost.workbench.openArtifact({ projectId, sessionId: result.session_id, runId: result.run_id, artifactId: result.artifact_ids[0] },
        { workbenchScopeId, signal: controller.signal });
      if (alive.current && !controller.signal.aborted) setNotice("不可变世界快照已保存并打开。");
    } catch (reason) { if (alive.current) setEditError(`${saved ? "快照已保存，但打开成果未完成。" : "快照结果未确认，请先检查工作成果。"}${message(reason)}`); }
    finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }

  function applyShape() {
    if (!snapshot) return;
    try {
      const bounds = validateBounds(selection, snapshot.world.document.size);
      let operation;
      if (shape === "sphere") {
        const center = bounds.min.map((n, i) => Math.floor((n + bounds.max[i] - 1) / 2));
        if (!Number.isInteger(radius) || radius < 0 || radius > 127 || center.some((n, i) => n - radius < 0 || n + radius >= snapshot.world.document.size[i]))
          throw new Error("球体中心位于选区中心；半径必须为整数且整个球体位于世界内。");
        operation = { kind: shape, layer_id: activeLayer, center, radius, palette_index: brush, hollow };
      } else if (shape === "replace") operation = { kind: shape, layer_id: activeLayer, bounds, from_index: fromIndex, to_index: brush };
      else if (shape === "boolean") operation = { kind: shape, layer_id: activeLayer, source_layer_id: sourceLayer, bounds, mode: booleanMode };
      else if (shape === "copy_region" || shape === "mirror") {
        if (destination.some((n, i) => !Number.isInteger(n) || n < 0 || n + bounds.max[i] - bounds.min[i] > snapshot.world.document.size[i])) throw new Error("复制目标超出世界边界。");
        operation = { kind: shape, layer_id: activeLayer, source_layer_id: sourceLayer, bounds, destination,
          ...(shape === "mirror" ? { axis: directionAxis } : {}) };
      } else if (shape === "extrude") {
        const index = axisIndex(directionAxis);
        if (!Number.isInteger(depth) || depth < 1 || depth > 255 || bounds.max[index] - bounds.min[index] !== 1
          || bounds.max[index] + depth > snapshot.world.document.size[index]) throw new Error("拉伸需要单格厚选区和世界内的正向深度。");
        operation = { kind: shape, layer_id: activeLayer, source_layer_id: sourceLayer, bounds, axis: directionAxis, depth, direction: 1 };
      }
      else operation = { kind: shape, layer_id: activeLayer, bounds, palette_index: brush, ...(shape === "box" ? { hollow } : {}) };
      void perform("worlds.apply", { operation });
    } catch (error) { setEditError(message(error)); }
  }

  if (!snapshot) return h("section", { className: "dbfox-voxel voxel-studio" },
    h("p", { role: readError ? "alert" : "status" }, readError || `正在加载世界… ${progress} 个分块`),
    readError ? h(Button, { onClick: () => void refresh(true) }, "重新读取世界") : null);
  const world = snapshot.world; const doc = world.document;
  const layer = doc.layers.find((item) => item.id === activeLayer) || doc.layers[0];
  const disabled = busy || loading || Boolean(readError);
  const editDisabled = disabled || layer.locked;
  const selectedEntry = doc.palette.find((entry) => entry.index === brush);
  const sourceRequired = ["copy_region", "mirror", "extrude", "boolean"].includes(shape);
  function ask() {
    try {
      const bounds = validateBounds(selection, doc.size);
      context.onAsk({ label: `${world.title} · ${layer.name} · 选区`, authority: { kind: WORLD_KIND, id: worldId },
        object: { kind: "dbfox.voxel.layer", id: layer.id, version: world.version }, locator: `bounds=${JSON.stringify(bounds)}` });
    } catch (error) { setEditError(message(error)); }
  }

  return h("section", { className: "dbfox-voxel voxel-studio", "aria-label": "Voxel Studio" },
    h("header", { className: "voxel-header" }, h(Icon), h("div", null, h("h2", null, world.title),
      h("p", { className: "voxel-muted" }, `${doc.size.join(" × ")} · ${world.nonzero_count.toLocaleString()} 个方块 · v${world.version}`)),
      h("span", { className: "voxel-version", role: "status" }, busy ? "正在保存…" : loading ? `同步 ${progress} 分块` : "已同步")),
    h("div", { className: "voxel-toolbar", role: "toolbar", "aria-label": "世界操作" },
      h(Button, { disabled: busy || loading, onClick: () => void refresh(true) }, "刷新"),
      h(Button, { disabled: disabled || !world.parent_version, onClick: () => void perform("worlds.undo", { target_version: world.parent_version }) }, `撤销${world.parent_version ? `到 v${world.parent_version}` : ""}`),
      h(Button, { disabled, onClick: () => void snapshotArtifact() }, "保存快照"),
      h(Button, { disabled, onClick: ask }, "询问 DBFox")),
    readError ? h("p", { className: "voxel-error", role: "alert" }, readError) : null,
    editError ? h("p", { className: "voxel-error", role: "alert" }, editError) : null,
    notice ? h("p", { className: "voxel-notice", role: "status" }, notice) : null,
    h(Viewport, { projection, palette: doc.palette, selection, crop, viewportRef, onPick: (point) => {
      if (disabled) return;
      setSelection({ min: point, max: point.map((n) => n + 1) });
      setSlice(point[axisIndex(axis)]);
      setMode("select");
    } }),
    h("label", { className: "voxel-check" }, h("input", { type: "checkbox", checked: crop, onChange: (event) => setCrop(event.target.checked) }), "仅预览选区"),
    h("div", { className: "voxel-editor" },
      h("div", { className: "voxel-editor-main" },
        h("div", { className: "voxel-section-title" }, h("h3", null, "切片画布"), h("span", { className: "voxel-muted" }, `${layer.name}${layer.locked ? " · 已锁定" : ""}`)),
        h("div", { className: "voxel-toolbar", role: "toolbar", "aria-label": "切片工具" },
          ...[["paint", "绘制矩形"], ["erase", "擦除矩形"], ["select", "选择区域"]].map(([value, label]) =>
            h(Button, { key: value, "aria-pressed": mode === value, disabled, onClick: () => setMode(value) }, label))),
        h("div", { className: "voxel-slice-controls" },
          h("label", { className: "voxel-field" }, h("span", null, "切片轴"), h("select", { value: axis, disabled, onChange: (event) => setAxis(event.target.value) },
            ...["x", "y", "z"].map((value) => h("option", { key: value, value }, value.toUpperCase())))),
          h(NumberField, { label: "切片位置", value: slice, max: doc.size[axisIndex(axis)] - 1, disabled,
            onChange: (value) => { if (Number.isInteger(value) && value >= 0 && value < doc.size[axisIndex(axis)]) setSlice(value); } }),
          h("input", { type: "range", "aria-label": "切片位置滑块", min: 0, max: doc.size[axisIndex(axis)] - 1,
            value: slice, disabled, onChange: (event) => setSlice(Number(event.target.value)) })),
        layer.locked ? h("p", { className: "voxel-muted" }, "当前层已锁定，仍可选择区域。解锁后可绘制。") : null,
        h(SliceCanvas, { key: `${worldId}:${activeLayer}`, snapshot, activeLayer, brush, axis, slice, mode,
          disabled: disabled || (layer.locked && mode !== "select"), locked: layer.locked, selection, setSelection, perform, interaction })),
      h("aside", { className: "voxel-inspector", "aria-label": "体素编辑设置" },
        h("section", { className: "voxel-section" }, h("h3", null, "方块调色板"),
          h("div", { className: "voxel-palette", role: "group", "aria-label": "选择方块颜色" },
            ...doc.palette.map((entry) => h("button", { key: entry.index, type: "button", className: `voxel-swatch${entry.index === 0 ? " voxel-swatch--air" : ""}`,
              style: { backgroundColor: entry.index === 0 ? undefined : entry.color }, "aria-label": `${entry.name} (${entry.index})`, title: `${entry.name} · ${entry.color}`,
              "aria-pressed": brush === entry.index, disabled, onClick: () => setBrush(entry.index) },
              h("span", { "aria-hidden": true }, entry.index === 0 ? "×" : entry.index)))),
          h("p", { className: "voxel-caption" }, selectedEntry ? `${selectedEntry.name} · ${selectedEntry.color}` : "选择一个方块"),
          h("details", null, h("summary", null, "添加颜色"),
            h("label", { className: "voxel-field" }, "颜色名称", h("input", { value: paletteName, maxLength: 80, disabled, onChange: (event) => setPaletteName(event.target.value) })),
            h("label", { className: "voxel-field" }, "颜色", h("input", { type: "color", value: paletteColor, disabled, onChange: (event) => setPaletteColor(event.target.value) })),
            h(Button, { disabled: disabled || !paletteName.trim() || doc.palette.length >= 256, onClick: () => {
              const used = new Set(doc.palette.map((entry) => entry.index)); let index = 1; while (used.has(index)) index += 1;
              void perform("worlds.configure", { operation: { kind: "palette_put", entry: { index, name: paletteName.trim(), color: paletteColor } } });
            } }, "添加调色板颜色"))),
        h("section", { className: "voxel-section" }, h("h3", null, "图层"),
          h("p", { className: "voxel-caption" }, "上层覆盖下层；显示开关仅影响预览。"),
          h("div", { className: "voxel-layers" }, ...[...doc.layers].reverse().map((item) => h("div", { key: item.id, className: "voxel-layer" },
            h("input", { type: "checkbox", "aria-label": `显示 ${item.name}`, checked: !hidden.has(item.id), onChange: () => setHidden((values) => {
              const next = new Set(values); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next;
            }) }),
            h(Button, { "aria-pressed": activeLayer === item.id, onClick: () => setActiveLayer(item.id), disabled }, item.name),
            h(Button, { "aria-label": `${item.locked ? "解锁" : "锁定"} ${item.name}`, disabled,
              onClick: () => void perform("worlds.configure", { operation: { kind: "layer_put", layer: { ...item, locked: !item.locked } } }) }, item.locked ? "已锁定" : "锁定")))),
          h("div", { className: "voxel-inline" }, h("input", { "aria-label": "新图层名称", placeholder: "新图层名称", value: layerName, maxLength: 80, disabled,
            onChange: (event) => setLayerName(event.target.value) }),
            h(Button, { disabled: disabled || !layerName.trim() || doc.layers.length >= 16, onClick: () => void perform("worlds.configure",
              { operation: { kind: "layer_put", layer: { id: `layer_${identity().replaceAll("-", "")}`, name: layerName.trim(), locked: false } } }) }, "添加层"))),
        h("section", { className: "voxel-section" }, h("h3", null, "选区与形状"),
          h("p", { className: "voxel-caption" }, "起点包含，终点不包含。也可在切片中拖动选择。"),
          ...["min", "max"].map((end) => h("fieldset", { key: end, className: "voxel-bounds" }, h("legend", null, end === "min" ? "起点" : "终点"),
            ...["X", "Y", "Z"].map((label, i) => h(NumberField, { key: label, label: `${end === "min" ? "起点" : "终点"} ${label}`, value: selection[end][i], min: end === "min" ? 0 : 1,
              max: doc.size[i] - (end === "min" ? 1 : 0), disabled, onChange: (value) => setSelection((bounds) => ({ ...bounds,
                [end]: bounds[end].map((n, j) => i === j ? value : n) })) })))),
          h("label", { className: "voxel-field" }, "操作", h("select", { "aria-label": "选区操作", value: shape, disabled, onChange: (event) => setShape(event.target.value) },
            ...[["fill", "填充"], ["box", "盒体"], ["sphere", "球体"], ["replace", "替换颜色"], ["copy_region", "复制区域"], ["mirror", "镜像"], ["extrude", "拉伸"], ["boolean", "布尔运算"]]
              .map(([value, label]) => h("option", { key: value, value }, label)))),
          ["box", "sphere"].includes(shape) ? h("label", { className: "voxel-check" }, h("input", { type: "checkbox", checked: hollow, disabled, onChange: (event) => setHollow(event.target.checked) }), "空心（保留内部原内容）") : null,
          shape === "sphere" ? h(NumberField, { label: "球体半径", value: radius, max: 127, disabled, onChange: setRadius }) : null,
          shape === "replace" ? h("label", { className: "voxel-field" }, "替换来源颜色", h("select", { value: fromIndex, disabled, onChange: (event) => setFromIndex(Number(event.target.value)) },
            ...doc.palette.map((entry) => h("option", { key: entry.index, value: entry.index }, entry.name)))) : null,
          sourceRequired ? h("label", { className: "voxel-field" }, "来源图层", h("select", { value: sourceLayer, disabled, onChange: (event) => setSourceLayer(event.target.value) },
            ...doc.layers.map((item) => h("option", { key: item.id, value: item.id }, item.name)))) : null,
          ["mirror", "extrude"].includes(shape) ? h("label", { className: "voxel-field" }, "操作轴", h("select", { value: directionAxis, disabled, onChange: (event) => setDirectionAxis(event.target.value) },
            ...["x", "y", "z"].map((value) => h("option", { key: value, value }, value.toUpperCase())))) : null,
          shape === "extrude" ? h("div", null, h(NumberField, { label: "正向拉伸深度", min: 1, max: 255, value: depth, disabled, onChange: setDepth }),
            h("p", { className: "voxel-caption" }, "来源选区在操作轴上必须仅一格厚。")) : null,
          ["mirror", "copy_region"].includes(shape) ? h("div", { className: "voxel-vector" }, ...["X", "Y", "Z"].map((label, i) => h(NumberField, { key: label,
            label: `目标 ${label}`, value: destination[i], max: doc.size[i] - 1, disabled, onChange: (value) => setDestination((values) => values.map((n, j) => j === i ? value : n)) }))) : null,
          shape === "boolean" ? h("label", { className: "voxel-field" }, "布尔方式", h("select", { value: booleanMode, disabled, onChange: (event) => setBooleanMode(event.target.value) },
            ...[["union", "并集"], ["intersection", "交集"], ["difference", "差集"], ["xor", "异或"]].map(([value, label]) => h("option", { key: value, value }, label)))) : null,
          h(Button, { primary: true, disabled: editDisabled, onClick: applyShape }, "应用到选区")),
        h("details", { className: "voxel-section" }, h("summary", null, "命名区域与历史版本"),
          h("div", { className: "voxel-inline" }, h("input", { "aria-label": "区域名称", placeholder: "区域名称", value: regionName, maxLength: 80, disabled,
            onChange: (event) => setRegionName(event.target.value) }),
            h(Button, { disabled: disabled || !regionName.trim() || doc.regions.length >= 128, onClick: () => {
              try { validateBounds(selection, doc.size); void perform("worlds.configure", { operation: { kind: "region_put", region:
                { id: `region_${identity().replaceAll("-", "")}`, name: regionName.trim(), bounds: selection } } }); }
              catch (error) { setEditError(message(error)); }
            } }, "保存选区")),
          ...doc.regions.map((region) => h(Button, { key: region.id, disabled, onClick: () => setSelection(region.bounds) }, region.name)),
          h(Button, { disabled, onClick: async () => {
            historyAbort.current?.abort(); const controller = new AbortController(); historyAbort.current = controller;
            try { const result = await host.operations.invoke("worlds.revisions", { world_id: worldId, limit: 32 }, { projectId, signal: controller.signal });
              if (alive.current && !controller.signal.aborted) {
                setRevisions(result.revisions);
                setTargetVersion(result.revisions.find((revision) => revision.version === world.parent_version)?.version || result.revisions[0]?.version || 1);
              } }
            catch (error) { if (alive.current && !controller.signal.aborted) setEditError(message(error)); }
          } }, "读取最近版本"),
          revisions.length ? h("div", { className: "voxel-inline" }, h("select", { "aria-label": "恢复目标版本", value: targetVersion, disabled,
            onChange: (event) => setTargetVersion(Number(event.target.value)) }, ...revisions.map((revision) => h("option", { key: revision.version, value: revision.version }, `v${revision.version}`))),
            h(Button, { disabled, onClick: () => void perform("worlds.undo", { target_version: targetVersion }) }, "恢复这个版本")) : null))));
}

function Workbench({ view, context }) {
  const [created, setCreated] = React.useState(null);
  const worldId = view.target?.type === "object" && view.target.object.kind === WORLD_KIND ? view.target.object.id : created?.world_id;
  const projectId = view.projectId || context.activeProjectId;
  if (!worldId) return h(CreateWorld, { projectId, onCreated: (world) => {
    setCreated(world);
    host.dockViews.open({ ...view, title: world.title, projectId,
      target: { type: "object", object: { kind: WORLD_KIND, id: world.world_id, version: world.version }, authority: { kind: WORLD_KIND, id: world.world_id } } });
  } });
  return h(Studio, { key: `${projectId}:${worldId}`, projectId, worldId, context });
}

function SnapshotViewer({ artifact, payload, context }) {
  const [snapshot, setSnapshot] = React.useState(null);
  const [projection, setProjection] = React.useState(null);
  const [error, setError] = React.useState("");
  const [attempt, setAttempt] = React.useState(0);
  const [hidden, setHidden] = React.useState(new Set());
  const viewportRef = React.useRef(null);
  const downloadUrl = React.useRef(null);
  const alive = React.useRef(true);
  React.useEffect(() => {
    alive.current = true;
    return own(() => {
      alive.current = false;
      if (downloadUrl.current) { URL.revokeObjectURL(downloadUrl.current); downloadUrl.current = null; }
    });
  }, []);
  React.useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null); setProjection(null); setError(""); setHidden(new Set());
    loadSnapshot(context.representations, artifact.id, payload, controller.signal).then((next) => {
      if (alive.current && !controller.signal.aborted) setSnapshot(next);
    }).catch((reason) => { if (alive.current && !controller.signal.aborted) setError(message(reason)); });
    return own(() => controller.abort());
  }, [artifact.id, payload.version, payload.content_hash, context.representations, attempt]);
  React.useEffect(() => {
    if (!snapshot) return;
    const controller = new AbortController();
    composeVisible(snapshot, hidden, controller.signal).then((value) => {
      if (alive.current && !controller.signal.aborted) setProjection(value);
    }).catch((reason) => { if (alive.current && !controller.signal.aborted) setError(message(reason)); });
    return own(() => controller.abort());
  }, [snapshot, hidden]);
  function download() {
    if (!alive.current || !snapshot) return;
    try {
      const blob = snapshotFile(snapshot, artifact.id);
      if (downloadUrl.current) URL.revokeObjectURL(downloadUrl.current);
      const url = URL.createObjectURL(blob); downloadUrl.current = url;
      const anchor = document.createElement("a"); anchor.href = url;
      anchor.download = `${payload.world_id}-v${payload.version}.voxel.json`;
      anchor.click();
      context.onToast("已交给浏览器下载，请选择保存位置。");
    } catch (reason) { setError(message(reason)); }
  }
  return h("article", { className: "dbfox-voxel voxel-snapshot", "aria-label": "不可变体素快照" },
    h("header", { className: "voxel-header" }, h(Icon), h("div", null,
      h("h3", null, payload.title), h("p", { className: "voxel-muted" }, `不可变快照 · v${payload.version} · ${payload.size.join(" × ")}`))),
    h("p", { className: "voxel-caption" }, "显示导出时的固定版本。图层开关只影响预览，下载包含全部图层。"),
    h("div", { className: "voxel-toolbar" },
      h(Button, { onClick: download, disabled: !snapshot }, "下载世界快照 JSON"),
      h(Button, { onClick: () => openWorld(payload.project_id, payload) }, "打开当前世界")),
    snapshot ? h(React.Fragment, null,
      h(Viewport, { projection, palette: snapshot.world.document.palette, selection: null, crop: false, viewportRef }),
      h("div", { className: "voxel-snapshot-layers", role: "group", "aria-label": "快照图层显示" },
        ...snapshot.world.document.layers.map((layer) => h("label", { key: layer.id, className: "voxel-check" },
          h("input", { type: "checkbox", checked: !hidden.has(layer.id), onChange: () => setHidden((values) => {
            const next = new Set(values); if (next.has(layer.id)) next.delete(layer.id); else next.add(layer.id); return next;
          }) }), layer.name)))) : !error ? h("p", { role: "status" }, "正在读取固定版本的完整快照…") : null,
    error ? h("div", { className: "voxel-error", role: "alert" }, error,
      h(Button, { onClick: () => setAttempt((value) => value + 1) }, "重新读取快照")) : null);
}

function SnapshotCard({ artifact, payload, context }) {
  React.useEffect(() => { notify(payload.project_id, payload.world_id); }, [payload.project_id, payload.world_id, payload.version]);
  if (context.surface === "workspace") return h(SnapshotViewer, { key: artifact.id, artifact, payload, context });
  return h("article", { className: "dbfox-voxel voxel-artifact" }, h(Icon), h("div", null,
    h("strong", null, payload.title), h("p", { className: "voxel-muted" }, `不可变快照 · v${payload.version} · ${payload.size.join(" × ")}`),
    context.openArtifact ? h(Button, { onClick: () => context.openArtifact(artifact) }, "查看导出快照") : null,
    h(Button, { onClick: () => openWorld(payload.project_id, payload) }, "打开当前世界")));
}

export function register(extensionHost) {
  host = extensionHost;
  React = window.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("Voxel Studio requires the Host React SDK.");
  if (typeof document !== "undefined" && !document.querySelector('link[data-dbfox-dlc="dbfox.voxel"]')) {
    const link = document.createElement("link"); link.rel = "stylesheet"; link.href = new URL("./studio.css", import.meta.url).href;
    link.dataset.dbfoxDlc = DLC_ID; document.head.appendChild(link);
  }
  host.connectors.register({ id: DLC_ID, title: "体素世界", icon: h(Icon), render: ({ projectId }) => h(Connector, { projectId }),
    addLabel: "新建体素世界", onAdd: ({ projectId }) => openWorld(projectId),
    listResources: async ({ projectId }) => (await listWorlds(projectId)).map((world) => ({ kind: WORLD_KIND, id: world.world_id, name: world.title,
      detail: `${world.size.join(" × ")} · v${world.version}` })),
    removeResource: async ({ projectId }, resource) => {
      const world = await host.operations.invoke("worlds.get", { world_id: resource.id }, { projectId });
      await host.operations.invoke("worlds.delete", { world_id: resource.id, expected_version: world.version, mutation_id: identity() }, { projectId });
      notify(projectId, resource.id);
    },
  });
  host.dockViews.register({ viewType: VIEW, icon: () => h(Icon), resolveTitle: (view) => view.title || "Voxel Studio",
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view, context) => h(Workbench, { view, context }),
  });
  host.artifactViews.register({ id: ARTIFACT, title: "体素世界快照", surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: ARTIFACT, schemaVersions: [1] }],
    representationTypes: [REPRESENTATION],
    parsePayload: (value) => {
      if (!value || typeof value.world_id !== "string" || typeof value.project_id !== "string" || typeof value.title !== "string"
        || !Number.isInteger(value.version) || value.version < 1 || !Array.isArray(value.size) || value.size.length !== 3)
        throw new Error("Invalid Voxel snapshot payload");
      return value;
    },
    render: (artifact, payload, context) => h(SnapshotCard, { artifact, payload, context }),
  });
}

export function deactivate() {
  for (const dispose of [...disposers]) dispose();
  listeners.clear();
  if (typeof document !== "undefined") document.querySelector('link[data-dbfox-dlc="dbfox.voxel"]')?.remove();
}
