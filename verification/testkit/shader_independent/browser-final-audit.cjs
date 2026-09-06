async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const fetch = async (path, data) => {
    const response = await page.context().request.post(base + path, { headers, data });
    const value = await response.json(); if (!response.ok()) throw new Error(`${path}: ${JSON.stringify(value)}`);
    await response.dispose(); return value;
  };
  // Recover the already completed cold ActionRun from public durable evidence.
  // This phase never calls documents.preview or any owner mutation again.
  const response = await page.context().request.get(base + 'conversations/b024c2bb-1fc7-412c-95b8-d9c13eb0cfe7', { headers });
  const conversation = await response.json(); await response.dispose();
  if (conversation.runs.length !== 1 || conversation.runs[0].status !== 'completed') throw new Error('Original cold ActionRun is not completed');
  const outputs = conversation.items.filter(item => item.type === 'function_call_output');
  if (outputs.length !== 1) throw new Error('Unexpected original ActionRun output count');
  const observation = JSON.parse(outputs[0].payload.output);
  if (observation.status !== 'succeeded' || !observation.facts.compiled || !observation.facts.rendered) throw new Error('Original cold driver outcome was not success');
  const published = { session_id: conversation.session.id, run_id: conversation.runs[0].id, artifact_ids: observation.artifact_ids, outcome: observation.facts };
  const close = page.getByRole('button', { name: '关闭 Aurora Study', exact: true });
  if (await close.isVisible()) await close.click();
  const tree = page.getByRole('treeitem', { name: 'Aurora Study', exact: true });
  if (!await tree.isVisible()) await page.getByRole('button', { name: 'Shader Independent Large QA', exact: true }).click();
  const reads = []; const observer = request => { if (request.method() === 'POST' && request.url().includes('/operations/documents.get')) reads.push(request.postDataJSON()); };
  page.on('request', observer); const started = Date.now(); await tree.click();
  const studio = page.locator('.shader-studio'); await studio.getByRole('tablist', { name: 'Shader stages', exact: true }).waitFor();
  const loadMs = Date.now() - started; page.off('request', observer);
  const stageCount = await studio.getByRole('tablist', { name: 'Shader stages', exact: true }).getByRole('tab').count();
  await studio.getByRole('button', { name: 'Uniforms', exact: true }).click();
  const uniformCount = await studio.getByRole('group', { name: 'Configured uniforms', exact: true }).getByLabel('Uniform name', { exact: true }).count();
  if (stageCount !== 62 || uniformCount !== 128) throw new Error('Current large document is incomplete');
  const snapshot = async (projectId, documentId, version, artifactId = null) => {
    const read = async parameters => artifactId ? (await fetch(`artifacts/${artifactId}/representations/dbfox.shader.document.v1/read`, { operation: 'page', parameters })).payload
      : fetch(`dlcs/dbfox.shader/operations/documents.get?project_id=${projectId}`, { document_id: documentId, version, ...parameters });
    const summary = await read({ section: 'summary' }); const pages = []; let offset = 0;
    do { const page = await read({ section: 'document_bytes', offset, limit: 16384 }); pages.push(page); if (!page.has_more) break; if (page.next_offset <= offset) throw new Error('Nonadvancing canonical byte page'); offset = page.next_offset; } while (true);
    const canonical = await page.evaluate(pages => btoa(pages.map(item => atob(item.document_bytes)).join('')), pages);
    const parsed = await page.evaluate(value => JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value), c => c.charCodeAt(0)))), canonical); const textures = [];
    for (const texture of parsed.document.textures) {
      const pieces = []; let offset = 0;
      do { const page = await read({ section: 'texture_bytes', texture_id: texture.id, offset, limit: 16384 }); pieces.push(page.texture_bytes.rgba_base64); if (!page.has_more) break; offset = page.next_offset; } while (true);
      textures.push({ content_hash: texture.content_hash, rgba_base64: await page.evaluate(pieces => btoa(pieces.map(value => atob(value)).join('')), pieces) });
    }
    return { projectId, documentId, version, artifactId, summary, canonical_base64: canonical, canonicalPageCount: pages.length, textures };
  };
  const snapshots = [await snapshot('e4af3bd4-e29e-47f9-afd1-eb20160fb6c6', '9a4b43a7-ba94-43be-83f4-753912e2c120', 1, 'artifact_cd67a13378744ae28c0b281e25c1897b')];
  snapshots.push(await snapshot('aabd2878-d186-4ceb-834c-f7c36a93510b', 'f000046a-cd02-4402-bb2d-333cfe6a4450', 12, 'artifact_1a7f2c5ad4164717a899d8a4abf863f6'));
  snapshots.push(await snapshot('126877c2-8713-4d83-b469-2b584a2cc15f', '60427616-04bb-480a-895f-182695fb2bed', 24));
  const previewId = published.artifact_ids.at(-1);
  const metadata = await fetch(`artifacts/${previewId}/representations/dbfox.shader.preview.v1/read`, { operation: 'metadata', parameters: {} });
  const png = await page.context().request.post(base + `artifacts/${previewId}/representations/dbfox.shader.preview-png.v1/stream`, { headers, data: { operation: 'export', parameters: {} } });
  if (!png.ok()) throw new Error('Cold public PNG stream failed');
  const pngBase64 = (await png.body()).toString('base64'); await png.dispose();
  return { candidate: '8a412cdb', recoveredAfterFixtureBufferError: true, conversation, loadMs, nativeReadSections: reads.map(item => item?.section ?? 'request-body-unavailable'), stageCount, uniformCount, published, snapshots, metadata, png_base64: pngBase64 };
}
