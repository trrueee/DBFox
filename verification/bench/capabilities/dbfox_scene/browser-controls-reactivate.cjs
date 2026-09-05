async (page) => {
  let release, arrived;
  const held = new Promise(resolve => {release = resolve;}), entered = new Promise(resolve => {arrived = resolve;});
  const pattern = '**/api/v1/conversations/*';
  let sessionStatus;
  const exports = [];
  const onRequest = request => { if (request.url().includes('/operations/scenes.artifact') && request.method() === 'POST') exports.push(request.url()); };
  const handler = async route => {
    if (route.request().method() !== 'GET' || !/\/conversations\/[^/?]+$/.test(route.request().url())) return route.continue();
    const response = await route.fetch();
    sessionStatus = response.status();
    arrived();
    await held;
    try { await route.fulfill({response}); } catch { /* The original caller was canceled. */ }
  };
  const probe = () => page.evaluate(async () => {
    const {getRuntimeSession} = await import('/src/lib/api/client.ts');
    return {generation:getRuntimeSession().generation, ...sceneControlsProbe.read()};
  });
  await page.route(pattern, handler);
  page.on('request', onRequest);
  try {
    const initialHeader = await page.locator('.dbfox-scene__header').innerText();
    const initialVersion = initialHeader.match(/v\d+/)[0];
    await page.locator('.dbfox-scene canvas').focus();
    await page.keyboard.down('Control');
    const before = await probe();
    if (!before.listeners.some(item => item.name === 'document' && item.type === 'keyup' && item.active)) throw new Error('Control-held interceptor missing before lifecycle change');
    const pending = page.waitForResponse(response => response.url().includes('/operations/scenes.artifact') && response.request().method() === 'POST');
    await page.getByRole('button', {name:'导出工件', exact:true}).click();
    const artifact = await (await pending).json();
    await Promise.race([entered, page.waitForTimeout(10000).then(() => {throw new Error('No formal Session response was intercepted');})]);
    const exit = page.getByRole('button', {name:'退出工作区全屏', exact:true});
    if (await exit.count()) await exit.click();
    await page.getByRole('button', {name:'扩展', exact:true}).click();
    await page.keyboard.up('Control');
    await page.getByRole('button', {name:'停用', exact:true}).click();
    await page.getByRole('button', {name:'立即重启', exact:true}).first().click();
    await page.getByText('未激活', {exact:true}).waitFor();
    await page.waitForFunction(() => sceneControlsProbe.read().stylesheets === 0);
    const disabled = await probe();
    if (disabled.domCanvases || disabled.stylesheets || disabled.listeners.some(item => item.active) || disabled.canvases.some(item => item.connected || !item.lost) || disabled.timers.active || disabled.raf.active || disabled.observers.some(item => item.active)) throw new Error('Deactivated Scene retained native or scheduling resources');
    await page.getByRole('button', {name:'启用', exact:true}).click();
    await page.getByRole('button', {name:'立即重启', exact:true}).first().click();
    await page.getByText('当前已激活', {exact:true}).waitFor();
    await page.waitForFunction(() => sceneControlsProbe.read().stylesheets === 1);
    const active = await probe();
    release();
    await page.getByRole('button', {name:'返回工作区', exact:true}).click();
    await page.waitForTimeout(500);
    const lateTab = await page.evaluate(async id => {
      const module = await import('/src/stores/workspaceStore.ts');
      return module.selectActiveDockTabs(module.useWorkspaceStore.getState()).some(tab => tab.target?.id === id);
    }, artifact.artifact_id);
    if (lateTab || active.generation <= disabled.generation || disabled.generation <= before.generation || exports.length !== 1 || sessionStatus !== 200) throw new Error('Late old-activation navigation or ActionRun replay occurred');
    await page.getByRole('button', {name:'打开 Scene Studio', exact:true}).click();
    await page.getByRole('combobox', {name:'打开场景', exact:true}).selectOption({label:'Controls Regression'});
    await page.locator('.dbfox-scene canvas').waitFor();
    const header = await page.locator('.dbfox-scene__header').innerText();
    if (!header.includes(initialVersion)) throw new Error('Reactivation changed canonical Scene state');
    return {artifact, sessionStatus, before, disabled, active, lateTab, actionRunsRequested:exports.length, header};
  } finally { release(); await page.keyboard.up('Control'); await page.unroute(pattern, handler); page.off('request', onRequest); }
}
