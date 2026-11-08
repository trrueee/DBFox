async (page) => {
  if (await page.getByRole('button', { name: '退出工作区全屏', exact: true }).count()) await page.getByRole('button', { name: '退出工作区全屏', exact: true }).click();
  const state = () => page.evaluate(async () => { const value = await window.dbfoxDesktop.engine.getStatus(); return { generation: value.generation, state: value.state }; });
  const before = await state();
  const viewport = page.getByLabel(/^体素三维视口/);
  const canvas = await viewport.elementHandle();
  const cdp = await page.context().newCDPSession(page);
  const group = 'voxel-adversarial-history-deactivate';
  try {
    const objectId = (await cdp.send('Runtime.evaluate', { expression: 'document.querySelector("canvas[aria-label^=体素三维视口]")', objectGroup: group })).result.objectId;
    const native = async () => (await cdp.send('DOMDebugger.getEventListeners', { objectId })).listeners.map(listener => listener.type);
    await viewport.focus();
    await page.keyboard.down('Control');
    const listenersBefore = await native();
    await page.getByRole('button', { name: '扩展', exact: true }).click();
    const afterUnmount = { connected: await canvas.evaluate(node => node.isConnected), lost: await canvas.evaluate(node => node.getContext('webgl2').isContextLost()), listeners: await native() };
    await page.keyboard.up('Control');
    if (afterUnmount.connected || !afterUnmount.lost || afterUnmount.listeners.length) throw new Error(JSON.stringify(afterUnmount));
    await page.getByRole('button', { name: '停用', exact: true }).click();
    await page.getByRole('button', { name: '立即重启', exact: true }).first().click();
    await page.waitForFunction(() => document.querySelector('article')?.textContent.includes('未激活'));
    const disabled = { engine: await state(), styles: await page.locator('link[data-dbfox-dlc="dbfox.voxel"]').count(), canvases: await page.locator('canvas').count() };
    await page.getByRole('button', { name: '返回工作区', exact: true }).click();
    disabled.resources = await page.getByRole('tree', { name: '体素世界', exact: true }).count();
    if (disabled.styles || disabled.canvases || disabled.resources || disabled.engine.generation <= before.generation) throw new Error(JSON.stringify(disabled));
    await page.getByRole('button', { name: '扩展', exact: true }).click();
    await page.getByRole('button', { name: '启用', exact: true }).click();
    await page.getByRole('button', { name: '立即重启', exact: true }).first().click();
    await page.getByRole('button', { name: '停用', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('article')?.textContent.includes('当前已激活'));
    await page.getByRole('button', { name: '返回工作区', exact: true }).click();
    await page.getByRole('treeitem', { name: 'Interactive Voxel', exact: true }).click();
    await page.locator('.voxel-viewport-status').filter({ hasText: '表面方块' }).waitFor();
    const enabled = { engine: await state(), styles: await page.locator('link[data-dbfox-dlc="dbfox.voxel"]').count(), header: await page.locator('.voxel-header').innerText() };
    if (enabled.engine.generation <= disabled.engine.generation || enabled.styles !== 1 || !enabled.header.includes('v12')) throw new Error(JSON.stringify(enabled));
    return { before, listenersBefore, afterUnmount, disabled, enabled, boundary: 'real historical GPU teardown with Control held, formal disable/restart/enable/restart; durable world preserved' };
  } finally {
    await page.keyboard.up('Control');
    await cdp.send('Runtime.releaseObjectGroup', { objectGroup: group });
    await cdp.detach();
    await canvas.dispose();
  }
}
