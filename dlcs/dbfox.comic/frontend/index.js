import { renderPage } from "./render.js";

const OWNER = "dbfox.comic", KIND = "dbfox.comic.document", ARTIFACT = "dbfox.comic.revision", REP = "dbfox.comic.document.v1", VIEW = "dbfox.comic.studio";
let React, host, stylesheet, active = false, epoch = 0;
const cleanups = new Set();
const h = (...args) => React.createElement(...args);
const id = (prefix) => `${prefix}-${crypto.randomUUID()}`;
const button = (label, onClick, disabled = false, extra = {}) => h("button", { type: "button", onClick, disabled, ...extra }, label);
const message = (error) => String(error?.message || "分镜操作失败，请检查当前版本。").slice(0, 360);
const rect = (x = .08, y = .08, width = .5, height = .3) => ({ x, y, width, height });
const labels = { character: "角色位置", bubble: "对白", caption: "字幕", note: "视觉注释" };

function open(projectId, comic) {
  host.dockViews.open({ viewKey: `${VIEW}:${projectId}:${comic?.id || "library"}`, viewType: VIEW, projectId,
    title: comic?.title || "Comic Studio", closeable: true,
    ...(comic ? { target: { type: "object", object: { kind: KIND, id: comic.id }, authority: { kind: KIND, id: comic.id } } } : {}) });
}

function PageCanvas({ page, selected, showNotes, onSelect, onTransform, onGesture, mode, disabled, snapshotVersion, panelTransforms = true }) {
  const mount = React.useRef(null), gesture = React.useRef(null);
  const [overflow, setOverflow] = React.useState([]);
  React.useEffect(() => {
    if (!mount.current) return;
    const svg = renderPage(page, { showNotes });
    svg.setAttribute("aria-hidden", "true");
    mount.current.replaceChildren(svg);
    const frame = requestAnimationFrame(() => setOverflow([...svg.querySelectorAll("foreignObject > div")].filter((div) => div.scrollHeight > div.clientHeight + 1 || div.scrollWidth > div.clientWidth + 1).map((div) => div.closest("[data-object-id]").dataset.objectId)));
    return () => { cancelAnimationFrame(frame); gesture.current = null; onGesture?.(false); mount.current?.replaceChildren(); };
  }, [page, showNotes]);
  React.useEffect(() => { for (const node of mount.current?.querySelectorAll("[data-object-id]") || []) node.style.filter = node.dataset.objectId === selected ? "drop-shadow(0 0 3px #397DD6)" : ""; }, [selected, page]);
  const locate = (identity) => {
    for (const panel of page.panels) {
      if (panel.id === identity) return { object: panel, panel: null };
      const element = panel.elements.find((e) => e.id === identity);
      if (element) return { object: element, panel };
    }
    return null;
  };
  const cancel = () => { gesture.current = null; onGesture?.(false); if (mount.current) mount.current.replaceChildren(renderPage(page, { showNotes })); };
  const start = (event) => {
    if (disabled || event.button !== 0) return;
    const element = event.target.closest?.("[data-object-id]");
    if (!element) return;
    const found = locate(element.dataset.objectId);
    if (!found) return;
    onSelect(found.object.id);
    if (!found.panel && !panelTransforms) return;
    const bounds = mount.current.querySelector("svg").getBoundingClientRect();
    gesture.current = { ...found, x: event.clientX, y: event.clientY, bounds, version: snapshotVersion, moved: false, next: null };
    onGesture?.(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const move = (event) => {
    const current = gesture.current;
    if (!current || disabled) return;
    const dx = event.clientX - current.x, dy = event.clientY - current.y;
    if (!current.moved && Math.hypot(dx, dy) < 4) return;
    current.moved = true;
    const base = current.object.rect;
    const width = current.bounds.width * (current.panel?.rect.width || 1), height = current.bounds.height * (current.panel?.rect.height || 1);
    const next = mode === "resize" ? { ...base, width: Math.max(.02, Math.min(1 - base.x, base.width + dx / width)), height: Math.max(.02, Math.min(1 - base.y, base.height + dy / height)) }
      : { ...base, x: Math.max(0, Math.min(1 - base.width, base.x + dx / width)), y: Math.max(0, Math.min(1 - base.height, base.y + dy / height)) };
    current.next = next;
    const preview = { ...page, panels: page.panels.map((p) => current.panel ? { ...p, elements: p.elements.map((e) => e.id === current.object.id ? { ...e, rect: next } : e) } : p.id === current.object.id ? { ...p, rect: next } : p) };
    mount.current.replaceChildren(renderPage(preview, { showNotes }));
  };
  const finish = () => {
    const current = gesture.current; gesture.current = null; onGesture?.(false);
    if (current?.moved && current.next && !disabled) onTransform(current.object, current.panel, current.next, current.version);
  };
  React.useEffect(() => { cleanups.add(cancel); return () => { cleanups.delete(cancel); gesture.current = null; }; }, [page, showNotes]);
  return h(React.Fragment, null, h("div", { className: "dbfox-comic-canvas", ref: mount, tabIndex: 0, role: "group", "aria-label": "画布：拖动移动，方向键微调，Escape 取消拖动",
    onPointerDown: start, onPointerMove: move, onPointerUp: finish, onPointerCancel: cancel,
    onKeyDown: (event) => {
      if (event.key === "Escape") { cancel(); return; }
      if (disabled || !selected || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault(); const found = locate(selected); if (!found || (!found.panel && !panelTransforms)) return;
      const step = event.shiftKey ? .05 : .01, next = { ...found.object.rect };
      const axis = ["ArrowLeft", "ArrowRight"].includes(event.key) ? "x" : "y";
      next[axis] = Math.max(0, Math.min(1 - next[axis === "x" ? "width" : "height"], next[axis] + (["ArrowLeft", "ArrowUp"].includes(event.key) ? -step : step)));
      onTransform(found.object, found.panel, next, snapshotVersion);
    } }), overflow.length > 0 && h("p", { className: "dbfox-comic-feedback", role: "status" }, `以下文字超出框内空间，请放大对象或缩小字号：${overflow.join("、")}`));
}

function Studio({ projectId, initialId, context }) {
  const [comics, setComics] = React.useState([]), [comicId, setComicId] = React.useState(initialId || "");
  const [snapshot, setSnapshot] = React.useState(null), [pages, setPages] = React.useState([]), [page, setPage] = React.useState(null);
  const [pageId, setPageId] = React.useState(""), [selected, setSelected] = React.useState("");
  const [title, setTitle] = React.useState(""), [view, setView] = React.useState("page"), [mode, setMode] = React.useState("move");
  const [notes, setNotes] = React.useState(false), [busy, setBusy] = React.useState(false), [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(""), [notice, setNotice] = React.useState(""), [draft, setDraft] = React.useState(null);
  const [zoom, setZoom] = React.useState(100), [revision, setRevision] = React.useState(1), [differences, setDifferences] = React.useState(null);
  const live = React.useRef({ alive: true, busy: false, generation: epoch, controller: null, serial: 0, draft: null, snapshot: null });
  live.current.draft = draft;
  const invoke = (name, input, signal) => host.operations.invoke(name, input, { projectId, signal });
  const valid = () => live.current.alive && active && live.current.generation === epoch;

  const read = async (identity = comicId, selectedPage = pageId, passive = false) => {
    if (!valid() || live.current.busy) return;
    const serial = ++live.current.serial;
    live.current.controller?.abort(); const controller = new AbortController(); live.current.controller = controller;
    if (!passive) setLoading(true);
    try {
      if (!identity) {
        const all = []; let offset = 0;
        for (;;) { const result = await invoke("comics.list", { offset, limit: 32 }, controller.signal); all.push(...result.comics); if (result.next_offset >= result.total) break; offset = result.next_offset; }
        if (valid() && serial === live.current.serial) setComics(all);
        return;
      }
      const first = await invoke("comics.get", { comic_id: identity, section: "pages", offset: 0, limit: 32 }, controller.signal);
      if (!valid() || serial !== live.current.serial) return;
      if (live.current.draft && first.comic.version !== live.current.snapshot?.version) {
        setNotice(`作品已更新到 v${first.comic.version}。你的草稿仍保留；请取消草稿并刷新后重新编辑。`); return;
      }
      const directory = [...first.items]; let offset = first.next_offset;
      while (offset < first.total) { const next = await invoke("comics.get", { comic_id: identity, section: "pages", version: first.comic.version, offset, limit: 32 }, controller.signal); directory.push(...next.items); offset = next.next_offset; }
      const currentPage = directory.some((p) => p.id === selectedPage) ? selectedPage : directory[0]?.id || "";
      const current = currentPage ? await invoke("comics.get", { comic_id: identity, section: "page", version: first.comic.version, object_id: currentPage }, controller.signal) : null;
      if (!valid() || serial !== live.current.serial) return;
      live.current.snapshot = first.comic; setSnapshot(first.comic); setPages(directory); setPageId(currentPage); setPage(current?.items[0] || null);
      setRevision(Math.max(1, first.comic.version - 1));
      if (!passive) { setNotice(""); setError(""); }
    } catch (failure) { if (valid() && !controller.signal.aborted) setError(message(failure)); }
    finally { if (valid() && serial === live.current.serial) setLoading(false); }
  };

  React.useEffect(() => {
    live.current.alive = true;
    const stop = () => { live.current.alive = false; ++live.current.serial; live.current.controller?.abort(); live.current.exportController?.abort(); live.current.diffController?.abort(); };
    cleanups.add(stop);
    return () => { stop(); cleanups.delete(stop); };
  }, []);
  React.useEffect(() => { read(comicId, pageId); }, [comicId, pageId]);
  React.useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === "visible" && !live.current.busy && !live.current.draft && !live.current.gesture) read(comicId, pageId, true); }, 1800);
    const stop = () => clearInterval(timer); cleanups.add(stop);
    return () => { stop(); cleanups.delete(stop); };
  }, [comicId, pageId]);

  const write = async (name, values, expected = live.current.snapshot?.version) => {
    if (!valid() || live.current.busy || (!expected && name !== "comics.create")) return;
    live.current.busy = true; setBusy(true); setError("");
    live.current.controller?.abort(); ++live.current.serial;
    try {
      const request = name === "comics.create" ? values : { comic_id: comicId, expected_version: expected, ...values };
      const result = await invoke(name, { ...request, request_id: id("request") });
      if (!valid()) return;
      setDraft(null); live.current.draft = null;
      if (name === "comics.artifact") {
        const controller = new AbortController(); live.current.exportController = controller;
        await host.workbench.openArtifact({ projectId, artifactId: result.artifact_id, runId: result.run_id, sessionId: result.session_id }, { workbenchScopeId: context.workbenchScopeId, signal: controller.signal });
      } else if (name === "comics.delete") { setComicId(""); setSnapshot(null); setPage(null); setPages([]); }
      else if (name === "comics.create") { open(projectId, result.comic); }
      live.current.busy = false;
      await read(name === "comics.delete" ? "" : name === "comics.create" ? result.comic.id : comicId, name === "comics.create" ? "" : pageId);
      if (valid()) setNotice(name === "comics.artifact" ? "固定版本工件已打开。" : result.changed ? "修改已保存。" : "内容相同，版本未改变。");
    } catch (failure) { if (valid()) setError(message(failure)); }
    finally { live.current.busy = false; if (valid()) setBusy(false); }
  };
  const apply = (operation, expected) => write("comics.apply", { operation }, expected);
  const compare = async (offset = 0) => {
    const controller = new AbortController(); live.current.diffController?.abort(); live.current.diffController = controller;
    try {
      const result = await invoke("comics.diff", { comic_id: comicId, from_version: revision, to_version: snapshot.version, offset, limit: 8 }, controller.signal);
      if (valid() && !controller.signal.aborted) setDifferences(result);
    } catch (failure) { if (valid() && !controller.signal.aborted) setError(message(failure)); }
  };
  let selectedPanel = page?.panels.find((p) => p.id === selected || p.elements.some((e) => e.id === selected)) || page?.panels[0];
  const selectedElement = selectedPanel?.elements.find((e) => e.id === selected);
  const disabled = busy || loading || !!draft;
  const select = (identity) => { if (draft) { setNotice("请先保存或取消当前草稿。"); return; } setSelected(identity); };
  const transform = (object, panel, next, expected) => apply(panel ? { kind: "element_update", panel_id: panel.id, element: { ...object, rect: next } }
    : { kind: "panel_layout", page_id: page.id, placements: [{ panel_id: object.id, rect: next }] }, expected);
  const createElement = (kind) => {
    if (!selectedPanel) return;
    const common = { id: id(kind), kind, rect: kind === "character" ? rect(.2, .32, .2, .62) : rect(.08, .08, .7, .27) };
    const element = kind === "character" ? { ...common, label: "角色", pose: "standing", facing: "front", color: "#527E94" }
      : kind === "bubble" ? { ...common, text: "在这里写对白", font_size: 22, style: "speech", tail_x: .35, tail_y: .6, speaker_id: null }
      : kind === "caption" ? { ...common, text: "时间与地点", font_size: 20, color: "#F4E8CB" } : { ...common, text: "镜头的视觉提示" };
    apply({ kind: { character: "character_place", bubble: "bubble_create", caption: "caption_create", note: "note_create" }[kind], panel_id: selectedPanel.id, [kind]: element });
  };
  const layout = () => {
    if (!page?.panels.length) return;
    const cols = page.panels.length === 1 ? 1 : 2, rows = Math.ceil(page.panels.length / cols), gap = .035;
    apply({ kind: "panel_layout", page_id: page.id, placements: page.panels.map((p, i) => ({ panel_id: p.id, rect: rect(gap + i % cols * ((1 - gap) / cols), gap + Math.floor(i / cols) * ((1 - gap) / rows), (1 - gap) / cols - gap, (1 - gap) / rows - gap) })) });
  };
  const field = (label, value, onChange, props = {}) => h("label", { className: "dbfox-comic-field" }, h("span", null, label), h("input", { value, onChange: (e) => onChange(e.target.value), ...props }));
  const draftField = (key, value) => setDraft((d) => ({ ...d, data: { ...d.data, [key]: value } }));

  if (!comicId) return h("section", { className: "dbfox-comic dbfox-comic-library" }, h("header", null, h("p", { className: "dbfox-comic-eyebrow" }, "VISUAL NARRATIVE"), h("h2", null, "Comic Studio"), h("p", null, "从一页分镜开始，让镜头、角色和对白成为可继续编辑的作品。")),
    h("form", { onSubmit: (e) => { e.preventDefault(); if (title.trim()) write("comics.create", { title: title.trim() }); } }, field("作品名称", title, setTitle, { maxLength: 160, placeholder: "例如：灯塔归途" }), h("button", { type: "submit", disabled: busy || !title.trim() }, "新建作品")),
    error && h("p", { role: "alert" }, error), h("div", { className: "dbfox-comic-projects" }, ...comics.map((comic) => button(`${comic.title} · ${comic.page_count} 页 · v${comic.version}`, () => open(projectId, comic), busy, { key: comic.id }))));

  return h("section", { className: "dbfox-comic dbfox-comic-studio" },
    h("header", { className: "dbfox-comic-topbar" }, h("div", null, h("p", { className: "dbfox-comic-eyebrow" }, "COMIC / STORYBOARD"), h("h2", null, snapshot?.title || "加载作品")),
      h("span", { className: "dbfox-comic-version" }, snapshot ? `v${snapshot.version} · ${snapshot.page_count} 页` : ""),
      button("刷新", () => read(), busy || !!draft), button("导出工件", () => write("comics.artifact", {}), disabled),
      button("交给 Agent", () => context.onAsk({ label: `${snapshot.title} · ${selected || pageId}`, authority: { kind: KIND, id: comicId }, object: { kind: selected ? "dbfox.comic.object" : KIND, id: selected || comicId, version: snapshot.version }, locator: selected ? `/objects/${encodeURIComponent(selected)}` : "/" }), disabled),
      button("作品库", () => open(projectId), disabled || !!draft)),
    h("div", { className: "dbfox-comic-toolbar" }, h("div", { role: "group", "aria-label": "视图" }, button("页面", () => setView("page"), false, { "aria-pressed": view === "page" }), button("分镜", () => setView("storyboard"), false, { "aria-pressed": view === "storyboard" })),
      button("添加页", () => apply({ kind: "page_create", page: { id: id("page"), title: `第 ${pages.length + 1} 页`, width: 720, height: 960, background: "#FFFFFF", panels: [] } }), disabled),
      button("添加面板", () => apply({ kind: "panel_create", page_id: page.id, panels: [{ id: id("panel"), title: `镜头 ${page.panels.length + 1}`, rect: rect(.05, .05, .9, .4), background: "#E8EDF0", elements: [] }] }), disabled || !page),
      button("整理布局", layout, disabled || !page?.panels.length),
      h("label", null, "拖动 ", h("select", { value: mode, onChange: (e) => setMode(e.target.value) }, h("option", { value: "move" }, "移动"), h("option", { value: "resize" }, "调整大小"))),
      h("label", null, "缩放 ", h("select", { value: zoom, onChange: (e) => setZoom(Number(e.target.value)) }, ...[50, 75, 100, 125, 150].map((n) => h("option", { value: n, key: n }, `${n}%`)))),
      h("label", null, h("input", { type: "checkbox", checked: notes, onChange: (e) => setNotes(e.target.checked) }), "视觉注释")),
    error && h("p", { className: "dbfox-comic-feedback dbfox-comic-error", role: "alert" }, error), notice && h("p", { className: "dbfox-comic-feedback", role: "status" }, notice),
    h("div", { className: "dbfox-comic-workspace" },
      h("nav", { className: "dbfox-comic-pages", "aria-label": "作品页面" }, h("h3", null, "页面"), ...pages.map((p, i) => button(`${String(i + 1).padStart(2, "0")}  ${p.title}`, () => { setPageId(p.id); setSelected(""); }, busy || !!draft, { key: p.id, "aria-current": p.id === pageId ? "page" : undefined })),
        page && h("div", { className: "dbfox-comic-page-actions" }, button("页面属性", () => setDraft({ type: "page", data: { page_id: page.id, title: page.title, background: page.background, width: page.width, height: page.height }, version: snapshot.version }), disabled || !!draft), button("上移页", () => { const order = pages.map((p) => p.id), at = order.indexOf(pageId); if (at > 0) { [order[at - 1], order[at]] = [order[at], order[at - 1]]; apply({ kind: "page_reorder", page_ids: order }); } }, disabled || pages[0]?.id === pageId), button("删除页", () => apply({ kind: "object_delete", object_id: pageId }), disabled))),
      h("main", { className: "dbfox-comic-stage", "aria-label": "作品区", style: { "--comic-zoom": zoom / 100 } },
        !page ? h("div", { className: "dbfox-comic-empty" }, h("h3", null, "第一幕，从这里开始"), h("p", null, "添加页面，然后放置面板、角色与对白。")) :
          view === "page" ? h("div", { className: "dbfox-comic-paper" }, h(PageCanvas, { page, selected, showNotes: notes, onSelect: select, onTransform: transform, onGesture: (value) => { live.current.gesture = value; }, mode, disabled: disabled || !!draft, snapshotVersion: snapshot.version })) :
            h("div", { className: "dbfox-comic-storyboard" }, ...page.panels.map((panel, index) => h("article", { key: panel.id, className: "dbfox-comic-shot-card" },
              h("header", null, button(`${String(index + 1).padStart(2, "0")} · ${panel.title}`, () => select(panel.id)), h("span", null, `${panel.shot.framing} · ${panel.shot.duration_seconds}s`)),
              h(PageCanvas, { page: { ...page, width: Math.round(panel.rect.width * page.width), height: Math.round(panel.rect.height * page.height), panels: [{ ...panel, rect: { x: 0, y: 0, width: 1, height: 1 } }] }, selected, showNotes: notes, onSelect: select,
                onTransform: (object, parent, next, version) => { if (parent) transform(object, panel, next, version); }, onGesture: (value) => { live.current.gesture = value; }, panelTransforms: false, mode, disabled: disabled || !!draft, snapshotVersion: snapshot.version }),
              h("p", null, panel.shot.description || "为这个镜头添加视觉描述"))))),
      h("aside", { className: "dbfox-comic-inspector", "aria-label": "面板与对白编辑器" }, h("h3", null, "镜头与对白"),
        page && h("div", { className: "dbfox-comic-object-list" }, ...page.panels.map((panel) => h("div", { key: panel.id }, button(panel.title, () => select(panel.id), false, { "aria-pressed": selected === panel.id }), ...panel.elements.map((element) => button(`${labels[element.kind]} · ${(element.label || element.text || "空白").slice(0, 22)}`, () => select(element.id), false, { key: element.id, "aria-pressed": selected === element.id, className: "dbfox-comic-child" }))))),
        selectedPanel && h("div", { className: "dbfox-comic-add-elements" }, ...["character", "bubble", "caption", "note"].map((kind) => button(`+ ${labels[kind]}`, () => createElement(kind), disabled || !!draft, { key: kind }))),
        selectedPanel && !draft && h("div", { className: "dbfox-comic-details" }, h("p", null, selectedElement ? `${labels[selectedElement.kind]} · ${selectedElement.id}` : `${selectedPanel.title} · ${selectedPanel.shot.framing}`),
          button(selectedElement ? "编辑对象" : "编辑镜头", () => setDraft({ type: selectedElement ? "element" : "shot", panelId: selectedPanel.id, data: structuredClone(selectedElement || selectedPanel.shot), version: snapshot.version }), disabled),
          button("面板属性", () => setDraft({ type: "panel", data: { panel_id: selectedPanel.id, title: selectedPanel.title, background: selectedPanel.background }, version: snapshot.version }), disabled),
          button("删除所选", () => apply({ kind: "object_delete", object_id: selectedElement?.id || selectedPanel.id }), disabled),
          button("镜头前移", () => { const order = page.panels.map((p) => p.id), at = order.indexOf(selectedPanel.id); if (at > 0) { [order[at - 1], order[at]] = [order[at], order[at - 1]]; apply({ kind: "panel_reorder", page_id: page.id, panel_ids: order }); } }, disabled || page.panels[0]?.id === selectedPanel.id)),
        draft && h("form", { className: "dbfox-comic-edit-form", onSubmit: (e) => { e.preventDefault(); apply(["page", "panel"].includes(draft.type) ? { kind: `${draft.type}_update`, ...draft.data } : draft.type === "shot" ? { kind: "shot_set", panel_id: draft.panelId, shot: draft.data } : { kind: "element_update", panel_id: draft.panelId, element: draft.data }, draft.version); } },
          h("p", null, `基于 v${draft.version} 的编辑草稿`),
          ["page", "panel"].includes(draft.type) ? h(React.Fragment, null,
            field("标题", draft.data.title, (value) => draftField("title", value), { maxLength: 120, required: true }),
            field("背景颜色", draft.data.background, (value) => draftField("background", value), { type: "color" }),
            draft.type === "page" && h(React.Fragment, null, ...[["width", "页面宽度"], ["height", "页面高度"]].map(([key, label]) => field(label, draft.data[key], (value) => draftField(key, Number(value)), { key, type: "number", min: 240, max: 2400, step: 1 })))) :
          draft.type === "shot" ? h(React.Fragment, null,
            ...[["framing", "景别", ["wide", "full", "medium", "close", "detail"]], ["angle", "角度", ["eye", "high", "low", "overhead"]], ["movement", "运镜", ["static", "pan", "tilt", "track", "zoom"]]].map(([key, label, options]) => h("label", { key, className: "dbfox-comic-field" }, label, h("select", { value: draft.data[key], onChange: (e) => draftField(key, e.target.value) }, ...options.map((v) => h("option", { key: v, value: v }, v))))),
            field("时长（秒）", draft.data.duration_seconds, (v) => draftField("duration_seconds", Number(v)), { type: "number", min: .1, max: 600, step: .1 }),
            h("label", { className: "dbfox-comic-field" }, "视觉描述", h("textarea", { value: draft.data.description, maxLength: 2000, onChange: (e) => draftField("description", e.target.value) }))) : h(React.Fragment, null,
            draft.data.kind === "character" ? field("角色视觉标签", draft.data.label, (v) => draftField("label", v), { maxLength: 120, required: true }) : h("label", { className: "dbfox-comic-field" }, "文字内容", h("textarea", { value: draft.data.text, maxLength: 2000, onChange: (e) => draftField("text", e.target.value) })),
            ...Object.entries(draft.data.rect).map(([key, value]) => field(key, value, (v) => draftField("rect", { ...draft.data.rect, [key]: Number(v) }), { key, type: "number", step: .01, min: 0, max: 1 })),
            draft.data.font_size && field("字号", draft.data.font_size, (v) => draftField("font_size", Number(v)), { type: "number", min: 10, max: 72 }),
            draft.data.color && field("颜色", draft.data.color, (v) => draftField("color", v), { type: "color" }),
            draft.data.kind === "character" && h(React.Fragment, null, ...[["pose", "姿态", ["standing", "walking", "seated", "reaching"]], ["facing", "朝向", ["left", "right", "front"]]].map(([key, label, options]) => h("label", { className: "dbfox-comic-field", key }, label, h("select", { value: draft.data[key], onChange: (e) => draftField(key, e.target.value) }, ...options.map((value) => h("option", { key: value, value }, value)))))),
            draft.data.kind === "bubble" && h(React.Fragment, null, h("label", { className: "dbfox-comic-field" }, "气泡样式", h("select", { value: draft.data.style, onChange: (e) => draftField("style", e.target.value) }, ...["speech", "thought", "shout"].map((value) => h("option", { key: value, value }, value)))), ...["tail_x", "tail_y"].map((key) => field(key, draft.data[key], (value) => draftField(key, Number(value)), { key, type: "number", min: 0, max: 1, step: .01 }))),
            draft.data.kind === "bubble" && h("label", { className: "dbfox-comic-field" }, "说话角色", h("select", { value: draft.data.speaker_id || "", onChange: (e) => draftField("speaker_id", e.target.value || null) }, h("option", { value: "" }, "不指定"), ...selectedPanel.elements.filter((e) => e.kind === "character").map((e) => h("option", { key: e.id, value: e.id }, e.label))))),
          h("button", { type: "submit", disabled: busy }, "保存修改"), button("取消草稿", () => { setDraft(null); live.current.draft = null; read(); }, busy)),
        snapshot && h("details", { className: "dbfox-comic-history" }, h("summary", null, "历史与恢复"), field("目标版本", revision, (v) => setRevision(Number(v)), { type: "number", min: 1, max: snapshot.version }), button("比较当前版本", () => compare(), disabled || !!draft), button("恢复为新版本", () => write("comics.undo", { target_version: revision }), disabled || !!draft), h("p", null, "历史版本保持不变，恢复会产生新版本。"),
          differences && h("div", { className: "dbfox-comic-diff", role: "status" }, h("p", null, `${differences.total} 项差异`), ...differences.differences.map((item, index) => h("pre", { key: index }, JSON.stringify(item, null, 2))), differences.next_offset < differences.total && button("下一页差异", () => compare(differences.next_offset), disabled)),
          button("删除作品", () => write("comics.delete", {}), disabled || !!draft)))));
}

function ComicArtifact({ artifact, payload, context }) {
  const [page, setPage] = React.useState(null), [pages, setPages] = React.useState([]), [error, setError] = React.useState("");
  const state = React.useRef({ alive: true, controller: null, serial: 0 });
  const select = async (pageId) => {
    const serial = ++state.current.serial, controller = state.current.controller;
    try { const result = await context.representations.read(artifact.id, REP, { operation: "page", parameters: { page_id: pageId } }, controller.signal); if (state.current.alive && !controller.signal.aborted && serial === state.current.serial) { setPage(result.payload.items[0]); setError(""); } }
    catch (e) { if (state.current.alive && !controller.signal.aborted && serial === state.current.serial) setError(message(e)); }
  };
  React.useEffect(() => {
    state.current.alive = true;
    const controller = new AbortController(); state.current.controller = controller;
    const stop = () => { state.current.alive = false; ++state.current.serial; controller.abort(); if (state.current.url) URL.revokeObjectURL(state.current.url); state.current.url = null; };
    cleanups.add(stop);
    (async () => { try { const all = []; let offset = 0; for (;;) { const result = await context.representations.read(artifact.id, REP, { operation: "pages", parameters: { offset, limit: 32 } }, controller.signal); all.push(...result.payload.items); if (!result.payload.has_more) break; offset = result.payload.next_offset; } if (state.current.alive && !controller.signal.aborted) { setPages(all); if (all.length) select(all[0].id); } } catch (e) { if (state.current.alive && !controller.signal.aborted) setError(message(e)); } })();
    return () => { stop(); cleanups.delete(stop); };
  }, [artifact.id]);
  const download = async (format) => {
    const controller = state.current.controller;
    try {
      const blob = await context.representations.stream(artifact.id, REP, { operation: `export_${format}`, parameters: {} }, controller.signal);
      if (!state.current.alive || controller.signal.aborted) return;
      if (state.current.url) URL.revokeObjectURL(state.current.url);
      const url = URL.createObjectURL(blob); state.current.url = url;
      const link = document.createElement("a"); link.href = url; link.download = `dbfox-comic-${payload.id}-v${payload.version}.${format}`; document.body.append(link); link.click(); link.remove();
    } catch (e) { if (state.current.alive && !controller.signal.aborted) setError(message(e)); }
  };
  return h("article", { className: "dbfox-comic dbfox-comic-artifact" }, h("h3", null, `${payload.title} · v${payload.version}`), h("p", null, `${payload.page_count} 页 · ${payload.panel_count} 面板 · 不可变快照`),
    h("div", { className: "dbfox-comic-toolbar" }, button("下载 HTML", () => download("html")), button("下载 JSON", () => download("json")),
      h("label", null, "页面 ", h("select", { value: page?.id || "", onChange: (e) => select(e.target.value) }, ...pages.map((p) => h("option", { key: p.id, value: p.id }, p.title))))),
    error && h("p", { role: "alert" }, error), page && h(PageCanvas, { page, disabled: true, showNotes: false, selected: null }),
    h("p", { className: "dbfox-comic-fingerprint" }, payload.content_hash));
}

export function register(extensionHost) {
  host = extensionHost; React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("Comic Studio requires the public Host React API.");
  active = true; epoch += 1;
  stylesheet?.remove(); stylesheet = document.createElement("link"); stylesheet.rel = "stylesheet"; stylesheet.href = new URL("./index.css", import.meta.url).href; document.head.append(stylesheet);
  host.connectors.register({ id: OWNER, title: "Comic Studio", icon: h("span", { "aria-hidden": true }, "▤"), addLabel: "新建漫画作品", onAdd: ({ projectId }) => open(projectId),
    render: ({ projectId }) => h("div", { className: "dbfox-comic" }, h("p", null, "漫画页面、镜头与对白"), button("打开 Comic Studio", () => open(projectId))),
    listResources: async ({ projectId }) => { const all = []; let offset = 0; const generation = epoch;
      for (;;) { const result = await host.operations.invoke("comics.list", { offset, limit: 32 }, { projectId }); if (!active || generation !== epoch) return []; all.push(...result.comics); if (result.next_offset >= result.total) break; offset = result.next_offset; }
      return all.map((c) => ({ kind: KIND, id: c.id, name: c.title, detail: `v${c.version} · ${c.page_count} 页` })); } });
  host.dockViews.register({ viewType: VIEW, resolveTitle: (view) => view.title, icon: () => h("span", { "aria-hidden": true }, "▤"), isVisible: (view, context) => view.projectId === context.activeProjectId,
    render: (view, context) => h(Studio, { key: `${view.projectId}:${view.viewKey}`, projectId: view.projectId, initialId: view.target?.type === "object" ? view.target.object.id : null, context }) });
  host.artifactViews.register({ id: "dbfox.comic.revision-view", title: "Comic 作品", priority: 100, surfaces: ["inline", "workspace"], artifactTypes: [{ type: ARTIFACT, schemaVersions: [1] }], representationTypes: [REP],
    parsePayload(value) { if (!value || typeof value.id !== "string" || typeof value.title !== "string" || !Number.isInteger(value.version) || !/^[a-f0-9]{64}$/.test(value.content_hash)) throw new Error("Invalid Comic revision Artifact"); return value; },
    render: (artifact, payload, context) => h(ComicArtifact, { key: artifact.id, artifact, payload, context }) });
}

export function deactivate() {
  active = false; epoch += 1;
  for (const stop of cleanups) stop();
  cleanups.clear(); stylesheet?.remove(); stylesheet = null;
}
