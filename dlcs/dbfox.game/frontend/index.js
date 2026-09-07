import { GAME_KIND, listGames, errorText } from './model.js';
import { createExecutor, packageDigestFromUrl } from './executor.js';
import { createStudio } from './studio.js';
import { createArtifactView, parseLocator } from './artifacts.js';

const VIEW = 'dbfox.game.workbench';
let current;
let clientId;
let counter = 0;

export function register(host) {
  deactivate();
  const React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React || !host.ui?.Tree) throw new Error('Game Studio requires the public Host React and Tree APIs.');
  const h = React.createElement;
  const controller = new AbortController();
  const cleanups = new Set();
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = new URL('./index.css', import.meta.url).href; style.dataset.dbfoxDlc = 'dbfox.game'; document.head.append(style);
  const activation = { controller, style, registerCleanup(callback) { cleanups.add(callback); return () => cleanups.delete(callback); }, cleanups, executor: null };
  current = activation;
  try {
    const packageDigest = packageDigestFromUrl(import.meta.url);
    clientId ??= crypto.randomUUID();
    activation.executor = createExecutor(host, { clientId, nextCounter: () => ++counter, packageDigest });
  } catch (error) {
    // Uninstalled browser development may preview; it cannot produce playtest evidence.
    const status = Object.freeze({ state: 'unavailable', message: errorText(error) });
    activation.executor = { getSnapshot: () => status, subscribe: () => () => {}, reconnect() {}, dispose() {} };
  }
  function open(projectId, game) {
    if (controller.signal.aborted) return;
    host.dockViews.open({ viewType: VIEW, viewKey: `${VIEW}:${projectId}:${game?.id ?? 'library'}`, title: game?.title ?? 'Game Studio', projectId, closeable: true, ...(game ? { target: { type: 'object', object: { kind: GAME_KIND, id: game.id }, authority: { kind: GAME_KIND, id: game.id } } } : {}) });
  }
  const Studio = createStudio(React, host, activation);
  const ArtifactView = createArtifactView(React, activation, open);
  function Connector({ projectId }) {
    const [games, setGames] = React.useState([]);
    const [error, setError] = React.useState('');
    React.useEffect(() => {
      const read = new AbortController();
      let timer;
      const stop = () => { clearTimeout(timer); read.abort(); }; const unregister = activation.registerCleanup(stop);
      async function refresh() {
        try {
          if (document.visibilityState === 'hidden') return;
          const page = await listGames((name, input, signal) => host.operations.invoke(name, input, { projectId, signal }), read.signal);
          if (!read.signal.aborted) { setGames(page.items.filter((item) => !item.deleted)); setError(''); }
        } catch (caught) { if (!read.signal.aborted) setError(errorText(caught)); }
        finally { if (!read.signal.aborted) timer = setTimeout(refresh, 5000); }
      }
      void refresh();
      return () => { unregister(); stop(); };
    }, [projectId]);
    const root = { id: 'library', name: 'Game Studio', children: games.map((game) => ({ ...game, name: game.title, children: [] })) };
    return h('div', { className: 'dbfox-game game-connector' }, h('button', { type: 'button', onClick: () => open(projectId) }, '+ 创建游戏'), error && h('p', { role: 'alert' }, error), h(host.ui.Tree, { rootItem: root, ariaLabel: '游戏库', getItemId: (item) => item.id, getItemLabel: (item) => item.name, getItemChildren: (item) => item.children, defaultExpandedIds: ['library'], onItemSelect: (item) => { if (item.id !== 'library') open(projectId, item); }, renderItemMeta: (item) => item.version ? h('span', { className: 'game-badge' }, `v${item.version}`) : null }));
  }
  const icon = h('span', { 'aria-hidden': true }, '▶');
  host.connectors.register({ id: 'dbfox.game', title: 'Game Studio', icon, addLabel: '创建游戏', onAdd: ({ projectId }) => open(projectId), render: ({ projectId }) => h(Connector, { projectId }), listResources: async ({ projectId }) => (await listGames((name, input, signal) => host.operations.invoke(name, input, { projectId, signal }), controller.signal)).items.filter((item) => !item.deleted).map((item) => ({ kind: GAME_KIND, id: item.id, name: item.title, detail: `v${item.version} · Phaser 4.2.1` })) });
  host.dockViews.register({ viewType: VIEW, icon: () => icon, resolveTitle: (view) => view.title, isVisible: (view, context) => view.projectId === context.activeProjectId, render: (view, context) => h(Studio, { view, context, key: `${view.viewKey}:${context.workbenchScopeId}` }) });
  host.artifactViews.register({ id: 'dbfox.game.artifact', title: 'Game', priority: 100, surfaces: ['inline', 'workspace'], artifactTypes: [{ type: 'dbfox.game.project-revision', schemaVersions: [1] }, { type: 'dbfox.game.playtest-report', schemaVersions: [1] }], parsePayload: parseLocator, render: (artifact, payload, context) => h(ArtifactView, { artifact, payload, context, key: artifact.id }) });
}

export function deactivate() {
  const old = current; current = undefined;
  if (!old) return;
  old.controller.abort(); old.executor?.dispose(); old.cleanups.forEach((stop) => stop()); old.cleanups.clear(); old.style.remove();
}
