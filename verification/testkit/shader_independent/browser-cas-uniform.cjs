async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const projectId = 'e3aa3b31-2e14-4b4b-8961-0e03021fc3ea';
  const uuid = () => page.evaluate(() => crypto.randomUUID());
  const op = async (name, data, expected = 200) => {
    const response = await page.context().request.post(base + `dlcs/dbfox.shader/operations/${name}?project_id=${projectId}`, { headers, data });
    const body = await response.json(); if (response.status() !== expected) throw new Error(`${name}: ${response.status()} ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  const inventory = await op('documents.list', {});
  if (inventory.items.some(item => item.title === 'Independent CAS and Uniforms')) throw new Error('Do not replay this admitted native scenario');
  await page.getByRole('textbox', { name: 'New document title', exact: true }).fill('Independent CAS and Uniforms');
  const creation = page.waitForResponse(value => value.url().includes('/operations/documents.create'));
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  const created = await (await creation).json(); const id = created.document.id;
  await page.getByRole('tab', { name: 'FS · Gradient', exact: true }).click();
  const editor = page.getByRole('textbox', { name: 'GLSL source editor', exact: true });
  const draft = '#version 300 es\nprecision highp float;\nuniform float gain;\nout vec4 color;\nvoid main(){ color=vec4(gain,0.0,0.0,1.0); }\n// retained native draft';
  await editor.click(); await editor.press('Control+a'); await page.keyboard.insertText(draft);
  await page.getByText('1 unsaved stage', { exact: true }).waitFor();
  const before = await op('documents.get', { document_id: id, version: 1, section: 'source', stage_id: created.created_refs.fragment });
  const external = await op('documents.apply', { document_id: id, expected_version: 1, request_id: await uuid(), operations: [
    { kind: 'stage_replace', stage_id: { id: created.created_refs.fragment }, source: before.source + '\n// actual external revision\n' }
  ] });
  await page.getByText('The document is now v2. Your draft is preserved on v1.', { exact: true }).waitFor();
  if (await page.getByRole('button', { name: 'Save source', exact: true }).isEnabled()) throw new Error('An observed stale draft remained writable');
  if (!(await editor.innerText()).includes('retained native draft')) throw new Error('External edit destroyed a local draft');
  const stale = await op('documents.apply', { document_id: id, expected_version: 1, request_id: await uuid(), operations: [
    { kind: 'rename_document', title: 'STALE MUST NOT APPLY' }
  ] }, 409);
  await page.getByRole('button', { name: 'Inspect latest & rebase', exact: true }).click();
  await page.getByRole('heading', { name: 'Resolve source conflicts', exact: true }).waitFor();
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/cas-conflict.png' });
  if ((await op('documents.head', { document_id: id })).version !== 2) throw new Error('Inspect/rebase silently committed a draft');
  await page.getByRole('button', { name: 'Keep my drafts on this reviewed revision', exact: true }).click();
  const saving = page.waitForResponse(value => value.url().includes('/operations/documents.apply'));
  await page.getByRole('button', { name: 'Save source', exact: true }).click();
  const saved = await (await saving).json();
  await page.getByText('Saved revision v3.', { exact: true }).waitFor();
  const source = await op('documents.get', { document_id: id, version: 3, section: 'source', stage_id: created.created_refs.fragment });
  if (source.source !== draft) throw new Error('Reviewed native draft source is not exact');
  await page.getByRole('button', { name: 'Uniforms', exact: true }).click();
  const add = page.getByRole('group', { name: 'Add a typed value', exact: true });
  await add.getByLabel('Uniform name', { exact: true }).fill('gain');
  await add.getByLabel('Value', { exact: true }).fill('0.25');
  const addition = page.waitForResponse(value => value.url().includes('/operations/documents.apply'));
  await add.getByRole('button', { name: 'Add uniform', exact: true }).click();
  const uniformAdded = await (await addition).json();
  await page.getByText('Saved revision v4.', { exact: true }).waitFor();
  const configured = page.getByRole('group', { name: 'Configured uniforms', exact: true });
  await configured.getByLabel('Value', { exact: true }).fill('0.75');
  const updating = page.waitForResponse(value => value.url().includes('/operations/documents.apply'));
  await configured.getByRole('button', { name: 'Save uniform', exact: true }).click();
  const uniformUpdated = await (await updating).json();
  await page.getByText('Saved revision v5.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Preview locally', exact: true }).click();
  await page.getByText('Revision v5 · actual WebGL pixels', { exact: true }).waitFor();
  const pixels = await page.getByRole('img', { name: 'Local WebGL preview, 256 by 256 pixels', exact: true }).evaluate(canvas => {
    const rgba = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set(); for (let i = 0; i < rgba.length; i += 4) colors.add(Array.from(rgba.slice(i, i + 4)).join(','));
    return { width: canvas.width, height: canvas.height, colors: [...colors] };
  });
  if (pixels.colors.length !== 1 || !['191,0,0,255', '192,0,0,255'].includes(pixels.colors[0])) throw new Error(JSON.stringify(pixels));
  const uniforms = await op('documents.get', { document_id: id, version: 5, section: 'uniforms' });
  const untouchedVertex1 = await op('documents.get', { document_id: id, version: 1, section: 'source', stage_id: created.created_refs.vertex });
  const untouchedVertex5 = await op('documents.get', { document_id: id, version: 5, section: 'source', stage_id: created.created_refs.vertex });
  if (untouchedVertex1.source !== untouchedVertex5.source || uniforms.items.length !== 1 || uniforms.items[0].value !== 0.75) throw new Error('Source locality or typed uniform identity failed');
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/uniform-native-preview.png' });
  return { created, external, stale, saved, source, uniformAdded, uniformUpdated, uniforms, pixels, vertexUnchanged: true };
}
