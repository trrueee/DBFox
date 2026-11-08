async (page) => {
  const pendingRequest = page.waitForRequest(value => value.url().includes('/api/v1/projects'));
  await page.reload();
  const request = await pendingRequest;
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'GET') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }) });
    const body = await response.json();
    if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  const project = (await api('projects')).find(item => item.name === 'Shader Independent QA');
  const operation = (name, data) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${project.id}`, data, 'POST');
  const summary = (await operation('documents.list', {})).items.find(item => item.title === 'Closed Dock Driver Proof');
  const history = [];
  for (const version of [1, 2, 3]) history.push(await operation('documents.get', { document_id: summary.id, version }));
  const actions = [];
  for (const conversation of (await api('conversations')).filter(item => item.project_id === project.id)) {
    const detail = await api(`conversations/${conversation.id}`);
    for (const run of detail.runs) {
      const artifacts = await api(`conversations/${conversation.id}/runs/${run.id}/artifacts`);
      actions.push({ conversation, run, artifacts, items: detail.items });
    }
  }
  if (summary.version !== 3 || history[0].document.content_hash !== history[2].document.content_hash || actions.length !== 4) throw new Error('Unexpected durable sequence');
  const reportVersions = actions.flatMap(action => action.artifacts).filter(item => item.type === 'dbfox.shader.compile-report').map(item => item.payload.version).sort();
  if (reportVersions.join(',') !== '1,2,3,3') throw new Error('Missing exact driver reports');
  return { boundary: 'read-only public recovery after final evidence-selector failure; no action replay', projectId: project.id,
    summary, history, actions, shaderDockCount: await page.locator('.shader-studio').count(),
    userAgent: await page.evaluate(() => navigator.userAgent), styles: await page.locator('link[href*="dlc-asset"]').evaluateAll(items => items.map(item => item.href)) };
}
