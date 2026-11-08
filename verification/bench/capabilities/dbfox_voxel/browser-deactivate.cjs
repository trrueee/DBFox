async (page) => {
  await page.getByRole('button',{name:'返回工作区',exact:true}).click();
  const canvas=await page.getByLabel(/^体素三维视口/).elementHandle();
  const before=await canvas.evaluate(e=>({connected:e.isConnected,lost:e.getContext('webgl2').isContextLost()}));
  await page.getByRole('button',{name:'扩展',exact:true}).click();
  const unmounted=await canvas.evaluate(e=>({connected:e.isConnected,lost:e.getContext('webgl2').isContextLost()}));
  await canvas.dispose();
  await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
  await page.waitForFunction(()=>document.querySelector('article')?.textContent.includes('当前未激活')||document.querySelector('article')?.textContent.includes('未激活'));
  const disabled={card:await page.locator('article').innerText(),styles:await page.locator('link[data-dbfox-dlc="dbfox.voxel"]').count(),canvases:await page.locator('canvas').count()};
  await page.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-disabled.png'});
  await page.getByRole('button',{name:'返回工作区',exact:true}).click();
  const noOwner={tree:await page.getByRole('tree',{name:'体素世界',exact:true}).count(),canvas:await page.locator('canvas').count(),styles:await page.locator('link[data-dbfox-dlc="dbfox.voxel"]').count()};
  return {before,unmounted,disabled,noOwner};
}
