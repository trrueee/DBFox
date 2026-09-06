import { byId, errorText, inputSpec, listGames, readGame, referenceFor, requestId, part } from './model.js';
import { behaviorKinds, componentKinds, createForms, defaultBehavior, defaultSpec, names } from './forms.js';
import { createViewport } from './viewport.js';
import { survivalOperations } from './presets.js';

export function createStudio(React, host, activation) {
  const h = React.createElement;
  const { Fields, Spec, RuleFields } = createForms(React);
  const Viewport = createViewport(React);
  const button = (label, click, disabled = false, props = {}) => h('button', { type: 'button', onClick: click, disabled, ...props }, label);

  function Studio({ view, context }) {
    const projectId = view.projectId;
    const [gameId, setGameId] = React.useState(view.target?.type === 'object' ? view.target.object.id : '');
    const [library, setLibrary] = React.useState(null);
    const [snapshot, setSnapshot] = React.useState(null);
    const [sceneId, setSceneId] = React.useState('');
    const [selection, setSelection] = React.useState([]);
    const [draft, setDraft] = React.useState(null);
    const [newer, setNewer] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [busy, setBusy] = React.useState(false);
    const [uncertain, setUncertain] = React.useState(false);
    const [error, setError] = React.useState('');
    const [notice, setNotice] = React.useState('');
    const [reload, setReload] = React.useState(0);
    const [playing, setPlaying] = React.useState(false);
    const [resetKey, setResetKey] = React.useState(0);
    const [stepKey, setStepKey] = React.useState(0);
    const [seed, setSeed] = React.useState(1);
    const [ticks, setTicks] = React.useState(3600);
    const [preview, setPreview] = React.useState(null);
    const [inputs, setInputs] = React.useState([]);
    const [tab, setTab] = React.useState('entities');
    const [bottom, setBottom] = React.useState('events');
    const [history, setHistory] = React.useState(null);
    const [diff, setDiff] = React.useState(null);
    const [createTitle, setCreateTitle] = React.useState('我的游戏');
    const status = React.useSyncExternalStore(activation.executor.subscribe, activation.executor.getSnapshot);
    const live = React.useRef({ alive: true, busy: false, loading: true, read: null, write: null });
    Object.assign(live.current, { snapshot, gameId, draft, uncertain });
    const invoke = React.useCallback((name, input, signal) => host.operations.invoke(name, input, { projectId, signal }), [projectId]);
    const registerCleanup = React.useCallback((callback) => activation.registerCleanup(callback), []);
    const game = snapshot?.document;
    const selected = game?.entities.find((item) => item.id === selection[0]);
    const locked = busy || loading || uncertain || snapshot?.revision.deleted || Boolean(newer) || Boolean(draft) || playing;

    const accept = React.useCallback((next) => {
      live.current.snapshot = next;
      setSnapshot(next);
      setPlaying(false); setPreview(null); setInputs([]); setHistory(null); setDiff(null);
      setSelection((ids) => ids.filter((id) => next?.document.entities.some((item) => item.id === id)));
      setSceneId((id) => next?.document.scenes.some((item) => item.id === id) ? id : next?.document.initial_scene_id ?? '');
      setNewer(null); setUncertain(false); live.current.uncertain = false;
    }, []);

    React.useEffect(() => {
      live.current.alive = true;
      const stop = () => { live.current.alive = false; live.current.read?.abort(); live.current.write?.abort(); };
      const unregister = registerCleanup(stop);
      return () => { unregister(); stop(); };
    }, [registerCleanup, context.workbenchScopeId]);

    React.useEffect(() => {
      const controller = new AbortController();
      live.current.read?.abort(); live.current.read = controller;
      live.current.loading = true; setLoading(true); setError('');
      (async () => {
        const inventory = await listGames(invoke, controller.signal);
        if (controller.signal.aborted || !live.current.alive) return;
        setLibrary(inventory);
        const next = gameId ? await readGame(invoke, gameId, controller.signal) : null;
        if (!controller.signal.aborted && live.current.alive) accept(next);
      })().catch((caught) => { if (!controller.signal.aborted && live.current.alive) setError(errorText(caught)); }).finally(() => {
        if (!controller.signal.aborted && live.current.alive) { live.current.loading = false; setLoading(false); }
      });
      return () => controller.abort();
    }, [gameId, reload, invoke, accept]);

    React.useEffect(() => {
      let stopped = false;
      let controller;
      let timer;
      async function poll() {
        try {
          if (document.visibilityState === 'hidden' || live.current.busy || live.current.loading || !live.current.snapshot) return;
          const before = live.current.snapshot;
          controller = new AbortController();
          const head = await invoke('games.head', { game_id: before.document.id }, controller.signal);
          if (stopped || live.current.busy || before !== live.current.snapshot || head.game.version === before.revision.version) return;
          if (live.current.draft) { setNewer(head.game.version); setPlaying(false); return; }
          const next = await readGame(invoke, before.document.id, controller.signal, head);
          if (!stopped && !live.current.busy && before === live.current.snapshot && !live.current.draft) { accept(next); setNotice(`已同步外部修改 · v${next.revision.version}`); }
        } catch (caught) { if (!stopped && !controller?.signal.aborted) setError('同步失败：' + errorText(caught)); }
        finally { if (!stopped) timer = setTimeout(poll, 5000); }
      }
      timer = setTimeout(poll, 5000);
      const stop = () => { stopped = true; clearTimeout(timer); controller?.abort(); };
      const unregister = registerCleanup(stop);
      return () => { unregister(); stop(); };
    }, [invoke, accept, registerCleanup]);

    const refresh = () => { if (!live.current.busy) { setPlaying(false); setReload((value) => value + 1); } };
    const edit = (next) => { if (live.current.busy || live.current.loading || live.current.uncertain) return; setPlaying(false); const value = { ...next, version: snapshot.revision.version }; live.current.draft = value; setDraft(value); setError(''); };
    const cancelDraft = () => { live.current.draft = null; setDraft(null); };

    async function write(name, input, version = live.current.snapshot?.revision.version) {
      if (!live.current.alive || live.current.busy || live.current.loading || live.current.uncertain) return false;
      const before = live.current.snapshot;
      const controller = new AbortController();
      live.current.write = controller;
      live.current.busy = true; setBusy(true); setPlaying(false); setError(''); setNotice('');
      live.current.read?.abort();
      const request = { ...input, request_id: requestId(), ...(name === 'games.create' ? {} : { game_id: before.document.id, expected_version: version }) };
      try {
        const result = await invoke(name, request, controller.signal);
        if (!live.current.alive || controller.signal.aborted) return false;
        cancelDraft();
        if (result.game.id !== gameId) { setGameId(result.game.id); }
        else accept(await readGame(invoke, result.game.id, controller.signal));
        if (controller.signal.aborted || !live.current.alive) return false;
        setLibrary((old) => old ? { ...old, library_version: result.library_version, items: [...old.items.filter((item) => item.id !== result.game.id), result.game] } : old);
        setNotice(`已保存 · v${result.game.version}`);
        return true;
      } catch (caught) {
        if (!controller.signal.aborted && live.current.alive) {
          setError(errorText(caught) + ' 请刷新确认当前版本；不会自动重放。');
          live.current.uncertain = true; setUncertain(true);
        }
        return false;
      } finally { if (live.current.write === controller) live.current.write = null; live.current.busy = false; if (live.current.alive) setBusy(false); }
    }

    const apply = (operations, version) => write('games.apply', { operations }, version);
    async function submitDraft(event) {
      event.preventDefault();
      const current = live.current.draft;
      if (!current) return;
      const spec = inputSpec(current.spec);
      let operation;
      if (current.kind === 'game') operation = { kind: 'game_rename', title: current.spec.title };
      if (current.kind === 'scene') operation = { kind: current.id ? 'scene_modify' : 'scene_create', ...(current.id ? { scene_id: byId(current.id) } : {}), scene: current.spec };
      if (current.kind === 'entity') operation = current.id ? { kind: 'entity_modify', entity_id: byId(current.id), ...spec } : { kind: 'entity_create', entities: [{ ...spec, components: current.components.map(inputSpec) }] };
      if (current.kind === 'component') operation = { kind: current.id ? 'component_modify' : 'component_add', ...(current.id ? { component_id: byId(current.id) } : { entity_id: byId(current.entityId) }), component: spec };
      if (current.kind === 'behavior') operation = { kind: current.id ? 'behavior_modify' : 'behavior_create', ...(current.id ? { behavior_id: byId(current.id) } : {}), behavior: spec, enabled: current.enabled };
      if (current.kind === 'rule') operation = { kind: current.id ? 'rule_modify' : 'rule_create', ...(current.id ? { rule_id: byId(current.id) } : {}), rule: spec, enabled: current.enabled };
      if (current.kind === 'variable') operation = { kind: current.id ? 'variable_modify' : 'variable_create', ...(current.id ? { variable_id: byId(current.id) } : {}), variable: current.spec };
      if (operation) await apply([operation], current.version);
    }

    async function action(name) {
      if (locked || !snapshot) return;
      if (!host.workbench.openArtifact) { setError('当前 Host 不支持打开耐久 Game 工件。'); return; }
      const workbenchScopeId = host.workbench.currentScopeId();
      const controller = new AbortController();
      live.current.write = controller; live.current.busy = true; setBusy(true); setError(''); setPlaying(false);
      try {
        const result = await invoke(name, { game_id: game.id, expected_version: snapshot.revision.version, request_id: requestId(), ...(name === 'games.playtest' ? { ticks, seed, inputs: inputs.filter((item) => item.tick < ticks) } : {}) }, controller.signal);
        if (!live.current.alive || controller.signal.aborted) return;
        if (!result.artifact_ids[0]) throw new Error('原 Run 没有返回可打开的 Game 工件。');
        await host.workbench.openArtifact({ projectId, sessionId: result.session_id, runId: result.run_id, artifactId: result.artifact_ids[0] }, { workbenchScopeId, signal: controller.signal });
        if (!controller.signal.aborted && live.current.alive) setNotice('已打开耐久工件。');
      } catch (caught) { if (!controller.signal.aborted && live.current.alive) setError(errorText(caught) + ' 查看原 Run 确认结果；不会重放。'); }
      finally { if (live.current.write === controller) live.current.write = null; live.current.busy = false; if (live.current.alive) setBusy(false); }
    }

    async function upload() {
      if (locked) return;
      const before = snapshot;
      live.current.busy = true; setBusy(true); setError('');
      let image;
      try {
        const file = await host.nativeDialogs.pickFile({ title: '导入 Game 图片', accept: ['png'], maxBytes: 2097152 });
        if (!file || !live.current.alive) return;
        const bytes = await host.nativeFiles.readPickedFile(file.path);
        if (!live.current.alive) return;
        image = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        if (image.width > 512 || image.height > 512) throw new Error('图片尺寸上限为 512 × 512。');
        if (!live.current.alive || live.current.snapshot !== before) return;
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context2d = canvas.getContext('2d');
        if (!context2d) throw new Error('Canvas 2D 不可用。');
        context2d.drawImage(image, 0, 0);
        const rgba = context2d.getImageData(0, 0, image.width, image.height).data;
        let binary = ''; for (let offset = 0; offset < rgba.length; offset += 16384) binary += String.fromCharCode(...rgba.subarray(offset, offset + 16384));
        live.current.busy = false;
        await write('assets.upload', { name: file.name.slice(0, 120), width: image.width, height: image.height, rgba_base64: btoa(binary) }, before.revision.version);
      } catch (caught) { if (live.current.alive) setError(errorText(caught)); }
      finally { image?.close(); live.current.busy = false; if (live.current.alive) setBusy(false); }
    }

    async function readHistory(offset = 0) {
      const before = snapshot;
      const controller = new AbortController(); live.current.read?.abort(); live.current.read = controller;
      try {
        const page = await invoke('games.revisions', { game_id: game.id, version: before.revision.version, offset, limit: 20 }, controller.signal);
        if (!controller.signal.aborted && live.current.snapshot === before) setHistory((old) => ({ ...page, items: offset ? [...(old?.items ?? []), ...page.items] : page.items }));
      } catch (caught) { if (!controller.signal.aborted && live.current.alive) setError(errorText(caught)); }
    }

    async function compareVersion(version) {
      const before = snapshot;
      const controller = new AbortController(); live.current.read?.abort(); live.current.read = controller;
      try {
        const page = await invoke('games.diff', { game_id: game.id, from_version: version, to_version: before.revision.version, offset: 0, limit: 50 }, controller.signal);
        if (!controller.signal.aborted && live.current.snapshot === before) setDiff({ ...page, from: version });
      } catch (caught) { if (!controller.signal.aborted && live.current.alive) setError(errorText(caught)); }
    }

    const entityDraft = (shape) => edit({ kind: 'entity', spec: { name: shape === 'fox' ? '狐狸' : shape === 'slime' ? '史莱姆' : '新实体', enabled: true, tags: [], scene_id: sceneId }, components: [defaultSpec('transform', game), { ...defaultSpec('visual', game), shape }] });
    const tree = game ? { id: game.id, name: game.title, children: game.scenes.map((scene) => ({ ...scene, node: 'scene', children: game.entities.filter((entity) => entity.scene_id === scene.id).map((entity) => ({ ...entity, node: 'entity', children: [] })) })) } : null;
    const updateDraft = (patch) => { const next = { ...draft, ...patch }; live.current.draft = next; setDraft(next); };
    const inspector = !game ? null : draft ? h('form', { onSubmit: submitDraft, className: 'game-editor' },
      h('div', { className: 'game-section-heading' }, h('h3', null, `${draft.id ? '编辑' : '新建'} ${names[draft.kind] ?? draft.kind}`), h('span', { className: 'game-badge' }, `基于 v${draft.version}`)),
      ['behavior', 'rule'].includes(draft.kind) && h(Fields, { game, value: { enabled: draft.enabled }, onChange: updateDraft }),
      draft.kind === 'rule' ? h(RuleFields, { game, value: draft.spec, entityId: selected?.id, onChange: (spec) => updateDraft({ spec }) }) : ['behavior', 'component'].includes(draft.kind) ? h(Spec, { game, value: draft.spec, kinds: draft.kind === 'component' ? componentKinds : behaviorKinds, fixed: Boolean(draft.id) || draft.kind === 'component', behavior: draft.kind === 'behavior', entityId: draft.entityId, onChange: (spec) => updateDraft({ spec }) }) : h(Fields, { game, value: draft.spec, onChange: (spec) => updateDraft({ spec }) }),
      draft.components?.map((component, index) => h('fieldset', { key: index }, h('legend', null, names[component.kind]), h(Spec, { game, value: component, kinds: componentKinds, fixed: true, onChange: (spec) => updateDraft({ components: draft.components.map((old, i) => i === index ? spec : old) }) }))),
      draft.version !== snapshot.revision.version && h('p', { className: 'game-warning' }, '草稿来自旧版本。先检查当前对象，再明确采用当前版本。', button(`草稿采用 v${snapshot.revision.version}`, () => updateDraft({ version: snapshot.revision.version }), busy)),
      h('div', { className: 'game-sticky-actions' }, h('button', { type: 'submit', className: 'game-primary', disabled: busy || uncertain || Boolean(newer) || draft.version !== snapshot.revision.version }, busy ? '保存中…' : '保存修改'), button('放弃草稿', cancelDraft, busy)),
    ) : selected ? h('div', { className: 'game-inspector' },
      h('div', { className: 'game-section-heading' }, h('h3', null, selected.name), button('询问 Agent', () => context.onAsk(referenceFor(snapshot, selected)))),
      h('p', { className: 'game-help' }, selected.enabled ? `${selected.tags.join(' · ') || '没有标签'} · ${selection.length} 个选中` : '未启用的实体可作为生成模板。'),
      button('编辑实体', () => edit({ kind: 'entity', id: selected.id, spec: { name: selected.name, enabled: selected.enabled, tags: selected.tags, scene_id: selected.scene_id } }), locked),
      selected.components.map((component) => h('section', { key: component.id, className: 'game-component-card' }, h('div', { className: 'game-section-heading' }, h('h4', null, names[component.spec.kind]), button('编辑', () => edit({ kind: 'component', id: component.id, spec: component.spec }), locked)), h('dl', { className: 'game-properties' }, Object.entries(component.spec).filter(([key]) => key !== 'kind' && key !== 'asset_id').map(([key, value]) => h('div', { key }, h('dt', null, key), h('dd', null, typeof value === 'boolean' ? value ? '是' : '否' : String(value))))), component.spec.kind !== 'transform' && button('移除组件', () => apply([{ kind: 'object_remove', object_id: byId(component.id), cascade: true }]), locked))),
      h('div', { className: 'game-button-row' }, componentKinds.filter((kind) => !part(selected, kind)).map((kind) => button('添加' + names[kind], () => edit({ kind: 'component', entityId: selected.id, spec: defaultSpec(kind, game) }), locked))),
      button('添加行为', () => { setTab('behaviors'); edit({ kind: 'behavior', entityId: selected.id, spec: defaultBehavior('player_control', game, selected.id), enabled: true }); }, locked),
      h('p', { className: 'game-help' }, '删除实体也会移除依赖它的行为和规则。'), button(`删除 ${selection.length} 个实体及依赖`, () => apply([{ kind: 'entity_delete', entity_ids: selection.map(byId), cascade: true }]), locked, { className: 'game-danger' }),
    ) : h('div', { className: 'game-inspector' }, h('h3', null, '场景设置'), h('p', { className: 'game-help' }, '选择实体检查组件，或在预览中拖动。所有保存都生成正式版本。'), button('编辑当前场景', () => { const { id, ...spec } = game.scenes.find((item) => item.id === sceneId); edit({ kind: 'scene', id, spec }); }, locked), button('设为启动场景', () => apply([{ kind: 'game_entry', scene_id: byId(sceneId) }]), locked || game.initial_scene_id === sceneId), button('重命名游戏', () => edit({ kind: 'game', id: game.id, spec: { title: game.title } }), locked), button('询问 Agent', () => context.onAsk(referenceFor(snapshot))), h('p', { className: 'game-help' }, '场景删除会移除其实体、行为和规则。启动场景需先调整。'), button('删除当前场景及依赖', () => apply([{ kind: 'object_remove', object_id: byId(sceneId), cascade: true }]), locked || game.initial_scene_id === sceneId), button('删除游戏（可从历史恢复）', () => write('games.delete', {}), locked, { className: 'game-danger' }));

    return h('section', { className: 'dbfox-game game-studio', 'aria-label': 'Game Studio' },
      h('header', { className: 'game-header' }, h('div', null, h('div', { className: 'game-eyebrow' }, 'GAME STUDIO'), h('h2', null, game?.title ?? '创作一个可以玩的世界')), h('div', { className: 'game-button-row' }, snapshot && h('span', { className: 'game-badge' }, `v${snapshot.revision.version}${snapshot.revision.deleted ? ' · 已删除' : ''}`), button('刷新', refresh, busy), button('导出工件', () => action('games.export'), locked || !snapshot))),
      h('div', { className: 'game-library-row' }, h('label', null, '游戏 ', h('select', { 'aria-label': '选择游戏', value: gameId, disabled: busy || Boolean(draft), onChange: (event) => { setPlaying(false); setSelection([]); setGameId(event.target.value); } }, h('option', { value: '' }, '游戏库'), library?.items.map((item) => h('option', { key: item.id, value: item.id }, item.title + (item.deleted ? ' · 已删除' : ''))))), h('span', { className: 'game-executor', 'data-state': status.state }, status.message), status.state === 'unavailable' && button('连接执行器', () => activation.executor.reconnect())),
      error && h('div', { className: 'game-error', role: 'alert' }, error), notice && h('div', { className: 'game-notice', role: 'status' }, notice),
      newer && h('div', { className: 'game-warning', role: 'status' }, `检测到外部 v${newer}，已保留草稿并暂停预览。`, button('载入新版本（保留草稿）', refresh, busy)),
      loading && h('div', { className: 'game-loading', role: 'status' }, '正在读取固定版本与图片…'),
      !loading && !game && h('div', { className: 'game-welcome' }, h('span', { className: 'game-welcome-mark', 'aria-hidden': true }, '▶'), h('h3', null, '从一只狐狸开始'), h('p', null, '创建场景、放置角色，再用行为与规则让世界运转。内置狐狸生存游戏可直接编辑。'), h('form', { onSubmit: (event) => { event.preventDefault(); void write('games.create', { title: createTitle, expected_library_version: library.library_version }); } }, h('input', { 'aria-label': '新游戏名称', value: createTitle, required: true, maxLength: 120, onChange: (event) => setCreateTitle(event.target.value) }), h('button', { type: 'submit', className: 'game-primary', disabled: busy || !library }, '创建游戏'))),
      game && !loading && h(React.Fragment, null,
        snapshot.revision.deleted && h('div', { className: 'game-warning' }, '此游戏已删除。历史内容仍可查看；选择一个未删除的历史版本恢复。', button('查看历史', () => { setBottom('history'); void readHistory(); }, busy)),
        h('div', { className: 'game-workspace' },
          h('aside', { className: 'game-library-panel' }, h('nav', { className: 'game-tabs', 'aria-label': '游戏对象' }, [['entities', '实体'], ['behaviors', '行为'], ['rules', '规则'], ['variables', '变量'], ['assets', '图片']].map(([id, label]) => button(label, () => setTab(id), false, { key: id, 'aria-pressed': tab === id }))),
            tab === 'entities' && h(React.Fragment, null, h('div', { className: 'game-button-row' }, button('+ 实体', () => entityDraft('rect'), locked), button('+ 狐狸', () => entityDraft('fox'), locked), button('+ 场景', () => edit({ kind: 'scene', spec: { name: '新场景', width: 800, height: 600, background: '#152333', gravity_x: 0, gravity_y: 0 } }), locked)), h(host.ui.Tree, { rootItem: tree, ariaLabel: '场景与实体', getItemId: (item) => item.id, getItemLabel: (item) => item.name, getItemChildren: (item) => item.children, defaultExpandedIds: [game.id, sceneId], selectedIds: selection, onItemSelect: (item) => { if (draft) return; if (item.node === 'entity') { setSceneId(item.scene_id); setSelection([item.id]); } else if (item.node === 'scene') { setSceneId(item.id); setSelection([]); } }, renderItemMeta: (item) => item.node === 'entity' && !item.enabled ? h('span', { className: 'game-badge' }, '模板') : null })),
            tab === 'behaviors' && h(React.Fragment, null, button('+ 行为', () => edit({ kind: 'behavior', enabled: true, spec: defaultBehavior('player_control', game, selected?.id) }), locked || !game.entities.length), game.behaviors.map((item) => h('section', { key: item.id, className: 'game-list-card' }, h('strong', null, names[item.spec.kind]), h('span', null, game.entities.find((entity) => entity.id === item.spec.entity_id)?.name), h('div', { className: 'game-button-row' }, button(item.enabled ? '已启用' : '已停用', () => apply([{ kind: 'behavior_modify', behavior_id: byId(item.id), behavior: inputSpec(item.spec), enabled: !item.enabled }]), locked), button('编辑', () => edit({ kind: 'behavior', id: item.id, spec: item.spec, enabled: item.enabled }), locked), button('删除', () => apply([{ kind: 'object_remove', object_id: byId(item.id) }]), locked))))),
            tab === 'rules' && h(React.Fragment, null, h('p', { className: 'game-help' }, '规则按下列顺序运行；首个结束动作拥有该 tick。'), button('+ 规则', () => edit({ kind: 'rule', enabled: true, spec: { name: '新规则', scene_id: sceneId, trigger: defaultSpec('elapsed_tick', game), actions: [defaultSpec('finish', game)] } }), locked), game.rules.map((item, index) => h('section', { key: item.id, className: 'game-list-card' }, h('strong', null, `${index + 1}. ${item.spec.name}`), h('span', null, names[item.spec.trigger.kind]), h('div', { className: 'game-button-row' }, button(item.enabled ? '已启用' : '已停用', () => apply([{ kind: 'rule_modify', rule_id: byId(item.id), rule: inputSpec(item.spec), enabled: !item.enabled }]), locked), button('编辑', () => edit({ kind: 'rule', id: item.id, spec: item.spec, enabled: item.enabled }), locked), button('上移', () => { const ids = game.rules.map((rule) => byId(rule.id)); [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]; void apply([{ kind: 'rule_reorder', rule_ids: ids }]); }, locked || index === 0), button('删除', () => apply([{ kind: 'object_remove', object_id: byId(item.id) }]), locked))))),
            tab === 'variables' && h(React.Fragment, null, button('+ 变量', () => edit({ kind: 'variable', spec: { name: 'score', value_type: 'int', initial: 0 } }), locked), game.variables.map(({ id, ...spec }) => h('section', { key: id, className: 'game-list-card' }, h('strong', null, spec.name), h('span', null, `${spec.value_type} · 初始 ${spec.initial} · 预览 ${preview?.variables[id] ?? spec.initial}`), button('编辑', () => edit({ kind: 'variable', id, spec }), locked), button('删除变量及依赖规则', () => apply([{ kind: 'object_remove', object_id: byId(id), cascade: true }]), locked)))),
            tab === 'assets' && h(React.Fragment, null, button('导入 PNG', upload, locked), h('p', { className: 'game-help' }, '最多 512 × 512；图片保存在正式版本中。Agent 也可显式读取 Pixel 工件后导入。'), game.assets.map((asset) => h('section', { key: asset.id, className: 'game-list-card' }, h('strong', null, asset.name), h('span', null, `${asset.width} × ${asset.height}`), asset.source && h('span', null, '来源：Pixel 固定版本 ' + asset.source.source_version), button('询问 Agent', () => context.onAsk(referenceFor(snapshot, asset, 'asset'))), button('删除图片及依赖', () => apply([{ kind: 'object_remove', object_id: byId(asset.id), cascade: true }]), locked)))),
          ),
          h('main', { className: 'game-preview-panel' },
            h('div', { className: 'game-preview-toolbar' }, h('label', null, '场景 ', h('select', { 'aria-label': '预览场景', value: sceneId, disabled: busy || Boolean(draft), onChange: (event) => { setPlaying(false); setSelection([]); setSceneId(event.target.value); } }, game.scenes.map((scene) => h('option', { key: scene.id, value: scene.id }, scene.name)))), h('div', { className: 'game-button-row' }, button(playing ? '暂停' : '播放', () => setPlaying(!playing), busy || Boolean(draft) || uncertain || preview?.outcome && preview.outcome !== 'running', { className: 'game-primary' }), button('单步', () => setStepKey((value) => value + 1), busy || playing || Boolean(draft)), button('重置', () => { setPlaying(false); setResetKey((value) => value + 1); }, busy))),
            h(Viewport, { snapshot, sceneId, selection, busy: busy || Boolean(draft) || uncertain || Boolean(newer) || snapshot.revision.deleted, playing, setPlaying, seed, resetKey, stepKey, onState: setPreview, onInputs: setInputs, onError: setError, onSelect: setSelection, onMove: (ids, dx, dy) => apply([{ kind: 'entities_transform', entity_ids: ids.map(byId), dx, dy }]), registerCleanup }),
            h('div', { className: 'game-preview-stats' }, h('span', null, `${((preview?.ticks_completed ?? 0) / 60).toFixed(1)} 秒 / tick ${preview?.ticks_completed ?? 0}`), h('span', null, `${preview?.entities.length ?? 0} 个运行实体`), h('span', null, preview?.outcome === 'running' ? '本地预览' : preview?.reason ?? 'Phaser 4.2.1')),
            !game.entities.length && h('div', { className: 'game-empty-prompt' }, h('h3', null, '让狐狸躲开史莱姆'), h('p', null, '添加可直接编辑的角色、生成器、生命与 60 秒获胜规则。'), button('添加狐狸生存示例', () => apply(survivalOperations(sceneId)), locked, { className: 'game-primary' })),
            h('div', { className: 'game-playtest-row' }, h('label', null, '种子 ', h('input', { type: 'number', min: 0, max: 2147483647, value: seed, disabled: busy || playing, 'aria-label': '随机种子', onChange: (event) => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 0 && value <= 2147483647) setSeed(value); } })), h('label', null, '时长 / tick ', h('input', { type: 'number', min: 1, max: 7200, value: ticks, 'aria-label': 'Playtest tick 数', onChange: (event) => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && value <= 7200) setTicks(value); } })), button('运行正式 Playtest', () => action('games.playtest'), locked || status.state !== 'ready', { className: 'game-primary' })), h('p', { className: 'game-help' }, `正式测试从启动场景运行 ${ticks} tick，使用当前种子和 ${inputs.filter((item) => item.tick < ticks).length} 条预览输入；结果保存为耐久工件。`),
          ),
          h('aside', { className: 'game-inspector-panel' }, inspector),
        ),
        h('section', { className: 'game-bottom-panel' }, h('nav', { className: 'game-tabs', 'aria-label': '游戏诊断' }, button('事件记录', () => setBottom('events'), false, { 'aria-pressed': bottom === 'events' }), button('版本历史', () => { setBottom('history'); void readHistory(); }, busy, { 'aria-pressed': bottom === 'history' }), button('撤销上个版本', () => write('games.undo', { target_version: snapshot.revision.version - 1 }), locked || snapshot.revision.version <= 1)),
          bottom === 'events' ? h('div', { className: 'game-event-log', role: 'log', 'aria-label': 'Phaser 事件记录' }, !preview?.events.length && h('p', { className: 'game-help' }, '播放或单步后，接触、伤害、生成和规则事件会出现在这里。'), preview?.events_truncated && h('p', { className: 'game-warning' }, `共 ${preview.event_count} 条事件；显示最多 1024 条并保留最终结果。`), preview?.events.slice(-100).map((event, index) => h('div', { key: index, className: 'game-event' }, h('code', null, String(event.tick).padStart(4, '0')), h('span', { className: 'game-badge' }, event.kind), h('span', null, event.detail))), preview?.events.length > 100 && h('p', { className: 'game-help' }, '界面显示最近 100 条已保留事件；正式报告可分页查看完整保留事件。')) : h('div', null,
            history?.items.map((item) => h('div', { key: item.version, className: 'game-history-row' }, h('strong', null, `v${item.version}`), h('span', null, `${item.operation ?? ''} · ${item.deleted ? '已删除' : '可恢复'}`), button('比较', () => compareVersion(item.version), busy), button('恢复为新版本', () => write('games.undo', { target_version: item.version }), busy || uncertain || Boolean(draft)))), history?.has_more && button('更多历史', () => readHistory(history.next_offset), busy), diff && h('div', { className: 'game-diff' }, h('h4', null, `v${diff.from} → v${snapshot.revision.version}`), diff.items.map((item) => h('p', { key: item.id }, `${item.change} · ${item.fields.join(', ')} · ${item.id}`)), diff.has_more && h('p', { className: 'game-help' }, `显示前 ${diff.items.length} / ${diff.total} 个差异；Agent 可分页检视。`)),
          )),
      ),
    );
  }
  return Studio;
}
