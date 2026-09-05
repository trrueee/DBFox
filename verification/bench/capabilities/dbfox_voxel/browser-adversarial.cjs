async (page) => {
  const result = { boundary: 'real signed Electron/EngineSupervisor; read-only HTTP replay copies an observed management read, never prints credentials' };
  await page.reload();
  await page.getByRole('treeitem', { name: 'Interactive Voxel', exact: true }).waitFor();
  if (await page.getByRole('button', { name: '退出工作区全屏', exact: true }).count()) await page.getByRole('button', { name: '退出工作区全屏', exact: true }).click();
  const leaf = page.getByRole('treeitem', { name: 'Interactive Voxel', exact: true });
  await leaf.click();
  await page.locator('.voxel-viewport-status').filter({ hasText: '表面方块' }).waitFor();
  const before = await page.locator('.voxel-header').innerText();
  await page.getByRole('button', { name: '关闭 Interactive Voxel', exact: true }).click();
  if (await page.locator('.voxel-studio').count()) throw new Error('Closed view remained mounted');
  // Do not clear the selection or reload: this is the original shared Host repro.
  const selectedAfterClose = await leaf.getAttribute('aria-selected');
  await leaf.click();
  await page.locator('.voxel-viewport-status').filter({ hasText: '表面方块' }).waitFor();
  result.treeReopen = { selectedAfterClose, before, after: await page.locator('.voxel-header').innerText() };
  if (result.treeReopen.after !== before || selectedAfterClose !== 'true') throw new Error(JSON.stringify(result.treeReopen));
  const responsePromise = page.waitForResponse(response => response.url().includes('/operations/worlds.get'));
  await page.getByRole('button', { name: '刷新', exact: true }).click();
  const observedResponse = await responsePromise;
  const baselineWorld = await observedResponse.json();
  const observed = observedResponse.request();
  await page.waitForFunction(() => !document.querySelector('.voxel-version').textContent.includes('读取'));
  if (observedResponse.status() !== 200 || baselineWorld.version !== 12) throw new Error('The verification chain must be at v12');
  const started = Date.now();
  const checkpoints = [];
  for (let i = 1; i <= 600; i++) {
    // Electron CDP exposes this request with null postData. Supply the exact
    // visible world's read-only selector while reusing authenticated transport.
    const response = await page.context().request.fetch(observed, { timeout: 10000, data: { world_id: baselineWorld.world_id } });
    if (response.status() !== 200) throw new Error(`Read ${i} HTTP ${response.status()}`);
    const body = await response.json();
    if (body.version !== baselineWorld.version || body.world_id !== baselineWorld.world_id) throw new Error(`Read ${i} changed durable identity`);
    if (i % 100 === 0) checkpoints.push({ reads: i, elapsedMs: Date.now() - started, version: body.version });
    await response.dispose();
  }
  result.readStress = checkpoints;
  const pattern = '**/operations/worlds.chunks*';
  let release, entered;
  const waiting = new Promise(resolve => { entered = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  let held = 0;
  const handler = async route => {
    held++;
    const response = await route.fetch();
    entered();
    await gate;
    await route.fulfill({ response }).catch(() => {});
  };
  // Drop the mounted projection before the read; a reopened world must request
  // actual chunks, not merely take the same-version memoized projection.
  await page.getByRole('button', { name: '关闭 Interactive Voxel', exact: true }).click();
  await page.route(pattern, handler);
  try {
    await leaf.click();
    await Promise.race([waiting, page.waitForTimeout(10000).then(() => { throw new Error('Chunk hold was not reached'); })]);
    await page.getByRole('button', { name: 'Voxel Empty QA', exact: true }).click();
    release();
    await page.waitForTimeout(700);
    const abandoned = await page.locator('.voxel-studio').count();
    if (abandoned) throw new Error('Late chunks published a world into an empty Project');
    result.lateRead = { held, abandonedStudioCount: abandoned, destination: 'Voxel Empty QA' };
  } finally {
    release?.();
    await page.unroute(pattern, handler);
  }
  await page.getByRole('button', { name: 'Voxel Independent QA', exact: true }).click();
  await page.getByRole('treeitem', { name: 'Interactive Voxel', exact: true }).click();
  await page.locator('.voxel-viewport-status').filter({ hasText: '表面方块' }).waitFor();
  result.reopened = await page.locator('.voxel-header').innerText();
  return result;
}
