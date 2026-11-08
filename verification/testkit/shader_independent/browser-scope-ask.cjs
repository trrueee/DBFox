async (page) => {
  const request = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const studio = page.locator('.shader-studio');
  const sourceTree = page.getByRole('treeitem', { name: 'Closed Dock Driver Proof', exact: true });
  if (!await sourceTree.isVisible()) await page.getByRole('button', { name: 'Shader Independent QA', exact: true }).click();
  await sourceTree.waitFor();
  if (!await studio.count()) {
    await sourceTree.click();
  }
  await studio.getByRole('tab', { name: 'FS · Gradient', exact: true }).click();
  const editor = studio.getByRole('textbox', { name: 'GLSL source editor', exact: true });
  await editor.click(); await editor.press('Control+Home');
  await editor.press('ArrowDown'); await editor.press('ArrowDown');
  await editor.press('Shift+ArrowDown'); await editor.press('Shift+ArrowDown');
  await studio.getByText('Lines 3–5', { exact: true }).waitFor();
  await studio.getByRole('button', { name: 'Ask about selected lines', exact: true }).click();
  const references = page.getByLabel('当前上下文', { exact: true });
  await references.getByText('Gradient · v4', { exact: true }).waitFor();
  const asked = await references.textContent();
  if (!asked.includes('dbfox.shader.stage')) throw new Error('Selected-line Ask did not create a stage reference chip');
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/native-selected-lines-ask.png' });
  await page.getByRole('button', { name: '关闭 Closed Dock Driver Proof', exact: true }).click();
  let held = false; let released = false; let release; let finish;
  const wait = new Promise(resolve => { release = resolve; });
  const done = new Promise(resolve => { finish = resolve; });
  const routeErrors = []; const targetId = '66cd4b63-0b4b-4e47-9640-d13f678a0a35';
  const handler = async route => {
    const input = route.request().postDataJSON();
    if (held || input.document_id !== targetId || input.section !== 'source') { await route.continue(); return; }
    const response = await route.fetch(); held = true;
    try { await wait; await route.fulfill({ response }); released = true; }
    catch (error) { routeErrors.push(error.message); }
    finally { finish(); }
  };
  await page.route('**/operations/documents.get**', handler);
  try {
    await sourceTree.click();
    const start = Date.now(); while (!held && Date.now() - start < 10000) await page.waitForTimeout(25);
    if (!held) throw new Error('No real source response held');
    await page.getByRole('button', { name: 'Shader Sampler QA', exact: true }).click();
    await page.waitForTimeout(200);
    const session = page.getByRole('navigation', { name: '主导航', exact: true }).getByRole('button', { name: /^Independent late compute cancellation \d/ });
    if (!await session.isVisible()) await page.getByRole('button', { name: 'Shader Sampler QA', exact: true }).click();
    await session.click();
    release(); await done; await page.waitForTimeout(600);
    if (await page.locator('.shader-studio').count() || await page.getByLabel('当前上下文', { exact: true }).count()) throw new Error('Old project response or reference leaked into a new Session');
    const text = await page.locator('main').innerText();
    if (!text.includes('Independent late compute cancellation')) throw new Error('Target Session is not selected');
    await page.screenshot({ path: 'docs/quality/evidence/shader-independent/late-project-session-source.png' });
    const times = []; let bytes = 0;
    for (let i = 0; i < 600; i++) {
      const start = Date.now(); const response = await page.context().request.get(base + 'projects', { headers, timeout: 10000 });
      if (!response.ok()) throw new Error(`Sustained production HTTP failed at ${i}`);
      bytes += (await response.body()).length; times.push(Date.now() - start); await response.dispose();
    }
    const sorted = [...times].sort((a, b) => a - b);
    return { asked, nativeSelection: { from: 3, to: 5, dirty: false }, originalDocumentId: targetId,
      heldRealSource: held, released, routeErrors, oldStudioCount: await studio.count(), staleReferenceCount: await page.getByLabel('当前上下文', { exact: true }).count(),
      sustainedHttp: { count: times.length, responseBytes: bytes, elapsedMs: times.reduce((a, b) => a + b, 0), maxMs: sorted.at(-1), p95Ms: sorted[Math.floor(sorted.length * .95)] } };
  } finally { release(); if (held) await done; await page.unroute('**/operations/documents.get**', handler); }
}
