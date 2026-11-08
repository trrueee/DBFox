async (page) => {
  const scenario = 'stress';
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const uuid = () => page.evaluate(() => crypto.randomUUID());
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }), timeout: 30000 });
    const body = await response.json(); if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  const title = scenario === 'stress' ? 'Shader Independent Stress QA' : 'Shader Independent Large QA';
  const projects = await api('projects', undefined, 'GET');
  if (projects.some(item => item.name === title)) throw new Error('Refuse to replay an admitted independent workload');
  const project = await api('projects', { name: title });
  const scope = { kind: 'dbfox.shader.studio', id: project.id };
  const conversation = await api('conversations', { project_id: project.id, title, resource_intents: [scope] });
  const sessionId = conversation.session.id;
  const enrolled = await api('credentials/batch', { credentials: [{ kind: 'llm_api_key', secret: 'independent-local-model-fixture' }] });
  const runs = []; const timings = [];
  let human = null;
  const op = (name, data) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${project.id}`, data);
  async function run(content) {
    const admitted = await api(`conversations/${sessionId}/inputs`, { content, idempotency_key: await uuid(), requested_resources: [scope],
      llm_credential_id: enrolled.credentials[0].id, api_base: 'http://127.0.0.1:19328/v1', model_name: 'shader-independent-' + scenario });
    const started = Date.now(); let final;
    while (Date.now() - started < 180000) {
      final = await api(`conversations/${sessionId}`, undefined, 'GET');
      const state = final.runs.find(item => item.id === admitted.run_id);
      if (state && !['queued', 'running', 'pending'].includes(state.status)) break;
      await page.waitForTimeout(350);
    }
    const state = final.runs.find(item => item.id === admitted.run_id);
    runs.push({ admitted, state }); timings.push(Date.now() - started);
    if (state?.status !== 'completed') throw new Error(`Original Run ${admitted.run_id} did not complete: ${JSON.stringify(state)}`);
    return final;
  }
  try {
    let final = await run(scenario === 'stress'
      ? 'Execute the complete Coral Plasma editing workload: procedural source, texture and uniform, scratch deletion, local patch, two-pass restructure, parameter change, actual compile/preview. Ask what softer means before the next edit.'
      : 'Create the complete large editable document with 62 stages and exact module sources in bounded batches. Inspect every stage page and source, export, then actually compile and render the exact final revision.');
    if (scenario === 'stress') {
      if (!runs[0].state.result.answer.text.includes('请明确')) throw new Error('The requested ambiguity did not produce a separate clarification');
      final = await run('Clarification: name the post pass Soft Post. Pause after committing so I can rename the document in the native Studio.');
      const calls = final.items.filter(item => item.type === 'function_call_output');
      const create = JSON.parse(calls.find(item => item.payload.call_id === 'create').payload.output).facts;
      await page.reload();
      await page.getByRole('button', { name: title, exact: true }).click();
      await page.getByRole('treeitem', { name: /Coral Plasma/ }).click();
      await page.getByRole('button', { name: 'History', exact: true }).click();
      await page.getByRole('textbox', { name: 'Document title', exact: true }).fill('Human preserved');
      const changed = page.waitForResponse(value => value.url().includes('/operations/documents.apply'));
      await page.getByRole('button', { name: 'Rename', exact: true }).click();
      human = await (await changed).json();
      if (human.document.title !== 'Human preserved' || human.document.id !== create.document.id) throw new Error('Native human title edit was not committed');
      await page.screenshot({ path: 'docs/quality/evidence/shader-independent/stress-human-edit.png' });
      final = await run('I renamed the document to Human preserved. Test that the stale version cannot overwrite it, inspect the current revision, bind the texture, undo only that binding, refine the final preview and explicitly rename it Coral Plasma · final, then compile and render the real two-pass output.');
    }
    const artifacts = [];
    for (const run of runs) artifacts.push(...await api(`conversations/${sessionId}/runs/${run.admitted.run_id}/artifacts`, undefined, 'GET'));
    const preview = artifacts.filter(item => item.type === 'dbfox.shader.preview').at(-1);
    if (!preview) throw new Error('No actual immutable preview Artifact was produced');
    const metadata = await api(`artifacts/${preview.id}/representations/dbfox.shader.preview.v1/read`, { operation: 'metadata', parameters: {} });
    const sample = await api(`artifacts/${preview.id}/representations/dbfox.shader.preview.v1/read`, { operation: 'sample', parameters: { width: 16, height: 16 } });
    const summary = await op('documents.get', { document_id: preview.payload.document_id, version: preview.payload.version, section: 'summary' });
    return { scenario, project, runs, timings, final, artifacts, human, metadata, sample, summary };
  } finally {
    const response = await page.context().request.delete(base + `credentials/leases/${enrolled.lease_id}`, { headers });
    if (!response.ok()) throw new Error(`Credential cleanup failed ${response.status()}`);
    await response.dispose();
  }
}
