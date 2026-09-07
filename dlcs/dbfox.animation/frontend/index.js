import { createPlayback, curveTrack, advance } from "./playback.js";
import { KIND, ARTIFACT, REPRESENTATION, identity, readDocument, reference, visibleKeys } from "./model.js";

let React, host, stylesheet, active = false;
const lifecycle = new Set(), VIEW = "dbfox.animation.workbench";
const h = (...args) => React.createElement(...args);
const button = (label, onClick, disabled = false, props = {}) => h("button", { type: "button", onClick, disabled, ...props }, label);
const errorText = (error) => String(error?.message || "动画操作失败").slice(0, 400);
const input = (label, value, onChange, props = {}) => h("label", { className: "dbfox-animation__field" }, h("span", null, label), h("input", { "aria-label": label, value, type: "number", onChange: (event) => onChange(event.target.value), ...props }));
const select = (label, value, onChange, options) => h("label", { className: "dbfox-animation__field" }, h("span", null, label), h("select", { "aria-label": label, value, onChange: (event) => onChange(event.target.value) }, options.map(([id, title]) => h("option", { key: id, value: id }, title))));
function open(projectId, animation) {
  host.dockViews.open({ viewKey: `${VIEW}:${projectId}:${animation?.id || "library"}`, viewType: VIEW, title: animation?.title || "Animation Studio", projectId, closeable: true,
    ...(animation ? { target: { type: "object", object: { kind: KIND, id: animation.id }, authority: { kind: KIND, id: animation.id } } } : {}) });
}

function Workbench({ projectId, initialId, context }) {
  const [animations, setAnimations] = React.useState([]), [animationId, setAnimationId] = React.useState(initialId || "");
  const [snapshot, setSnapshot] = React.useState(null), [selectedTrack, setSelectedTrack] = React.useState(""), [selectedKey, setSelectedKey] = React.useState("");
  const [busy, setBusy] = React.useState(false), [loading, setLoading] = React.useState(false), [error, setError] = React.useState(""), [notice, setNotice] = React.useState("");
  const [tick, setTick] = React.useState(0), [playing, setPlaying] = React.useState(false), [clipId, setClipId] = React.useState("");
  const [windowStart, setWindowStart] = React.useState(0), [windowSpan, setWindowSpan] = React.useState(8000), [rowStart, setRowStart] = React.useState(0);
  const [draft, setDraft] = React.useState(null), [exported, setExported] = React.useState(null), [refresh, setRefresh] = React.useState(0);
  const live = React.useRef({ alive: true, busy: false, read: null, write: null, snapshot: null, generation: 0 });
  const playback = React.useRef(null), preview = React.useRef(null), root = React.useRef(null);
  const invoke = React.useCallback((name, body, signal) => host.operations.invoke(name, body, { projectId, signal }), [projectId]);
  const track = snapshot?.tracks.find((item) => item.id === selectedTrack), key = snapshot?.keyframes.find((item) => item.id === selectedKey);
  const target = snapshot?.targets.find((item) => item.id === track?.target_id);
  const refreshList = React.useCallback(async (signal) => { const result = await invoke("animations.list", { offset: 0, limit: 100 }, signal); if (live.current.alive) setAnimations(result.animations); }, [invoke]);
  React.useEffect(() => {
    live.current.alive = true;
    const stop = () => { live.current.alive = false; live.current.generation++; live.current.read?.abort(); live.current.write?.abort(); playback.current?.dispose(); };
    lifecycle.add(stop);
    const controller = new AbortController();
    refreshList(controller.signal).catch((caught) => { if (!controller.signal.aborted) setError(errorText(caught)); });
    return () => { controller.abort(); stop(); lifecycle.delete(stop); };
  }, [refreshList]);
  React.useEffect(() => {
    const observer = new IntersectionObserver((entries) => { if (!entries.some((entry) => entry.isIntersecting)) setPlaying(false); });
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  React.useEffect(() => () => { live.current.write?.abort(); }, [context.workbenchScopeId]);
  React.useEffect(() => {
    const controller = new AbortController(), generation = ++live.current.generation;
    live.current.read?.abort(); live.current.read = controller;
    setSnapshot(null); setPlaying(false); setDraft(null); setExported(null); setError("");
    if (!animationId) return () => controller.abort();
    setLoading(true);
    readDocument(invoke, animationId, controller.signal).then((value) => {
      if (!live.current.alive || generation !== live.current.generation) return;
      live.current.snapshot = value; setSnapshot(value); setAnimations((items) => items.map((item) => item.id === value.animation.id ? value.animation : item));
      setSelectedTrack((id) => value.tracks.some((item) => item.id === id) ? id : value.tracks[0]?.id || "");
      setSelectedKey((id) => value.keyframes.some((item) => item.id === id) ? id : "");
      setWindowSpan((span) => Math.min(span, value.timing.duration));
      setWindowStart((start) => Math.min(start, Math.max(0, value.timing.duration - 1)));
      setClipId((id) => value.clips.some((item) => item.id === id) ? id : "");
    }).catch((caught) => { if (!controller.signal.aborted) setError(errorText(caught)); })
      .finally(() => { if (generation === live.current.generation) setLoading(false); });
    return () => controller.abort();
  }, [animationId, refresh, invoke]);
  React.useEffect(() => {
    if (!snapshot) return;
    const next = createPlayback(snapshot, clipId || null); playback.current = next;
    setTick((value) => Math.max(next.start, Math.min(next.end, value)));
    return () => { next.dispose(); if (playback.current === next) playback.current = null; };
  }, [snapshot, clipId]);
  React.useEffect(() => {
    const engine = playback.current;
    if (!engine) return;
    engine.seek(tick);
    if (preview.current && target) {
      const object = engine.targets.get(target.id);
      if (object) { preview.current.style.transform = `translate(${Math.max(-80, Math.min(80, object.position.x * 12))}px,${Math.max(-50, Math.min(50, -object.position.y * 12))}px) rotate(${object.rotation.z}rad) scale(${Math.max(.1, Math.min(3, Math.abs(object.scale.x)))},${Math.max(.1, Math.min(3, Math.abs(object.scale.y)))})`; }
    }
  }, [tick, target, snapshot, clipId]);
  React.useEffect(() => {
    if (!playing || !snapshot || !playback.current) return;
    let frame, last = performance.now(), current = tick;
    const loop = (now) => {
      if (!active || !live.current.alive || document.visibilityState === "hidden") { setPlaying(false); return; }
      const engine = playback.current;
      const step = advance(current, Math.min(250, now - last) * snapshot.timing.rate, engine.start, engine.end, snapshot.timing.loop, snapshot.markers);
      last = now; current = step.tick; setTick(current);
      if (step.crossed.length) setNotice(`标记：${step.crossed.map((id) => snapshot.markers.find((marker) => marker.id === id)?.name).join(" · ")}`);
      if (step.ended) setPlaying(false); else frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [playing, snapshot, clipId]);

  async function mutate(operation, version = snapshot?.animation.version) {
    if (live.current.busy || !snapshot || !active) return false;
    live.current.busy = true; setBusy(true); setPlaying(false); setError("");
    try {
      const controller = new AbortController(); live.current.write = controller;
      const result = await invoke("animations.apply", { animation_id: snapshot.animation.id, expected_version: version, operation, request_id: identity("edit") }, controller.signal);
      if (!live.current.alive) return false;
      setDraft(null); setNotice(result.changed ? `已保存 v${result.animation.version}` : "内容未改变"); setRefresh((value) => value + 1); return true;
    } catch (caught) { if (live.current.alive) setError(`${errorText(caught)} 保留当前编辑，请刷新后重新检查。`); return false; }
    finally { live.current.busy = false; if (live.current.alive) setBusy(false); }
  }
  async function action(name, body) {
    if (live.current.busy || !active) return;
    live.current.busy = true; setBusy(true); setPlaying(false); setError("");
    try {
      const controller = new AbortController(); live.current.write = controller;
      const scope = context.workbenchScopeId;
      if (name === "animations.artifact" && !host.workbench.openArtifact) throw new Error("当前 Host 不支持打开导出工件。");
      const result = await invoke(name, { ...body, request_id: identity("action") }, controller.signal);
      if (!live.current.alive) return;
      if (name === "animations.create") { await refreshList(); setAnimationId(result.animation.id); }
      else if (name === "animations.artifact") {
        setExported(result);
        await host.workbench.openArtifact({ projectId, sessionId: result.session_id, runId: result.run_id, artifactId: result.artifact_id }, { workbenchScopeId: scope, signal: controller.signal });
        if (live.current.alive) setNotice("固定版本 Artifact 已打开，可查看和下载。");
      }
      else if (name === "animations.delete") { setAnimationId(""); setDraft(null); await refreshList(); setNotice("动画已删除；已有固定版本 Artifact 保留。"); }
      else { setDraft(null); setRefresh((value) => value + 1); }
    } catch (caught) { if (live.current.alive) setError(errorText(caught)); }
    finally { live.current.busy = false; if (live.current.alive) setBusy(false); }
  }
  function undo() { if (snapshot?.animation.version > 1) void action("animations.undo", { animation_id: animationId, expected_version: snapshot.animation.version, target_version: snapshot.animation.version - 1 }); }
  function chooseKey(item) { if(draft||locked)return; setPlaying(false); setSelectedKey(item.id); setSelectedTrack(item.track_id); setTick(item.tick); setDraft(null); }
  function keyboard(event) {
    if (/INPUT|SELECT|TEXTAREA/.test(event.target.tagName) || event.target.isContentEditable || busy) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); undo(); }
    else if (event.code === "Space") { event.preventDefault(); if (!draft) setPlaying((value) => !value); }
    else if (key && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault(); const frame = Math.round(key.tick * snapshot.timing.fps / 1000), delta = (event.shiftKey ? 10 : 1) * (event.key === "ArrowLeft" ? -1 : 1);
      void mutate({ kind: "keyframe_move", keyframes: [{ id: key.id, tick: Math.max(0, Math.min(snapshot.timing.duration, Math.round((frame + delta) * 1000 / snapshot.timing.fps))), value: key.value }] });
    } else if (key && (event.key === "Delete" || event.key === "Backspace")) { event.preventDefault(); void mutate({kind:"entity_delete",section:"keyframes",ids:[key.id],cascade:false}); }
  }
  const locked = busy || loading;
  const viewEnd = snapshot ? Math.min(snapshot.timing.duration, windowStart + windowSpan) : windowSpan;
  return h("section", { className: "dbfox-animation", ref: root, onKeyDown: keyboard, tabIndex: 0, "aria-label": "Animation Studio" },
    h("header", { className: "dbfox-animation__toolbar" }, h("strong", null, "Animation Studio"),
      select("动画", animationId, (id) => { setAnimationId(id); setSelectedKey(""); }, [["", "选择动画"], ...animations.map((item) => [item.id, `${item.title} · v${item.version}`])]),
      h(NewDocument, { busy: locked, create: (title) => action("animations.create", { title }) }),
      button("刷新", () => { setRefresh((value) => value + 1); void refreshList(); }, locked),
      button("撤销", undo, locked || !snapshot || snapshot.animation.version <= 1 || !!draft),
      button("导出固定版本", () => action("animations.artifact", { animation_id: animationId, expected_version: snapshot.animation.version }), locked || !snapshot || !!draft)),
    error ? h("p", { role: "alert", className: "dbfox-animation__error" }, error) : null,
    h("p", { role: "status", className: "dbfox-animation__status" }, loading ? "正在读取固定版本…" : notice || (snapshot ? `v${snapshot.animation.version} · ${snapshot.tracks.length} 轨道 · ${snapshot.keyframes.length} 关键帧` : "创建动画，然后添加对象与轨道。")),
    snapshot ? h(React.Fragment, null,
      h("div", { className: "dbfox-animation__transport" }, button(playing ? "暂停" : "播放", () => { if (!playing && tick >= playback.current?.end) setTick(playback.current.start); setPlaying((value) => !value); }, locked || !!draft),
        button("起点", () => { setPlaying(false); setTick(playback.current.start); }, locked),
        input("播放位置 ms", Math.round(tick), (value) => { setPlaying(false); setTick(Math.max(playback.current.start, Math.min(playback.current.end, Number(value)))); }, { min: 0, max: snapshot.timing.duration, step: 1, disabled: locked }),
        select("片段", clipId, (id) => { setPlaying(false); setClipId(id); }, [["", "完整时间线"], ...snapshot.clips.map((item) => [item.id, item.name])]),
        input("窗口起点 ms", windowStart, (value) => setWindowStart(Math.max(0, Math.min(snapshot.timing.duration - 1, Number(value)))), { min: 0, max: snapshot.timing.duration - 1 }),
        input("窗口长度 ms", windowSpan, (value) => setWindowSpan(Math.max(1, Math.min(snapshot.timing.duration, Number(value)))), { min: 1, max: snapshot.timing.duration })),
      h("div", { className: "dbfox-animation__layout" }, h("main", { className: "dbfox-animation__main" },
        h(Timeline, { snapshot, start: windowStart, end: viewEnd, rowStart, setRowStart, selectedTrack, selectedKey, tick, locked: locked || !!draft,
          chooseTrack: (id) => { setSelectedTrack(id); setSelectedKey(""); }, chooseKey, seek: (value) => { setPlaying(false); setTick(value); }, mutate, draft, setDraft }),
        h("div", { className: "dbfox-animation__row" }, button("关键帧 +", () => mutate({ kind: "keyframe_add", keyframes: [{ id: identity("key"), track_id: track.id, tick: Math.round(tick), value: 0, curve_id: null }] }), locked || !track || !!draft),
          button("标记 +", () => mutate({ kind: "marker_set", marker: { id: identity("marker"), name: "标记", tick: Math.round(tick) } }), locked || !!draft),
          button("交给 Agent", () => context.onAsk(reference(snapshot, key, track)), locked),
          h("span", { className: "dbfox-animation__muted" }, "空格播放 · 方向键移动关键帧 · Delete 删除 · Ctrl+Z 撤销")),
        track ? h(CurveEditor, { key: `${snapshot.animation.version}:${track.id}:${selectedKey}`, snapshot, track, selected: key, chooseKey, locked: locked || !!draft, mutate, setDraft }) : h("p", null, "添加轨道以开始设置关键帧。"),
        h(KeyTable, { keys: snapshot.keyframes.filter((item) => item.track_id === selectedTrack).sort((a,b) => a.tick-b.tick), selectedKey, chooseKey }),
      ), h("aside", { className: "dbfox-animation__inspector" },
        h("div", { className: "dbfox-animation__preview", "aria-label": "局部对象 XY 运动预览" }, h("span", { className: "dbfox-animation__muted" }, "局部 XY 预览"), h("div", { className: "dbfox-animation__preview-object", ref: preview }, target?.name || "对象")),
        target?.source ? h("small", null, `Scene ${target.source.scene_id} · v${target.source.version} · ${target.source.object_id}`) : null,
        h(Inspector, { key: `${snapshot.animation.version}:${selectedKey}:${selectedTrack}`, snapshot, track, selected: key, tick, locked, mutate, draft, setDraft }),
      )),
      h("details", null, h("summary", null, "文档管理"), h("p", null, "删除会从活动资源移除动画；已有固定版本 Artifact 保留。"),
        button("删除当前动画", () => action("animations.delete", { animation_id: animationId, expected_version: snapshot.animation.version }), locked || !!draft)),
      exported ? h("small", null, `Artifact ${exported.artifact_id}`) : null,
    ) : null);
}

function NewDocument({ create, busy }) {
  const [title, setTitle] = React.useState("");
  return h("form", { className: "dbfox-animation__row", onSubmit: (event) => { event.preventDefault(); if(title.trim()) void create(title.trim()); } },
    input("新动画名称", title, setTitle, { type: "text", maxLength: 120, required: true, disabled: busy }), h("button", { type: "submit", disabled: busy || !title.trim() }, "创建"));
}

function Timeline({ snapshot, start, end, rowStart, setRowStart, selectedTrack, selectedKey, tick, locked, chooseTrack, chooseKey, seek, mutate, setDraft }) {
  const canvas = React.useRef(null), drag = React.useRef(null), [width, setWidth] = React.useState(600), [dragTick, setDragTick] = React.useState(null);
  const rows = snapshot.tracks.slice(rowStart, rowStart + 12), rowHeight = 30, header = 34, height = header + Math.max(3, rows.length) * rowHeight;
  const keys = React.useMemo(() => visibleKeys(snapshot.keyframes, rows.map((item) => item.id), start, end), [snapshot, rowStart, start, end]);
  React.useEffect(() => { const element = canvas.current; const observer = new ResizeObserver(() => setWidth(Math.max(180, element.clientWidth))); observer.observe(element); return () => observer.disconnect(); }, []);
  const x = (time) => (time - start) / Math.max(1, end - start) * width;
  React.useEffect(() => {
    const element = canvas.current, context = element.getContext("2d"), colors = getComputedStyle(element);
    const dpr = Math.min(2, devicePixelRatio || 1); element.width = width * dpr; element.height = height * dpr; context.scale(dpr, dpr);
    context.fillStyle = colors.getPropertyValue("--dbfox-animation__bg").trim(); context.fillRect(0,0,width,height);
    context.strokeStyle = colors.getPropertyValue("--dbfox-animation__border").trim(); context.fillStyle = colors.color; context.font = "11px sans-serif";
    const divisions=Math.max(2,Math.floor(width/75));
    for(let i=0;i<=divisions;i++){ const px=i/divisions*width; context.beginPath();context.moveTo(px,0);context.lineTo(px,height);context.stroke();const label=`${Math.round(start+(end-start)*i/divisions)}`;context.fillText(label,Math.min(px+3,width-context.measureText(label).width-3),12); }
    for(let index=0;index<rows.length;index++){ if(rows[index].id===selectedTrack){context.fillStyle=colors.getPropertyValue("--dbfox-animation__selected").trim();context.fillRect(0,header+index*rowHeight,width,rowHeight);} }
    for(const marker of snapshot.markers){if(marker.tick<start||marker.tick>end)continue; const px=x(marker.tick); context.fillStyle=colors.getPropertyValue("--dbfox-animation__accent").trim();context.fillRect(px-1,17,2,12);context.fillText(marker.name.slice(0,10),px+3,27);}
    for(const key of keys){const index=rows.findIndex((row)=>row.id===key.track_id),px=x(key.id===selectedKey&&dragTick!==null?dragTick:key.tick),py=header+index*rowHeight+rowHeight/2;context.fillStyle=colors.getPropertyValue(key.id===selectedKey?"--dbfox-animation__accent":"--dbfox-animation__text").trim();context.beginPath();context.moveTo(px,py-5);context.lineTo(px+5,py);context.lineTo(px,py+5);context.lineTo(px-5,py);context.closePath();context.fill();}
    context.strokeStyle=colors.getPropertyValue("--dbfox-animation__accent").trim();context.beginPath();context.moveTo(x(tick),0);context.lineTo(x(tick),height);context.stroke();
  }, [snapshot,start,end,rowStart,selectedTrack,selectedKey,tick,width,height,dragTick]);
  function point(event){const rect=canvas.current.getBoundingClientRect();return {x:event.clientX-rect.left,y:event.clientY-rect.top};}
  function toTick(px){return Math.max(0,Math.min(snapshot.timing.duration,Math.round(start+px/width*(end-start))));}
  function down(event){if(locked)return;const position=point(event), row=rows[Math.floor((position.y-header)/rowHeight)];const item=row?keys.filter((key)=>key.track_id===row.id).reduce((best,key)=>Math.abs(x(key.tick)-position.x)<8&&(!best||Math.abs(x(key.tick)-position.x)<Math.abs(x(best.tick)-position.x))?key:best,null):null;
    canvas.current.setPointerCapture(event.pointerId);
    if(item){chooseKey(item);drag.current={key:item,version:snapshot.animation.version,x:position.x,moved:false};}else{seek(toTick(position.x));drag.current={scrub:true};if(row)chooseTrack(row.id);}
  }
  function move(event){const gesture=drag.current;if(!gesture)return;const position=point(event);if(gesture.scrub){seek(toTick(position.x));return;}if(Math.abs(position.x-gesture.x)>3){gesture.moved=true;setDragTick(toTick(position.x));setDraft({kind:"gesture"});}}
  function up(event){const gesture=drag.current;drag.current=null;setDragTick(null);setDraft(null);if(gesture?.moved){void mutate({kind:"keyframe_move",keyframes:[{id:gesture.key.id,tick:toTick(point(event).x),value:gesture.key.value}]},gesture.version);}}
  return h("section",{className:"dbfox-animation__timeline","aria-label":"时间线"},h("div",{className:"dbfox-animation__row"},h("strong",null,"轨道与关键帧"),button("上一组轨道",()=>setRowStart(Math.max(0,rowStart-12)),rowStart===0),button("下一组轨道",()=>setRowStart(rowStart+12),rowStart+12>=snapshot.tracks.length)),
    h("div",{className:"dbfox-animation__timeline-grid"},h("div",{className:"dbfox-animation__track-labels",style:{paddingTop:header}},rows.map((row)=>button(row.name,()=>chooseTrack(row.id),false,{key:row.id,"aria-pressed":row.id===selectedTrack,style:{height:rowHeight},title:`${row.id} · ${row.property}`}))),
      h("canvas",{ref:canvas,style:{height},tabIndex:0,"aria-label":"时间线：单击定位或选择关键帧，拖动关键帧移动时间；表格提供键盘替代",onPointerDown:down,onPointerMove:move,onPointerUp:up,onPointerCancel:()=>{drag.current=null;setDraft(null);setDragTick(null);}})));
}

function KeyTable({keys,selectedKey,chooseKey}){
  const [page,setPage]=React.useState(0);React.useEffect(()=>setPage(0),[keys.length]);
  return h("details",{className:"dbfox-animation__key-table"},h("summary",null,`关键帧列表 · ${keys.length}（键盘可操作）`),h("div",{className:"dbfox-animation__row"},button("上一页",()=>setPage(Math.max(0,page-1)),page===0),button("下一页",()=>setPage(page+1),(page+1)*50>=keys.length)),
    h("table",null,h("thead",null,h("tr",null,h("th",null,"关键帧"),h("th",null,"时间 ms"),h("th",null,"值"))),h("tbody",null,keys.slice(page*50,page*50+50).map((key)=>h("tr",{key:key.id},h("td",null,button(key.id,()=>chooseKey(key),false,{"aria-pressed":selectedKey===key.id})),h("td",null,key.tick),h("td",null,key.value))))));
}

function CurveEditor({snapshot,track,selected,locked,mutate,setDraft}){
  const canvas=React.useRef(null),gesture=React.useRef(null),[local,setLocal]=React.useState(null);
  const keys=snapshot.keyframes.filter((key)=>key.track_id===track.id).sort((a,b)=>a.tick-b.tick), index=keys.findIndex((key)=>key.id===selected?.id), next=keys[index+1];
  const original=snapshot.curves.find((curve)=>curve.id===selected?.curve_id)||{id:identity("curve"),kind:"linear",x1:1/3,y1:1/3,x2:2/3,y2:2/3}, curve=local||original;
  React.useEffect(()=>{
    const element=canvas.current,ctx=element.getContext("2d"),style=getComputedStyle(element),w=element.width=600,hh=element.height=200;
    ctx.fillStyle=style.getPropertyValue("--dbfox-animation__bg");ctx.fillRect(0,0,w,hh);ctx.strokeStyle=style.getPropertyValue("--dbfox-animation__border");ctx.strokeRect(30,15,540,160);
    if(!selected||!next)return;
    const native=curveTrack(".position[x]",[{tick:0,value:0,curve_id:curve.id},{tick:1000,value:1}],new Map([[curve.id,curve]])).createInterpolant(new Float64Array(1));
    const px=(value)=>30+value*540,py=(value)=>175-value*160;ctx.strokeStyle=style.getPropertyValue("--dbfox-animation__accent");ctx.lineWidth=2;ctx.beginPath();for(let i=0;i<=200;i++){const value=native.evaluate(i/200)[0];if(i===0)ctx.moveTo(px(0),py(value));else ctx.lineTo(px(i/200),py(value));}ctx.stroke();
    if(curve.kind==="bezier"){ctx.strokeStyle=style.color;ctx.beginPath();ctx.moveTo(px(0),py(0));ctx.lineTo(px(curve.x1),py(curve.y1));ctx.moveTo(px(1),py(1));ctx.lineTo(px(curve.x2),py(curve.y2));ctx.stroke();for(const n of [1,2]){ctx.fillStyle=style.getPropertyValue("--dbfox-animation__accent");ctx.beginPath();ctx.arc(px(curve[`x${n}`]),py(curve[`y${n}`]),7,0,Math.PI*2);ctx.fill();}}
  },[snapshot,track,selected,local]);
  function position(event){const rect=canvas.current.getBoundingClientRect();return {x:(event.clientX-rect.left)/rect.width*600,y:(event.clientY-rect.top)/rect.height*200};}
  function down(event){if(locked||!selected||!next||curve.kind!=="bezier")return;const p=position(event);const handle=[1,2].find((n)=>Math.hypot(p.x-(30+curve[`x${n}`]*540),p.y-(175-curve[`y${n}`]*160))<15);if(handle){gesture.current={handle,curve:{...curve}};canvas.current.setPointerCapture(event.pointerId);setDraft({kind:"curve"});}}
  function move(event){if(!gesture.current)return;const p=position(event),n=gesture.current.handle,value={...gesture.current.curve,[`x${n}`]:Math.max(0,Math.min(1,(p.x-30)/540)),[`y${n}`]:Math.max(-4,Math.min(4,(175-p.y)/160))};if(value.x1>value.x2)value[`x${n}`]=value[`x${n===1?2:1}`];gesture.current.curve=value;setLocal(value);}
  function up(){const change=gesture.current;gesture.current=null;setDraft(null);if(change)void mutate({kind:"easing_set",curve:change.curve,keyframe_ids:[selected.id]});}
  return h("section",{className:"dbfox-animation__curves"},h("div",{className:"dbfox-animation__row"},h("strong",null,"区间曲线"),selected&&next?h("span",null,`${selected.tick} → ${next.tick} ms`):h("span",{className:"dbfox-animation__muted"},"选择一个有后续关键帧的关键帧")),
    h("canvas",{ref:canvas,"aria-label":"曲线图：拖动 Bézier 控制点；属性面板提供数值编辑替代",onPointerDown:down,onPointerMove:move,onPointerUp:up,onPointerCancel:()=>{gesture.current=null;setLocal(null);setDraft(null);}}));
}

function Form({title,initial,build,mutate,locked,setDraft,children}){
  const [value,setValue]=React.useState(initial),[dirty,setDirty]=React.useState(false);
  const change=(patch)=>{setValue((old)=>({...old,...patch}));setDirty(true);setDraft({kind:"form",title});};
  return h("form",{onSubmit:(event)=>{event.preventDefault();void mutate(build(value));}},h("fieldset",{disabled:locked},h("legend",null,title),children(value,change),h("div",{className:"dbfox-animation__row"},h("button",{type:"submit",disabled:!dirty},"保存"),dirty?button("取消",()=>{setValue(initial);setDirty(false);setDraft(null);}):null)));
}

function Inspector({snapshot,track,selected,tick,locked,mutate,draft,setDraft}){
  const [clipPage,setClipPage]=React.useState(0),[markerPage,setMarkerPage]=React.useState(0);
  const form=(title,initial,build,children)=>h(Form,{key:title,title,initial,build,mutate,locked:locked||(draft?.kind==="form"&&draft.title!==title),setDraft,children});
  const curve=snapshot.curves.find((item)=>item.id===selected?.curve_id)||{id:identity("curve"),kind:"linear",x1:1/3,y1:1/3,x2:2/3,y2:2/3};
  return h(React.Fragment,null,
    track?form("轨道属性",track,(value)=>({kind:"track_modify",track:value}),(value,change)=>h(React.Fragment,null,
      input("轨道名称",value.name,(name)=>change({name}),{type:"text",required:true,maxLength:120}),
      select("轨道目标",value.target_id,(target_id)=>change({target_id}),snapshot.targets.map((target)=>[target.id,target.name])),
      select("动画属性",value.property,(property)=>change({property}),["position","rotation","scale"].flatMap((type)=>["x","y","z"].map((axis)=>[`${type}.${axis}`,`${type}.${axis}`]))),
      h("label",null,h("input",{type:"checkbox",checked:value.enabled,onChange:(event)=>change({enabled:event.target.checked})}),"启用轨道"))):null,
    selected?form("关键帧",{tick:selected.tick,value:selected.value},(value)=>({kind:"keyframe_move",keyframes:[{id:selected.id,tick:Number(value.tick),value:Number(value.value)}]}),(value,change)=>h(React.Fragment,null,
      input("关键帧时间 ms",value.tick,(tick)=>change({tick}),{min:0,max:snapshot.timing.duration,step:1}),input("关键帧值",value.value,(value)=>change({value}),{step:"any",min:-1000000,max:1000000}),button("删除关键帧",()=>mutate({kind:"entity_delete",section:"keyframes",ids:[selected.id],cascade:false}),locked))):null,
    selected?form("缓动控制点",curve,(value)=>({kind:"easing_set",curve:{...value,x1:Number(value.x1),y1:Number(value.y1),x2:Number(value.x2),y2:Number(value.y2)},keyframe_ids:[selected.id]}),(value,change)=>h(React.Fragment,null,
      select("插值方式",value.kind,(kind)=>change({kind}),[["linear","线性"],["hold","保持"],["bezier","Bézier"]]),
      value.kind==="bezier"?[1,2].map((n)=>h("div",{key:n,className:"dbfox-animation__row"},input(`控制点 ${n} 时间`,value[`x${n}`],(x)=>change({[`x${n}`]:x}),{min:0,max:1,step:.01}),input(`控制点 ${n} 值`,value[`y${n}`],(y)=>change({[`y${n}`]:y}),{min:-4,max:4,step:.01}))):null,
      h("small",null,"曲线作用于当前关键帧到下一帧的区间。共享曲线的所有引用会一起改变。"))):null,
    h("details",{open:!snapshot.targets.length},h("summary",null,"对象与轨道"),h(CreateTarget,{locked,mutate}),h(CreateTrack,{snapshot,locked,mutate}),
      track?button("删除轨道及所属关键帧",()=>mutate({kind:"entity_delete",section:"tracks",ids:[track.id],cascade:true}),locked):null),
    h("details",null,h("summary",null,"时序"),form("动画名称",{title:snapshot.title},(value)=>({kind:"animation_rename",title:value.title}),(value,change)=>input("动画名称",value.title,(title)=>change({title}),{type:"text",required:true,maxLength:120})),form("动画时序",snapshot.timing,(value)=>({kind:"timing_modify",timing:{duration:Number(value.duration),fps:Number(value.fps),rate:Number(value.rate),loop:value.loop}}),(value,change)=>h(React.Fragment,null,
      input("总时长 ms",value.duration,(duration)=>change({duration}),{min:1,max:3600000,step:1}),select("帧率",String(value.fps),(fps)=>change({fps}),[24,25,30,48,50,60,120].map((fps)=>[String(fps),String(fps)])),input("播放速率",value.rate,(rate)=>change({rate}),{min:.1,max:4,step:.1}),h("label",null,h("input",{type:"checkbox",checked:value.loop,onChange:(event)=>change({loop:event.target.checked})}),"循环")))),
    h("details",null,h("summary",null,`片段 · ${snapshot.clips.length}`),h(CreateClip,{snapshot,locked,mutate}),h("div",{className:"dbfox-animation__row"},button("上一页片段",()=>setClipPage(Math.max(0,clipPage-1)),clipPage===0),button("下一页片段",()=>setClipPage(clipPage+1),(clipPage+1)*10>=snapshot.clips.length)),snapshot.clips.slice(clipPage*10,clipPage*10+10).map((clip)=>h("div",{key:clip.id},form(`${clip.name} 轨道`,clip,(value)=>({kind:"clip_modify",clip:value}),(value,change)=>h(React.Fragment,null,input("现有片段名称",value.name,(name)=>change({name}),{type:"text",required:true,maxLength:120}),h(TrackSelector,{snapshot,value:value.track_ids,onChange:(track_ids)=>change({track_ids}),disabled:locked}))),form(clip.name,{start:clip.start,end:clip.end},(value)=>({kind:"clip_trim",clip_id:clip.id,start:Number(value.start),end:Number(value.end)}),(value,change)=>h(React.Fragment,null,input(`${clip.name} 起点 ms`,value.start,(start)=>change({start}),{min:0,max:snapshot.timing.duration,step:1}),input(`${clip.name} 终点 ms`,value.end,(end)=>change({end}),{min:1,max:snapshot.timing.duration,step:1}),button("删除片段",()=>mutate({kind:"entity_delete",section:"clips",ids:[clip.id],cascade:false}),locked)))))),
    h("details",null,h("summary",null,`标记 · ${snapshot.markers.length}`),h("div",{className:"dbfox-animation__row"},button("上一页标记",()=>setMarkerPage(Math.max(0,markerPage-1)),markerPage===0),button("下一页标记",()=>setMarkerPage(markerPage+1),(markerPage+1)*20>=snapshot.markers.length)),snapshot.markers.slice(markerPage*20,markerPage*20+20).map((marker)=>h("div",{key:marker.id},form(marker.name,{name:marker.name,tick:marker.tick},(value)=>({kind:"marker_set",marker:{id:marker.id,name:value.name,tick:Number(value.tick)}}),(value,change)=>h(React.Fragment,null,input("标记名称",value.name,(name)=>change({name}),{type:"text",maxLength:120,required:true}),input("标记时间 ms",value.tick,(tick)=>change({tick}),{min:0,max:snapshot.timing.duration,step:1}),button("删除标记",()=>mutate({kind:"entity_delete",section:"markers",ids:[marker.id],cascade:false}),locked))))),h("small",null,`标记第 ${markerPage+1} 页，每页 20 个`)),
    h("small",{className:"dbfox-animation__muted"},`当前 ${Math.round(tick)} ms。修改时序不会隐式删除越界关键帧。`));
}

function CreateTarget({locked,mutate}){const[name,setName]=React.useState("对象");return h("form",{onSubmit:(event)=>{event.preventDefault();void mutate({kind:"target_create",target:{id:identity("target"),name}});}},input("对象名称",name,setName,{type:"text",required:true,maxLength:120,disabled:locked}),h("button",{type:"submit",disabled:locked},"添加对象"));}
function CreateTrack({snapshot,locked,mutate}){const[target,setTarget]=React.useState(snapshot.targets[0]?.id||""),[property,setProperty]=React.useState("position.x"),[name,setName]=React.useState("位置 X");return h("form",{onSubmit:(event)=>{event.preventDefault();void mutate({kind:"track_create",track:{id:identity("track"),target_id:target,name,property,enabled:true}});}},select("目标对象",target,setTarget,snapshot.targets.map((item)=>[item.id,item.name])),input("轨道名称",name,setName,{type:"text",required:true,maxLength:120,disabled:locked}),select("轨道属性",property,setProperty,["position","rotation","scale"].flatMap((type)=>["x","y","z"].map((axis)=>[`${type}.${axis}`,`${type}.${axis}`]))),h("button",{type:"submit",disabled:locked||!target},"添加轨道"));}
function TrackSelector({snapshot,value,onChange,disabled}) {
  return h("label",{className:"dbfox-animation__field"},h("span",null,"片段轨道（最多 128；Ctrl/Shift 多选）"),h("select",{multiple:true,size:4,value,"aria-label":"片段轨道",disabled,onChange:(event)=>onChange(Array.from(event.target.selectedOptions,(option)=>option.value).slice(0,128))},snapshot.tracks.map((track)=>h("option",{key:track.id,value:track.id},track.name))));
}
function CreateClip({snapshot,locked,mutate}) {
  const [name,setName]=React.useState("片段"),[tracks,setTracks]=React.useState(snapshot.tracks.slice(0,128).map((track)=>track.id));
  return h("form",{onSubmit:(event)=>{event.preventDefault();void mutate({kind:"clip_create",clip:{id:identity("clip"),name,track_ids:tracks,start:0,end:snapshot.timing.duration}});}},input("片段名称",name,setName,{type:"text",required:true,maxLength:120,disabled:locked}),h(TrackSelector,{snapshot,value:tracks,onChange:setTracks,disabled:locked}),h("button",{type:"submit",disabled:locked||!tracks.length},"创建所选轨道片段"));
}

function ArtifactView({artifact,payload,context}){
  const [busy,setBusy]=React.useState(false),[error,setError]=React.useState("");const state=React.useRef({alive:true,controller:null,url:null});
  React.useEffect(()=>{state.current.alive=true;const stop=()=>{state.current.alive=false;state.current.controller?.abort();if(state.current.url)URL.revokeObjectURL(state.current.url);};lifecycle.add(stop);return()=>{stop();lifecycle.delete(stop);};},[]);
  async function download(){if(busy||!active)return;setBusy(true);setError("");state.current.controller=new AbortController();try{const blob=await context.representations.stream(artifact.id,REPRESENTATION,{operation:"export_json",parameters:{}},state.current.controller.signal);if(!state.current.alive)return;if(state.current.url)URL.revokeObjectURL(state.current.url);state.current.url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=state.current.url;anchor.download=`animation-${payload.animation_id}-v${payload.version}.json`;anchor.click();}catch(caught){if(state.current.alive)setError(errorText(caught));}finally{if(state.current.alive)setBusy(false);}}
  return h("article",{className:"dbfox-animation dbfox-animation__artifact"},h("strong",null,`${payload.title} · v${payload.version}`),h("p",null,"固定动画文档 · 保留曲线、片段、标记和来源"),h("div",{className:"dbfox-animation__row"},button("下载 Animation JSON",download,busy),button("打开工作台",()=>open(payload.project_id,{id:payload.animation_id,title:payload.title}))),h("small",null,payload.content_hash),error?h("p",{role:"alert"},error):null);
}

export function register(extensionHost){host=extensionHost;React=globalThis.__DBFOX_EXTENSION_HOST__?.React;if(!React)throw new Error("Animation Studio requires public Host React.");active=true;
  stylesheet=document.createElement("link");stylesheet.rel="stylesheet";stylesheet.href=new URL("./index.css",import.meta.url).href;stylesheet.dataset.dbfoxDlc="dbfox.animation";document.head.append(stylesheet);
  host.connectors.register({id:"dbfox.animation",title:"Animation Studio",icon:h("span",{"aria-hidden":true},"◈"),addLabel:"创建动画",onAdd:({projectId})=>open(projectId),render:({projectId})=>h("div",{className:"dbfox-animation"},button("打开 Animation Studio",()=>open(projectId))),listResources:async({projectId})=>(await host.operations.invoke("animations.list",{offset:0,limit:100},{projectId})).animations.map((item)=>({kind:KIND,id:item.id,name:item.title,detail:`v${item.version} · ${item.counts.keyframes} keys`}))});
  host.dockViews.register({viewType:VIEW,icon:()=>h("span",{"aria-hidden":true},"◈"),resolveTitle:(view)=>view.title,isVisible:(view,context)=>view.projectId===context.activeProjectId,render:(view,context)=>h(Workbench,{key:`${view.projectId}:${view.viewKey}`,projectId:view.projectId,initialId:view.target?.type==="object"?view.target.object.id:null,context})});
  host.artifactViews.register({id:"dbfox.animation.revision-view",title:"Animation 导出",priority:100,surfaces:["inline","workspace"],artifactTypes:[{type:ARTIFACT,schemaVersions:[1]}],representationTypes:[REPRESENTATION],parsePayload(value){if(!value||typeof value.animation_id!=="string"||typeof value.project_id!=="string"||!Number.isInteger(value.version)||typeof value.content_hash!=="string")throw new Error("Invalid Animation Artifact");return value;},render:(artifact,payload,context)=>h(ArtifactView,{key:artifact.id,artifact,payload,context})});
}
export function deactivate(){active=false;for(const stop of lifecycle)stop();lifecycle.clear();stylesheet?.remove();stylesheet=null;}
