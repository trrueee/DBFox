async (page) => {
  if (await page.getByRole('button', { name: '工作区全屏', exact: true }).count()) await page.getByRole('button', { name: '工作区全屏', exact: true }).click();
  await page.getByRole('tab', { name: 'FS · Gradient', exact: true }).click();
  const request = await page.waitForRequest(value => value.url().includes('/operations/documents.head'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const projectId = 'e3aa3b31-2e14-4b4b-8961-0e03021fc3ea';
  const id = '66cd4b63-0b4b-4e47-9640-d13f678a0a35';
  const api = async (path, data) => {
    const response = await page.context().request.post(base + path, { headers, data, timeout: 20000 });
    const result = await response.json();
    if (!response.ok()) throw new Error(`${path}: ${response.status()} ${JSON.stringify(result)}`);
    await response.dispose(); return result;
  };
  const operation = (name, data) => api(`dlcs/dbfox.shader/operations/${name}?project_id=${projectId}`, data);
  const initial = await operation('documents.get', { document_id: id, section: 'stages', version: 3 });
  const fragment = initial.items.find(item => item.kind === 'fragment');
  const read = (version) => operation('documents.get', { document_id: id, stage_id: fragment.id, section: 'source', version, limit: 50 });
  const before = await read(3);
  const head = await operation('documents.head', { document_id: id });
  if (![3, 4].includes(head.version)) throw new Error('Do not replay the native edit');
  const marker = '\n// independent native CodeMirror edit\n';
  let saved = null;
  if (head.version === 3) {
    const editor = page.getByRole('textbox', { name: 'GLSL source editor', exact: true });
    await editor.click(); await editor.press('Control+End');
    await page.keyboard.insertText(marker);
    await page.getByText('1 unsaved stage', { exact: true }).waitFor();
    const responsePromise = page.waitForResponse(value => value.url().includes('/operations/documents.apply'));
    await editor.press('Control+s');
    const savedResponse = await responsePromise;
    saved = await savedResponse.json();
    if (savedResponse.status() !== 200 || saved.document.version !== 4) throw new Error('Native keyboard Save failed');
    await page.getByText('Saved revision v4.', { exact: true }).waitFor();
  }
  const after = await read(4);
  // The native contenteditable insertion uses the existing terminal line break.
  if (after.source !== before.source.slice(0, -1) + marker) throw new Error('Native editor changed unrequested source');
  const metadata = await operation('documents.get', { document_id: id, section: 'stages', version: 4 });
  const vertex = initial.items.find(item => item.kind === 'vertex');
  if (JSON.stringify(metadata.items.find(item => item.id === vertex.id)) !== JSON.stringify(vertex)) throw new Error('Native fragment edit changed the vertex stage');
  await page.getByRole('button', { name: 'Preview locally', exact: true }).click();
  await page.getByText('Revision v4 · actual WebGL pixels', { exact: true }).waitFor();
  await page.screenshot({ path: 'output/playwright/shader-independent-native-edit.png' });
  const publishResponse = page.waitForResponse(value => value.url().includes('/operations/documents.preview'));
  await page.getByRole('button', { name: 'Render & publish', exact: true }).click();
  const actionResponse = await publishResponse;
  const published = await actionResponse.json();
  if (actionResponse.status() !== 200 || !published.outcome.rendered || published.outcome.document.version !== 4) throw new Error('Native publication did not render this revision');
  await page.getByRole('img', { name: 'Immutable preview at revision 4, 256 by 256', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Download PNG', exact: true }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'output/playwright/shader-independent-native-published.png' });
  return { boundary: 'real native CodeMirror keyboard insertion and Mod-S; actual local WebGL; formal ActionRun; actual Artifact navigation and native download',
    before, saved, after, recoveredAlreadyCommittedEdit: saved === null, vertexUnchanged: true, published, alerts: await page.getByRole('alert').allTextContents() };
}
