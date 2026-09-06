async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, expected = 200) => {
    const response = await page.context().request.post(base + path, { headers, data, timeout: 30000 });
    const body = await response.json(); if (response.status() !== expected) throw new Error(`${path}: ${response.status()} ${JSON.stringify(body)}`); await response.dispose(); return body;
  };
  const listing = await page.context().request.get(base + 'projects', { headers }); const projects = await listing.json(); await listing.dispose();
  const project = projects.find(item => item.name === 'Shader Independent Large QA');
  const id = '60427616-04bb-480a-895f-182695fb2bed';
  const op = (name, data, expected) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${project.id}`, data, expected);
  const uuid = () => page.evaluate(() => crypto.randomUUID());
  const before = await op('documents.get', { document_id: id, section: 'summary' });
  if (!((before.document.version === 21 && before.metadata.uniform_count === 0) || (before.document.version === 24 && before.metadata.uniform_count === 128))) throw new Error('Refuse to replay maximum uniforms');
  const stages = await op('documents.get', { document_id: id, version: 21, section: 'stages', limit: 50 });
  const fragment = stages.items.find(item => item.kind === 'fragment'); const pass = before.metadata.preview.pass_id;
  const names = Array.from({ length: 128 }, (_, index) => 'gain' + String(index).padStart(3, '0'));
  const source = '#version 300 es\nprecision highp float;\n' + names.map(name => 'uniform float ' + name + ';').join('\n') + '\nout vec4 color;\nvoid main(){float gain=(' + names.join('+') + ')/128.0; color=vec4(gain,0.0,0.0,1.0);}\n';
  const operations = names.map((name, index) => ({ kind: 'uniform_create', pass_id: { id: pass }, name, type: 'float', value: index / 127 }));
  operations.push({ kind: 'stage_replace', stage_id: { id: fragment.id }, source });
  const changed = []; let version = before.document.version;
  for (let offset = 0; before.document.version === 21 && offset < operations.length; offset += 64) {
    const result = await op('documents.apply', { document_id: id, expected_version: version, request_id: await uuid(), operations: operations.slice(offset, offset + 64) });
    changed.push(result); version = result.document.version;
  }
  if (before.document.version === 24) {
    let currentSource = ''; let offset = 0;
    while (true) { const value = await op('documents.get', { document_id: id, version, section: 'source', stage_id: fragment.id, offset, limit: 50 }); currentSource += value.source; if (!value.has_more) break; offset = value.next_offset; }
    if (currentSource !== source) throw new Error('Already committed source differs; do not replay');
  }
  const rejected = await op('documents.apply', { document_id: id, expected_version: version, request_id: await uuid(), operations: [{ kind: 'uniform_create', name: 'overflow', pass_id: { id: pass }, type: 'float', value: 1 }] }, 400);
  const head = await op('documents.head', { document_id: id }); if (head.version !== version) throw new Error('Overquota write changed the revision');
  const started = Date.now();
  const compiled = await op('documents.compile', { document_id: id, expected_version: version, request_id: await uuid() });
  const rendered = await op('documents.preview', { document_id: id, expected_version: version, request_id: await uuid() });
  if (!compiled.outcome.compiled || !rendered.outcome.rendered) throw new Error('The actual driver did not accept all 128 active floats');
  const sample = await api(`artifacts/${rendered.artifact_ids.at(-1)}/representations/dbfox.shader.preview.v1/read`, { operation: 'sample', parameters: { width: 32, height: 32 } });
  return { before, changed, rejected, head, compiled, rendered, sample, gpuActionsMs: Date.now() - started, activeUniformCount: 128, generatedSource: source };
}
