async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const project = 'e4af3bd4-e29e-47f9-afd1-eb20160fb6c6'; const id = '9a4b43a7-ba94-43be-83f4-753912e2c120';
  const op = async (name, data) => {
    const response = await page.context().request.post(base + `dlcs/dbfox.shader/operations/${name}?project_id=${project}`, { headers, data });
    const body = await response.json(); if (!response.ok()) throw new Error(`${name}: ${JSON.stringify(body)}`); await response.dispose(); return body;
  };
  const before = await op('documents.head', { document_id: id });
  if (before.version !== 3 || before.deleted) throw new Error('Refuse to replay the historical delete scenario');
  await page.getByRole('button', { name: 'Shader Native Agent Fixed QA', exact: true }).click();
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: /Native Responses GPU repair/ }).click();
  const original = page.locator('.shader-artifact').filter({ hasText: 'IMMUTABLE · v1' });
  await original.getByRole('button', { name: 'Inspect immutable source', exact: true }).click();
  await original.getByRole('combobox', { name: 'Immutable shader stage', exact: true }).selectOption('6a40f6ef-4c1d-42a8-81e6-11003a22fee6');
  const v1Text = await original.getByRole('textbox', { name: 'GLSL source editor', exact: true }).innerText();
  if (v1Text.includes('BROKEN_TOKEN')) throw new Error('Historical v1 source was rebound to a later revision');
  await original.getByRole('button', { name: 'Download revision JSON', exact: true }).click();
  await page.waitForTimeout(400);
  await page.getByRole('treeitem', { name: /Native Agent Error Repair/ }).click();
  await page.locator('.shader-studio').getByRole('button', { name: 'History', exact: true }).click();
  const removing = page.waitForResponse(value => value.url().includes('/operations/documents.delete'));
  await page.getByRole('button', { name: 'Delete document (keep history)', exact: true }).click();
  const deleted = await (await removing).json();
  if (!deleted.document.deleted || deleted.document.version !== 4) throw new Error('Native history-preserving delete did not commit');
  // The old inline Artifact is still public and renders independently of the current head.
  await original.getByRole('button', { name: 'Download revision JSON', exact: true }).click();
  await page.waitForTimeout(400);
  const report = page.locator('.shader-artifact').filter({ hasText: 'IMMUTABLE · v2' }).filter({ has: page.getByRole('button', { name: 'Line 4', exact: true }) });
  await report.getByRole('button', { name: 'Line 4', exact: true }).click();
  const studio = page.locator('.shader-studio').filter({ hasText: 'Historical revision · read-only' });
  await studio.waitFor();
  const editor = studio.getByRole('textbox', { name: 'GLSL source editor', exact: true });
  const text = await editor.innerText();
  if (!text.includes('BROKEN_TOKEN')) throw new Error('Diagnostic navigation did not open the pinned failed source');
  if (await studio.getByRole('button', { name: 'Save source', exact: true }).isEnabled()) throw new Error('Historical source is writable');
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/historical-diagnostic-after-delete.png' });
  const metadata = await op('documents.get', { document_id: id, version: 1, section: 'summary' });
  return { before, deleted, v1Text, historicalV2Text: text, historicalSaveDisabled: true,
    historicalEditorEditable: await editor.getAttribute('contenteditable'), metadata, alerts: await page.getByRole('alert').allTextContents() };
}
