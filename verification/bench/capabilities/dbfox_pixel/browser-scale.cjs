async (page) => {
  const reads=[];const listener=async response=>{if(response.url().includes('/operations/frames.read'))reads.push({status:response.status(),time:Date.now()});};
  page.on('response',listener);
  await page.evaluate(()=>{window.__pixelQaLongTasks=[];window.__pixelQaObserver=new PerformanceObserver(list=>window.__pixelQaLongTasks.push(...list.getEntries().map(x=>x.duration)));window.__pixelQaObserver.observe({type:'longtask',buffered:false});});
  const started=Date.now();
  try {
    await page.getByRole('button',{name:'打开作品',exact:true}).nth(2).click();
    await page.getByRole('application',{name:'像素画布 16 × 16',exact:true}).waitFor();
    const firstCanvasMs=Date.now()-started;
    await page.getByRole('combobox',{name:'跳转帧页',exact:true}).selectOption('6');
    await page.getByRole('button',{name:'选择第 200 帧',exact:true}).waitFor();
    await page.waitForFunction(()=>!document.querySelector('[aria-label="选择第 200 帧"]')?.disabled);
    const allFramesMs=Date.now()-started;
    const lastPageButtons=await page.getByRole('group',{name:'选择帧',exact:true}).getByRole('button').count();
    await page.getByRole('button',{name:'选择第 200 帧',exact:true}).click();
    await page.getByRole('button',{name:'播放动画',exact:true}).click();
    const labels=new Set();for(let i=0;i<8;i++){labels.add(await page.locator('canvas[aria-label^="动画预览"]').getAttribute('aria-label'));await page.waitForTimeout(80);}
    await page.getByRole('button',{name:'暂停播放',exact:true}).click();
    if(labels.size<2 || lastPageButtons!==8)throw new Error('200 frame paging/playback failed');
    const measured=await page.evaluate(()=>({elements:document.querySelectorAll('.dbfox-pixel *').length,canvases:document.querySelectorAll('.dbfox-pixel canvas').length,longTasks:window.__pixelQaLongTasks,styles:document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length}));
    await page.screenshot({path:'output/playwright/pixel-two-hundred-frames.png'});
    return {firstCanvasMs,allFramesMs,frameReads:reads.length,statuses:[...new Set(reads.map(x=>x.status))],lastPageButtons,previewLabels:[...labels],...measured};
  } finally {page.off('response',listener);await page.evaluate(()=>{window.__pixelQaObserver.disconnect();delete window.__pixelQaObserver;delete window.__pixelQaLongTasks;});}
}
