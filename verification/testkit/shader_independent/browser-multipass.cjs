async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const uuid = () => page.evaluate(() => crypto.randomUUID());
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { headers, method, ...(data === undefined ? {} : { data }), timeout: 20000 });
    const result = await response.json();
    if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(result)}`);
    await response.dispose(); return result;
  };
  const projects = await api('projects', undefined, 'GET');
  if (projects.some(item => item.name === 'Shader Sampler QA')) throw new Error('Do not replay this exact sampler experiment');
  const project = await api('projects', { name: 'Shader Sampler QA' });
  const operation = (name, data) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${project.id}`, data);
  const created = await operation('documents.create', { title: 'Two Pass Corner Orientation', expected_generation: 0, request_id: await uuid() });
  const ref = created.created_refs;
  const rgba = [255,0,0,255, 0,255,0,255, 0,0,255,255, 255,255,0,255];
  const base64 = await page.evaluate(bytes => btoa(String.fromCharCode(...bytes)), rgba);
  const source = '#version 300 es\nprecision highp float;\nuniform vec2 u_resolution;\nuniform sampler2D u_tex;\nout vec4 color;\nvoid main(){color=texture(u_tex,gl_FragCoord.xy/u_resolution);}\n';
  const modified = await operation('documents.apply', { document_id: created.document.id, expected_version: 1, request_id: await uuid(), operations: [
    { kind: 'stage_replace', stage_id: { id: ref.fragment }, source },
    { kind: 'texture_create', ref: 'corners', title: 'Top-left red, green / blue, yellow', width: 2, height: 2, rgba_base64: base64 },
    { kind: 'pass_update', pass_id: { id: ref.pass }, width: 2, height: 2 },
    { kind: 'binding_set', pass_id: { id: ref.pass }, name: 'u_tex', source: { kind: 'texture', texture_id: { ref: 'corners' } }, filter: 'nearest', wrap: 'clamp' },
    { kind: 'pass_create', ref: 'second', title: 'Second immutable pass', vertex_stage_id: { id: ref.vertex }, fragment_stage_id: { id: ref.fragment }, width: 2, height: 2, clear_color: [0,0,0,0], bindings: [{ name: 'u_tex', source: { kind: 'pass', pass_id: { id: ref.pass } }, filter: 'nearest', wrap: 'clamp' }] },
    { kind: 'preview_set', pass_id: { ref: 'second' }, width: 2, height: 2, time_seconds: 0 },
  ] });
  const started = Date.now();
  const rendered = await operation('documents.preview', { document_id: created.document.id, expected_version: 2, request_id: await uuid() });
  const elapsedMs = Date.now() - started;
  if (!rendered.outcome.compiled || !rendered.outcome.rendered) throw new Error('Actual multipass rendering failed');
  const artifactId = rendered.artifact_ids.at(-1);
  const sample = await api(`artifacts/${artifactId}/representations/dbfox.shader.preview.v1/read`, { operation: 'sample', parameters: { width: 2, height: 2 } });
  if (JSON.stringify(sample.payload.rgba) !== JSON.stringify(rgba) || sample.payload.row_order !== 'top-left') throw new Error('Texture or pass orientation changed the exact four corners');
  const stream = await page.context().request.post(base + `artifacts/${artifactId}/representations/dbfox.shader.preview-png.v1/stream`, { headers, data: { operation: 'export', parameters: {} } });
  if (!stream.ok() || !stream.headers()['content-type'].startsWith('image/png')) throw new Error('Public PNG stream failed');
  const png = Array.from(await stream.body()); await stream.dispose();
  return { boundary: 'actual WebGL texture upload/first FBO/second pass sampling/readPixels; public immutable sample and PNG stream', project, created, modified, rendered, elapsedMs, sample, pngBytes: png };
}
