import { DOCUMENT, REPORT, collectPages, errorText, loadDocument } from './model.js';
import { createViewport } from './viewport.js';

export function parseLocator(value) {
  if (!value || typeof value.project_id !== 'string' || typeof value.game_id !== 'string' || typeof value.title !== 'string' || !Number.isInteger(value.version) || value.version < 1 || !/^[a-f0-9]{64}$/.test(value.content_hash) || (value.report_id !== undefined && typeof value.report_id !== 'string')) throw new Error('Invalid Game Artifact locator.');
  return value;
}

export function createArtifactView(React, activation, open) {
  const h = React.createElement;
  const Viewport = createViewport(React);
  return function GameArtifact({ artifact, payload, context }) {
    const [snapshot, setSnapshot] = React.useState(null);
    const [report, setReport] = React.useState(null);
    const [events, setEvents] = React.useState([]);
    const [entities, setEntities] = React.useState([]);
    const [error, setError] = React.useState('');
    const [loading, setLoading] = React.useState(true);
    const [busy, setBusy] = React.useState(false);
    const [playing, setPlaying] = React.useState(false);
    const [resetKey, setResetKey] = React.useState(0);
    const [stepKey, setStepKey] = React.useState(0);
    const [preview, setPreview] = React.useState(null);
    const live = React.useRef({ alive: true, controller: null, download: null, url: null, busy: false });
    const isReport = artifact.type === 'dbfox.game.playtest-report';
    const representation = isReport ? REPORT : DOCUMENT;
    const registerCleanup = React.useCallback((callback) => activation.registerCleanup(callback), []);
    React.useEffect(() => {
      const controller = new AbortController();
      live.current.alive = true; live.current.controller = controller;
      async function read(parameters, signal) {
        const result = await context.representations.read(artifact.id, representation, { operation: 'page', parameters }, signal);
        if (result.source_version !== String(payload.version) || result.source_fingerprint !== payload.content_hash || result.consistency !== 'durable_snapshot') throw new Error('Game 工件来源与固定版本不一致。');
        return result.payload;
      }
      (async () => {
        if (isReport) {
          const first = await read({ section: 'summary' }, controller.signal);
          const eventPage = await collectPages(read, { section: 'events' }, controller.signal, first.game);
          const entityPage = await collectPages(read, { section: 'entities' }, controller.signal, first.game);
          if (!controller.signal.aborted) { setReport(first.metadata.report); setEvents(eventPage.items); setEntities(entityPage.items); }
        } else {
          const loaded = await loadDocument(read, null, controller.signal);
          if (!controller.signal.aborted) setSnapshot(loaded);
        }
      })().catch((caught) => { if (!controller.signal.aborted) setError(errorText(caught)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
      const stop = () => { live.current.alive = false; controller.abort(); live.current.download?.abort(); if (live.current.url) { URL.revokeObjectURL(live.current.url); live.current.url = null; } };
      const unregister = registerCleanup(stop);
      return () => { unregister(); stop(); };
    }, [artifact.id, representation, payload.version, payload.content_hash, context.representations, isReport, registerCleanup]);

    async function download() {
      if (!live.current.alive || live.current.busy) return;
      live.current.busy = true; setBusy(true); setError('');
      const controller = new AbortController(); live.current.download = controller;
      try {
        const blob = await context.representations.stream(artifact.id, representation, { operation: 'export', parameters: {} }, controller.signal);
        if (!live.current.alive || controller.signal.aborted) return;
        if (live.current.url) URL.revokeObjectURL(live.current.url);
        live.current.url = URL.createObjectURL(blob);
        const anchor = document.createElement('a'); anchor.href = live.current.url; anchor.download = `game-${payload.game_id}-v${payload.version}${isReport ? '-playtest' : ''}.json`; anchor.click();
        context.onToast(`已导出固定版本 v${payload.version}`);
      } catch (caught) { if (!controller.signal.aborted && live.current.alive) setError(errorText(caught)); }
      finally { live.current.busy = false; if (live.current.alive) setBusy(false); }
    }
    const button = (label, click, disabled = false) => h('button', { type: 'button', onClick: click, disabled }, label);
    return h('article', { className: 'dbfox-game game-artifact' },
      h('div', { className: 'game-section-heading' }, h('h3', null, payload.title), h('span', { className: 'game-badge' }, `固定 v${payload.version}`)),
      h('div', { className: 'game-button-row' }, button(isReport ? '下载 Playtest 报告' : '下载 Game 包', download, busy || loading), button('编辑当前游戏', () => open(payload.project_id, { id: payload.game_id, title: payload.title })), context.compact && context.openArtifact && button('展开工件', () => context.openArtifact(artifact))),
      loading && h('p', { role: 'status' }, '正在读取耐久 Game 工件…'), error && h('p', { className: 'game-error', role: 'alert' }, error),
      report && h(React.Fragment, null, h('div', { className: 'game-report-summary' }, h('strong', null, report.outcome), h('p', null, report.reason), h('span', null, `${report.ticks_completed} / ${report.ticks_requested} ticks · seed ${report.seed} · ${report.entity_count} 实体 · ${report.engine}`)), report.events_truncated && h('p', { className: 'game-warning' }, `${report.event_count} 条事件，耐久报告保留前 1024 条并包含最终结果。`),
        h('details', { open: !context.compact }, h('summary', null, `事件记录 · ${events.length}`), h('div', { className: 'game-event-log' }, events.map((event, index) => h('div', { key: index, className: 'game-event' }, h('code', null, event.tick), h('span', { className: 'game-badge' }, event.kind), h('span', null, event.detail))))),
        h('details', null, h('summary', null, `最终实体 · ${entities.length}`), h('div', { className: 'game-table-scroll' }, h('table', null, h('thead', null, h('tr', null, ['实体', 'X', 'Y', '速度 X', '速度 Y', '生命'].map((title) => h('th', { key: title }, title)))), h('tbody', null, entities.map((entity) => h('tr', { key: entity.id }, h('td', null, entity.id), ...['x', 'y', 'vx', 'vy', 'health'].map((key) => h('td', { key }, entity[key] === undefined ? '—' : Number(entity[key]).toFixed(2))))))))),
      ),
      snapshot && h(React.Fragment, null, h('p', { className: 'game-help' }, `${snapshot.document.scenes.length} 场景 · ${snapshot.document.entities.length} 实体 · ${snapshot.document.rules.length} 规则。下方是该工件固定版本的本地 Phaser 预览。`), !context.compact && h(React.Fragment, null, h('div', { className: 'game-button-row' }, button(playing ? '暂停' : '播放固定版本', () => setPlaying(!playing), preview?.outcome && preview.outcome !== 'running'), button('单步', () => setStepKey((value) => value + 1), playing), button('重置', () => { setPlaying(false); setResetKey((value) => value + 1); })), h(Viewport, { snapshot, sceneId: snapshot.document.initial_scene_id, selection: [], onSelect: () => {}, onMove: async () => false, busy: false, playing, setPlaying, resetKey, stepKey, seed: 1, onState: setPreview, onInputs: () => {}, onError: setError, registerCleanup }), h('p', { className: 'game-help' }, `tick ${preview?.ticks_completed ?? 0} · ${preview?.reason ?? ''}`))),
    );
  };
}
