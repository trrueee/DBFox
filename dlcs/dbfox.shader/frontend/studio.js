import { createRenderer, decodeBytes, flipRows } from './renderer.js';
import { loadDocument, draftOperations, rebaseDrafts } from './document-data.js';
import { mountEditor } from './editor.js';
import { inspectorComponents, decodePickedPng } from './inspectors.js';

export function studioComponents(React, host, activation) {
  const h = React.createElement;
  const { Passes, Uniforms, Textures } = inspectorComponents(React);
  const button = (title, action, options = {}) => h('button', { type: 'button', onClick: action, ...options }, title);
  const option = (id, title) => h('option', { key: id, value: id }, title);
  const field = (label, control) => h('label', { className: 'shader-field' }, h('span', null, label), control);
  const errorMessage = (error) => error instanceof Error ? error.message.slice(0, 600) : 'The Shader operation failed.';
  const cache = activation.drafts;
  const kind = 'dbfox.shader.studio';

  function CodeEditor({ stage, source, onChange, onSave, onSelection, diagnostics, readOnly = false, focusLine, panelId, labelledBy }) {
    const parent = React.useRef(null);
    const instance = React.useRef(null);
    const callbacks = React.useRef({ onChange, onSave, onSelection });
    callbacks.current = { onChange, onSave, onSelection };
    React.useEffect(() => {
      instance.current = mountEditor(parent.current, { source, readOnly, onChange: (value) => callbacks.current.onChange?.(value), onSave: () => callbacks.current.onSave?.(), onSelection: (selection) => callbacks.current.onSelection?.(selection) });
      return () => { instance.current?.destroy(); instance.current = null; };
    }, [stage.id]); // Each stage has its own editor lifetime, never another stage's undo stack.
    React.useEffect(() => { instance.current?.replace(source); }, [source]);
    React.useEffect(() => { instance.current?.setReadOnly(readOnly); }, [readOnly]);
    React.useEffect(() => { instance.current?.diagnostics(diagnostics ?? []); }, [diagnostics]);
    React.useEffect(() => { if (focusLine) instance.current?.focusLine(focusLine.line); }, [focusLine]);
    return h('div', { ref: parent, className: 'shader-code', 'aria-label': `${stage.title} source`, ...(panelId ? { id: panelId, role: 'tabpanel', 'aria-labelledby': labelledBy } : {}) });
  }

  function PreviewCanvas({ preview }) {
    const canvas = React.useRef(null);
    React.useEffect(() => {
      if (!canvas.current || !preview?.rendered) return;
      const { width, height } = preview;
      canvas.current.width = width; canvas.current.height = height;
      const bytes = flipRows(decodeBytes(preview.rgba_base64), width, height);
      canvas.current.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(bytes), width, height), 0, 0);
    }, [preview]);
    return h('div', { className: 'shader-preview-canvas' }, preview?.rendered
      ? h('canvas', { ref: canvas, role: 'img', 'aria-label': `Local WebGL preview, ${preview.width} by ${preview.height} pixels` })
      : h('div', { className: 'shader-preview-empty' }, h('strong', null, 'Your shader, in pixels'), h('span', null, 'Run a local preview to see this revision or your source draft.')));
  }

  function Diagnostics({ items, onFocus, label }) {
    return h('section', { className: 'shader-diagnostics', 'aria-label': label }, h('h3', null, label), items.length === 0 ? h('p', { className: 'shader-muted' }, 'No diagnostics in this result.') : h('ul', null, items.map((item, index) => h('li', { key: index, 'data-severity': item.severity },
      h('strong', null, item.severity), item.stage_id && item.line ? button(`Line ${item.line}`, () => onFocus(item)) : null,
      h('span', null, item.message), h('small', null, item.code)))));
  }

  async function catalog(projectId, signal) {
    const documents = [];
    let offset = 0; let generation = 0;
    do {
      const page = await host.operations.invoke('documents.list', { offset, limit: 50 }, { projectId, signal });
      signal.throwIfAborted();
      if (offset && generation !== page.studio_generation) throw new Error('The Studio changed during listing. Refresh to read its current inventory.');
      generation = page.studio_generation; documents.push(...page.items);
      if (!page.has_more) return { documents, generation };
      if (page.next_offset <= offset || documents.length > 128) throw new Error('Invalid Studio inventory cursor.');
      offset = page.next_offset;
    } while (offset <= 128);
    throw new Error('Studio inventory exceeds its bounded page contract.');
  }

  function open(projectId, documentId, title = 'Shader Studio', version, locator) {
    const scope = host.workbench.currentScopeId();
    host.dockViews.open({ viewKey: `dbfox.shader.studio:${scope}:${documentId ?? projectId}${version === undefined ? '' : `:v${version}`}`, viewType: 'dbfox.shader.studio', title, closeable: true, projectId,
      ...(documentId ? { target: { type: 'object', object: { kind: 'dbfox.shader.document', id: documentId, ...(version === undefined ? {} : { version }) }, authority: { kind, id: projectId }, ...(locator ? { locator } : {}) } } : {}) });
  }

  function Connector({ projectId }) {
    const [items, setItems] = React.useState([]);
    const [error, setError] = React.useState('');
    const [refresh, setRefresh] = React.useState(0);
    React.useEffect(() => {
      const controller = new AbortController();
      const abort = () => controller.abort(); activation.signal.addEventListener('abort', abort, { once: true });
      setError('');
      void catalog(projectId, controller.signal).then((value) => { if (!controller.signal.aborted) setItems(value.documents); }).catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); });
      return () => { controller.abort(); activation.signal.removeEventListener('abort', abort); };
    }, [projectId, refresh]);
    const root = { id: projectId, title: 'Shader Studio', children: items.map((item) => ({ ...item, children: [] })) };
    return h('div', { className: 'dbfox-shader shader-connector' },
      h(host.ui.Tree, { rootItem: root, ariaLabel: 'Shader documents', getItemId: (item) => item.id, getItemLabel: (item) => item.title, getItemChildren: (item) => item.children, defaultExpandedIds: [projectId], onItemSelect: (item) => open(projectId, item.id === projectId ? undefined : item.id, item.title), renderItemMeta: (item) => item.version ? `v${item.version}${item.deleted ? ' · deleted' : ''}` : `${items.length} documents` }),
      error && h('p', { role: 'alert', className: 'shader-error' }, error), h('div', { className: 'shader-actions' }, button('Open Studio', () => open(projectId)), button('Refresh', () => setRefresh((value) => value + 1))));
  }

  function Studio({ view, context }) {
    const tabPrefix = React.useId();
    const projectId = view.projectId;
    const scope = context.workbenchScopeId;
    const initialId = view.target?.type === 'object' && view.target.object.kind === 'dbfox.shader.document' ? view.target.object.id : '';
    const [documentId, setDocumentId] = React.useState(initialId);
    const pinnedVersion = documentId === initialId && view.target?.type === 'object' && Number.isSafeInteger(view.target.object.version) ? view.target.object.version : undefined;
    const historical = pinnedVersion !== undefined;
    const [inventory, setInventory] = React.useState({ documents: [], generation: 0 });
    const [loaded, setLoaded] = React.useState(null);
    const [drafts, setDrafts] = React.useState({});
    const [incoming, setIncoming] = React.useState(null);
    const [conflicts, setConflicts] = React.useState([]);
    const [external, setExternal] = React.useState(null);
    const [uncertain, setUncertain] = React.useState(false);
    const [section, setSection] = React.useState('Source');
    const [stageId, setStageId] = React.useState('');
    const [passId, setPassId] = React.useState('');
    const [selection, setSelection] = React.useState({ from: 1, to: 1 });
    const [focusLine, setFocusLine] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [loading, setLoading] = React.useState(true);
    const [message, setMessage] = React.useState('');
    const [error, setError] = React.useState('');
    const [local, setLocal] = React.useState(null);
    const [localBusy, setLocalBusy] = React.useState(false);
    const [live, setLive] = React.useState(false);
    const [previewRequest, setPreviewRequest] = React.useState(0);
    const [published, setPublished] = React.useState(null);
    const [history, setHistory] = React.useState(null);
    const [historyVersion, setHistoryVersion] = React.useState('');
    const [difference, setDifference] = React.useState(null);
    const [refreshKey, setRefreshKey] = React.useState(0);
    const lifetime = React.useRef(null);
    const lock = React.useRef(false);
    const state = React.useRef(null);
    state.current = { loaded, drafts };
    const gpu = React.useSyncExternalStore(activation.executor.subscribe, activation.executor.getSnapshot);
    const canonical = loaded?.snapshot.document;
    const stage = canonical?.stages.find((item) => item.id === stageId) ?? canonical?.stages[0];
    const pass = canonical?.passes.find((item) => item.id === passId) ?? canonical?.passes[0];
    const pending = canonical ? draftOperations(canonical, drafts) : [];
    const dirty = pending.length > 0;
    const canWrite = Boolean(loaded && !historical && !loaded.summary.deleted && !external && !uncertain && !busy);
    const canConfigure = canWrite && !dirty;
    const read = (parameters, signal) => host.operations.invoke('documents.get', { document_id: documentId, ...parameters }, { projectId, signal });

    const current = (controller) => !controller.signal.aborted && !activation.signal.aborted && host.workbench.currentScopeId() === scope;
    function adopt(value, nextDrafts = {}) {
      setLoaded(value); setDrafts(nextDrafts); setExternal(null); setIncoming(null); setConflicts([]); setUncertain(false); setPublished(null); setLocal(null);
      setStageId((old) => value.snapshot.document.stages.some((item) => item.id === old) ? old : value.snapshot.document.stages[0]?.id ?? '');
      setPassId((old) => value.snapshot.document.passes.some((item) => item.id === old) ? old : value.snapshot.document.passes[0]?.id ?? '');
    }

    React.useEffect(() => {
      const controller = new AbortController(); lifetime.current = controller; lock.current = false; setBusy(false);
      const abort = () => controller.abort(); activation.signal.addEventListener('abort', abort, { once: true });
      setLoading(true); setError(''); setLoaded(null); setLocal(null); setLocalBusy(false); setPublished(null); setHistory(null); setDifference(null);
      void (async () => {
        const list = await catalog(projectId, controller.signal);
        if (!current(controller)) return;
        setInventory(list);
        if (!documentId) { setLoading(false); return; }
        const latest = await loadDocument(read, controller.signal, pinnedVersion);
        if (!current(controller)) return;
        const cached = cache.get(`${scope}:${documentId}`);
        if (!historical && cached && draftOperations(cached.loaded.snapshot.document, cached.drafts).length) {
          adopt(cached.loaded, cached.drafts);
          if (latest.summary.version !== cached.loaded.summary.version) setExternal(latest.summary);
        } else adopt(latest);
        const location = view.target?.type === 'object' && view.target.locator ? /^stage\/([^/]+)\/line\/(\d+)$/.exec(view.target.locator) : null;
        if (location && latest.snapshot.document.stages.some((item) => item.id === location[1])) { setStageId(location[1]); setFocusLine({ line: Number(location[2]), token: performance.now() }); }
      })().catch((error) => { if (current(controller)) setError(errorMessage(error)); }).finally(() => { if (current(controller)) setLoading(false); });
      return () => { controller.abort(); activation.signal.removeEventListener('abort', abort); };
    }, [projectId, documentId, scope, refreshKey, pinnedVersion]);

    React.useEffect(() => {
      if (!loaded || historical) return;
      if (draftOperations(loaded.snapshot.document, drafts).length) cache.set(`${scope}:${documentId}`, { loaded, drafts });
      else cache.delete(`${scope}:${documentId}`);
    }, [loaded, drafts, scope, documentId]);

    React.useEffect(() => {
      if (!loaded || historical || !lifetime.current) return;
      const controller = lifetime.current;
      let stopped = false; let timer;
      async function checkHead() {
        if (stopped || !current(controller)) return;
        try {
          if (globalThis.document.visibilityState !== 'hidden' && !lock.current) {
            const head = await host.operations.invoke('documents.head', { document_id: documentId }, { projectId, signal: controller.signal });
            if (!stopped && current(controller) && head.version !== state.current.loaded?.summary.version) {
              const value = state.current;
              if (draftOperations(value.loaded.snapshot.document, value.drafts).length) setExternal(head);
              else {
                const next = await loadDocument(read, controller.signal);
                if (!stopped && current(controller) && !lock.current && !draftOperations(state.current.loaded.snapshot.document, state.current.drafts).length) { adopt(next); setMessage(`Synchronized external revision v${next.summary.version}.`); }
              }
            }
          }
        } catch (error) { if (!stopped && current(controller)) setError(`Head check failed: ${errorMessage(error)}`); }
        if (!stopped && current(controller)) timer = setTimeout(checkHead, 1000);
      }
      timer = setTimeout(checkHead, 1000);
      return () => { stopped = true; clearTimeout(timer); };
    }, [documentId, loaded?.summary.version, scope]);

    async function run(task, { write = false } = {}) {
      const controller = lifetime.current;
      if (!controller || !current(controller) || lock.current) return;
      lock.current = true; setBusy(true); setError(''); setMessage('');
      try { await task(controller); }
      catch (error) {
        if (current(controller)) {
          setError(errorMessage(error) + (write ? ' The write outcome is not retried. Inspect the current revision and history before making another edit.' : ''));
          if (write) setUncertain(true);
        }
      } finally { if (current(controller)) { lock.current = false; setBusy(false); } }
    }

    const reloadAfterMutation = async (controller, result) => {
      const next = await loadDocument(read, controller.signal, result.document.version);
      if (!current(controller)) return;
      adopt(next); setMessage(result.changed ? `Saved revision v${result.document.version}.` : 'No semantic change; the revision is unchanged.');
      const inventory = await catalog(projectId, controller.signal);
      if (current(controller)) setInventory(inventory);
    };
    function apply(operations) {
      if (!canWrite || !operations.length) return;
      void run(async (controller) => {
        const result = await host.operations.invoke('documents.apply', { document_id: documentId, expected_version: loaded.summary.version, request_id: crypto.randomUUID(), operations }, { projectId, signal: controller.signal });
        await reloadAfterMutation(controller, result);
      }, { write: true });
    }
    const save = () => apply(pending);
    function ask(objectKind = 'document', id = documentId, locator = '', title = canonical?.title) {
      if (!loaded || !current(lifetime.current)) return;
      context.onAsk({ label: `${title} · v${loaded.summary.version}`, authority: { kind, id: projectId }, object: { kind: `dbfox.shader.${objectKind}`, id, version: loaded.summary.version }, locator: `document/${documentId}${locator}` });
    }
    const focusDiagnostic = (item) => { if (canonical?.stages.some((stage) => stage.id === item.stage_id)) { setStageId(item.stage_id); setSection('Source'); setFocusLine({ line: item.line ?? 1, token: performance.now() }); } };

    function reviewLatest() {
      void run(async (controller) => {
        const latest = await loadDocument(read, controller.signal);
        if (!current(controller)) return;
        const outcome = rebaseDrafts(canonical, latest.snapshot.document, drafts);
        if (!outcome.conflicts.length) { adopt(latest, outcome.drafts); setMessage('Rebased your draft onto the inspected revision. Review it, then Save explicitly.'); }
        else { setIncoming(latest); setConflicts(outcome.conflicts); setMessage('Some draft stages changed externally. Compare each source before choosing which text to keep.'); }
      });
    }

    function publish(action) {
      if (!canConfigure) return;
      const openArtifact = host.workbench.openArtifact;
      if (typeof openArtifact !== 'function') { setError('This Host cannot open generated Artifacts. No publication was started.'); return; }
      const capturedScope = host.workbench.currentScopeId();
      void run(async (controller) => {
        const result = await host.operations.invoke(`documents.${action}`, { document_id: documentId, expected_version: loaded.summary.version, request_id: crypto.randomUUID() }, { projectId, signal: controller.signal });
        if (!current(controller)) return;
        const artifactId = result.artifact_ids.at(-1);
        setPublished({ result, scope: capturedScope, controller, artifactId });
        setMessage(action === 'export' ? 'Published an immutable document revision.' : result.outcome.compiled ? 'Published an exact-revision compile report.' : 'Published a failed compile report with actual diagnostics.');
        if (!artifactId) throw new Error('The action returned no Artifact identity. Inspect its original Run.');
        await openArtifact({ projectId, sessionId: result.session_id, runId: result.run_id, artifactId }, { workbenchScopeId: capturedScope, signal: controller.signal });
      }, { write: true });
    }

    const localKey = loaded ? JSON.stringify([loaded.summary.version, drafts]) : '';
    React.useEffect(() => {
      if (!loaded || (!live && !previewRequest) || loading) return;
      const controller = new AbortController();
      const parent = lifetime.current;
      const abort = () => controller.abort(); parent.signal.addEventListener('abort', abort, { once: true });
      let renderer;
      const timer = setTimeout(() => {
        if (!current(parent) || controller.signal.aborted) return;
        setLocalBusy(true);
        void (async () => {
          renderer = createRenderer(globalThis.document.createElement('canvas'));
          const snapshot = { ...loaded.snapshot, document: { ...canonical, stages: canonical.stages.map((item) => ({ ...item, source: drafts[item.id] ?? item.source })) } };
          const result = await renderer.execute(snapshot, { kind: 'preview', signal: controller.signal });
          if (!controller.signal.aborted && current(parent)) setLocal({ result, key: localKey, draft: dirty });
        })().catch((error) => { if (!controller.signal.aborted && current(parent)) setError(`Local preview: ${errorMessage(error)}`); }).finally(() => { renderer?.dispose(); if (!controller.signal.aborted && current(parent)) setLocalBusy(false); });
      }, live ? 600 : 0);
      return () => { clearTimeout(timer); controller.abort(); renderer?.dispose(); parent.signal.removeEventListener('abort', abort); };
    }, [live, previewRequest, live ? localKey : loaded?.summary.version, scope, loading]);

    function showHistory(offset = 0) {
      void run(async (controller) => {
        const page = await host.operations.invoke('documents.revisions', { document_id: documentId, version: loaded.summary.version, offset, limit: 20 }, { projectId, signal: controller.signal });
        if (current(controller)) { setHistory(page); setHistoryVersion(String(page.items.find((item) => item.version < loaded.summary.version)?.version ?? loaded.summary.version)); }
      });
    }
    function showDiff(offset = 0, source = false) {
      void run(async (controller) => {
        const page = await host.operations.invoke('documents.diff', { document_id: documentId, from_version: Number(historyVersion), to_version: loaded.summary.version, section: source ? 'source' : 'summary', ...(source ? { stage_id: stage.id } : {}), offset, limit: 50 }, { projectId, signal: controller.signal });
        if (current(controller)) setDifference({ page, source });
      });
    }
    function restore() {
      if (dirty || historical || !historyVersion) return;
      void run(async (controller) => {
        const result = await host.operations.invoke('documents.undo', { document_id: documentId, expected_version: loaded.summary.version, target_version: Number(historyVersion), request_id: crypto.randomUUID() }, { projectId, signal: controller.signal });
        await reloadAfterMutation(controller, result); setHistory(null); setDifference(null);
      }, { write: true });
    }

    return h('main', { className: 'dbfox-shader shader-studio', 'aria-label': 'Shader Studio', 'aria-busy': busy || loading },
      h('header', { className: 'shader-header' }, h('div', null, h('span', { className: 'shader-eyebrow' }, 'PROCEDURAL VISUALS'), h('h1', null, 'Shader Studio')), h('div', { className: 'shader-executor-status', 'data-state': gpu.state }, h('span', null, gpu.message), gpu.state === 'unavailable' && button('Reconnect GPU', () => activation.executor.reconnect()))),
      h('div', { className: 'shader-document-bar' }, field('Document', h('select', { value: documentId, disabled: busy, onChange: (event) => { setDocumentId(event.target.value); setPreviewRequest(0); } }, option('', 'Choose a document'), inventory.documents.map((item) => option(item.id, `${item.title} · v${item.version}${item.deleted ? ' · deleted' : ''}`)))),
        h('form', { className: 'shader-create-form', onSubmit: (event) => {
          event.preventDefault(); const title = String(new FormData(event.currentTarget).get('title'));
          void run(async (controller) => {
            const result = await host.operations.invoke('documents.create', { title, expected_generation: inventory.generation, request_id: crypto.randomUUID() }, { projectId, signal: controller.signal });
            if (current(controller)) { setDocumentId(result.document.id); setPreviewRequest(0); }
          }, { write: true });
        } }, h('input', { name: 'title', 'aria-label': 'New document title', placeholder: 'New document title', required: true, maxLength: 120, disabled: busy }), h('button', { type: 'submit', disabled: busy || loading }, 'Create')),
        button('Refresh inventory', () => setRefreshKey((value) => value + 1), { disabled: busy })),
      h('div', { className: 'shader-notices', 'aria-live': 'polite' }, message && h('p', { className: 'shader-success' }, message), error && h('p', { role: 'alert', className: 'shader-error' }, error)),
      loading ? h('div', { className: 'shader-empty', role: 'status' }, 'Reading version-fixed document pages…') : !loaded ? h('div', { className: 'shader-empty' }, h('h2', null, 'Start with a fragment of an idea'), h('p', null, 'Create a document to get a vertex stage, a fragment stage and a fullscreen pass. Edit, compile, inspect and refine in one place.')) : h(React.Fragment, null,
        h('div', { className: 'shader-toolbar' }, h('strong', null, canonical.title), h('span', { className: 'shader-badge' }, `v${loaded.summary.version}`), h('span', { className: 'shader-muted' }, historical ? 'Historical revision · read-only' : dirty ? `${pending.length} unsaved stage${pending.length === 1 ? '' : 's'}` : loaded.summary.deleted ? 'Deleted · history remains readable' : 'Saved'),
          button('Save source', save, { disabled: !canWrite || !dirty, className: 'shader-primary' }), button('Compile & publish', () => publish('compile'), { disabled: !canConfigure || gpu.state !== 'ready' }), button('Render & publish', () => publish('preview'), { disabled: !canConfigure || gpu.state !== 'ready' }), button('Export revision', () => publish('export'), { disabled: !canConfigure }), button('Ask Agent', () => ask()), historical && button('Open current document', () => open(projectId, documentId, canonical.title))),
        (external || uncertain) && h('section', { className: 'shader-conflict', role: 'alert' }, h('strong', null, external ? `The document is now v${external.version}. Your draft is preserved on v${loaded.summary.version}.` : 'The last write outcome needs inspection.'), h('p', null, 'Inspect the latest immutable revision before saving. Rebase only carries a draft automatically when its original target source is unchanged.'), h('div', { className: 'shader-actions' }, button('Inspect latest & rebase', reviewLatest, { disabled: busy }), button('Discard drafts & load latest', () => { cache.delete(`${scope}:${documentId}`); setDrafts({}); setRefreshKey((value) => value + 1); }, { disabled: busy }))),
        incoming && h('section', { className: 'shader-conflict' }, h('h2', null, 'Resolve source conflicts'), conflicts.map((id) => {
          const before = canonical.stages.find((item) => item.id === id); const after = incoming.snapshot.document.stages.find((item) => item.id === id);
          return h('article', { key: id }, h('h3', null, before?.title ?? id), after ? h('div', { className: 'shader-compare' }, h('div', null, h('h4', null, 'Your retained draft'), h(CodeEditor, { stage: before, source: drafts[id], readOnly: true })), h('div', null, h('h4', null, `Published source v${incoming.summary.version}`), h(CodeEditor, { stage: after, source: after.source, readOnly: true }))) : h('p', null, 'This stage was deleted externally. Copy your draft before discarding it or recreate a stage explicitly.'));
        }), button('Keep my drafts on this reviewed revision', () => {
          if (conflicts.some((id) => !incoming.snapshot.document.stages.some((stage) => stage.id === id))) { setError('A draft stage was deleted. Copy its source before loading the latest revision.'); return; }
          adopt(incoming, drafts); setMessage('Your explicit source choices are rebased. Save source to commit them with the new version fence.');
        }, { disabled: busy })),
        h('nav', { className: 'shader-section-tabs', 'aria-label': 'Shader editing sections' }, ['Source', 'Passes', 'Uniforms', 'Textures', 'History'].map((name) => button(name, () => { setSection(name); if (name === 'History' && !history) showHistory(); }, { key: name, 'aria-current': section === name ? 'page' : undefined }))),
        h('div', { className: 'shader-work-area' }, h('section', { className: 'shader-main-panel' },
          section === 'Source' && h(React.Fragment, null,
            h('div', { className: 'shader-stage-tabs', role: 'tablist', 'aria-label': 'Shader stages', onKeyDown: (event) => {
              const index = canonical.stages.findIndex((item) => item.id === stage.id); const count = canonical.stages.length;
              const next = event.key === 'ArrowRight' ? (index + 1) % count : event.key === 'ArrowLeft' ? (index + count - 1) % count : event.key === 'Home' ? 0 : event.key === 'End' ? count - 1 : null;
              if (next === null) return;
              event.preventDefault(); setStageId(canonical.stages[next].id); setSelection({ from: 1, to: 1 }); event.currentTarget.querySelectorAll('button')[next]?.focus();
            } }, canonical.stages.map((item) => button(`${item.kind === 'vertex' ? 'VS' : 'FS'} · ${item.title}${drafts[item.id] !== undefined && drafts[item.id] !== item.source ? ' *' : ''}`, () => { setStageId(item.id); setSelection({ from: 1, to: 1 }); }, { key: item.id, id: `${tabPrefix}-${item.id}`, role: 'tab', tabIndex: item.id === stage?.id ? 0 : -1, 'aria-controls': `${tabPrefix}-panel`, 'aria-selected': item.id === stage?.id }))),
            stage && h(CodeEditor, { stage, source: drafts[stage.id] ?? stage.source, onChange: (source) => setDrafts((old) => ({ ...old, [stage.id]: source })), onSave: save, onSelection: setSelection, diagnostics: local?.key === localKey ? local.result.diagnostics.filter((item) => item.stage_id === stage.id) : [], readOnly: busy || historical || loaded.summary.deleted, focusLine, panelId: `${tabPrefix}-panel`, labelledBy: `${tabPrefix}-${stage.id}` }),
            h('div', { className: 'shader-editor-footer' }, h('span', { id: 'shader-editor-help' }, 'GLSL ES 3.00 · Ctrl/Cmd+S saves · Tab indents'), h('span', null, `Lines ${selection.from}–${selection.to}`), stage && button('Ask about selected lines', () => ask('stage', stage.id, `/stage/${stage.id}/lines/${selection.from}-${selection.to}`, stage.title), { disabled: dirty })),
            h('details', { className: 'shader-stage-management' }, h('summary', null, 'Manage shader stages'), h('fieldset', { disabled: !canConfigure, className: 'shader-fieldset' }, h('legend', null, 'Add a stage'), h('form', { className: 'shader-create-form', onSubmit: (event) => {
              event.preventDefault(); const form = new FormData(event.currentTarget); const kind = String(form.get('kind'));
              const template = canonical.stages.find((item) => item.kind === kind);
              apply([{ kind: 'stage_create', stage_kind: kind, title: String(form.get('title')), source: template?.source ?? '#version 300 es\nvoid main() {}\n' }]);
            } }, h('input', { name: 'title', 'aria-label': 'New stage title', placeholder: 'New stage title', maxLength: 120, required: true }), h('select', { name: 'kind', 'aria-label': 'New stage kind', defaultValue: 'fragment' }, option('fragment', 'Fragment'), option('vertex', 'Vertex')), h('button', { type: 'submit' }, 'Add stage')), stage && button('Remove selected stage', () => apply([{ kind: 'stage_remove', stage_id: { id: stage.id } }]), { className: 'shader-danger' }), h('p', { className: 'shader-muted' }, 'A referenced stage must be removed from its passes first.')))),
          section === 'Passes' && h(Passes, { document: canonical, selectedId: pass?.id, onSelect: setPassId, onApply: apply, disabled: !canConfigure, onAsk: (item) => ask('pass', item.id, `/pass/${item.id}`, item.title) }),
          section === 'Uniforms' && h(Uniforms, { document: canonical, onApply: apply, disabled: !canConfigure, version: loaded.summary.version }),
          section === 'Textures' && h(Textures, { document: canonical, blobs: loaded.snapshot.textures, onApply: apply, disabled: !canConfigure, onImport: () => { void run(async (controller) => {
            const operation = await decodePickedPng(host, controller.signal); if (!operation || !current(controller)) return;
            const result = await host.operations.invoke('documents.apply', { document_id: documentId, expected_version: loaded.summary.version, request_id: crypto.randomUUID(), operations: [operation] }, { projectId, signal: controller.signal });
            await reloadAfterMutation(controller, result);
          }, { write: true }); } }),
          section === 'History' && h('div', { className: 'shader-inspector' }, h('h2', null, 'Immutable history'), h('p', { className: 'shader-muted' }, 'Restore creates a new revision. Old reports and textures remain pinned to their original versions.'),
            history && h(React.Fragment, null, field('Historical revision', h('select', { value: historyVersion, onChange: (event) => { setHistoryVersion(event.target.value); setDifference(null); } }, history.items.map((item) => option(String(item.version), `v${item.version} · ${item.title}${item.deleted ? ' · deleted' : ''} · ${item.content_hash.slice(0, 8)}`)))),
              h('div', { className: 'shader-actions' }, button('Previous history page', () => showHistory(Math.max(0, history.offset - 20)), { disabled: busy || history.offset === 0 }), button('Next history page', () => showHistory(history.next_offset), { disabled: busy || !history.has_more }), button('Compare changes', () => showDiff(), { disabled: busy }), button('Compare selected stage source', () => showDiff(0, true), { disabled: busy || !stage }), button('Restore this revision', restore, { disabled: historical || busy || dirty || Boolean(external) || uncertain }))),
            difference && h('section', { className: 'shader-diff' }, h('h3', null, `v${historyVersion} → v${loaded.summary.version}`), difference.source ? difference.page.metadata.source_diff_available === false ? h('p', null, 'This source exceeds the bounded text-diff budget. Read the exact historical source through its revision Artifact.') : h('pre', null, difference.page.source || 'No source changes.') : h('ul', null, difference.page.items.map((item, index) => h('li', { key: index }, `${item.section} · ${item.change} · ${item.id}`))), difference.page.has_more && button('Next diff page', () => showDiff(difference.page.next_offset, difference.source), { disabled: busy })),
            h('fieldset', { disabled: !canConfigure, className: 'shader-fieldset' }, h('legend', null, 'Document settings'), h('form', { key: loaded.summary.version, className: 'shader-create-form', onSubmit: (event) => { event.preventDefault(); apply([{ kind: 'rename_document', title: String(new FormData(event.currentTarget).get('title')) }]); } }, h('input', { name: 'title', 'aria-label': 'Document title', defaultValue: canonical.title, maxLength: 120, required: true }), h('button', { type: 'submit' }, 'Rename')),
              button('Delete document (keep history)', () => { void run(async (controller) => { const result = await host.operations.invoke('documents.delete', { document_id: documentId, expected_version: loaded.summary.version, request_id: crypto.randomUUID() }, { projectId, signal: controller.signal }); await reloadAfterMutation(controller, result); }, { write: true }); }, { className: 'shader-danger' }))),
        ),
        h('aside', { className: 'shader-preview-panel', 'aria-label': 'Preview and diagnostics' }, h('div', { className: 'shader-panel-title' }, h('h2', null, 'Preview'), h('span', { className: 'shader-badge' }, 'LOCAL · UNPUBLISHED')),
          h(PreviewCanvas, { preview: local?.result }), h('p', { className: 'shader-muted' }, local ? `${local.draft ? 'Unsaved source draft' : `Revision v${loaded.summary.version}`} · ${local.key !== localKey ? 'outdated preview' : local.result.rendered ? 'actual WebGL pixels' : 'compile failed'}` : 'No local render yet.'),
          h('div', { className: 'shader-actions' }, button(localBusy ? 'Rendering…' : 'Preview locally', () => { setLocalBusy(false); setPreviewRequest((value) => value + 1); }, { disabled: loading || localBusy || loaded.summary.deleted }), field('Live draft preview', h('input', { type: 'checkbox', checked: live, onChange: (event) => { setLive(event.target.checked); setLocalBusy(false); } }))),
          h('fieldset', { disabled: !canConfigure, className: 'shader-fieldset' }, h('legend', null, 'Fixed preview configuration'), h('form', { key: loaded.summary.version, className: 'shader-form', onSubmit: (event) => {
            event.preventDefault(); const data = new FormData(event.currentTarget); apply([{ kind: 'preview_set', pass_id: { id: String(data.get('pass')) }, width: Number(data.get('width')), height: Number(data.get('height')), time_seconds: Number(data.get('time')) }]);
          } }, field('Final output pass', h('select', { name: 'pass', defaultValue: canonical.preview.pass_id }, canonical.passes.map((item) => option(item.id, item.title)))), h('div', { className: 'shader-grid-two' }, field('Width', h('input', { name: 'width', type: 'number', required: true, min: 1, max: 256, step: 1, defaultValue: canonical.preview.width })), field('Height', h('input', { name: 'height', type: 'number', required: true, min: 1, max: 256, step: 1, defaultValue: canonical.preview.height }))), field('Time (seconds)', h('input', { name: 'time', type: 'number', required: true, min: 0, max: 86400, step: 'any', defaultValue: canonical.preview.time_seconds })), h('button', { type: 'submit' }, 'Save preview configuration'))),
          local && h(Diagnostics, { items: local.result.diagnostics, onFocus: focusDiagnostic, label: 'Local diagnostics' }), published?.result.outcome.diagnostics && h(Diagnostics, { items: published.result.outcome.diagnostics, onFocus: focusDiagnostic, label: 'Published report diagnostics' }),
          published?.artifactId && button('Open published Artifact', () => { const saved = published; if (current(saved.controller) && host.workbench.openArtifact) void host.workbench.openArtifact({ projectId, sessionId: saved.result.session_id, runId: saved.result.run_id, artifactId: saved.artifactId }, { workbenchScopeId: saved.scope, signal: saved.controller.signal }).catch((error) => { if (current(saved.controller)) setError(errorMessage(error)); }); }),
        )),
      ));
  }
  return { Studio, Connector, CodeEditor, PreviewCanvas, Diagnostics, open };
}
