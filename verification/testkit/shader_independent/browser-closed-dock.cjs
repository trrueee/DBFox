async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders();
  delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const uuid = () => page.evaluate(() => crypto.randomUUID());
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }), timeout: 20000 });
    const body = await response.json();
    if (!response.ok()) throw new Error(`${path}: HTTP ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  if (await page.locator('.shader-studio').count()) throw new Error('This proof requires the Dock to remain closed');
  const projects = await api('projects', undefined, 'GET');
  let project = projects.find(item => item.name === 'Shader Independent QA');
  if (!project) project = await api('projects', { name: 'Shader Independent QA' });
  const operation = (name, data) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${project.id}`, data);
  const inventory = await operation('documents.list', {});
  if (inventory.items.some(item => item.title === 'Closed Dock Driver Proof')) throw new Error('Use the recorded proof; do not replay its writes');
  const created = await operation('documents.create', { title: 'Closed Dock Driver Proof', expected_generation: inventory.studio_generation, request_id: await uuid() });
  const id = created.document.id;
  const stages = await operation('documents.get', { document_id: id, version: 1, section: 'stages' });
  const fragment = stages.items.find(item => item.kind === 'fragment');
  const source = await operation('documents.get', { document_id: id, version: 1, section: 'source', stage_id: fragment.id, limit: 50 });
  const actions = [];
  async function action(kind, version, compiled) {
    const started = Date.now();
    const result = await operation(`documents.${kind}`, { document_id: id, expected_version: version, request_id: await uuid() });
    actions.push({ kind, version, elapsedMs: Date.now() - started, result });
    if (result.outcome.compiled !== compiled) throw new Error(`Unexpected actual driver status: ${JSON.stringify(result)}`);
    if (await page.locator('.shader-studio').count()) throw new Error('An action opened the Dock');
    return result;
  }
  await action('compile', 1, true);
  const invalid = '#version 300 es\nprecision highp float;\nout vec4 color;\nvoid main(){ color = vec4(1.0) BROKEN_TOKEN; }\n';
  const changed = await operation('documents.apply', { document_id: id, expected_version: 1, request_id: await uuid(), operations: [{ kind: 'stage_replace', stage_id: { id: fragment.id }, source: invalid }] });
  await action('compile', 2, false);
  const repaired = await operation('documents.apply', { document_id: id, expected_version: 2, request_id: await uuid(), operations: [{ kind: 'stage_replace', stage_id: { id: fragment.id }, source: source.source }] });
  await action('compile', 3, true);
  await action('preview', 3, true);
  const after = await operation('documents.head', { document_id: id });
  if (after.version !== 3 || after.content_hash !== created.document.content_hash) throw new Error('Exact repair changed original source identity');
  return { boundary: 'signed production Electron/Main/Preload/HTTP/ActionRun/activation WebGL executor; Dock never opened',
    projectId: project.id, created, changed, repaired, fragmentId: fragment.id, source: source.source, actions, after,
    shaderDockCount: await page.locator('.shader-studio').count(), userAgent: await page.evaluate(() => navigator.userAgent),
    styles: await page.locator('link[href*="dlc-asset"]').evaluateAll(items => items.map(item => item.href)),
    cspNote: 'Electron installs CSP at its response-header boundary; separate controlled violation probe required' };
}
