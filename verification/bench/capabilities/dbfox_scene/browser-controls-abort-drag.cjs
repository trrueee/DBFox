async (page) => {
  const writes = [];
  const onRequest = request => { if (request.url().includes('/operations/scenes.apply') && request.method() === 'POST') writes.push(request.url()); };
  page.on('request', onRequest);
  try {
    const full = page.getByRole('button', {name:'工作区全屏', exact:true});
    if (await full.count()) await full.click();
    await page.getByRole('treeitem', {name:'Controls Cube', exact:true}).click();
    const initialHeader = await page.locator('.dbfox-scene__header').innerText();
    const initialVersion = initialHeader.match(/v\d+/)[0];
    await page.getByRole('button', {name:'聚焦 F', exact:true}).click();
    const box = await page.locator('.dbfox-scene canvas').boundingBox();
    const x = box.x + box.width / 2 + 72, y = box.y + box.height / 2 + 24;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 30, y + 10, {steps:8});
    const dragging = await page.getByRole('button', {name:'放弃草稿并刷新', exact:true}).count();
    if (!dragging) throw new Error('The real TransformControls gesture did not enter editing state');
    await page.getByRole('button', {name:'关闭 Scene Studio', exact:true}).focus();
    await page.keyboard.press('Space');
    await page.waitForFunction(() => sceneControlsProbe.read().domCanvases === 0 && sceneControlsProbe.read().canvases.every(item => item.lost));
    await page.mouse.up();
    await page.keyboard.up('Control');
    await page.waitForTimeout(5300);
    const closed = await page.evaluate(() => sceneControlsProbe.read());
    if (writes.length || closed.listeners.some(item => item.active) || closed.timers.active || closed.raf.active) throw new Error('The disposed in-progress gesture retained callbacks or committed after close');
    await page.getByRole('button', {name:'退出工作区全屏', exact:true}).click();
    await page.getByRole('button', {name:'打开 Scene Studio', exact:true}).click();
    await page.getByRole('combobox', {name:'打开场景', exact:true}).selectOption({label:'Controls Regression'});
    await page.getByRole('treeitem', {name:'Controls Cube', exact:true}).click();
    await page.getByRole('spinbutton', {name:'位置 X', exact:true}).waitFor();
    const heading = await page.locator('.dbfox-scene__header').innerText();
    if (!heading.includes(initialVersion)) throw new Error('Closing an unfinished gesture changed the durable version');
    return {dragging:!!dragging, lateWrites:writes.length, heading, closed};
  } finally { await page.mouse.up(); await page.keyboard.up('Control'); page.off('request', onRequest); }
}
