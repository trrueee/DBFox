import { loadDocument } from './document-data.js';

export function parseLocator(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Invalid Shader Artifact locator.');
  for (const name of ['project_id', 'document_id', 'content_hash', 'title']) if (typeof payload[name] !== 'string' || !payload[name]) throw new Error(`Shader Artifact is missing ${name}.`);
  if (!Number.isSafeInteger(payload.version) || payload.version < 1 || !/^[a-f0-9]{64}$/.test(payload.content_hash)) throw new Error('Invalid Shader Artifact revision.');
  if (payload.report_id !== undefined && payload.report_id !== null && typeof payload.report_id !== 'string') throw new Error('Invalid Shader report identity.');
  return payload;
}

export function artifactComponents(React, host, activation, components) {
  const h = React.createElement;
  const { CodeEditor, Diagnostics, open } = components;

  function View({ artifact, payload, context }) {
    const [page, setPage] = React.useState(null);
    const [revision, setRevision] = React.useState(null);
    const [stageId, setStageId] = React.useState('');
    const [png, setPng] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [error, setError] = React.useState('');
    const canvas = React.useRef(null);
    const lifetime = React.useRef(null);
    const lock = React.useRef(false);
    const downloads = React.useRef(new Map());
    const isDocument = artifact.type === 'dbfox.shader.document-revision';
    const isReport = artifact.type === 'dbfox.shader.compile-report';
    const representation = isDocument ? 'dbfox.shader.document.v1' : isReport ? 'dbfox.shader.compile-report.v1' : 'dbfox.shader.preview.v1';
    const read = async (operation, parameters, signal) => {
      const result = await context.representations.read(artifact.id, representation, { operation, parameters }, signal);
      signal.throwIfAborted();
      if (result.consistency !== 'durable_snapshot' || result.source_version !== String(payload.version) || result.source_fingerprint !== payload.content_hash) throw new Error('Artifact representation does not match its frozen revision.');
      return result.payload;
    };
    React.useEffect(() => {
      const controller = new AbortController(); lifetime.current = controller; lock.current = false; setBusy(true); setError(''); setPage(null); setRevision(null); setPng(null);
      const abort = () => controller.abort(); activation.signal.addEventListener('abort', abort, { once: true });
      void (async () => {
        const page = await read(isDocument ? 'page' : isReport ? 'diagnostics' : 'metadata', isDocument ? { section: 'summary' } : isReport ? { offset: 0, limit: 20 } : {}, controller.signal);
        if (controller.signal.aborted) return;
        setPage(page);
        if (!isDocument && !isReport) {
          const blob = await context.representations.stream(artifact.id, 'dbfox.shader.preview-png.v1', { operation: 'export', parameters: {} }, controller.signal);
          controller.signal.throwIfAborted();
          if (blob.type !== 'image/png' || blob.size > 1048576) throw new Error('Invalid bounded PNG representation.');
          setPng(blob);
        }
      })().catch((error) => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Artifact read failed.'); }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
      return () => {
        controller.abort(); activation.signal.removeEventListener('abort', abort);
        for (const [url, timer] of downloads.current) { clearTimeout(timer); URL.revokeObjectURL(url); }
        downloads.current.clear();
      };
    }, [artifact.id]);
    React.useEffect(() => {
      if (!png || !canvas.current) return;
      let stopped = false; let bitmap;
      void createImageBitmap(png, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' }).then((image) => {
        bitmap = image;
        if (stopped || lifetime.current.signal.aborted || !canvas.current) { image.close(); return; }
        canvas.current.width = image.width; canvas.current.height = image.height;
        canvas.current.getContext('2d').drawImage(image, 0, 0); image.close(); bitmap = null;
      }).catch((error) => { if (!stopped) setError(error.message); });
      return () => { stopped = true; bitmap?.close(); };
    }, [png]);
    const download = (blob, name) => {
      if (lifetime.current.signal.aborted) return;
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = name; anchor.click();
      const timer = setTimeout(() => { URL.revokeObjectURL(url); downloads.current.delete(url); }, 1000);
      downloads.current.set(url, timer);
    };
    const task = async (callback) => {
      if (lock.current || lifetime.current.signal.aborted) return;
      lock.current = true; setBusy(true); setError('');
      try { await callback(lifetime.current.signal); }
      catch (error) { if (!lifetime.current.signal.aborted) setError(error instanceof Error ? error.message : 'Artifact read failed.'); }
      finally { if (!lifetime.current.signal.aborted) { lock.current = false; setBusy(false); } }
    };
    const load = async (signal) => {
      const result = await loadDocument((parameters, signal) => {
        const { version, ...page } = parameters;
        if (version !== undefined && version !== payload.version) throw new Error('Cannot override an Artifact revision.');
        return read('page', page, signal);
      }, signal, payload.version);
      signal.throwIfAborted(); setRevision(result); setStageId(result.snapshot.document.stages[0].id); return result;
    };
    const stage = revision?.snapshot.document.stages.find((item) => item.id === stageId);
    return h('article', { className: 'dbfox-shader shader-artifact', 'aria-busy': busy },
      h('header', { className: 'shader-panel-title' }, h('h2', null, payload.title), h('span', { className: 'shader-badge' }, `IMMUTABLE · v${payload.version}`)),
      h('p', { className: 'shader-muted' }, `${isDocument ? 'Document revision' : isReport ? 'Compile report' : 'Rendered preview'} · ${payload.content_hash.slice(0, 16)}`),
      artifact.status && h('small', null, `Artifact status: ${artifact.status}`), error && h('p', { className: 'shader-error', role: 'alert' }, error), busy && h('p', { role: 'status' }, 'Reading the immutable representation…'),
      isDocument && page && h(React.Fragment, null, h('dl', { className: 'shader-facts' }, h('dt', null, 'Stages / passes'), h('dd', null, `${page.metadata.stage_count} / ${page.metadata.pass_count}`), h('dt', null, 'Uniforms / textures'), h('dd', null, `${page.metadata.uniform_count} / ${page.metadata.texture_count}`), h('dt', null, 'Language'), h('dd', null, 'GLSL ES 3.00')),
        h('div', { className: 'shader-actions' }, h('button', { type: 'button', disabled: busy, onClick: () => { void task(load); } }, 'Inspect immutable source'), h('button', { type: 'button', disabled: busy, onClick: () => { void task(async (signal) => { const value = revision ?? await load(signal); signal.throwIfAborted(); download(new Blob([JSON.stringify(value.snapshot, null, 2)], { type: 'application/json' }), `shader-${payload.document_id}-v${payload.version}.json`); }); } }, 'Download revision JSON')),
        stage && h('section', { className: 'shader-artifact-source' }, h('select', { 'aria-label': 'Immutable shader stage', value: stageId, onChange: (event) => setStageId(event.target.value) }, revision.snapshot.document.stages.map((item) => h('option', { key: item.id, value: item.id }, `${item.kind} · ${item.title}`))), h(CodeEditor, { stage, source: stage.source, readOnly: true }))),
      isReport && page && h(React.Fragment, null, h('p', { className: page.metadata.compiled ? 'shader-success' : 'shader-error' }, page.metadata.compiled ? 'Actual compile and link succeeded for this revision.' : 'Compilation failed for this revision.'), h('p', { className: 'shader-muted' }, `${page.metadata.elapsed_ms} ms · ${page.metadata.capabilities.version}${page.metadata.log_truncated ? ` · driver log truncated (${page.metadata.log_truncated})` : ''}`), h(Diagnostics, { items: page.items, label: 'Immutable diagnostics', onFocus: (item) => open(payload.project_id, payload.document_id, payload.title, payload.version, `stage/${item.stage_id}/line/${item.line}`) }),
        h('div', { className: 'shader-actions' }, h('button', { type: 'button', disabled: busy || page.offset === 0, onClick: () => { void task(async (signal) => setPage(await read('diagnostics', { offset: Math.max(0, page.offset - 20), limit: 20 }, signal))); } }, 'Previous diagnostics'), h('button', { type: 'button', disabled: busy || !page.has_more, onClick: () => { void task(async (signal) => setPage(await read('diagnostics', { offset: page.next_offset, limit: 20 }, signal))); } }, 'Next diagnostics'))),
      !isDocument && !isReport && page && h(React.Fragment, null, h('div', { className: 'shader-preview-canvas' }, h('canvas', { ref: canvas, role: 'img', 'aria-label': `Immutable preview at revision ${payload.version}, ${page.width} by ${page.height}` })), h('p', null, `${page.width} × ${page.height} · RGBA8 · ${page.elapsed_ms} ms`), h('p', { className: 'shader-muted' }, `Pixel hash ${page.pixel_hash}`), h('button', { type: 'button', disabled: !png || busy, onClick: () => download(png, `shader-${payload.report_id}.png`) }, 'Download PNG')),
      h('div', { className: 'shader-actions' }, h('button', { type: 'button', onClick: () => open(payload.project_id, payload.document_id, payload.title) }, 'Open current document')));
  }
  return { View };
}
