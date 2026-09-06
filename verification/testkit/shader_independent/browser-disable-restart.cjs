async (page) => {
  const styles = () => page.locator('link').evaluateAll(items => items.filter(item => item.href.startsWith('dlc-asset:') && item.href.includes('/frontend/studio.css')).map(item => item.href));
  const before = { text: await page.locator('body').innerText(), styles: await styles() };
  if (!before.text.includes('等待重启停用') || before.styles.length !== 1) throw new Error('Expected the explicitly disabled desired state with old active runtime');
  await page.getByRole('button', { name: '立即重启', exact: true }).first().click();
  await page.getByText('等待重启停用', { exact: true }).waitFor({ state: 'hidden' });
  await page.waitForFunction(() => !Array.from(document.querySelectorAll('link')).some(item => item.href.startsWith('dlc-asset:') && item.href.includes('/frontend/studio.css')));
  const disabled = { text: await page.locator('body').innerText(), styles: await styles(), studios: await page.locator('.shader-studio').count(), artifacts: await page.locator('.shader-artifact').count() };
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/native-disabled-restart.png' });
  await page.getByRole('button', { name: '启用', exact: true }).click();
  await page.getByRole('button', { name: '立即重启', exact: true }).first().waitFor();
  await page.getByRole('button', { name: '立即重启', exact: true }).first().click();
  await page.getByText('当前已激活', { exact: true }).waitFor();
  const observed = await page.waitForRequest(value => value.url().includes('/operations/compute.next'));
  const headers = await observed.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = observed.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'GET') => {
    const response = await page.context().request.fetch(base + path, { headers, method, ...(data === undefined ? {} : { data }) });
    const body = await response.json(); if (!response.ok()) throw new Error(path); await response.dispose(); return body;
  };
  const projects = await api('projects'); const project = projects.find(item => item.name === 'Shader Independent Large QA');
  const largeHead = await api(`dlcs/dbfox.shader/operations/documents.head?project_id=${project.id}`, { document_id: '60427616-04bb-480a-895f-182695fb2bed' }, 'POST');
  if (largeHead.version !== 24 || largeHead.deleted) throw new Error('Restart lost committed large document');
  const sessions = await api('conversations'); const session = sessions.find(item => item.title === 'Independent late compute cancellation fixed');
  const cancelled = await api(`conversations/${session.id}`);
  if (cancelled.runs[0].status !== 'cancelled') throw new Error('Restart reopened a cancelled Run');
  const enabled = { text: await page.locator('body').innerText(), styles: await styles() };
  if (enabled.styles.length !== 1) throw new Error('Reactivation did not register exactly one stylesheet');
  return { before, disabled, enabled, largeHead, cancelled };
}
