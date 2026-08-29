import { renderMeasure } from "./notation.js";
import { playScore, playTimedNotes, previewPitch } from "./playback.js";

const DLC_ID = "dbfox.music";
const STUDIO_VIEW = "dbfox.music.piano-studio";
const SCORE_KIND = "dbfox.music.score";
const LIBRARY_KIND = "dbfox.music.library";
const AUDIO_KIND = "dbfox.music.audio";
const SCORE_ARTIFACT = "dbfox.music.score_revision";
const TRANSCRIPTION_ARTIFACT = "dbfox.music.transcription";

let host;
let React;
const projectState = new Map();
const studioState = new Map();
const audioBuffers = new Map();
const listeners = new Set();

const h = (...args) => React.createElement(...args);
const emit = () => { for (const listener of listeners) listener(); };

function useVersion() {
  const [, setVersion] = React.useState(0);
  React.useEffect(() => {
    const listener = () => setVersion((value) => value + 1);
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, []);
}

function ensureStylesheet() {
  if (typeof document === "undefined") return;
  const href = new URL("./studio.css", import.meta.url).href;
  if (document.querySelector(`link[data-dbfox-dlc="${DLC_ID}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  link.dataset.dbfoxDlc = DLC_ID;
  document.head.appendChild(link);
}

async function invoke(name, input, projectId) {
  return host.operations.invoke(name, input, { projectId });
}

async function loadProject(projectId) {
  const [scoreResult, audioResult] = await Promise.all([
    invoke("scores.list", {}, projectId),
    invoke("audio.list", {}, projectId),
  ]);
  projectState.set(projectId, {
    scores: Array.isArray(scoreResult?.scores) ? scoreResult.scores : [],
    audio: Array.isArray(audioResult?.sources) ? audioResult.sources : [],
  });
  emit();
}

function stateKey(projectId, kind, id) {
  return `${host.workbench.currentScopeId()}:${projectId}:${kind}:${id}`;
}

function openStudio(projectId, kind, value) {
  const id = value?.id || value?.scoreId || value?.score_id || "new";
  const key = stateKey(projectId, kind, id);
  studioState.set(key, { projectId, scopeId: host.workbench.currentScopeId(), kind, value });
  host.dockViews.open({
    viewKey: `music-studio:${key}`,
    viewType: STUDIO_VIEW,
    title: value?.title || value?.name || "Piano Studio",
    closeable: true,
    projectId,
    stateKey: key,
    target: kind === "empty" ? undefined : {
      type: "object",
      object: {
        kind: kind === "score" ? SCORE_KIND : AUDIO_KIND,
        id,
        version: kind === "score" ? value.head_revision || value.revision : `${value.fingerprint}:${value.analysis_revision}`,
      },
    },
  });
}

function promoteEmptyStudio(projectId, value) {
  if (!projectId) return false;
  for (const [key, state] of studioState.entries()) {
    if (
      state.projectId !== projectId
      || state.scopeId !== host.workbench.currentScopeId()
      || state.kind !== "empty"
    ) continue;
    studioState.set(key, { ...state, kind: "score", value });
    host.dockViews.open({
      viewKey: `music-studio:${key}`,
      viewType: STUDIO_VIEW,
      title: value.title || "Piano Studio",
      closeable: true,
      projectId,
      stateKey: key,
      target: {
        type: "object",
        object: { kind: SCORE_KIND, id: value.scoreId, version: value.revision },
      },
    });
    return true;
  }
  return false;
}

function ResourceRow({ projectId, kind, item }) {
  const isScore = kind === "score";
  return h("div", { className: "dbfox-music__resource" },
    h("button", {
      type: "button",
      className: "dbfox-music__resource-main",
      onClick: () => openStudio(projectId, kind, item),
    },
    h("span", { className: "dbfox-music__resource-icon", "aria-hidden": true }, isScore ? "♪" : "≈"),
    h("span", { className: "dbfox-music__resource-label" }, item.title || item.name),
    h("small", null, isScore ? `R${item.head_revision}` : (item.analysis_revision ? "已转录" : "待转录"))));
}

async function decodeSelection(selection) {
  const bytes = await host.nativeFiles.readPickedFile(selection.path);
  const context = new AudioContext();
  try {
    return await context.decodeAudioData(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  } finally {
    void context.close();
  }
}

function mediaType(name) {
  const extension = name.split(".").pop()?.toLowerCase();
  return ({ wav: "audio/wav", mp3: "audio/mpeg", m4a: "audio/mp4", flac: "audio/flac", ogg: "audio/ogg" })[extension] || "application/octet-stream";
}

function MusicConnector({ projectId }) {
  useVersion();
  const [loading, setLoading] = React.useState(!projectState.has(projectId));
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let active = true;
    loadProject(projectId).catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason))).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [projectId]);
  const data = projectState.get(projectId) || { scores: [], audio: [] };

  async function importAudio() {
    setError("");
    try {
      const selection = await host.nativeDialogs.pickFile({
        title: "导入钢琴录音",
        accept: ["wav", "mp3", "m4a", "flac", "ogg"],
        maxBytes: 134217728,
      });
      if (!selection) return;
      setLoading(true);
      const buffer = await decodeSelection(selection);
      const result = await invoke("audio.import", {
        source_path: selection.path,
        name: selection.name,
        media_type: mediaType(selection.name),
        duration_seconds: buffer.duration,
        sample_rate: buffer.sampleRate,
        channels: buffer.numberOfChannels,
      }, projectId);
      audioBuffers.set(result.source.id, buffer);
      await loadProject(projectId);
      openStudio(projectId, "audio", result.source);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法导入音频。");
    } finally {
      setLoading(false);
    }
  }

  return h("section", { className: "dbfox-music" },
    loading ? h("p", { className: "dbfox-music__status" }, "正在读取音乐空间…") : null,
    data.scores.map((score) => h(ResourceRow, { key: score.id, projectId, kind: "score", item: score })),
    data.audio.map((audio) => h(ResourceRow, { key: audio.id, projectId, kind: "audio", item: audio })),
    !loading && !data.scores.length && !data.audio.length
      ? h("p", { className: "dbfox-music__empty" }, "还没有乐谱或录音。") : null,
    h("button", { type: "button", className: "dbfox-music__import", onClick: () => void importAudio(), disabled: loading }, "导入钢琴录音"),
    error ? h("p", { className: "dbfox-music__error", role: "alert" }, error) : null);
}

function ScoreMeasure({ document, measure, active, uncertain, selected, onSelect }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!ref.current) return;
    renderMeasure(ref.current, document, measure);
  }, [document, measure]);
  return h("button", {
    type: "button",
    className: `dbfox-music-measure${active ? " is-active" : ""}${uncertain ? " is-uncertain" : ""}${selected ? " is-selected" : ""}`,
    "aria-label": `第 ${measure} 小节${uncertain ? "，低置信度" : ""}`,
    onClick: () => onSelect?.(measure),
  }, h("span", { className: "dbfox-music-measure__number" }, measure), h("div", { ref }));
}

function ScoreView({ document, currentMeasure, uncertainMeasures = new Set(), selectedMeasure, onSelectMeasure }) {
  return h("div", { className: "dbfox-music-score", role: "region", "aria-label": "乐谱" },
    Array.from({ length: document.measure_count }, (_, index) => h(ScoreMeasure, {
      key: index + 1,
      document,
      measure: index + 1,
      active: currentMeasure === index + 1,
      uncertain: uncertainMeasures.has(index + 1),
      selected: selectedMeasure === index + 1,
      onSelect: onSelectMeasure,
    })));
}

function PianoKeyboard({ document, activeNotes, full, onFull }) {
  const pitches = document?.notes?.map((note) => note.pitch) || [];
  let low = full ? 21 : Math.max(21, Math.floor(((Math.min(...pitches, 48)) - 12) / 12) * 12);
  let high = full ? 108 : Math.min(108, Math.max(low + 59, Math.ceil(((Math.max(...pitches, 84)) + 12) / 12) * 12));
  const whites = [];
  const blacks = [];
  let whiteIndex = 0;
  for (let pitch = low; pitch <= high; pitch += 1) {
    const black = [1, 3, 6, 8, 10].includes(pitch % 12);
    if (black) blacks.push({ pitch, left: whiteIndex });
    else { whites.push(pitch); whiteIndex += 1; }
  }
  const handlePitchKey = (event, pitch) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    void previewPitch(pitch);
  };
  return h("section", { className: "dbfox-music-keyboard", "aria-label": "钢琴键盘" },
    h("header", null, h("span", null, "PIANO"), h("button", {
      type: "button", onClick: onFull, "aria-pressed": full,
    }, full ? "Adaptive" : "Full 88")),
    h("div", { className: "dbfox-music-keyboard__scroll" },
      h("svg", { className: `dbfox-music-keyboard__keys${full ? " is-full" : ""}`, viewBox: `0 0 ${whites.length} 10`, preserveAspectRatio: "none", role: "group", "aria-label": "可试听钢琴键" },
        whites.map((pitch, index) => h("rect", {
          key: pitch, x: index, y: 0, width: 1, height: 10, rx: .08, role: "button", tabIndex: 0, className: `dbfox-music-key is-white${activeNotes.includes(pitch) ? " is-active" : ""}`,
          "aria-label": `试听 MIDI 音高 ${pitch}`, onClick: () => void previewPitch(pitch), onKeyDown: (event) => handlePitchKey(event, pitch),
        })),
        blacks.map(({ pitch, left }) => h("rect", {
          key: pitch, x: left - .32, y: 0, width: .64, height: 6.2, rx: .08, role: "button", tabIndex: 0, className: `dbfox-music-key is-black${activeNotes.includes(pitch) ? " is-active" : ""}`,
          "aria-label": `试听 MIDI 音高 ${pitch}`, onClick: () => void previewPitch(pitch), onKeyDown: (event) => handlePitchKey(event, pitch),
        })))));
}

function Transport({ playing, loop, onPlay, onStop, onLoop, position, duration, selectedMeasure, onAskMeasure }) {
  return h("div", { className: "dbfox-music-transport", role: "group", "aria-label": "播放控制" },
    h("button", { type: "button", onClick: onPlay, className: playing ? "is-active" : "", "aria-label": playing ? "暂停" : "播放" }, playing ? "Ⅱ" : "▶"),
    h("button", { type: "button", onClick: onStop, "aria-label": "停止" }, "■"),
    h("button", { type: "button", onClick: onLoop, className: loop ? "is-active" : "", "aria-pressed": loop }, "Loop"),
    h("span", null, `${formatTime(position)} / ${formatTime(duration)}`),
    selectedMeasure ? h("button", {
      type: "button",
      className: "dbfox-music-transport__ask",
      onClick: () => onAskMeasure?.(selectedMeasure),
      title: `就第 ${selectedMeasure} 小节向 DBFox 提问`,
    }, `💬 小节 ${selectedMeasure}`) : null);
}

function formatTime(value) {
  const seconds = Math.max(0, Number(value) || 0);
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function ScoreStudio({ projectId, source, context }) {
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  const [playing, setPlaying] = React.useState(false);
  const [loop, setLoop] = React.useState(false);
  const [position, setPosition] = React.useState(0);
  const [activeNotes, setActiveNotes] = React.useState([]);
  const [full, setFull] = React.useState(false);
  const [selectedMeasure, setSelectedMeasure] = React.useState(null);
  const controller = React.useRef(null);
  const loopRef = React.useRef(false);
  React.useEffect(() => {
    let active = true;
    invoke("scores.get", { score_id: source.id || source.scoreId || source.score_id, revision: source.revision || null }, projectId)
      .then((value) => active && setResult(value))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason)));
    return () => { active = false; controller.current?.abort(); };
  }, [projectId, source.id, source.scoreId, source.score_id, source.revision]);
  if (error) return h("p", { className: "dbfox-music-studio__error", role: "alert" }, error);
  if (!result) return h("p", { className: "dbfox-music-studio__loading" }, "正在打开乐谱…");
  const document = result.revision.document;
  const duration = document.measure_count * document.meter.beats * 60 / document.tempo;
  const currentMeasure = Math.min(document.measure_count, Math.floor(position / (document.meter.beats * 60 / document.tempo)) + 1);

  function stop(reset = true) {
    controller.current?.abort();
    controller.current = null;
    setPlaying(false);
    setActiveNotes([]);
    if (reset) setPosition(0);
  }
  async function play() {
    if (playing) { stop(false); return; }
    const control = new AbortController();
    controller.current = control;
    setPlaying(true);
    do {
      await playScore(document, { from: position, onPosition: setPosition, onNotes: setActiveNotes, signal: control.signal });
      if (!loopRef.current || control.signal.aborted) break;
      setPosition(0);
    } while (loopRef.current);
    if (!control.signal.aborted) stop();
  }

  function handleAskMeasure(m) {
    if (!m) return;
    context.onAsk({
      label: `${document.title || "乐谱"} · 第 ${m} 小节`,
      authority: { kind: SCORE_KIND, id: result.revision.score_id },
      object: {
        kind: "dbfox.music.measure",
        id: `${result.revision.score_id}:${m}`,
        version: result.revision.revision,
      },
      locator: `measure:${m}`,
    });
  }

  return h("article", { className: "dbfox-music-studio" },
    h("div", { className: "dbfox-music-studio__meta" },
      h("span", null, `${document.key.tonic} ${document.key.mode} · ${document.meter.beats}/${document.meter.beat_unit} · ♩${document.tempo} · Rev ${result.revision.revision}`)),
    h(Transport, {
      playing,
      loop,
      onPlay: () => void play(),
      onStop: () => stop(),
      onLoop: () => setLoop((value) => {
        loopRef.current = !value;
        return !value;
      }),
      position,
      duration,
      selectedMeasure,
      onAskMeasure: handleAskMeasure,
    }),
    h(ScoreView, {
      document,
      currentMeasure,
      selectedMeasure,
      onSelectMeasure: (m) => setSelectedMeasure((prev) => prev === m ? null : m),
    }),
    h(PianoKeyboard, { document, activeNotes, full, onFull: () => setFull((value) => !value) }));
}

function waveformPath(buffer) {
  if (!buffer) return "";
  const values = buffer.getChannelData(0);
  const points = 160;
  const sampled = [];
  for (let index = 0; index < points; index += 1) {
    const start = Math.floor(index * values.length / points);
    const end = Math.floor((index + 1) * values.length / points);
    let peak = 0;
    for (let cursor = start; cursor < end; cursor += 1) peak = Math.max(peak, Math.abs(values[cursor]));
    sampled.push(`${index / (points - 1) * 100},${24 - peak * 21}`);
  }
  return `M ${sampled.join(" L ")}`;
}

function AudioStudio({ projectId, source, showToast }) {
  const [result, setResult] = React.useState(null);
  const [status, setStatus] = React.useState("idle");
  const [progress, setProgress] = React.useState(0);
  const [error, setError] = React.useState("");
  const [position, setPosition] = React.useState(0);
  const [activeNotes, setActiveNotes] = React.useState([]);
  const [full, setFull] = React.useState(false);
  const controller = React.useRef(null);
  const effectiveSource = result?.source || source;
  const buffer = audioBuffers.get(effectiveSource.id);
  React.useEffect(() => {
    let active = true;
    invoke("audio.get", { audio_source_id: source.id }, projectId).then((value) => active && setResult(value)).catch((reason) => active && setError(String(reason)));
    return () => { active = false; controller.current?.abort(); };
  }, [projectId, source.id]);

  async function transcribe() {
    if (!buffer) { setError("重新打开后需要再次选择原音频，才能在本机运行转录模型。"); return; }
    setStatus("transcribing");
    setError("");
    try {
      const { transcribePiano } = await import("./transcription.js");
      const transcription = await transcribePiano(buffer, setProgress);
      if (!transcription.notes.length) throw new Error("没有检测到钢琴音符。");
      const committed = await invoke("audio.commit_transcription", { audio_source_id: source.id, ...transcription }, projectId);
      setResult(committed);
      setStatus("ready");
      await loadProject(projectId);
      showToast("转录候选已保存为新乐谱。", "success");
    } catch (reason) {
      setStatus("error");
      setError(reason instanceof Error ? reason.message : "转录失败。");
    }
  }

  function stop() { controller.current?.abort(); controller.current = null; setPosition(0); setActiveNotes([]); }
  async function playOriginal() {
    if (!buffer) { setError("原音频当前不在内存中，请从资源栏重新导入。 "); return; }
    stop();
    const context = new AudioContext();
    await context.resume();
    const control = new AbortController();
    controller.current = control;
    const node = context.createBufferSource();
    node.buffer = buffer;
    node.connect(context.destination);
    const origin = context.currentTime;
    node.start();
    const tick = () => {
      if (control.signal.aborted || context.currentTime - origin >= buffer.duration) { node.stop(); void context.close(); return; }
      setPosition(context.currentTime - origin); requestAnimationFrame(tick);
    };
    tick();
  }
  async function playTranscription() {
    if (!result?.transcription) return;
    stop();
    const control = new AbortController();
    controller.current = control;
    await playTimedNotes(result.transcription.notes, { from: 0, onPosition: setPosition, onNotes: setActiveNotes, signal: control.signal });
  }
  const transcription = result?.transcription;
  const uncertain = transcription?.uncertain_ranges || [];
  return h("article", { className: "dbfox-music-studio dbfox-music-studio--audio" },
    h("div", { className: "dbfox-music-studio__meta" }, h("span", null, transcription ? `Transcription · ${Math.round(transcription.confidence * 100)}% confidence` : "Audio Source")),
    h("section", { className: "dbfox-music-waveform", "aria-label": "音频波形" },
      h("svg", { viewBox: "0 0 100 48", preserveAspectRatio: "none", "aria-hidden": true }, h("path", { d: waveformPath(buffer) })),
      h("progress", { className: "dbfox-music-waveform__progress", value: Math.min(100, position / effectiveSource.duration_seconds * 100), max: 100, "aria-label": "播放进度" }),
      h("small", null, formatTime(position))),
    transcription ? h("div", { className: "dbfox-music-ab", role: "group", "aria-label": "原音频与转录对照" },
      h("button", { type: "button", onClick: () => void playOriginal() }, "▶ Original"),
      h("button", { type: "button", onClick: () => void playTranscription() }, "▶ Transcription"),
      h("button", { type: "button", onClick: stop }, "■")) : null,
    !transcription ? h("div", { className: "dbfox-music-transcribe" },
      h("p", null, "使用本机 Basic Pitch 模型提取音符候选；Agent 只负责后续结构修复。"),
      h("button", { type: "button", onClick: () => void transcribe(), disabled: status === "transcribing" }, status === "transcribing" ? `正在转录 ${Math.round(progress * 100)}%` : "开始钢琴转录")) :
      h("section", { className: "dbfox-music-confidence" },
        h("strong", null, `${transcription.notes.length} notes · ♩${transcription.tempo} · ${transcription.key.tonic} ${transcription.key.mode}`),
        h("p", null, uncertain.length ? `${uncertain.length} 个区间需要复核；在对话中要求创建并修订乐谱。` : "没有检测到显著低置信区间；可在对话中创建乐谱。")),
    transcription ? h(PianoKeyboard, {
      document: { notes: transcription.notes },
      activeNotes,
      full,
      onFull: () => setFull((value) => !value),
    }) : null,
    error ? h("p", { className: "dbfox-music-studio__error", role: "alert" }, error) : null);
}

function EmptyStudio({ projectId }) {
  return h("div", { className: "dbfox-music-start" },
    h("span", { "aria-hidden": true }, "♪"),
    h("h2", null, "Start with an idea"),
    h("p", null, "在对话中直接告诉 Agent 创作意图："),
    h("blockquote", null, "“写一段安静、缓慢、带夜晚感的钢琴曲”"),
    h("p", { className: "dbfox-music-start__hint" }, "Agent 将自动调用 Music 能力创作新乐谱并在当前工作区打开。"));
}

function PianoStudioDock({ view, context }) {
  const state = studioState.get(view.stateKey || "");
  const projectId = view.projectId || context.activeProjectId;
  if (!state) {
    if (view.target?.type === "object" && view.target.object.kind === SCORE_KIND) return h(ScoreStudio, { projectId, source: { id: view.target.object.id, revision: view.target.object.version }, context });
    if (view.target?.type === "object" && view.target.object.kind === AUDIO_KIND) return h(AudioStudio, { projectId, source: { id: view.target.object.id, name: view.title, duration_seconds: 1 }, showToast: context.showToast, context });
    return h(EmptyStudio, { projectId });
  }
  if (state.kind === "score") return h(ScoreStudio, { projectId, source: state.value, context });
  if (state.kind === "audio") return h(AudioStudio, { projectId, source: state.value, showToast: context.showToast, context });
  return h(EmptyStudio, { projectId });
}

function parseScoreArtifact(value) {
  if (!value || typeof value !== "object" || typeof value.scoreId !== "string" || !Number.isInteger(value.revision)) throw new Error("Invalid score revision Artifact");
  return value;
}

function ScoreArtifactCard({ artifact, payload }) {
  const libraryRef = artifact.resource_refs?.find((ref) => ref.kind === LIBRARY_KIND);
  const projectId = payload.projectId || libraryRef?.id || artifact.provenance?.project_id || "";
  React.useEffect(() => {
    promoteEmptyStudio(projectId, payload);
  }, [artifact.id, projectId]);
  return h("article", { className: "dbfox-music-artifact" },
    h("span", { className: "dbfox-music-artifact__icon", "aria-hidden": true }, "♪"),
    h("div", null, h("strong", null, payload.title), h("small", null, `${payload.measureCount} measures · ${payload.key} · ♩${payload.tempo} · Revision ${payload.revision}`)),
    h("button", { type: "button", onClick: () => {
      openStudio(projectId, "score", payload);
    } }, "Open in Piano Studio →"));
}

function parseTranscriptionArtifact(value) {
  if (!value || typeof value !== "object" || typeof value.sourceAudioId !== "string") throw new Error("Invalid transcription Artifact");
  return value;
}

function TranscriptionArtifactCard({ artifact, payload }) {
  return h("article", { className: "dbfox-music-artifact" }, h("span", { className: "dbfox-music-artifact__icon", "aria-hidden": true }, "≈"), h("div", null, h("strong", null, artifact.title), h("small", null, `${Math.round(payload.confidence * 100)}% confidence · ${payload.uncertainRanges?.length || 0} uncertain ranges`)));
}

export function register(extensionHost) {
  host = extensionHost;
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("DBFox React host is unavailable");
  ensureStylesheet();
  host.connectors.register({
    id: DLC_ID,
    title: "Music",
    icon: h("span", { "aria-hidden": true }, "♪"),
    addLabel: "New score",
    onAdd: ({ projectId }) => {
      openStudio(projectId, "empty", { title: "Piano Studio" });
    },
    render: ({ projectId }) => h(MusicConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: STUDIO_VIEW,
    icon: () => h("span", { "aria-hidden": true }, "♪"),
    resolveTitle: (view) => view.title || "Piano Studio",
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view, context) => h(PianoStudioDock, { view, context }),
  });
  host.artifactViews.register({ id: "dbfox.music.score", title: "乐谱", priority: 60, surfaces: ["inline", "workspace"], artifactTypes: [{ type: SCORE_ARTIFACT, schemaVersions: [1] }], parsePayload: parseScoreArtifact, render: (artifact, payload) => h(ScoreArtifactCard, { artifact, payload }) });
  host.artifactViews.register({ id: "dbfox.music.transcription", title: "转录", priority: 60, surfaces: ["inline", "workspace"], artifactTypes: [{ type: TRANSCRIPTION_ARTIFACT, schemaVersions: [1] }], parsePayload: parseTranscriptionArtifact, render: (artifact, payload) => h(TranscriptionArtifactCard, { artifact, payload }) });
}

export function deactivate() {
  projectState.clear();
  studioState.clear();
  audioBuffers.clear();
  listeners.clear();
  if (typeof document !== "undefined") document.querySelectorAll(`link[data-dbfox-dlc="${DLC_ID}"]`).forEach((link) => link.remove());
  host = undefined;
  React = undefined;
}
