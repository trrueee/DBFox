async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }), timeout: 30000 });
    const body = await response.json(); if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  const projects = await api('projects', undefined, 'GET');
  const project = projects.find(item => item.name === 'Shader Independent Large QA');
  if (!project) throw new Error('No original large workload exists');
  const sessions = await api('conversations', undefined, 'GET');
  const sessionId = sessions.find(item => item.project_id === project.id).id;
  const before = await api(`conversations/${sessionId}`, undefined, 'GET');
  const op = (name, data) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${project.id}`, data);
  const documents = await op('documents.list', {});
  const original = await op('documents.get', { document_id: documents.items[0].id, section: 'summary' });
  if (before.runs.length !== 1 || before.runs[0].status !== 'completed' || original.metadata.stage_count !== 59 || original.document.version !== 20) throw new Error('Original budget boundary changed; do not replay');
  const scope = { kind: 'dbfox.shader.studio', id: project.id };
  const enrolled = await api('credentials/batch', { credentials: [{ kind: 'llm_api_key', secret: 'independent-local-model-fixture' }] });
  try {
    const started = Date.now();
    const admitted = await api(`conversations/${sessionId}/inputs`, { content: 'Continue the remaining module_57 through module_59 batch only; the first 59 stages already exist. Complete fixed paging, source inspection, export and actual GPU compile/render without repeating any previous batch.',
      idempotency_key: await page.evaluate(() => crypto.randomUUID()), requested_resources: [scope], llm_credential_id: enrolled.credentials[0].id,
      api_base: 'http://127.0.0.1:19328/v1', model_name: 'shader-independent-large' });
    let final;
    while (Date.now() - started < 90000) {
      final = await api(`conversations/${sessionId}`, undefined, 'GET');
      const state = final.runs.find(item => item.id === admitted.run_id);
      if (state && !['queued', 'running', 'pending'].includes(state.status)) break;
      await page.waitForTimeout(350);
    }
    const state = final.runs.find(item => item.id === admitted.run_id);
    if (state.status !== 'completed') throw new Error(JSON.stringify(state));
    const artifacts = [];
    for (const run of final.runs) artifacts.push(...await api(`conversations/${sessionId}/runs/${run.id}/artifacts`, undefined, 'GET'));
    const preview = artifacts.filter(item => item.type === 'dbfox.shader.preview').at(-1);
    if (!preview) throw new Error('No actual preview after explicit continuation');
    const metadata = await api(`artifacts/${preview.id}/representations/dbfox.shader.preview.v1/read`, { operation: 'metadata', parameters: {} });
    const summary = await op('documents.get', { document_id: preview.payload.document_id, version: preview.payload.version, section: 'summary' });
    return { boundary: 'Original production turn budget retained; explicit subsequent user input continues only remaining batch', project, before, original, admitted, final, artifacts, metadata, summary, continuationMs: Date.now() - started };
  } finally {
    const response = await page.context().request.delete(base + `credentials/leases/${enrolled.lease_id}`, { headers });
    if (!response.ok()) throw new Error(`Credential cleanup failed ${response.status()}`);
    await response.dispose();
  }
}
