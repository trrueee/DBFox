async (page) => {
  const cdp = await page.context().newCDPSession(page);
  try {
    await page.getByRole('button', {name:'关闭 Scene Studio', exact:true}).click();
    await page.waitForFunction(() => sceneControlsProbe.read().domCanvases === 0 && sceneControlsProbe.read().canvases.every(item => item.lost));
    const reply = await cdp.send('Runtime.evaluate', {
      expression:`JSON.stringify(sceneControlsProbe.listeners.filter(item => (getEventListeners(item.target)[item.type] || []).some(event => event.listener === item.callback && event.useCapture === item.capture)).map(item => ({type:item.type, name:item.name})))`,
      includeCommandLineAPI:true, returnByValue:true,
    });
    const nativeRemaining = JSON.parse(reply.result.value);
    const closed = await page.evaluate(() => sceneControlsProbe.read());
    if (nativeRemaining.length || closed.listeners.some(item => item.active) || closed.timers.active || closed.raf.active || closed.observers.some(item => item.active)) throw new Error('Final native cleanup failed');
    const restored = await page.evaluate(() => { sceneControlsProbe.restore(); delete globalThis.sceneControlsResults; return !globalThis.sceneControlsProbe; });
    return {closed, nativeRemaining, restored};
  } finally { await cdp.detach(); }
}
