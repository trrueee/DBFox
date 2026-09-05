async (page) => {
  if (await page.getByRole('button', { name: '退出工作区全屏', exact: true }).count()) await page.getByRole('button', { name: '退出工作区全屏', exact: true }).click();
  // The older of the two real saved-snapshot Sessions owns the original v8.
  await page.getByRole('button', { name: /^保存体素快照 \d/ }).last().click();
  const reads = [], pending = [];
  const listener = response => { if (response.url().includes('/representations/')) pending.push(response.json().then(value => reads.push({ status: response.status(), operation: value.operation,
    version: value.source_version, fingerprint: value.source_fingerprint, chunkCount: value.payload?.chunks?.length }))); };
  page.on('response', listener);
  const cdp = await page.context().browser().newBrowserCDPSession();
  try {
    await page.getByRole('button', { name: '查看导出快照', exact: true }).click();
    await page.getByRole('button', { name: '工作区全屏', exact: true }).click();
    const download = page.getByRole('button', { name: '下载世界快照 JSON', exact: true });
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(button => button.textContent === '下载世界快照 JSON' && !button.disabled));
    await page.locator('.voxel-snapshot .voxel-viewport-status').filter({ hasText: '表面方块' }).waitFor();
    const title = await page.locator('.voxel-snapshot header').innerText();
    if (!title.includes('v8')) throw new Error(`Wrong historical fixture: ${title}`);
    await page.screenshot({ path: 'verification/bench/capabilities/dbfox_voxel/evidence/adversarial-historical.png' });
    await cdp.send('Browser.setDownloadBehavior', { behavior: 'default', eventsEnabled: true });
    const starts = [];
    cdp.on('Browser.downloadWillBegin', event => starts.push({ guid: event.guid, filename: event.suggestedFilename }));
    const completed = new Promise(resolve => cdp.on('Browser.downloadProgress', event => { if (event.state === 'completed' || event.state === 'canceled') resolve(event); }));
    await download.click();
    const native = await Promise.race([completed, page.waitForTimeout(20000).then(() => { throw new Error('Native download did not complete'); })]);
    await Promise.all(pending);
    if (native.state !== 'completed' || reads.some(read => read.version !== '8')) throw new Error('Historical version/download failure');
    return { title, reads, starts, native, editableSlices: await page.getByRole('application', { name: /体素切片/ }).count(), boundary: 'v8 Artifact re-read through new verified frontend while live world is v12; real native DownloadItem with verifier-controlled save path' };
  } finally { page.off('response', listener); await cdp.detach(); }
}
