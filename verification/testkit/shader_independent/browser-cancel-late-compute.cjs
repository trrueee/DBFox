async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { headers, method, ...(data === undefined ? {} : { data }), timeout: 20000 });
    const body = await response.json(); if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(body)}`); await response.dispose(); return body;
  };
  const projects = await api('projects', undefined, 'GET');
  const project = projects.find(item => item.name === 'Shader Sampler QA');
  const scope = { kind: 'dbfox.shader.studio', id: project.id };
  const previous = await api('conversations', undefined, 'GET');
  if (previous.some(item => item.title === 'Independent late compute cancellation fixed')) throw new Error('Do not replay the cancellation Run');
  const conversation = await api('conversations', { project_id: project.id, title: 'Independent late compute cancellation fixed', resource_intents: [scope] });
  const sessionId = conversation.session.id;
  const enrolled = await api('credentials/batch', { credentials: [{ kind: 'llm_api_key', secret: 'independent-local-model-fixture' }] });
  let release; const waiting = new Promise(resolve => { release = resolve; }); let held = null; let settleHeld;
  const heldDone = new Promise(resolve => { settleHeld = resolve; }); const routeErrors = [];
  const completions = [];
  const completeListener = response => { if (response.url().includes('/operations/compute.complete')) completions.push(response.status()); };
  page.on('response', completeListener);
  const route = async route => {
    const response = await route.fetch(); const value = await response.json();
    const original = value.status === 'request' && !held;
    if (original) { held = value.request; await waiting; }
    try { await route.fulfill({ response }); } catch (error) { routeErrors.push(error.message); }
    finally { if (original) settleHeld(); }
  };
  await page.route('**/operations/compute.next**', route);
  try {
    const admitted = await api(`conversations/${sessionId}/inputs`, { content: 'Compile the current two-pass document once. This verification will cancel the original Run while its real compute request is in transit.',
      idempotency_key: await page.evaluate(() => crypto.randomUUID()), requested_resources: [scope], llm_credential_id: enrolled.credentials[0].id,
      api_base: 'http://127.0.0.1:19328/v1', model_name: 'shader-independent-cancel-fixed' });
    const started = Date.now();
    while (!held && Date.now() - started < 10000) await page.waitForTimeout(50);
    if (!held) throw new Error(`No original compute request was observed for ${admitted.run_id}`);
    const cancelled = await api(`runs/${admitted.run_id}/cancel`, {});
    let final;
    for (let count = 0; count < 100; count++) {
      final = await api(`conversations/${sessionId}`, undefined, 'GET');
      if (final.runs.find(item => item.id === admitted.run_id).status === 'cancelled') break;
      await page.waitForTimeout(100);
    }
    if (final.runs.find(item => item.id === admitted.run_id).status !== 'cancelled') throw new Error('Original Run did not reach cancellation');
    release(); await heldDone; await page.waitForTimeout(1500);
    const after = await api(`conversations/${sessionId}`, undefined, 'GET');
    const artifacts = await api(`conversations/${sessionId}/runs/${admitted.run_id}/artifacts`, undefined, 'GET');
    if (artifacts.length || after.runs.find(item => item.id === admitted.run_id).status !== 'cancelled') throw new Error('Late GPU work changed a terminal Run or published an Artifact');
    const compile = after.items.filter(item => item.type === 'function_call' && item.payload.call_id === 'cancel-compile');
    if (compile.length !== 1 || compile[0].payload.attempt !== 1) throw new Error('Original write was replayed');
    return { project, admitted, cancelled, after, artifacts, lateCompletionHttpStatuses: completions, routeErrors,
      originalCompute: { request_id: held.request_id, invocation_id: held.invocation_id, document_id: held.document_id, version: held.version, content_hash: held.content_hash },
      boundary: 'Held only the real compute.next HTTP response; cancelled the original production Agent Run; released the unchanged late response' };
  } finally {
    release(); if (held) await heldDone; await page.unroute('**/operations/compute.next**', route); page.off('response', completeListener);
    const response = await page.context().request.delete(base + `credentials/leases/${enrolled.lease_id}`, { headers });
    if (!response.ok()) throw new Error('Credential lease cleanup failed'); await response.dispose();
  }
}
