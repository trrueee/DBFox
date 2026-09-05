import { SCENE_KIND, LIBRARY_KIND, ARTIFACT_TYPE, REPRESENTATION_TYPE, requestId, listScenes, readScene, hierarchy, parentCandidates, referenceFor } from "./model.js";

const DLC_ID = "dbfox.scene";
const VIEW = "dbfox.scene.workbench";
const lifecycle = new Set();
let React;
let host;
let stylesheet;
let active = false;
const h = (...args) => React.createElement(...args);
const labels = { box: "立方体", sphere: "球体", cylinder: "圆柱", cone: "圆锥", plane: "平面", torus: "圆环", group: "组", point: "点光源", directional: "平行光", spot: "聚光灯", camera: "相机" };

function button(label, onClick, disabled = false, extra = {}) {
  return h("button", { type: "button", onClick, disabled, ...extra }, label);
}
function errorText(error) {
  const message = typeof error?.message === "string" ? error.message : "场景操作失败。";
  return message.slice(0, 360);
}
function openWorkbench(projectId, scene) {
  host.dockViews.open({ viewKey: `${VIEW}:${projectId}:${scene?.id || "library"}`, viewType: VIEW,
    title: scene?.title || "Scene Studio", projectId, closeable: true,
    ...(scene ? { target: { type: "object", object: { kind: SCENE_KIND, id: scene.id }, authority: { kind: SCENE_KIND, id: scene.id } } } : {}),
  });
}

function useVisible(ref) {
  const [visible, setVisible] = React.useState(true);
  React.useEffect(() => {
    let intersects = true;
    const update = () => setVisible(active && intersects && document.visibilityState !== "hidden");
    const observer = typeof IntersectionObserver === "function" ? new IntersectionObserver((entries) => {
      intersects = entries.some((entry) => entry.isIntersecting);
      update();
    }) : null;
    if (ref.current) observer?.observe(ref.current);
    document.addEventListener("visibilitychange", update);
    update();
    const stop = () => { observer?.disconnect(); document.removeEventListener("visibilitychange", update); setVisible(false); };
    lifecycle.add(stop);
    return () => { lifecycle.delete(stop); observer?.disconnect(); document.removeEventListener("visibilitychange", update); };
  }, [ref]);
  return visible;
}

function Workbench({ projectId, initialSceneId, context }) {
  const rootRef = React.useRef(null);
  const visible = useVisible(rootRef);
  const [scenes, setScenes] = React.useState([]);
  const [sceneId, setSceneId] = React.useState(initialSceneId || "");
  const [snapshot, setSnapshot] = React.useState(null);
  const [selectedId, setSelectedId] = React.useState(null);
  const [title, setTitle] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  const [newer, setNewer] = React.useState(null);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [exported, setExported] = React.useState(null);
  const [mode, setMode] = React.useState("translate");
  const [space, setSpace] = React.useState("local");
  const [cameraId, setCameraId] = React.useState("");
  const [reload, setReload] = React.useState(0);
  const viewportRef = React.useRef(null);
  const exportController = React.useRef(null);
  const live = React.useRef({ snapshot, sceneId, busy: false, editing: null, loading: true, alive: true, readController: null });
  const selected = snapshot?.objects.find((object) => object.id === selectedId) || null;
  const invoke = React.useCallback((name, input, signal) => host.operations.invoke(name, input, { projectId, signal }), [projectId]);
  const lockEditing = React.useCallback((value) => { live.current.editing = value; setEditing(value); }, []);
  const accept = React.useCallback((next) => {
    live.current.snapshot = next;
    setSnapshot(next);
    if (next) setScenes((items) => items.map((item) => item.id === next.scene.id ? next.scene : item));
    setNewer(null);
    setSelectedId((id) => next?.objects.some((object) => object.id === id) ? id : null);
    setCameraId((id) => next?.objects.some((object) => object.id === id && object.kind === "camera") ? id : "");
  }, []);

  React.useEffect(() => {
    live.current.alive = true;
    const stop = () => { live.current.alive = false; live.current.readController?.abort(); exportController.current?.abort(); };
    lifecycle.add(stop);
    return () => { stop(); lifecycle.delete(stop); };
  }, []);

  React.useEffect(() => () => exportController.current?.abort(), [projectId, context.workbenchScopeId]);

  React.useEffect(() => {
    const controller = new AbortController();
    live.current.readController?.abort();
    live.current.readController = controller;
    live.current.sceneId = sceneId;
    live.current.loading = true;
    setLoading(true);
    setError("");
    (async () => {
      const inventory = await listScenes(invoke, controller.signal);
      if (controller.signal.aborted || !live.current.alive) return;
      setScenes(inventory);
      if (!sceneId) { accept(null); return; }
      const next = await readScene(invoke, sceneId, controller.signal);
      if (!controller.signal.aborted && live.current.alive) accept(next);
    })().catch((caught) => {
      if (!controller.signal.aborted && live.current.alive) setError(errorText(caught));
    }).finally(() => {
      if (!controller.signal.aborted && live.current.alive) { live.current.loading = false; setLoading(false); }
    });
    return () => controller.abort();
  }, [sceneId, invoke, reload, accept]);

  React.useEffect(() => {
    if (!visible) return undefined;
    let stopped = false;
    let controller;
    let timer;
    const poll = async () => {
      if (!live.current.alive || stopped) return;
      try {
        if (!live.current.busy && !live.current.loading && live.current.editing !== "drag") {
          const displayed = live.current.snapshot;
          controller = new AbortController();
          if (!sceneId) {
            const inventory = await listScenes(invoke, controller.signal);
            if (!stopped && !live.current.busy && !live.current.sceneId) setScenes(inventory);
            return;
          }
          const first = await invoke("scenes.get", { scene_id: sceneId, section: "objects", offset: 0, limit: 100 }, controller.signal);
          if (stopped || live.current.busy || live.current.loading || displayed !== live.current.snapshot) return;
          if (first.scene.version !== live.current.snapshot?.scene.version) {
            if (live.current.editing) setNewer(first.scene.version);
            else {
              const next = await readScene(invoke, sceneId, controller.signal, first);
              if (!stopped && !live.current.busy && !live.current.loading && !live.current.editing && displayed === live.current.snapshot) {
                accept(next);
                setNotice(`已同步外部修改 · v${next.scene.version}`);
              }
            }
          }
        }
      } catch (caught) {
        if (!stopped && !controller?.signal.aborted) setError(`同步失败：${errorText(caught)}`);
      } finally {
        if (!stopped) timer = setTimeout(poll, 5000);
      }
    };
    timer = setTimeout(poll, 5000);
    const stop = () => { stopped = true; clearTimeout(timer); controller?.abort(); };
    lifecycle.add(stop);
    return () => { stop(); lifecycle.delete(stop); };
  }, [visible, sceneId, invoke, accept]);

  const refresh = () => {
    if (live.current.busy) return;
    lockEditing(null);
    setNotice("");
    setExported(null);
    setReload((value) => value + 1);
  };

  async function write(name, input, options = {}) {
    if (live.current.busy || live.current.loading || !live.current.alive || !active) return false;
    const displayed = live.current.snapshot;
    live.current.busy = true;
    setBusy(true);
    setError("");
    setNotice("");
    // request_id and displayed revision are captured once. Unknown writes are never replayed.
    const payload = name === "scenes.create" ? { ...input, request_id: requestId() } : {
      scene_id: displayed.scene.id, expected_version: options.version ?? displayed.scene.version,
      request_id: requestId(), ...input,
    };
    live.current.readController?.abort();
    try {
      const navigationHost = host;
      const workbenchScopeId = context.workbenchScopeId;
      const controller = name === "scenes.artifact" ? new AbortController() : null;
      if (controller) {
        if (!navigationHost.workbench.openArtifact) throw new Error("当前 Host 不支持打开导出工件，请升级 Host。");
        exportController.current = controller;
      }
      const result = await invoke(name, payload, controller?.signal);
      if (!live.current.alive || !active) return false;
      if (name === "scenes.artifact") {
        controller.signal.throwIfAborted();
        setExported({ ...result, title: displayed.scene.title, version: displayed.scene.version, reference: referenceFor(displayed) });
        await navigationHost.workbench.openArtifact({ projectId, sessionId: result.session_id,
          runId: result.run_id, artifactId: result.artifact_id }, { workbenchScopeId, signal: controller.signal });
        if (!live.current.alive || controller.signal.aborted) return false;
        setNotice("已打开固定版本导出工件，可下载 GLB / glTF。");
      } else if (name === "scenes.delete") {
        accept(null); setSceneId("");
      } else {
        const controller = new AbortController();
        live.current.readController = controller;
        const next = await readScene(invoke, result.scene.id, controller.signal);
        if (!live.current.alive) return false;
        lockEditing(null);
        accept(next);
        setSceneId(next.scene.id);
        if (options.selectId) setSelectedId(options.selectId);
        else if (options.selectChanged) setSelectedId(result.changed_ids.find((id) => next.objects.some((object) => object.id === id)) || null);
        setNotice(result.changed ? `已保存 · v${next.scene.version}` : "内容未改变");
      }
      const inventory = await listScenes(invoke);
      if (live.current.alive) setScenes(inventory);
      return true;
    } catch (caught) {
      if (live.current.alive) {
        setError(`${errorText(caught)} 请刷新确认当前版本，再决定下一步；本次操作不会自动重试。`);
        if (options.drag) viewportRef.current?.update(displayed);
        if (options.drag) lockEditing(null);
      }
      return false;
    } finally {
      live.current.busy = false;
      if (live.current.alive) setBusy(false);
    }
  }
  const apply = (operation, options) => write("scenes.apply", { operation }, options);
  function choose(id) {
    if (live.current.editing || live.current.busy) return;
    setSelectedId(id === "scene-root" ? null : id);
  }
  function add(kind) {
    const id = `object.${requestId()}`;
    const common = { id, name: labels[kind], parent_id: selected?.kind === "group" ? selected.id : null };
    if (kind === "camera") void apply({ kind: "camera_create", camera: { ...common, kind: "camera", position: [4, 3, 6] } }, { selectId: id });
    else if (["point", "directional", "spot"].includes(kind)) void apply({ kind: "light_create", light: { ...common, kind: "light", light_type: kind, position: [2, 4, 2], intensity: kind === "directional" ? 3 : 40 } }, { selectId: id });
    else void apply({ kind: "object_create", objects: [{ ...common, kind: kind === "group" ? "group" : "mesh", ...(kind === "group" ? {} : { geometry_id: `geometry.${kind}` }) }] }, { selectId: id });
  }
  function duplicate() { if (selected) void apply({ kind: "object_duplicate", object_ids: [selected.id], include_subtree: true, offset: [1, 0, 0] }, { selectChanged: true }); }
  function remove() { if (selected) void apply({ kind: "object_delete", object_ids: [selected.id], include_subtree: true }); }
  function undo() { if (snapshot?.scene.version > 1) void write("scenes.undo", { target_version: snapshot.scene.version - 1 }); }
  const disabled = busy || loading || !!editing || !snapshot;
  const keys = (event) => {
    if (disabled) return;
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && key === "z") { event.preventDefault(); undo(); }
    else if ((event.ctrlKey || event.metaKey) && key === "d") { event.preventDefault(); duplicate(); }
    else if (key === "delete" || key === "backspace") { event.preventDefault(); remove(); }
    else if (["w", "e", "r"].includes(key)) { event.preventDefault(); setMode({ w: "translate", e: "rotate", r: "scale" }[key]); }
  };
  const tree = React.useMemo(() => snapshot ? hierarchy(snapshot) : null, [snapshot]);
  return h("section", { className: "dbfox-scene", ref: rootRef, "aria-label": "Scene Studio 工作台" },
    h("header", { className: "dbfox-scene__header" },
      h("div", null, h("strong", null, "Scene Studio"), h("span", { className: "dbfox-scene__muted" }, snapshot ? ` v${snapshot.scene.version} · ${snapshot.objects.length} 个对象` : " 本地三维创作")),
      h("select", { "aria-label": "打开场景", value: sceneId, disabled: busy || !!editing, onChange: (event) => { accept(null); setExported(null); setSceneId(event.target.value); } },
        h("option", { value: "" }, "场景库"), scenes.map((scene) => h("option", { key: scene.id, value: scene.id }, scene.title))),
      button(editing ? "放弃草稿并刷新" : "刷新", refresh, busy),
      button("撤销上一版本", undo, disabled || snapshot?.scene.version <= 1),
      button("导出工件", () => write("scenes.artifact", {}), disabled),
      button("引用到 Agent", () => context.onAsk(snapshot ? referenceFor(snapshot, selected) : { label: "Scene Library", authority: { kind: LIBRARY_KIND, id: projectId }, object: { kind: LIBRARY_KIND, id: projectId }, locator: "/" }), busy || loading),
    ),
    error ? h("div", { role: "alert", className: "dbfox-scene__error" }, error) : null,
    newer ? h("div", { role: "status", className: "dbfox-scene__notice" }, `场景已有 v${newer}，当前草稿基于 v${snapshot.scene.version}。保存可能冲突；刷新会放弃草稿。`) : null,
    notice ? h("div", { role: "status", className: "dbfox-scene__notice" }, notice) : null,
    exported ? h("div", { className: "dbfox-scene__export" },
      h("span", null, `${exported.title} · v${exported.version} · 导出工件已保存`),
      button("引用导出工件", () => context.onAsk({ ...exported.reference, label: `${exported.title} · 导出 v${exported.version}`, artifactId: exported.artifact_id }))) : null,
    loading ? h("div", { role: "status", className: "dbfox-scene__loading" }, "正在读取同一版本的场景…") : null,
    !sceneId ? h("div", { className: "dbfox-scene__library" },
      h("h2", null, "创建你的三维场景"), h("p", null, "从基础几何开始，调整层级、材质、光线和镜头。每次编辑都保存为可撤销的版本。"),
      h("form", { onSubmit: (event) => { event.preventDefault(); void write("scenes.create", { title: title.trim() }).then((ok) => { if (ok) setTitle(""); }); } },
        h("input", { "aria-label": "新场景名称", placeholder: "场景名称", value: title, maxLength: 160, required: true, onChange: (event) => setTitle(event.target.value), disabled: busy }),
        h("button", { type: "submit", disabled: busy || loading || !title.trim() }, "创建场景")),
      !loading && !scenes.length ? h("p", { className: "dbfox-scene__muted" }, "尚无场景。也可以引用 Scene Library 让 Agent 创建。") : null,
      h("div", { className: "dbfox-scene__cards" }, scenes.map((scene) => button(`${scene.title} · v${scene.version} · ${scene.object_count} 对象`, () => setSceneId(scene.id), busy, { key: scene.id })))) : null,
    sceneId && snapshot ? h("div", { className: "dbfox-scene__body", "aria-busy": busy || loading },
      h("aside", { className: "dbfox-scene__hierarchy", "aria-label": "场景层级" },
        h("h3", null, "层级"),
        h("div", { className: "dbfox-scene__tree", "aria-disabled": disabled }, h(host.ui.Tree, {
          rootItem: tree, ariaLabel: "场景对象", getItemId: (item) => item.id, getItemLabel: (item) => item.name,
          getItemChildren: (item) => item.children, defaultExpandedIds: ["scene-root"],
          selectedIds: selectedId ? [selectedId] : [], onItemSelect: (item) => choose(item.id),
          onSelectedIdsChange: (ids) => choose(ids[ids.length - 1] || null),
          renderItemMeta: (item) => h("span", { className: "dbfox-scene__muted" }, item.visible === false ? "隐藏" : item.kind),
        })),
        !snapshot.objects.length ? h("p", { className: "dbfox-scene__muted" }, "使用上方添加菜单放入第一个对象。") : null,
        h("div", { className: "dbfox-scene__row" }, button("复制子树", duplicate, disabled || !selected), button("删除子树", remove, disabled || !selected)),
        h("details", null, h("summary", null, "管理场景"), button("删除此场景", () => write("scenes.delete", {}), disabled))),
      h("main", { className: "dbfox-scene__main" },
        h("div", { className: "dbfox-scene__toolbar", role: "toolbar", "aria-label": "视口工具" },
          h("select", { "aria-label": "添加对象", value: "", disabled, onChange: (event) => add(event.target.value) },
            h("option", { value: "", disabled: true }, "+ 添加"), Object.entries(labels).map(([id, label]) => h("option", { key: id, value: id }, label))),
          [ ["translate", "移动 W"], ["rotate", "旋转 E"], ["scale", "缩放 R"] ].map(([id, label]) => button(label, () => setMode(id), disabled, { key: id, "aria-pressed": mode === id })),
          h("select", { "aria-label": "变换坐标系", value: space, disabled, onChange: (event) => setSpace(event.target.value) }, h("option", { value: "local" }, "局部"), h("option", { value: "world" }, "世界")),
          button("聚焦 F", () => viewportRef.current?.focus(selectedId), !snapshot),
          h("select", { "aria-label": "视角", value: cameraId, disabled: !!editing, onChange: (event) => setCameraId(event.target.value) }, h("option", { value: "" }, "编辑视角"), snapshot.objects.filter((item) => item.kind === "camera").map((item) => h("option", { key: item.id, value: item.id }, item.name)))),
        h(Viewport, { snapshot, selectedId, mode, space, cameraId, visible, disabled: busy || loading || (!!editing && editing !== "drag"), dragging: editing === "drag", viewportRef,
          onSelect: choose, onKey: keys, onError: setError,
          onDragStart: () => lockEditing("drag"), onDragCancel: () => lockEditing(null),
          onDragEnd: (transform, version) => { void apply({ kind: "object_transform", transforms: [transform] }, { version, drag: true }); },
        }),
        h("footer", { className: "dbfox-scene__footer" }, h("span", null, "拖动旋转 · 右键平移 · 滚轮缩放 · Esc 取消拖动"), h("span", null, "Y ↑ · 米 · Euler XYZ 弧度"))),
      h("aside", { className: "dbfox-scene__inspector", "aria-label": "检查器" }, h("h3", null, selected ? selected.name : "场景设置"),
        h(Inspector, { key: `${snapshot.scene.id}:${snapshot.scene.version}:${selectedId || "scene"}:${reload}`, snapshot, selected, apply, editing, busy: busy || loading, onDirty: lockEditing }),
      ),
    ) : null,
  );
}

function Viewport(props) {
  const ref = React.useRef(null);
  const current = React.useRef(props);
  current.current = props;
  const [failure, setFailure] = React.useState("");
  React.useEffect(() => {
    if (!props.visible) return undefined;
    let stopped = false;
    let view;
    setFailure("");
    import("./viewport.js").then(({ createViewport }) => {
      if (stopped || !active) return;
      view = createViewport(ref.current, {
        onSelect: (id) => current.current.onSelect(id), onKey: (event) => current.current.onKey(event),
        onDragStart: () => current.current.onDragStart(), onDragEnd: (...args) => current.current.onDragEnd(...args),
        onDragCancel: () => current.current.onDragCancel(), onError: (message) => setFailure(message),
      });
      props.viewportRef.current = view;
      view.update(current.current.snapshot);
      view.select(current.current.selectedId);
      view.setMode(current.current.mode, current.current.space);
      view.setCamera(current.current.cameraId);
      view.setEnabled(!current.current.disabled);
    }).catch(() => { if (!stopped) setFailure("三维视口无法启动。请检查 WebGL 支持并重新打开工作台。对象仍可通过检查器编辑。"); });
    const stop = () => { stopped = true; view?.dispose(); props.viewportRef.current = null; if (current.current.dragging) current.current.onDragCancel(); };
    lifecycle.add(stop);
    return () => { stop(); lifecycle.delete(stop); };
  }, [props.visible, props.viewportRef]);
  React.useEffect(() => { props.viewportRef.current?.update(props.snapshot); }, [props.snapshot, props.viewportRef]);
  React.useEffect(() => { props.viewportRef.current?.select(props.selectedId); }, [props.selectedId, props.viewportRef]);
  React.useEffect(() => { props.viewportRef.current?.setMode(props.mode, props.space); }, [props.mode, props.space, props.viewportRef]);
  React.useEffect(() => { props.viewportRef.current?.setCamera(props.cameraId); }, [props.cameraId, props.viewportRef]);
  // During a drag the selected object stays attached until mouseUp; busy fences only the commit.
  React.useEffect(() => { props.viewportRef.current?.setEnabled(!props.disabled); }, [props.disabled, props.viewportRef]);
  return h("div", { className: "dbfox-scene__viewport-shell" }, h("div", { ref, className: "dbfox-scene__viewport" }), failure ? h("div", { role: "alert", className: "dbfox-scene__viewport-error" }, failure) : null);
}

function Field({ label, value, onChange, type = "number", ...rest }) {
  return h("label", { className: "dbfox-scene__field" }, h("span", null, label), h("input", { "aria-label": label, value, type, step: "any", onChange: (event) => onChange(type === "number" ? event.target.value : event.target.value), ...rest }));
}
function Vector({ label, value, onChange, min, max, axes = ["X", "Y", "Z"] }) {
  return h("div", { className: "dbfox-scene__vector" }, h("span", null, label), h("div", null, value.map((entry, index) => h("label", { key: index, className: "dbfox-scene__field" },
    h("span", null, axes[index]), h("input", { type: "number", "aria-label": `${label} ${axes[index]}`, value: entry, min, max, step: "any", required: true,
      onChange: (event) => onChange(value.map((item, axis) => axis === index ? event.target.value : item)) })))));
}
function numbers(values) { return values.map(Number); }
function Check({ label, value, onChange }) {
  return h("label", { className: "dbfox-scene__check" }, h("input", { type: "checkbox", checked: value, onChange: (event) => onChange(event.target.checked) }), label);
}
function EditForm({ id, title, initial, operation, apply, editing, busy, onDirty, children, always = false }) {
  const [draft, setDraft] = React.useState(initial);
  const [dirty, setDirty] = React.useState(false);
  const locked = busy || (!!editing && editing !== id);
  const change = (patch) => { setDraft((value) => ({ ...value, ...patch })); setDirty(true); onDirty(id); };
  return h("form", { className: "dbfox-scene__form", onSubmit: (event) => {
    event.preventDefault();
    if (!locked && (dirty || always)) void apply(operation(draft)).then((ok) => { if (ok) { setDirty(false); onDirty(null); } });
  } }, h("fieldset", { disabled: locked }, h("legend", null, title), children(draft, change),
    h("div", { className: "dbfox-scene__row" }, h("button", { type: "submit", disabled: !dirty && !always }, `保存${title}`),
      dirty ? button("取消编辑", () => { setDraft(initial); setDirty(false); onDirty(null); }) : null)));
}

function Inspector({ snapshot, selected, ...editingProps }) {
  const form = (id, title, initial, operation, children, always = false) => h(EditForm, { key: id, id, title, initial, operation, children, always, ...editingProps });
  const settings = form("settings", "场景设置", { title: snapshot.scene.title, ...snapshot.settings }, (draft) => ({ kind: "scene_settings_update", title: draft.title.trim(), settings: { background: numbers(draft.background), default_camera_id: draft.default_camera_id || null } }), (draft, change) => h(React.Fragment, null,
    h(Field, { label: "场景名称", type: "text", value: draft.title, required: true, maxLength: 160, onChange: (title) => change({ title }) }),
    h(Vector, { label: "背景线性 RGB", axes: ["R", "G", "B"], value: draft.background, min: 0, max: 1, onChange: (background) => change({ background }) }),
    h("label", { className: "dbfox-scene__field" }, "默认相机", h("select", { "aria-label": "默认相机", value: draft.default_camera_id || "", onChange: (event) => change({ default_camera_id: event.target.value }) }, h("option", { value: "" }, "无"), snapshot.objects.filter((object) => object.kind === "camera").map((object) => h("option", { key: object.id, value: object.id }, object.name))))));
  const materialForm = (material, create = false) => form(create ? "new-material" : "material", create ? "新材质" : "材质参数", material,
    (draft) => ({ kind: create ? "material_create" : "material_update", material: { ...draft, id: create ? `material.${requestId()}` : draft.id, name: draft.name.trim(), base_color: numbers(draft.base_color), metallic: Number(draft.metallic), roughness: Number(draft.roughness) } }),
    (draft, change) => h(React.Fragment, null,
      h(Field, { label: create ? "新材质名称" : "材质名称", type: "text", value: draft.name, required: true, maxLength: 120, onChange: (name) => change({ name }) }),
      h(Vector, { label: "基础色线性 RGBA", axes: ["R", "G", "B", "A"], value: draft.base_color, min: 0, max: 1, onChange: (base_color) => change({ base_color }) }),
      h(Field, { label: "金属度", value: draft.metallic, min: 0, max: 1, required: true, onChange: (metallic) => change({ metallic }) }),
      h(Field, { label: "粗糙度", value: draft.roughness, min: 0, max: 1, required: true, onChange: (roughness) => change({ roughness }) }),
      h(Check, { label: "双面", value: draft.double_sided, onChange: (double_sided) => change({ double_sided }) })), create);
  const newMaterial = h("details", null, h("summary", null, "创建材质"), materialForm({ name: "新材质", base_color: [0.65, 0.65, 0.65, 1], metallic: 0, roughness: 0.6, double_sided: false }, true));
  if (!selected) return h(React.Fragment, null, settings, newMaterial, h("p", { className: "dbfox-scene__muted" }, "选择对象后可编辑局部变换、名称、父级与专属参数。"));
  const material = snapshot.materials.find((item) => item.id === selected.material_id);
  return h(React.Fragment, null,
    h("p", { className: "dbfox-scene__object-id" }, `${selected.kind} · ${selected.id}`),
    form("object", "对象", { name: selected.name, visible: selected.visible }, (draft) => ({ kind: "object_update", object_id: selected.id, name: draft.name.trim(), visible: draft.visible }), (draft, change) => h(React.Fragment, null,
      h(Field, { label: "对象名称", type: "text", value: draft.name, required: true, maxLength: 120, onChange: (name) => change({ name }) }), h(Check, { label: "可见", value: draft.visible, onChange: (visible) => change({ visible }) }))),
    form("transform", "局部变换", { position: selected.position, rotation: selected.rotation, scale: selected.scale }, (draft) => ({ kind: "object_transform", transforms: [{ object_id: selected.id, position: numbers(draft.position), rotation: numbers(draft.rotation), scale: numbers(draft.scale) }] }), (draft, change) => h(React.Fragment, null,
      h(Vector, { label: "位置", value: draft.position, min: -1000000, max: 1000000, onChange: (position) => change({ position }) }),
      h(Vector, { label: "旋转 rad", value: draft.rotation, min: -Math.PI * 200, max: Math.PI * 200, onChange: (rotation) => change({ rotation }) }),
      h(Vector, { label: "缩放", value: draft.scale, min: 0.0001, max: 100000, onChange: (scale) => change({ scale }) }))),
    form("parent", "父级", { parent_id: selected.parent_id }, (draft) => ({ kind: "object_reparent", object_ids: [selected.id], parent_id: draft.parent_id || null }), (draft, change) => h(React.Fragment, null,
      h("select", { "aria-label": "父级对象", value: draft.parent_id || "", onChange: (event) => change({ parent_id: event.target.value }) }, h("option", { value: "" }, "场景根节点"), parentCandidates(snapshot.objects, selected.id).map((item) => h("option", { key: item.id, value: item.id }, item.name))), h("small", null, "保持局部变换；更改父级会改变世界位置。"))),
    selected.kind === "mesh" ? h(React.Fragment, null,
      form("assignment", "材质分配", { material_id: selected.material_id }, (draft) => ({ kind: "material_assign", object_ids: [selected.id], material_id: draft.material_id || null }), (draft, change) => h("select", { "aria-label": "对象材质", value: draft.material_id || "", onChange: (event) => change({ material_id: event.target.value }) }, h("option", { value: "" }, "默认材质"), snapshot.materials.map((item) => h("option", { key: item.id, value: item.id }, item.name)))),
      material ? materialForm(material) : null, newMaterial) : null,
    selected.kind === "light" ? form("light", "灯光", { color: selected.color, intensity: selected.intensity, range: selected.range ?? "", inner_cone_angle: selected.inner_cone_angle, outer_cone_angle: selected.outer_cone_angle }, (draft) => ({ kind: "light_update", light_id: selected.id, color: numbers(draft.color), intensity: Number(draft.intensity), ...(draft.range === "" ? { clear_range: true } : { range: Number(draft.range) }), inner_cone_angle: Number(draft.inner_cone_angle), outer_cone_angle: Number(draft.outer_cone_angle) }), (draft, change) => h(React.Fragment, null,
      h(Vector, { label: "灯光线性 RGB", axes: ["R", "G", "B"], value: draft.color, min: 0, max: 1, onChange: (color) => change({ color }) }),
      h(Field, { label: "强度", value: draft.intensity, min: 0, max: 1000000, required: true, onChange: (intensity) => change({ intensity }) }),
      selected.light_type !== "directional" ? h(Field, { label: "范围（空白为无限）", value: draft.range, min: 0.0001, max: 1000000, onChange: (range) => change({ range }) }) : null,
      selected.light_type === "spot" ? h(React.Fragment, null, h(Field, { label: "内锥角 rad", value: draft.inner_cone_angle, min: 0, max: 1.570796, required: true, onChange: (inner_cone_angle) => change({ inner_cone_angle }) }), h(Field, { label: "外锥角 rad", value: draft.outer_cone_angle, min: 0.0001, max: 1.570796, required: true, onChange: (outer_cone_angle) => change({ outer_cone_angle }) })) : null)) : null,
    selected.kind === "camera" ? form("camera", "相机", { yfov: selected.yfov, znear: selected.znear, zfar: selected.zfar }, (draft) => ({ kind: "camera_update", camera_id: selected.id, yfov: Number(draft.yfov), znear: Number(draft.znear), zfar: Number(draft.zfar) }), (draft, change) => h(React.Fragment, null,
      h(Field, { label: "垂直视角 rad", value: draft.yfov, min: 0.010001, max: 3.14159, required: true, onChange: (yfov) => change({ yfov }) }),
      h(Field, { label: "近裁面", value: draft.znear, min: 0.00001, max: 100000, required: true, onChange: (znear) => change({ znear }) }),
      h(Field, { label: "远裁面", value: draft.zfar, min: 0.00001, max: 1000000, required: true, onChange: (zfar) => change({ zfar }) }))) : null,
  );
}

function SceneArtifact({ artifact, payload, context }) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const state = React.useRef({ busy: false, controller: null, url: null, alive: true });
  React.useEffect(() => {
    state.current.alive = true;
    const stop = () => { state.current.alive = false; state.current.controller?.abort(); if (state.current.url) URL.revokeObjectURL(state.current.url); };
    lifecycle.add(stop);
    return () => { stop(); lifecycle.delete(stop); };
  }, []);
  async function download(format) {
    if (state.current.busy || !active) return;
    state.current.busy = true;
    setBusy(true); setError("");
    state.current.controller = new AbortController();
    try {
      const blob = await context.representations.stream(artifact.id, REPRESENTATION_TYPE, { operation: `export_${format}`, parameters: {} }, state.current.controller.signal);
      if (!state.current.alive) return;
      if (state.current.url) URL.revokeObjectURL(state.current.url);
      state.current.url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = state.current.url;
      anchor.download = `scene-${payload.scene_id}-v${payload.version}.${format}`;
      anchor.click();
      context.onToast(`已导出 ${format.toUpperCase()} · v${payload.version}`);
    } catch (caught) { if (state.current.alive) setError(errorText(caught)); }
    finally { state.current.busy = false; if (state.current.alive) setBusy(false); }
  }
  return h("article", { className: "dbfox-scene dbfox-scene__artifact" }, h("h3", null, `${payload.title} · v${payload.version}`),
    h("p", null, `${payload.object_count} 个对象 · ${payload.material_count} 个材质 · 固定版本`),
    h("div", { className: "dbfox-scene__row" }, button("下载 GLB", () => download("glb"), busy), button("下载 glTF", () => download("gltf"), busy), button("编辑当前场景", () => openWorkbench(payload.project_id, { id: payload.scene_id, title: payload.title }), busy)),
    error ? h("p", { role: "alert" }, error) : null);
}

export function register(extensionHost) {
  host = extensionHost;
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React || !host.ui?.Tree) throw new Error("Scene Studio requires the public Host React and Tree APIs.");
  active = true;
  if (typeof document !== "undefined") {
    stylesheet?.remove();
    stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = new URL("./index.css", import.meta.url).href;
    stylesheet.dataset.dbfoxDlc = DLC_ID;
    document.head.append(stylesheet);
  }
  host.connectors.register({ id: DLC_ID, title: "Scene Studio", icon: h("span", { "aria-hidden": true }, "◇"),
    addLabel: "创建三维场景", onAdd: ({ projectId }) => openWorkbench(projectId),
    render: ({ projectId }) => h("div", { className: "dbfox-scene dbfox-scene__connector" }, h("p", null, "三维场景 · 材质 · 光线 · 相机"), button("打开 Scene Studio", () => openWorkbench(projectId))),
    listResources: async ({ projectId }) => (await listScenes((name, input, signal) => host.operations.invoke(name, input, { projectId, signal }))).map((scene) => ({ kind: SCENE_KIND, id: scene.id, name: scene.title, detail: `v${scene.version} · ${scene.object_count} 对象` })),
  });
  host.dockViews.register({ viewType: VIEW, icon: () => h("span", { "aria-hidden": true }, "◇"), resolveTitle: (view) => view.title,
    isVisible: (view, context) => view.projectId === context.activeProjectId,
    render: (view, context) => h(Workbench, { key: `${view.projectId}:${view.viewKey}`, projectId: view.projectId, initialSceneId: view.target?.type === "object" ? view.target.object.id : null, context }),
  });
  host.artifactViews.register({ id: "dbfox.scene.revision-view", title: "Scene 导出", priority: 100, surfaces: ["inline", "workspace"], artifactTypes: [{ type: ARTIFACT_TYPE, schemaVersions: [1] }], representationTypes: [REPRESENTATION_TYPE],
    parsePayload(value) {
      if (!value || typeof value.scene_id !== "string" || typeof value.project_id !== "string" || !Number.isInteger(value.version) || value.version < 1 || typeof value.title !== "string") throw new Error("Invalid Scene revision Artifact");
      return value;
    },
    render: (artifact, payload, context) => h(SceneArtifact, { key: artifact.id, artifact, payload, context }),
  });
}
export function deactivate() {
  active = false;
  for (const stop of lifecycle) stop();
  lifecycle.clear();
  stylesheet?.remove();
  stylesheet = null;
}
