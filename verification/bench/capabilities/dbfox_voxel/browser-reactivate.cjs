async (page) => {
  const generationBefore=await page.evaluate(async()=>{const state=await window.dbfoxDesktop.engine.getStatus();return {generation:state.generation,state:state.state};});
  await page.getByRole('button',{name:'扩展',exact:true}).click();
  await page.getByRole('button',{name:'启用',exact:true}).click();
  await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
  await page.getByRole('button',{name:'停用',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('article')?.textContent.includes('当前已激活'));
  await page.getByRole('button',{name:'返回工作区',exact:true}).click();
  await page.getByRole('treeitem',{name:'Interactive Voxel',exact:true}).click();
  await page.getByRole('heading',{name:'Interactive Voxel',exact:true}).waitFor();
  const result={generationBefore,generationAfter:await page.evaluate(async()=>{const state=await window.dbfoxDesktop.engine.getStatus();return {generation:state.generation,state:state.state};}),
    header:await page.locator('.voxel-header').innerText(),styles:await page.locator('link[data-dbfox-dlc="dbfox.voxel"]').count(),canvases:await page.locator('canvas').count()};
  await page.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-reactivated.png'});
  return result;
}
