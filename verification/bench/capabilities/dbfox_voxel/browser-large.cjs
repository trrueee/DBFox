async (page) => {
  const results=[];
  for(const name of ['Cyberpunk Fox Shrine','128 Cubed Boundary World']) {
    await page.reload();
    await page.getByRole('treeitem',{name,exact:true}).waitFor();
    const pages=[];const pending=[];const listener=r=>{if(r.url().includes('/operations/worlds.chunks'))pending.push(r.json().then(data=>pages.push({version:data.version,chunks:data.chunks.length,next:!!data.next_after,bytes:JSON.stringify(data).length})));};
    page.on('response',listener);
    const start=Date.now();
    try {
      if(await page.getByRole('tab',{name,exact:true}).count())await page.getByRole('tab',{name,exact:true}).click();
      else await page.getByRole('treeitem',{name,exact:true}).click();
      await page.getByRole('heading',{name,exact:true}).waitFor();
      await page.getByRole('button',{name:'工作区全屏',exact:true}).click();
      await page.locator('.voxel-viewport-status').waitFor({state:'visible'}).catch(()=>{});
      await page.waitForFunction(()=>[...document.querySelectorAll('.voxel-viewport-status')].some(e=>/表面方块|预览已截断/.test(e.textContent)));
      const loadedMs=Date.now()-start;
      const viewport=page.getByLabel(/^体素三维视口/);
      await viewport.scrollIntoViewIfNeeded();
      await page.screenshot({path:`verification/bench/capabilities/dbfox_voxel/evidence/electron-${name.startsWith('128')?'128-world':'fox-shrine'}.png`});
      await Promise.all(pending);
      results.push({name,loadedMs,pages,heading:await page.locator('.voxel-header').innerText(),status:await page.locator('.voxel-viewport-status').innerText(),
        metrics:await page.evaluate(()=>({elements:document.querySelectorAll('*').length,canvases:document.querySelectorAll('canvas').length,
          heapBytes:performance.memory?.usedJSHeapSize,viewport:[innerWidth,innerHeight]}))});
      if(name.startsWith('128')) {
        await page.getByRole('checkbox',{name:'仅预览选区',exact:true}).check();
        await page.getByText('64 个表面方块',{exact:true}).waitFor();
        results.at(-1).croppedStatus=await page.locator('.voxel-viewport-status').innerText();
        await page.setViewportSize({width:560,height:1000});
        await page.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-narrow.png'});
        results.at(-1).narrow=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,studioWidth:document.querySelector('.voxel-studio').getBoundingClientRect().width,
          gridColumns:getComputedStyle(document.querySelector('.voxel-editor')).gridTemplateColumns}));
        await page.setViewportSize({width:1440,height:902});
      }
    }finally {page.off('response',listener);}
  }
  return results;
}
