async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path) => { const response = await page.context().request.get(base + path, { headers }); const data = await response.json(); if (!response.ok()) throw new Error(path); await response.dispose(); return data; };
  const projects = await api('projects'); const conversations = await api('conversations'); const results = [];
  for (const name of ['Shader Native Agent Fixed QA', 'Shader Independent Stress QA', 'Shader Independent Large QA']) {
    const project = projects.find(item => item.name === name); const session = conversations.find(item => item.project_id === project.id);
    const conversation = await api(`conversations/${session.id}`); const artifacts = [];
    for (const run of conversation.runs) artifacts.push(...await api(`conversations/${session.id}/runs/${run.id}/artifacts`));
    const documents = artifacts.filter(item => item.type === 'dbfox.shader.document-revision');
    const artifact = name === 'Shader Native Agent Fixed QA' ? documents.find(item => item.payload.version === 1) : documents.at(-1);
    const pages = []; const started = Date.now();
    const read = async (parameters) => {
      const response = await page.context().request.post(base + `artifacts/${artifact.id}/representations/dbfox.shader.document.v1/read`, { headers, data: { operation: 'page', parameters } });
      const text = await response.text(); const envelope = JSON.parse(text); await response.dispose();
      if (!response.ok() || envelope.consistency !== 'durable_snapshot' || envelope.source_version !== String(artifact.payload.version) || envelope.source_fingerprint !== artifact.payload.content_hash) throw new Error('Fixed public representation failed');
      pages.push({ parameters, raw: text }); return envelope.payload;
    };
    await read({ section: 'summary' });
    const sections = {};
    for (const section of ['stages', 'passes', 'uniforms', 'textures']) {
      const items = []; let offset = 0;
      while (true) { const value = await read({ section, offset, limit: 50 }); items.push(...value.items); if (!value.has_more) break; if (value.next_offset <= offset) throw new Error('Nonadvancing public cursor'); offset = value.next_offset; }
      sections[section] = items;
    }
    for (const stage of sections.stages) {
      let offset = 0;
      while (true) { const value = await read({ section: 'source', stage_id: stage.id, offset, limit: 50 }); if (!value.has_more) break; if (value.next_offset <= offset) throw new Error('Nonadvancing source cursor'); offset = value.next_offset; }
    }
    for (const texture of sections.textures) {
      let offset = 0;
      while (true) { const value = await read({ section: 'texture_bytes', texture_id: texture.id, offset, limit: 16384 }); if (!value.has_more) break; if (value.next_offset <= offset) throw new Error('Nonadvancing texture cursor'); offset = value.next_offset; }
    }
    const preview = artifacts.filter(item => item.type === 'dbfox.shader.preview').at(-1);
    let png = null;
    if (preview) {
      const response = await page.context().request.post(base + `artifacts/${preview.id}/representations/dbfox.shader.preview-png.v1/stream`, { headers, data: { operation: 'export', parameters: {} } });
      if (!response.ok() || !response.headers()['content-type'].startsWith('image/png')) throw new Error('Public preview stream failed');
      png = { artifact: preview, bytes_base64: (await response.body()).toString('base64') }; await response.dispose();
    }
    results.push({ project, artifact, pages, png, elapsedMs: Date.now() - started });
  }
  return { boundary: 'Public fixed Artifact pages; raw JSON retained to preserve canonical numeric types for independent Python hash audit', results };
}
