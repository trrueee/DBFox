async (page) => {
  const evidencePath = 'verification/bench/capabilities/dbfox_scene/evidence/controls-close.json';
  const cdp = await page.context().newCDPSession(page);
  const requests = [];
  const onRequest = request => { if (request.url().includes('/operations/scenes.')) requests.push({name: request.url().split('/operations/')[1], method: request.method()}); };
  page.on('request', onRequest);
  const nativeRead = async () => {
    const reply = await cdp.send('Runtime.evaluate', {
      expression: `JSON.stringify(sceneControlsProbe.listeners.map(item => ({id:item.id, type:item.type, name:item.name, nativePresent:(getEventListeners(item.target)[item.type] || []).some(event => event.listener === item.callback && event.useCapture === item.capture)})))`,
      includeCommandLineAPI: true, returnByValue: true,
    });
    if (reply.exceptionDetails) throw new Error('Native listener inspection failed');
    return JSON.parse(reply.result.value);
  };
  const open = async () => {
    const exitFull = page.getByRole('button', {name:'退出工作区全屏', exact:true});
    if (await exitFull.count()) await exitFull.click();
    await page.getByRole('button', {name:'打开 Scene Studio', exact:true}).click();
    const full = page.getByRole('button', {name:'工作区全屏', exact:true});
    if (await full.count()) await full.click();
    await page.getByRole('combobox', {name:'打开场景', exact:true}).selectOption({label:'Controls Regression'});
    await page.getByRole('treeitem', {name:'Controls Cube', exact:true}).waitFor();
    await page.locator('.dbfox-scene canvas').waitFor();
    await page.waitForFunction(() => sceneControlsProbe.read().canvases.some(item => item.connected && !item.lost));
  };
  const results = [];
  try {
    for (const controlHeld of [false, true, false, true]) {
      await open();
      await page.locator('.dbfox-scene canvas').focus();
      if (controlHeld) await page.keyboard.down('Control');
      const before = await page.evaluate(() => sceneControlsProbe.read());
      const nativeBefore = await nativeRead();
      if (!before.timers.delays.includes(5000) || !['ResizeObserver','IntersectionObserver'].every(name => before.observers.some(item => item.name === name && item.active))) throw new Error('The probe did not observe active owner polling and visibility resources');
      const keyboards = before.listeners.filter(item => item.active && item.name === 'document' && item.capture && ['keydown','keyup'].includes(item.type));
      if (!keyboards.some(item => item.type === 'keydown') || (controlHeld && !keyboards.some(item => item.type === 'keyup'))) throw new Error('Control interceptors were not actually registered');
      if (!keyboards.every(item => nativeBefore.some(native => native.id === item.id && native.nativePresent))) throw new Error('Probe does not match native listeners before close');
      await page.getByRole('button', {name:'关闭 Scene Studio', exact:true}).click();
      await page.waitForFunction(() => sceneControlsProbe.read().domCanvases === 0 && sceneControlsProbe.read().canvases.every(item => item.lost));
      const closed = await page.evaluate(() => sceneControlsProbe.read());
      const nativeClosed = await nativeRead();
      const startRequests = requests.length;
      await page.waitForTimeout(5300); // longer than the owner's 5s polling period
      const settled = await page.evaluate(() => sceneControlsProbe.read());
      const lateRequests = requests.slice(startRequests);
      const result = {controlHeld, before, nativeBefore, closed, nativeClosed, settled, lateRequests};
      results.push(result);
      await page.evaluate(value => { globalThis.sceneControlsResults = value; }, {cases:results});
      if (closed.listeners.some(item => item.active) || nativeClosed.some(item => item.nativePresent)) throw new Error('Native owner listener survived actual tab close');
      if (!keyboards.every(item => closed.listeners.find(entry => entry.id === item.id)?.removedWithCanvasAttached)) throw new Error('Controls detached after canvas removal');
      if (closed.raf.active || closed.timers.active || closed.observers.some(item => item.active) || closed.domCanvases || closed.canvases.some(item => item.connected || !item.lost)) throw new Error('Owner graphics or scheduling resource survived close');
      if (lateRequests.length || closed.raf.ran !== settled.raf.ran || JSON.stringify(closed.observers) !== JSON.stringify(settled.observers)) throw new Error('Owner activity arrived after close');
      if (controlHeld) await page.keyboard.up('Control');
    }
    await open();
    return {cases:results, passed:results.length, currentCanvas:await page.locator('.dbfox-scene canvas').count(), evidencePath};
  } finally {
    await page.keyboard.up('Control');
    page.off('request', onRequest);
    await cdp.detach();
  }
}
