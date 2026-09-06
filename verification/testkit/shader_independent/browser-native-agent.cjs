async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const uuid = () => page.evaluate(() => crypto.randomUUID());
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }), timeout: 20000 });
    const body = await response.json();
    if (!response.ok()) throw new Error(`${path}: HTTP ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  if (await page.locator('.shader-studio').count()) throw new Error('Agent GPU proof starts with Dock closed');
  const projects = await api('projects', undefined, 'GET');
  const project = projects.find(item => item.name === 'Shader Native Agent Fixed QA') ?? await api('projects', { name: 'Shader Native Agent Fixed QA' });
  const scope = { kind: 'dbfox.shader.studio', id: project.id };
  const prior = (await api('conversations', undefined, 'GET')).find(item => item.project_id === project.id);
  const conversation = prior ? await api(`conversations/${prior.id}`, undefined, 'GET') : await api('conversations', { project_id: project.id, title: 'Native Responses GPU repair', resource_intents: [scope] });
  if (conversation.runs.length) throw new Error('An admitted Agent proof must be inspected, never replayed');
  const sessionId = conversation.session.id;
  const enrolled = await api('credentials/batch', { credentials: [{ kind: 'llm_api_key', secret: 'independent-local-model-fixture' }] });
  let admitted, final;
  try {
    admitted = await api(`conversations/${sessionId}/inputs`, {
      content: 'Create Native Agent Error Repair with the deliberately invalid BROKEN_TOKEN in its fragment source. Compile with the actual driver, inspect the returned report, repair only that token, compile again, render and export the exact repaired revision.',
      idempotency_key: await uuid(), requested_resources: [scope], llm_credential_id: enrolled.credentials[0].id,
      api_base: 'http://127.0.0.1:19328/v1', model_name: 'shader-independent-gpu-fixed' });
    const started = Date.now();
    while (Date.now() - started < 90000) {
      final = await api(`conversations/${sessionId}`, undefined, 'GET');
      const run = final.runs.find(item => item.id === admitted.run_id);
      if (run && !['queued', 'running', 'pending'].includes(run.status)) break;
      await page.waitForTimeout(500);
    }
    const artifacts = await api(`conversations/${sessionId}/runs/${admitted.run_id}/artifacts`, undefined, 'GET');
    return { boundary: 'same production Sidecar SessionCoordinator/RunLoop/OpenAI SDK; only loopback model Responses controlled',
      project, admitted, final, artifacts, shaderDockCount: await page.locator('.shader-studio').count(), elapsedMs: Date.now() - started };
  } finally {
    // No business preference is persisted. Revoke only this unconsumed enrollment lease.
    const response = await page.context().request.fetch(base + `credentials/leases/${enrolled.lease_id}`, { method: 'DELETE', headers });
    if (!response.ok()) throw new Error(`Independent credential cleanup failed: HTTP ${response.status()}`);
    await response.dispose();
  }
}
