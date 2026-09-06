async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'GET') => {
    const response = await page.context().request.fetch(base + path, { headers, method, ...(data === undefined ? {} : { data }) });
    const result = await response.json();
    if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(result)}`);
    await response.dispose(); return result;
  };
  const project = (await api('projects')).find(item => item.name === 'Shader Independent QA');
  const results = [];
  for (const conversation of (await api('conversations')).filter(item => item.project_id === project.id)) {
    const detail = await api(`conversations/${conversation.id}`);
    for (const run of detail.runs) {
      for (const artifact of await api(`conversations/${conversation.id}/runs/${run.id}/artifacts`)) {
        if (!['dbfox.shader.compile-report', 'dbfox.shader.preview'].includes(artifact.type)) continue;
        const report = artifact.type === 'dbfox.shader.compile-report';
        const representation = report ? 'dbfox.shader.compile-report.v1' : 'dbfox.shader.preview.v1';
        const value = await api(`artifacts/${artifact.id}/representations/${representation}/read`, {
          operation: report ? 'diagnostics' : 'metadata', parameters: report ? { offset: 0, limit: 20 } : {} }, 'POST');
        if (value.source_version !== String(artifact.payload.version) || value.source_fingerprint !== artifact.payload.content_hash || value.consistency !== 'durable_snapshot') throw new Error('Artifact did not remain pinned');
        results.push({ artifact, value });
      }
    }
  }
  if (!results.some(item => item.artifact.payload.version === 2 && item.value.payload.items?.some(diagnostic => diagnostic.line === 4 && diagnostic.severity === 'error'))) throw new Error('The real driver did not report the injected source location');
  return { projectId: project.id, reports: results };
}
