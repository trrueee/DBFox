async (page) => {
  const request = await page.waitForRequest((value) => value.url().includes('/operations/playtest.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }), timeout: 30000 });
    const body = response.status() === 204 ? null : await response.json();
    if (!response.ok()) throw new Error(`${path}: HTTP ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  const projects = await api('projects', undefined, 'GET');
  if (projects.some((item) => item.name === 'Game Native Agent QA')) throw new Error('Inspect the existing admitted Run instead of replaying this creation phase');
  if (await page.getByRole('button', { name: '关闭 Game Studio', exact: true }).count()) await page.getByRole('button', { name: '关闭 Game Studio', exact: true }).click();
  if (await page.locator('.game-studio').count()) throw new Error('Agent executor proof requires Studio closed');
  const project = await api('projects', { name: 'Game Native Agent QA' });
  const scope = { kind: 'dbfox.game.library', id: project.id };
  const conversation = await api('conversations', { project_id: project.id, title: 'Native fox survival design and playtest', resource_intents: [scope] });
  const sessionId = conversation.session.id;
  const enrolled = await api('credentials/batch', { credentials: [{ kind: 'llm_api_key', secret: 'game-local-model-verification' }] });
  try {
    const admitted = await api(`conversations/${sessionId}/inputs`, {
      content: 'Create a fox evading spawned slimes with a sixty-second win rule. Run a real stationary playtest, observe the loss, adjust only the health component, then run the recorded movement route and export the exact winning version.',
      idempotency_key: await page.evaluate(() => crypto.randomUUID()), requested_resources: [scope], llm_credential_id: enrolled.credentials[0].id,
      api_base: 'http://127.0.0.1:19330/v1', model_name: 'game-author-native',
    });
    let final;
    const start = Date.now();
    while (Date.now() - start < 90000) {
      final = await api(`conversations/${sessionId}`, undefined, 'GET');
      const run = final.runs.find((item) => item.id === admitted.run_id);
      if (run && !['queued', 'running', 'pending'].includes(run.status)) break;
      await page.waitForTimeout(500);
    }
    const artifacts = await api(`conversations/${sessionId}/runs/${admitted.run_id}/artifacts`, undefined, 'GET');
    const result = { project, admitted, final, artifacts, studioCount: await page.locator('.game-studio').count(), elapsedMs: Date.now() - start, boundary: 'production Electron/Main/Preload/Sidecar/OpenAI SDK with only loopback model Responses controlled' };
    await page.evaluate((evidence) => { window.gameNativeEvidence = evidence; }, result);
    return result;
  } finally {
    await api(`credentials/leases/${enrolled.lease_id}`, undefined, 'DELETE');
  }
}
