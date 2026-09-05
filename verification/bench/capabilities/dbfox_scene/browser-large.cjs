async (page) => {
  await page.evaluate(() => {
    window.sceneQaLongTasks = [];
    window.sceneQaObserver = new PerformanceObserver(items => window.sceneQaLongTasks.push(...items.getEntries().map(e => e.duration)));
    window.sceneQaObserver.observe({entryTypes:['longtask']});
  });
  let pages = 0;
  const onResponse = r => { if(r.url().includes('/operations/scenes.get')) pages += 1; };
  page.on('response', onResponse);
  const started = Date.now();
  await page.getByRole('combobox', {name:'打开场景',exact:true}).selectOption({label:'10000 Object Hierarchy'});
  await page.getByRole('treeitem', {name:'Large Root',exact:true}).waitFor({timeout:60000});
  const loadedMs = Date.now()-started;
  const collapsed = await page.evaluate(async () => {
    const intervals=[];
    await new Promise(resolve=> { let before=performance.now(); const frame=t=>{intervals.push(t-before);before=t;if(intervals.length<90) requestAnimationFrame(frame);else resolve();};requestAnimationFrame(frame);});
    const gl=document.querySelector('canvas').getContext('webgl2');
    const debug=gl.getExtension('WEBGL_debug_renderer_info');
    return {treeitems:document.querySelectorAll('[role="treeitem"]').length,
      visibleTreeitems:[...document.querySelectorAll('[role="treeitem"]')].filter(e=>e.getClientRects().length).length,
      elements:document.querySelectorAll('*').length,intervals,longTasks:window.sceneQaLongTasks,
      heap:performance.memory?.usedJSHeapSize,renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
      canvas:{width:gl.canvas.width,height:gl.canvas.height}};
  });
  await page.screenshot({path:'output/playwright/scene-10000-collapsed.png'});
  page.off('response',onResponse);
  await page.evaluate(()=>{window.sceneQaObserver.disconnect();delete window.sceneQaObserver;delete window.sceneQaLongTasks;});
  return {loadedMs,pages,collapsed};
}
